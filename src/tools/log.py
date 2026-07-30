"""
일지 관리 도구 모듈

이 모듈은 날짜 기반으로 임베딩 데이터를 조회하고 일지를 생성/저장하는 도구를 제공합니다.

제공 도구:
    - retriever_vectordb: 날짜 기반 VectorDB 검색
    - maker_logfile: 일지 파일 저장
"""
import os
import re
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_chroma import Chroma
from .. import llm_router


@tool
def retriever_vectordb(date: str, reference_len: str,user_id: str) -> str:
    """
    이 도구는 사용자의 요청에서 2026년 07월 09일, 2026_12_03, 2026.01.13와 같은 날짜 형식의 데이터를 받으면 chroma_db에서
    그 날짜와 유사도가 높은 문서를 가져오는 도구입니다.
    05월 13일과 같이 년도가 없다면 올해 년도를 측정해서 찾으세요.

    Args:
        date: 사용자가 요청한 날짜 데이터. 사용자 메시지에서 날짜 정보를 추출하여 입력하세요.
        reference_len: 사용자가 참조하라고 정한 참조 문서의 특성, 종류, 타겟. 사용자 메시지에서 참조하라고 한 정보의 수를 추출하여 입력하세요.

    Returns:
        검색된 문서 목록과 내용
    """
    # ChromaDB 컬렉션 열기
    reopened = Chroma(
        collection_name=f"user_{user_id}",  # 컬렉션 이름 지정
        embedding_function=llm_router.embedding_function,
        client=llm_router.chroma_client,  # 서버 모드 클라이언트 사용
    )

    # 참조 문서 개수 설정 (기본값: 5)
    k = int(reference_len) if reference_len else 5

    # 날짜 정규화 (YYYY-MM-DD 형식으로)
    date_normalized = re.sub(r'\D', '', date)
    if len(date_normalized) >= 8:
        date_filter = f"{date_normalized[:4]}-{date_normalized[4:6]}-{date_normalized[6:8]}"
    else:
        date_filter = date

    # 1차: 메타데이터 필터로 정확한 날짜 찾기
    try:
        docs = reopened.get(where={"date": date_filter}, limit=k)
        if docs and docs.get('documents'):
            print(f"[DEBUG] 메타데이터 필터로 {len(docs['documents'])}개 문서 찾음")
            # Document 객체로 변환
            docs = [
                Document(
                    page_content=content,
                    metadata=metadata
                )
                for content, metadata in zip(docs['documents'], docs['metadatas'])
            ]
        else:
            # 2차: 유사도 검색
            print(f"[DEBUG] 메타데이터 검색 실패, 유사도 검색 시도...")
            docs = reopened.similarity_search(f"작성 날짜: {date}", k=k)
    except Exception as e:
        # 메타데이터 검색 실패 시 유사도 검색
        print(f"[DEBUG] 메타데이터 검색 오류: {e}")
        docs = reopened.similarity_search(f"작성 날짜: {date}", k=k)

    # LLM이 읽기 쉬운 형식으로 변환
    if not docs:
        return f"'{date}' 날짜와 관련된 기록을 찾을 수 없습니다."

    result_text = f"'{date}' 날짜 관련 검색 결과 ({len(docs)}개 문서):\n\n"
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        doc_type = doc.metadata.get("type", "document")
        doc_date = doc.metadata.get("date", "날짜 정보 없음")

        result_text += f"--- 문서 {i} ---\n"
        result_text += f"날짜: {doc_date}\n"
        result_text += f"출처: {source}\n"
        result_text += f"타입: {doc_type}\n"
        result_text += f"내용:\n{doc.page_content}\n\n"

    return result_text


@tool
def maker_logfile(date: str, content: str) -> str:
    """
    생성된 일지를 마크다운 파일로 저장합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식, 예: 2026-07-09)
        content: 일지 내용 (마크다운 형식)

    Returns:
        저장된 파일 경로 메시지
    """
    # logs 디렉토리 생성 (없으면)
    os.makedirs("logs", exist_ok=True)

    # 파일명 생성 (YYYY.MM.DD_log.md 형식)
    filename = f"logs/{date.replace('-', '.')}_log.md"

    # 파일 저장
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    return f"✅ 일지 저장 완료: {filename}"
