"""
일지 관리 도구 모듈

이 모듈은 날짜 기반으로 임베딩 데이터를 조회하고 일지를 생성/저장하는 도구를 제공합니다.

제공 도구:
    - retriever_vectordb: 날짜(또는 날짜 범위) 기반 VectorDB 검색
    - maker_logfile: 일지 파일 저장 및 재임베딩

설계 노트:
    검색은 날짜 메타데이터 필터만 사용합니다. 날짜 문자열을 임베딩해 유사도로
    찾는 방식은 날짜와 아무 상관관계가 없으므로 폴백으로도 쓰지 않습니다.
    해당 날짜에 기록이 없으면 그 사실을 그대로 알립니다.
"""
import os
from datetime import date as date_cls, datetime, timedelta

from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_chroma import Chroma

from .. import llm_router
from .ingest_rules import normalize_date, parse_user_date

# 한 번의 조회로 확장할 수 있는 최대 날짜 수 (ChromaDB $in 필터 크기 제한)
MAX_DATE_SPAN = 92

# 한 번의 조회 결과로 내보낼 최대 분량 (자).
# 하루치는 대개 수천 자라 여유롭고, 이 예산이 실제로 걸리는 곳은 기간 조회다.
MAX_RESULT_CHARS = 40_000

# 예산을 넘겼을 때 커밋당 남길 파일 수. 앞에서부터 차례로 시도한다.
# 커밋 문서의 부피는 대부분 파일 변경 목록이 차지하는데, 일지에 필요한 것은
# '무엇을 했는가'(메시지)와 '얼마나 바꿨는가'(요약 줄)이지 파일별 증감이 아니다.
SHRINK_STEPS = (3, 0)

LOGS_DIR = "logs"
JOURNAL_SOURCE_NAME = "일지"


def _open_collection(user_id: str) -> Chroma:
    """사용자별 ChromaDB 컬렉션 열기"""
    return Chroma(
        collection_name=f"user_{user_id}",
        embedding_function=llm_router.embedding_function,
        client=llm_router.chroma_client,
    )


def _date_range(start: str, end: str) -> list[str]:
    """start~end 사이의 날짜 문자열 목록을 생성한다 (양끝 포함)."""
    begin = date_cls.fromisoformat(start)
    finish = date_cls.fromisoformat(end)
    if finish < begin:
        begin, finish = finish, begin

    span = (finish - begin).days + 1
    if span > MAX_DATE_SPAN:
        finish = begin + timedelta(days=MAX_DATE_SPAN - 1)
        span = MAX_DATE_SPAN

    return [(begin + timedelta(days=i)).isoformat() for i in range(span)]


def _known_dates(store: Chroma, limit: int = 10) -> list[str]:
    """벡터DB에 실제로 존재하는 날짜 목록 (최신순)."""
    try:
        found = store.get(include=["metadatas"])
    except Exception as e:
        print(f"[retriever] 날짜 목록 조회 실패: {e}")
        return []

    dates = {
        meta.get("date")
        for meta in (found.get("metadatas") or [])
        if meta and meta.get("date")
    }
    return sorted(dates, reverse=True)[:limit]


def _shrink_commit(text: str, keep_files: int) -> str:
    """커밋 문서에서 파일별 변경 목록을 keep_files 개만 남긴다."""
    lines = text.split("\n")
    head = [line for line in lines if not line.startswith("- ")]
    # 수집 단계에서 이미 붙은 '... 외 N개 파일' 표시는 여기서 다시 계산한다
    files = [line for line in lines if line.startswith("- ") and not line.startswith("- ...")]

    if len(files) <= keep_files:
        return text

    trimmed = files[:keep_files]
    if keep_files:
        trimmed.append(f"- ... 외 {len(files) - keep_files}개")
    return "\n".join(head + trimmed)


