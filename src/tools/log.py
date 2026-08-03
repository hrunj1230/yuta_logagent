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


@tool
def retriever_vectordb(date: str, reference_len: str, user_id: str, end_date: str = "") -> str:
    """
    지정한 날짜(또는 날짜 범위)에 기록된 문서를 벡터DB에서 조회합니다.

    2026년 07월 09일, 2026_12_03, 2026.01.13 같은 다양한 날짜 표기를 처리합니다.
    연도가 없으면 올해 연도로 간주하세요.
    "이번 주", "지난 3일" 처럼 기간을 묻는 요청은 date에 시작일, end_date에 종료일을 넣으세요.

    Args:
        date: 조회할 날짜 (기간 조회 시 시작일)
        reference_len: 가져올 문서 개수. 비어 있으면 5
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

    try:
        k = int(reference_len)
    except (TypeError, ValueError):
        k = 5
    k = max(1, k)

    store = _open_collection(user_id)

    # 날짜 메타데이터 필터로만 조회한다.
    # 문자열 비교 연산자는 ChromaDB에서 신뢰할 수 없으므로 $in 으로 명시한다.
    where = {"date": targets[0]} if len(targets) == 1 else {"date": {"$in": targets}}

    try:
        found = store.get(where=where, limit=k, include=["documents", "metadatas"])
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

    docs = [
        Document(page_content=content, metadata=meta or {})
        for content, meta in zip(contents, metadatas)
    ]

    period = f"{start} ~ {finish}" if finish else start
    result_text = f"'{period}' 검색 결과 ({len(docs)}개 문서):\n\n"

    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        result_text += f"--- 문서 {i} ---\n"
        result_text += f"날짜: {meta.get('date', '날짜 정보 없음')}\n"
        result_text += f"출처: {meta.get('source_name', 'unknown')}\n"
        result_text += f"타입: {meta.get('source_type', 'document')}\n"
        if meta.get("file_path"):
            result_text += f"경로: {meta['file_path']}\n"
        result_text += f"내용:\n{doc.page_content}\n\n"

    return result_text


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
