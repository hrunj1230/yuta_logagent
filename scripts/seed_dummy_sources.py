"""
더미 소스 생성 스크립트 (git_log / agent_chatlog)

일지 생성과 평가를 시험하려면 하루에 문서·커밋·대화가 함께 있어야 하는데,
실제 데이터에는 문서만 있는 날이 대부분이다. 이 스크립트는 각 날짜의 실제 TIL
내용을 근거로 그날 있었을 법한 커밋 이력과 AI 대화를 생성해 채워 넣는다.

⚠️ 생성된 데이터에는 모두 synthetic=True 메타데이터가 붙는다.
   이 시스템은 "실제로 무엇을 했는가"의 기록이므로, 지어낸 내용이 진짜와
   구분되지 않으면 일지가 사실이 아닌 것을 사실처럼 보고하게 된다.
   표식이 있으면 검색에서 걸러내거나 나중에 일괄 삭제할 수 있다.

사용법:
    uv run python -m scripts.seed_dummy_sources alex
    uv run python -m scripts.seed_dummy_sources alex --dry-run   # 생성만 하고 저장 안 함
    uv run python -m scripts.seed_dummy_sources alex --purge     # 기존 더미 삭제 후 재생성
"""
import json
import sys
from collections import defaultdict
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from langchain_core.documents import Document

from src.llm_router import SEED_MODEL
from src.storage.database import SessionLocal
from src.storage.models import EmbeddingStatus, Source, SourceType
from src.tools.embedding import _get_chroma_collection, _save_to_chromadb

load_dotenv()

# 한 번의 요청으로 처리할 날짜 수. 여러 날을 함께 주면 저장소가 시간에 따라
# 이어지는 흐름(같은 파일이 반복 수정되는 등)이 자연스러워진다.
DATES_PER_BATCH = 8

# 근거로 넘길 그날 TIL 본문의 최대 길이
TOPIC_CHARS = 1200

DUMMY_SOURCES = {
    SourceType.GIT_LOG: "학습 저장소 커밋이력 (더미)",
    SourceType.AGENT_CHATLOG: "AI 대화 기록 (더미)",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "commits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "files": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "path": {"type": "string"},
                                            "added": {"type": "integer"},
                                            "deleted": {"type": "integer"},
                                        },
                                        "required": ["path", "added", "deleted"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["message", "files"],
                            "additionalProperties": False,
                        },
                    },
                    "chat": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "turns": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "role": {"type": "string", "enum": ["user", "assistant"]},
                                        "text": {"type": "string"},
                                    },
                                    "required": ["role", "text"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["title", "turns"],
                        "additionalProperties": False,
                    },
                },
                "required": ["date", "commits", "chat"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["days"],
    "additionalProperties": False,
}

SYSTEM = """당신은 학습 기록 시스템의 테스트 데이터를 만든다.

주어진 날짜별 TIL 문서 내용을 근거로, 그 사람이 그날 실제로 했을 법한
git 커밋 이력과 AI 어시스턴트 대화를 생성한다.

규칙:
- 반드시 그날 TIL에 실제로 등장한 주제·용어만 사용한다. 새로운 주제를 지어내지 않는다.
- 커밋 메시지는 한국어로 쓰되 conventional commit 형식(docs:, feat:, fix:, refactor:)을 따른다.
- 커밋은 하루 1~3개. 문서 정리 위주의 날은 1개, 실습·구현이 있는 날은 2~3개.
- 파일 경로는 날짜 문서(YYYY-MM-DD.md)와 주제별 파일을 섞어 쓰고, 여러 날에 걸쳐
  같은 파일이 이어서 수정되도록 한다.
- 대화는 그날 배운 것 중 헷갈렸을 만한 지점을 묻고 답하는 형태로 2~3턴.
  사용자 발화는 짧고 구어체로, 답변은 그날 TIL 내용에 근거해 간결하게.
- 실제로 배우지 않은 내용을 답변에 넣지 않는다."""


def _load_til_by_date(user_id: str) -> dict[str, str]:
    """사용자의 TIL 문서를 날짜별로 모아 근거 텍스트를 만든다."""
    collection = _get_chroma_collection(user_id)
    found = collection.get(include=["documents", "metadatas"])

    by_date: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for text, meta in zip(found.get("documents") or [], found.get("metadatas") or []):
        if not meta or meta.get("source_type") != "git":
            continue  # 문서 소스만 근거로 삼는다 (더미끼리 참조하지 않도록)
        date = meta.get("date")
        if date:
            by_date[date].append((meta.get("chunk_index") or 0, text or ""))

    return {
        date: "\n".join(t for _, t in sorted(chunks))[:TOPIC_CHARS]
        for date, chunks in sorted(by_date.items())
    }


def _generate_batch(client, batch: list[tuple[str, str]]) -> list[dict]:
    """날짜 묶음 하나에 대해 커밋·대화를 생성한다."""
    prompt = "다음 날짜별 TIL 내용을 근거로 각 날짜의 커밋과 대화를 만들어라.\n\n"
    for date, text in batch:
        prompt += f"### {date}\n{text}\n\n"

    response = client.messages.create(
        model=SEED_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"요청이 거부되었습니다: {response.stop_details}")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["days"]