def _render_doc(index: int, doc: Document, keep_files: int | None) -> str:
    """문서 하나를 결과 블록으로 만든다."""
    meta = doc.metadata
    content = doc.page_content
    if keep_files is not None and meta.get("source_type") == "git_log":
        content = _shrink_commit(content, keep_files)

    lines = [
        f"--- 문서 {index} ---",
        f"날짜: {meta.get('date', '날짜 정보 없음')}",
        f"출처: {meta.get('source_name', 'unknown')}",
        f"타입: {meta.get('source_type', 'document')}",
    ]
    if meta.get("file_path"):
        lines.append(f"경로: {meta['file_path']}")
    lines.append(f"내용:\n{content}\n\n")
    return "\n".join(lines)


def _render(docs: list[Document]) -> tuple[str, str]:
    """
    문서 목록을 분량 예산 안에 들어가는 본문으로 만든다.

    개수로 자르지 않는다. 날짜 필터는 정확일치라 문서 사이에 우열이 없어서,
    개수로 자르면 '중요한 N건'이 아니라 '먼저 저장된 N건'이 남는다. 그러면
    나중에 임베딩한 소스가 통째로 밀려난다 (커밋 42건 중 3건만 남는 식).

    대신 분량이 넘칠 때 커밋의 파일 변경 목록부터 덜어낸다. 커밋을 통째로
    버리는 것보다 손실이 적기 때문이다.

    Returns:
        (본문, 안내문). 덜어낸 것이 없으면 안내문은 빈 문자열.
    """
    for keep in (None, *SHRINK_STEPS):
        body = "".join(_render_doc(i, doc, keep) for i, doc in enumerate(docs, 1))
        if len(body) <= MAX_RESULT_CHARS:
            if keep is None:
                return body, ""
            what = "생략했습니다" if keep == 0 else f"{keep}개로 줄였습니다"
            return body, f"\n(분량이 커서 커밋의 파일 변경 목록을 {what}.)"

    # 파일 목록을 모두 걷어내도 넘치면 문서 수를 줄인다.
    # docs 는 날짜순이므로 앞에서부터 채우면 '앞 기간은 온전하고 뒤가 잘린다'가 되어
    # 무엇이 빠졌는지 말할 수 있다. 저장 순서대로 자르면 나중에 임베딩한 소스가
    # 통째로 빠지면서, 빠진 것이 무엇인지조차 알 수 없다.
    kept: list[str] = []
    size = 0
    for i, doc in enumerate(docs, 1):
        block = _render_doc(i, doc, keep_files=0)
        if size + len(block) > MAX_RESULT_CHARS:
            break
        kept.append(block)
        size += len(block)

    omitted = len(docs) - len(kept)
    covered = docs[len(kept) - 1].metadata.get("date") if kept else None
    span = f" {docs[0].metadata.get('date')} ~ {covered} 까지만 담겼습니다." if covered else ""
    return "".join(kept), (
        f"\n⚠️ 분량이 커서 커밋의 파일 목록을 생략하고 {omitted}개 문서를 제외했습니다"
        f" (전체 {len(docs)}개 중 {len(kept)}개 표시).{span} 기간을 좁혀 다시 조회하세요."
    )


