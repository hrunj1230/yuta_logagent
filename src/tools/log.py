"""
일지 관리 도구 모듈

이 모듈은 날짜 기반으로 임베딩 데이터를 조회하고 일지를 생성/저장하는 도구를 제공합니다.

제공 도구:
    - retriever_vectordb: 날짜(또는 날짜 범위) 기반 VectorDB 검색
    - maker_logfile: 일지 파일 저장 및 재임베딩
    - generate_daily_journals: 기간 안의 날짜마다 일지를 하나씩 생성

설계 노트:
    검색은 날짜 메타데이터 필터만 사용합니다. 날짜 문자열을 임베딩해 유사도로
    찾는 방식은 날짜와 아무 상관관계가 없으므로 폴백으로도 쓰지 않습니다.
    해당 날짜에 기록이 없으면 그 사실을 그대로 알립니다.

    기간 요청은 날짜별로 쪼개 처리합니다. 일주일치를 한 번에 조회하면 49,728자로
    분량 예산을 넘겨 문서가 통째로 빠지는데, 하루씩 처리하면 가장 큰 날도
    24,113자라 예산에 닿지 않습니다. 유실이 구조적으로 불가능해집니다.
"""
import io
import json
import os
import re
import threading
import zipfile
from datetime import date as date_cls, datetime, timedelta

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_chroma import Chroma
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

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

    어떤 소스를 보고 썼는지도 함께 기록한다. 나중에 날짜로 다시 세면 그 사이
    추가된 소스까지 '포함됐다'고 잘못 표시되기 때문이다 — 일지는 쓰던 시점의
    자료로 만들어진 것이지 지금 자료로 만들어진 것이 아니다.
    """
    try:
        store = _open_collection(user_id)
        contributors = _contributing_sources(store, date)

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
                # 쓰던 시점에 어떤 소스를 봤는지. 화면에서 '이 일지의 재료'로 보여준다.
                "contributors": json.dumps(contributors, ensure_ascii=False),
                "embedded_at": datetime.now().isoformat(),
            },
        )])

        replaced = f" (이전 일지 {len(stale_ids)}개 교체)" if stale_ids else ""
        return f"🔎 일지를 검색 대상에 등록했습니다{replaced}."

    except Exception as e:
        # 파일 저장은 이미 성공했으므로 임베딩 실패로 전체를 실패 처리하지 않는다
        print(f"[maker_logfile] 일지 임베딩 실패: {e}")
        return f"⚠️ 파일은 저장했으나 검색 등록에 실패했습니다: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 기간 일지 생성 — 날짜별로 쪼개서 하나씩
# ─────────────────────────────────────────────────────────────────────────────

# 일지 생성 진행률. 백그라운드 스레드가 쓰고 화면 폴링이 읽는다.
# 서버가 죽으면 작업도 함께 죽으므로 메모리에 둔다 — 임베딩은 수십 분씩 돌아
# DB(sources.embedding_stats)에 남기지만, 일지 생성은 몇 분이면 끝난다.
_journal_jobs: dict[str, dict] = {}
_journal_lock = threading.Lock()

# 하루 일지를 쓰는 LLM 에게 주는 지침.
# 도구를 붙이지 않는다 — 자료를 받아 요약을 뱉는 정형 작업이라 판단이 필요 없고,
# 도구 스키마 2,071 토큰을 날짜마다 다시 실을 이유가 없다.
DAILY_JOURNAL_PROMPT = """당신은 개발자의 하루를 정리하는 일지 작성자입니다.

주어진 자료는 그날 하루의 기록입니다 — 커밋 이력, 작성한 문서, AI 와 나눈 대화.
이것만 보고 그날의 일지를 마크다운으로 작성하세요.

원칙:
- 자료에 없는 내용을 지어내지 마세요. 근거가 자료에 있어야 합니다.
- 나열이 아니라 흐름을 쓰세요. 무엇을 하려 했고, 무엇에 막혔고, 어떻게 풀었는지.
- 커밋 메시지를 그대로 옮겨 적지 말고, 무엇을 만든 것인지로 바꿔 쓰세요.
- 막힌 지점과 해결 과정이 있으면 반드시 남기세요. 나중에 가장 쓸모 있는 부분입니다.
- 자료가 빈약하면 짧게 쓰세요. 분량을 채우려 부풀리지 마세요.