def _commit_document(day: dict, commit: dict, index: int, user_id: str, source_id: int) -> Document:
    """커밋 하나를 실제 git_log 수집 결과와 같은 형식의 Document로 만든다."""
    files = commit.get("files") or []
    added = sum(f.get("added", 0) for f in files)
    deleted = sum(f.get("deleted", 0) for f in files)

    lines = [
        f"[{day['date']}] {commit['message']}",
        f"작성자: {user_id}",
        f"변경: {len(files)}개 파일 (+{added} / -{deleted})",
    ]
    lines += [f"- {f['path']} (+{f.get('added', 0)}/-{f.get('deleted', 0)})" for f in files]

    return Document(
        page_content="\n".join(lines),
        metadata={
            "user_id": user_id,
            "source_id": source_id,
            "source_type": "git_log",
            "source_name": DUMMY_SOURCES[SourceType.GIT_LOG],
            # 실제 커밋 SHA가 아니므로 합성임이 드러나는 형태로 만든다
            "commit_sha": f"synthetic-{day['date']}-{index}",
            "author": user_id,
            "date": day["date"],
            "date_origin": "synthetic",
            "message": commit["message"],
            "files_changed": len(files),
            "lines_added": added,
            "lines_deleted": deleted,
            "synthetic": True,
            "embedded_at": datetime.now().isoformat(),
        },
    )


def _chat_document(day: dict, user_id: str, source_id: int) -> Document | None:
    """대화 세션 하나를 Document로 만든다."""
    chat = day.get("chat") or {}
    turns = chat.get("turns") or []
    if not turns:
        return None

    speaker = {"user": "나", "assistant": "AI"}
    lines = [f"[{day['date']}] AI 대화: {chat.get('title', '(제목 없음)')}", ""]
    lines += [f"{speaker.get(t['role'], t['role'])}: {t['text']}" for t in turns]

    return Document(
        page_content="\n".join(lines),
        metadata={
            "user_id": user_id,
            "source_id": source_id,
            "source_type": "agent_chatlog",
            "source_name": DUMMY_SOURCES[SourceType.AGENT_CHATLOG],
            "session_id": f"synthetic-{day['date']}",
            "title": chat.get("title", ""),
            "turn_count": len(turns),
            "date": day["date"],
            "date_origin": "synthetic",
            "synthetic": True,
            "embedded_at": datetime.now().isoformat(),
        },
    )


def _ensure_sources(user_id: str) -> dict[SourceType, int]:
    """더미 소스를 DB에 등록하고 source_id를 돌려준다."""
    db = SessionLocal()
    ids = {}
    try:
        for source_type, name in DUMMY_SOURCES.items():
            location = f"synthetic://{user_id}/{source_type.value}"
            source = db.query(Source).filter_by(user_id=user_id, location=location).first()
            if not source:
                source = Source(
                    user_id=user_id,
                    name=name,
                    type=source_type,
                    location=location,
                    embedding_status=EmbeddingStatus.COMPLETED,
                    last_synced_at=datetime.now(),
                )
                db.add(source)
                db.commit()
                db.refresh(source)
            ids[source_type] = source.id
        return ids
    finally:
        db.close()


def purge(user_id: str) -> int:
    """이 스크립트가 만든 청크를 전부 삭제한다."""
    collection = _get_chroma_collection(user_id)
    found = collection.get(where={"synthetic": True})
    ids = found.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def main(user_id: str, dry_run: bool = False, do_purge: bool = False) -> int:
    if do_purge:
        print(f"🗑️  기존 더미 청크 {purge(user_id)}개 삭제\n")

    til = _load_til_by_date(user_id)
    if not til:
        print(f"❌ {user_id}의 TIL 문서를 찾지 못했습니다. 먼저 소스를 임베딩하세요.")
        return 1

    dates = sorted(til)
    print(f"📚 근거 문서: {len(dates)}일 ({dates[0]} ~ {dates[-1]})")

    source_ids = _ensure_sources(user_id) if not dry_run else {t: 0 for t in DUMMY_SOURCES}
    client = anthropic.Anthropic()

    all_days: list[dict] = []
    batches = [dates[i:i + DATES_PER_BATCH] for i in range(0, len(dates), DATES_PER_BATCH)]

    for n, batch_dates in enumerate(batches, 1):
        batch = [(d, til[d]) for d in batch_dates]
        print(f"⏳ [{n}/{len(batches)}] {batch_dates[0]} ~ {batch_dates[-1]} 생성 중...")
        try:
            all_days.extend(_generate_batch(client, batch))
        except Exception as e:
            print(f"   ⚠️ 실패, 건너뜁니다: {e}")

    # 근거 없는 날짜가 섞이지 않도록 실제 TIL이 있는 날짜만 남긴다
    valid = [d for d in all_days if d.get("date") in til]
    dropped = len(all_days) - len(valid)

    commits = [
        _commit_document(day, c, i, user_id, source_ids[SourceType.GIT_LOG])
        for day in valid
        for i, c in enumerate(day.get("commits") or [])
    ]
    chats = [
        doc for day in valid
        if (doc := _chat_document(day, user_id, source_ids[SourceType.AGENT_CHATLOG]))
    ]

    print(f"\n생성 결과: 커밋 {len(commits)}개 · 대화 {len(chats)}개 · 대상 {len(valid)}일")
    if dropped:
        print(f"  (근거 날짜와 맞지 않아 버린 항목: {dropped}개)")

    if dry_run:
        print("\n--- dry-run 미리보기 ---")
        for doc in (commits[:2] + chats[:1]):
            print(doc.page_content)
            print()
        return 0

    print("\n⏳ 임베딩 중...")
    _save_to_chromadb(commits + chats, user_id)
    print(f"✅ 완료: {len(commits) + len(chats)}개 청크 저장 (모두 synthetic=True)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(
        sys.argv[1],
        dry_run="--dry-run" in sys.argv,
        do_purge="--purge" in sys.argv,
    ))