@tool
def retriever_vectordb(date: str, user_id: str, end_date: str = "") -> str:
    """
    지정한 날짜(또는 날짜 범위)에 기록된 문서를 벡터DB에서 조회합니다.

    해당 날짜의 문서를 모두 가져옵니다. 개수를 지정할 필요가 없습니다.

    2026년 07월 09일, 2026_12_03, 2026.01.13 같은 다양한 날짜 표기를 처리합니다.
    연도가 없으면 올해 연도로 간주하세요.
    "이번 주", "지난 3일" 처럼 기간을 묻는 요청은 date에 시작일, end_date에 종료일을 넣으세요.

    Args:
        date: 조회할 날짜 (기간 조회 시 시작일)
        user_id: 사용자 ID
        end_date: 기간 조회 시 종료일. 단일 날짜 조회면 비워 두세요

    Returns:
        검색된 문서 목록과 내용
    """
    start = parse_user_date(date)
    if not start:
        return f"❌ '{date}'를 날짜로 해석하지 못했습니다. YYYY-MM-DD 형식으로 알려주세요."

    finish = parse_user_date(end_date) if end_date else None
    targets = _date_range(start, finish) if finish else [start]

    store = _open_collection(user_id)

    # 날짜 메타데이터 필터로만 조회한다.
    # 문자열 비교 연산자는 ChromaDB에서 신뢰할 수 없으므로 $in 으로 명시한다.
    where = {"date": targets[0]} if len(targets) == 1 else {"date": {"$in": targets}}

    try:
        # 개수 제한을 두지 않는다 — 분량 조절은 _render 가 담당한다
        found = store.get(where=where, include=["documents", "metadatas"])
    except Exception as e:
        return f"❌ 검색 중 오류가 발생했습니다: {e}"

    contents = found.get("documents") or []
    metadatas = found.get("metadatas") or []

    if not contents:
        period = f"{start} ~ {finish}" if finish else start
        message = f"📭 '{period}'에 기록된 문서가 없습니다."

        available = _known_dates(store)
        if available:
            message += "\n\n기록이 있는 최근 날짜: " + ", ".join(available)
        else:
            message += "\n\n아직 임베딩된 문서가 없습니다. 소스를 등록하고 embed_source를 실행하세요."
        return message

    # 저장 순서는 임베딩한 순서일 뿐 의미가 없다. 날짜순으로 세워야 LLM 이 흐름을
    # 읽을 수 있고, 분량이 넘쳐 뒤를 자를 때도 어디까지 담겼는지 말할 수 있다.
    docs = sorted(
        (
            Document(page_content=content, metadata=meta or {})
            for content, meta in zip(contents, metadatas)
        ),
        key=lambda d: (
            d.metadata.get("date") or "",
            d.metadata.get("source_type") or "",
            d.metadata.get("file_path") or "",
        ),
    )

    period = f"{start} ~ {finish}" if finish else start
    body, note = _render(docs)

    return f"'{period}' 검색 결과 ({len(docs)}개 문서):{note}\n\n{body}"


@tool
def maker_logfile(date: str, content: str, user_id: str) -> str:
    """
    생성된 일지를 마크다운 파일로 저장하고, 이후 검색되도록 벡터DB에 등록합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식, 예: 2026-07-09)
        content: 일지 내용 (마크다운 형식)
        user_id: 사용자 ID

    Returns:
        저장 결과 메시지
    """
    normalized = parse_user_date(date)
    if not normalized:
        return f"❌ '{date}'를 날짜로 해석하지 못했습니다. YYYY-MM-DD 형식으로 알려주세요."

    os.makedirs(LOGS_DIR, exist_ok=True)
    filename = f"{LOGS_DIR}/{normalized.replace('-', '.')}_log.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    embed_note = _embed_journal(normalized, content, user_id, filename)
    return f"✅ 일지 저장 완료: {filename}\n{embed_note}"


def _embed_journal(date: str, content: str, user_id: str, filename: str) -> str:
    """
    일지를 벡터DB에 등록한다 (같은 날짜의 기존 일지는 교체).

    일지는 원문 위에 놓이는 요약 계층이며, 여러 날에 걸친 질문에 답할 때의
    주 진입점이 된다. 저장만 하고 임베딩하지 않으면 이 계층이 끊긴다.
    """
    try:
        store = _open_collection(user_id)

        # 같은 날짜의 이전 일지를 제거해 중복 누적을 막는다
        existing = store.get(where={"$and": [
            {"source_type": "journal"},
            {"date": date},
        ]})
        stale_ids = existing.get("ids", [])
        if stale_ids:
            store.delete(ids=stale_ids)

        store.add_documents([Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": 0,
                "source_type": "journal",
                "source_name": JOURNAL_SOURCE_NAME,
                "file_path": filename,
                "date": date,
                "date_origin": "journal",
                "embedded_at": datetime.now().isoformat(),
            },
        )])

        replaced = f" (이전 일지 {len(stale_ids)}개 교체)" if stale_ids else ""
        return f"🔎 일지를 검색 대상에 등록했습니다{replaced}."

    except Exception as e:
        # 파일 저장은 이미 성공했으므로 임베딩 실패로 전체를 실패 처리하지 않는다
        print(f"[maker_logfile] 일지 임베딩 실패: {e}")
        return f"⚠️ 파일은 저장했으나 검색 등록에 실패했습니다: {e}"