응답은 일지 본문만 담습니다. "다음은 일지입니다" 같은 머리말을 붙이지 마세요."""


def journal_progress(user_id: str) -> dict:
    """진행 상황 스냅샷 (화면 폴링용)."""
    with _journal_lock:
        return dict(_journal_jobs.get(user_id) or {})


def _set_progress(user_id: str, **fields) -> None:
    with _journal_lock:
        _journal_jobs.setdefault(user_id, {}).update(fields)


def _journal_path(date: str) -> str:
    return f"{LOGS_DIR}/{date.replace('-', '.')}_log.md"


def _dates_with_records(user_id: str, targets: list[str]) -> list[str]:
    """
    기간 안에서 실제로 기록이 있는 날짜만 추린다.

    기록이 없는 날까지 LLM 을 부르면 "자료가 없습니다"라는 일지가 생긴다.
    """
    try:
        store = _open_collection(user_id)
        where = {"date": targets[0]} if len(targets) == 1 else {"date": {"$in": targets}}
        found = store.get(where=where, include=["metadatas"])
    except Exception as e:
        print(f"[journal] 날짜 조회 실패: {e}")
        return []

    return sorted({
        meta["date"]
        for meta in (found.get("metadatas") or [])
        if meta and meta.get("date")
    })


def _write_one_day(date: str, user_id: str) -> str:
    """하루치 자료를 모아 일지를 쓰고 저장한다."""
    material = retriever_vectordb.invoke({"date": date, "user_id": user_id})

    response = llm_router.anthropic_llm.invoke([
        SystemMessage(content=DAILY_JOURNAL_PROMPT),
        HumanMessage(content=f"[{date}] 자료\n\n{material}"),
    ])
    body = response.content if isinstance(response.content, str) else str(response.content)

    return maker_logfile.invoke({"date": date, "content": body, "user_id": user_id})
    # material 과 body 는 지역 변수다. 다음 날짜로 넘어가면 사라지므로
    # 기간이 길어져도 한 번에 들고 있는 자료는 하루치를 넘지 않는다.


def _run_journal_job(user_id: str, dates: list[str]) -> None:
    """백그라운드에서 날짜별로 일지를 만든다."""
    written, failed = [], []

    for index, date in enumerate(dates, 1):
        _set_progress(user_id, phase="writing", done=index - 1, total=len(dates), date=date)
        try:
            _write_one_day(date, user_id)
            written.append(date)
        except Exception as e:
            print(f"[journal] {date} 작성 실패: {e}")
            failed.append(f"{date}({e})")

    _set_progress(
        user_id, phase="done", done=len(dates), total=len(dates), date="",
        written=written, failed=failed,
    )
    print(f"[journal] 완료 — 작성 {len(written)}건, 실패 {len(failed)}건")


@tool
def generate_daily_journals(
    start_date: str,
    end_date: str,
    user_id: str,
    existing: str = "",
) -> str:
    """
    기간 안의 날짜마다 일지를 하나씩 만들어 저장합니다 (백그라운드 실행).

    이틀 이상을 요청받으면 retriever_vectordb 대신 이 도구를 쓰세요.
    날짜별로 따로 처리하므로 기간이 길어도 자료가 잘리지 않습니다.

    이미 일지가 있는 날이 있으면 작업을 시작하지 않고 사용자에게 물어봅니다.
    사용자의 답을 받은 뒤 existing 을 채워 다시 호출하세요.

    Args:
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)
        user_id: 사용자 ID
        existing: 이미 일지가 있는 날 처리 방법.
                  "skip"=건너뛰기, "overwrite"=다시 쓰기.
                  비워 두면 겹치는 날이 있을 때 사용자에게 확인을 요청합니다.

    Returns:
        시작 안내 또는 확인 요청 (완료 결과가 아님)
    """
    start = parse_user_date(start_date)
    finish = parse_user_date(end_date)
    if not start or not finish:
        return "❌ 날짜를 해석하지 못했습니다. YYYY-MM-DD 형식으로 알려주세요."

    targets = _date_range(start, finish)

    running = journal_progress(user_id)
    if running.get("phase") == "writing":
        return (
            f"⏳ 이미 일지를 만드는 중입니다 "
            f"({running.get('done', 0)}/{running.get('total', 0)}, 현재 {running.get('date', '')})."
        )

    dates = _dates_with_records(user_id, targets)
    if not dates:
        period = f"{start} ~ {finish}"
        return f"📭 '{period}'에 기록된 자료가 없어 만들 일지가 없습니다."

    already = [date for date in dates if os.path.exists(_journal_path(date))]

    if already and not existing:
        preview = ", ".join(already[:5]) + (f" 외 {len(already) - 5}일" if len(already) > 5 else "")
        return (
            f"🤔 기간 안 {len(dates)}일 중 {len(already)}일은 이미 일지가 있습니다: {preview}\n\n"
            "이 날들을 어떻게 할까요?\n"
            "- 건너뛰고 나머지만 만들기\n"
            "- 자료를 다시 읽어 새로 쓰기 (기존 일지는 덮어씁니다)\n\n"
            "사용자에게 물어본 뒤 existing 에 \"skip\" 또는 \"overwrite\" 를 넣어 다시 호출하세요."
        )

    skipped = []
    if existing == "skip":
        skipped = already
        dates = [date for date in dates if date not in already]

    if not dates:
        return f"✅ 기간 안 {len(skipped)}일 모두 이미 일지가 있어 새로 만들 것이 없습니다."

    _set_progress(user_id, phase="starting", done=0, total=len(dates), date="",
                  written=[], failed=[], skipped=skipped)

    threading.Thread(
        target=_run_journal_job,
        args=(user_id, dates),
        daemon=True,
        name=f"journal-{user_id}",
    ).start()

    notice = f"🚀 {start} ~ {finish} 기간의 일지를 만들기 시작했습니다 ({len(dates)}일)."
    if skipped:
        notice += f"\n이미 일지가 있는 {len(skipped)}일은 건너뜁니다."
    notice += "\n\n하루씩 차례로 작성하며, 진행 상황은 화면에 표시됩니다."
    return notice


def describe_journal_progress(progress: dict) -> str:
    """진행 상태를 사람이 읽을 문장으로 만든다."""
    phase = progress.get("phase")
    done, total = progress.get("done") or 0, progress.get("total") or 0

    if phase == "starting":
        return "준비 중"
    if phase == "writing":
        date = progress.get("date") or ""
        percent = f", {done * 100 // total}%" if total else ""
        return f"{date} 작성 중 ({done}/{total}{percent})"
    if phase == "done":
        failed = progress.get("failed") or []
        tail = f", 실패 {len(failed)}건" if failed else ""
        return f"완료 ({len(progress.get('written') or [])}건 작성{tail})"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 일지 관리 화면용 조회
# ─────────────────────────────────────────────────────────────────────────────

def _contributing_sources(store: Chroma, date: str) -> list[dict]:
    """
    그 날짜에 기록이 있는 소스를 세어 돌려준다 (일지 자신은 제외).

    Returns:
        [{"source_id": 7, "name": "...", "type": "git_log", "chunks": 3}, ...]
    """
    try:
        found = store.get(where={"date": date}, include=["metadatas"])
    except Exception as e:
        print(f"[journal] 기여 소스 조회 실패 ({date}): {e}")
        return []

    tally: dict[int, dict] = {}
    for meta in found.get("metadatas") or []:
        if not meta or meta.get("source_type") == "journal":
            continue
        key = meta.get("source_id")
        entry = tally.setdefault(key, {
            "source_id": key,
            "name": meta.get("source_name") or "",
            "type": meta.get("source_type") or "",
            "chunks": 0,
        })
        entry["chunks"] += 1

    return sorted(tally.values(), key=lambda e: -e["chunks"])


def _journal_head(path: str) -> tuple[str, int]:
    """
    일지의 제목 줄과 글자 수.

    파일 크기(getsize)를 글자 수로 쓰면 안 된다 — 한글은 UTF-8 에서 3바이트라
    실제보다 세 배 가까이 부풀려 보인다 (1,340자 문서가 2,202 으로 표시됐다).
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "", 0

    title = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break
        if stripped:
            title = stripped[:60]
            break

    return title, len(text)


def journal_overview(user_id: str) -> dict:
    """
    일지 관리 화면에 필요한 것을 한 번에 모은다.

    진실은 파일(logs/*.md)이고 벡터DB는 파생 색인이다. 사용자가 열고 고치는
    대상이 파일이며, 색인은 언제든 파일에서 다시 만들 수 있기 때문이다.
    그래서 목록은 파일에서 만들고, 색인 여부를 옆에 표시한다.

    Returns:
        {"journals": [...], "unindexed": 3}
    """
    store = _open_collection(user_id)

    try:
        indexed = store.get(where={"source_type": "journal"}, include=["metadatas"])
        by_date = {
            meta["date"]: meta
            for meta in (indexed.get("metadatas") or [])
            if meta and meta.get("date")
        }
    except Exception as e:
        print(f"[journal] 색인 조회 실패: {e}")
        by_date = {}

    journals = []
    for name in sorted(os.listdir(LOGS_DIR) if os.path.isdir(LOGS_DIR) else [], reverse=True):
        if not name.endswith("_log.md"):
            continue

        date = normalize_date(name.replace("_log.md", "").replace(".", "-"))
        if not date:
            continue

        path = f"{LOGS_DIR}/{name}"
        meta = by_date.get(date)

        # 기록해 둔 것이 있으면 그것을 쓴다. 없는 옛 일지는 날짜로 다시 세되,
        # 그 사이 소스가 바뀌었을 수 있으므로 추정이라고 밝힌다.
        if meta and meta.get("contributors"):
            try:
                sources, estimated = json.loads(meta["contributors"]), False
            except (ValueError, TypeError):
                sources, estimated = _contributing_sources(store, date), True
        else:
            sources, estimated = _contributing_sources(store, date), True

        title, chars = _journal_head(path)
        journals.append({
            "date": date,
            "title": title,
            "path": path,
            "chars": chars,
            "indexed": date in by_date,
            "sources": sources,
            "sources_estimated": estimated,
        })

    return {
        "journals": journals,
        "unindexed": sum(1 for j in journals if not j["indexed"]),
    }


def reindex_journal(user_id: str, date: str) -> str:
    """파일에 있는 일지를 벡터DB에 다시 등록한다."""
    normalized = normalize_date(date)
    if not normalized:
        return f"❌ '{date}'를 날짜로 해석하지 못했습니다."

    path = _journal_path(normalized)
    if not os.path.exists(path):
        return f"❌ 일지 파일이 없습니다: {path}"

    with open(path, encoding="utf-8") as f:
        content = f.read()

    return _embed_journal(normalized, content, user_id, path)


# ─────────────────────────────────────────────────────────────────────────────
# 일지 뷰어 — 마크다운 렌더
# ─────────────────────────────────────────────────────────────────────────────

def _highlight_code(code: str, lang: str, attrs: str) -> str:
    """
    코드 블록에 색을 입힌다. 언어를 모르면 빈 문자열을 돌려주는데,
    그러면 markdown-it 이 알아서 이스케이프한 기본 블록을 만든다.
    """
    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    return highlight(code, lexer, HtmlFormatter(cssclass="hl"))


# html=False 가 핵심이다. 일지는 LLM 이 쓰지만 그 재료는 사용자 저장소의 문서와
# 커밋 메시지다 — 남의 저장소를 소스로 등록하면 임의의 HTML 이 흘러들 수 있다.
_markdown = (
    MarkdownIt("commonmark", {"html": False, "highlight": _highlight_code})
    .enable("table")
    .enable("strikethrough")
)

# Pygments 스타일시트는 손으로 쓰지 않고 뽑아 쓴다 — 테마를 바꿔도 따라온다
HIGHLIGHT_CSS = HtmlFormatter(cssclass="hl", style="friendly").get_style_defs(".hl")

# CommonMark 는 GFM 체크박스를 모른다. 플러그인을 더 받는 대신 렌더 뒤에 바꾼다.
_TASK_OPEN = re.compile(r"<li>(<p>)?\[([ xX])\]\s*")


def _render_task_lists(html: str) -> str:
    """`- [ ]` / `- [x]` 를 체크박스로 바꾼다."""
    def swap(match: re.Match) -> str:
        paragraph, mark = match.group(1) or "", match.group(2)
        done = mark.lower() == "x"
        box = '<span class="task-box done">✔</span>' if done else '<span class="task-box"></span>'
        return f'<li class="task{" done" if done else ""}">{paragraph}{box}'

    return _TASK_OPEN.sub(swap, html)


def render_journal(user_id: str, date: str) -> dict | None:
    """
    일지 한 편을 화면에 띄울 형태로 만든다.

    Returns:
        {"date", "title", "html", "raw", "chars", "sources", ...} 또는
        파일이 없으면 None
    """
    normalized = normalize_date(date)
    if not normalized:
        return None

    path = _journal_path(normalized)
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    overview = journal_overview(user_id)
    dates = [journal["date"] for journal in overview["journals"]]
    current = next((j for j in overview["journals"] if j["date"] == normalized), None)

    # 목록은 최신순이므로 '이전 글'은 뒤쪽 = 더 오래된 날이다
    index = dates.index(normalized) if normalized in dates else -1
    newer = dates[index - 1] if index > 0 else ""
    older = dates[index + 1] if 0 <= index < len(dates) - 1 else ""

    title, chars = _journal_head(path)
    return {
        "date": normalized,
        "title": title,
        "html": _render_task_lists(_markdown.render(raw)),
        "raw": raw,
        "chars": chars,
        "path": path,
        "indexed": bool(current and current["indexed"]),
        "sources": current["sources"] if current else [],
        "sources_estimated": bool(current and current["sources_estimated"]),
        "newer": newer,
        "older": older,
    }


def journal_archive(user_id: str) -> tuple[bytes, int]:
    """
    모든 일지를 zip 으로 묶는다.

    렌더된 HTML 이 아니라 원본 마크다운을 담는다 — 옵시디언이나 노션으로
    그대로 옮길 수 있어야 한다.

    Returns:
        (zip 바이트, 담긴 파일 수)
    """
    buffer = io.BytesIO()
    count = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for journal in journal_overview(user_id)["journals"]:
            try:
                archive.write(journal["path"], arcname=os.path.basename(journal["path"]))
                count += 1
            except OSError as e:
                print(f"[journal] 압축 실패 ({journal['path']}): {e}")

    return buffer.getvalue(), count
