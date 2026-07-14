from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState
from langchain_community.document_loaders import DirectoryLoader, TextLoader, JSONLoader
from langchain_chroma import Chroma
from langchain_core.documents import Document
import src.llm_router as llm_router
import hashlib
import zipfile
import tempfile
import json
import os
## chroma 인덱싱

@tool
#파일 임베딩 tool -- 파일 처리용
def embedding_file(path: str) -> str:
    """
    이 도구는 특정 경로의 파일을 임베딩해서 chromadb에 적재하기 위한 도구 입니다.
    사용자의 메시지에서 파일 또는 디렉토리 경로를 추출하여 path로 사용하세요.
    경로는 ../Yuta_TIL, ./docs, /Users/*/Documents 와 같은 형태입니다.
    
    Args:
        path: 임베딩할 디렉토리 경로. 사용자 메시지에서 경로 정보를 추출하여 입력하세요.
    """
    all_docs = []
    # ZIP 파일 처리
    if path.endswith('.zip'):
        print(f"ZIP 파일 감지: {path}")
        # 임시 디렉토리에 압축 해제
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        print(f"압축 해제 완료: {temp_dir}")
        load_path = temp_dir
    else:
        load_path = path
    
    # 텍스트 파일 로드
    for pattern in ["**/*.md", "**/*.txt"]:
        loader = DirectoryLoader(
            path=load_path,
            glob=pattern,
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        docs = loader.load()

        # 파일명에서 날짜 추출 (YYYY_MM_DD, YYYY-MM-DD 형식)
        import re
        for doc in docs:
            source = doc.metadata.get("source", "")
            # 파일명에서 날짜 패턴 찾기
            date_patterns = [
                r'(\d{4})[_-](\d{1,2})[_-](\d{1,2})',  # 2026_05_14 또는 2026-05-14
                r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',  # 2026년 05월 14일
            ]

            date_found = None
            for pattern_regex in date_patterns:
                match = re.search(pattern_regex, source)
                if match:
                    year, month, day = match.groups()
                    date_found = f"{year}년 {int(month)}월 {int(day)}일"
                    doc.metadata["date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    break

            # 날짜를 문서 내용 앞에 추가 (검색 향상)
            if date_found:
                doc.page_content = f"작성 날짜: {date_found}\n\n{doc.page_content}"

        all_docs.extend(docs)

    # JSON 파일 로드 (Claude 대화 내용)
    json_loader = DirectoryLoader(
        path=load_path,
        glob="**/*.json",
        loader_cls=JSONLoader,
        loader_kwargs={
            "jq_schema": ".",
            "text_content": False
        }
    )
    json_docs = json_loader.load()

    # claude의 대화 내용 JSON 문서를 읽기 쉬운 형태로 변환
    for doc in json_docs:
        try:
            data = json.loads(doc.page_content)
            # conversations.json 처리
            if "conversations" in data or isinstance(data, list):
                conversations = data.get("conversations", data) if isinstance(data, dict) else data
                for conv in conversations:
                    if isinstance(conv, dict):
                        messages = conv.get("messages", [])
                        conv_text = f"Conversation: {conv.get('name', 'Untitled')}\n\n"
                        for msg in messages:
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")
                            conv_text += f"{role}: {content}\n\n"

                        all_docs.append(Document(
                            page_content=conv_text,
                            metadata={
                                "source": doc.metadata.get("source", "unknown"),
                                "type": "claude_conversation"
                            }
                        ))
        except:
            # JSON 파싱 실패 시 원본 그대로 사용
            all_docs.append(doc)

    docs = all_docs
    # 꼭 TIL이 아닐수 있다. 하지만 데이터가 잘 안나오면 분류를 해야할수 있다.
    # for doc in docs:
    #     doc.metadata["source_type"] = "TIL"

    # 빈 문서 필터링
    non_empty_docs = [doc for doc in docs if doc.page_content.strip()]

    if not non_empty_docs:
        return "No non-empty documents to embed"

    print(f"총 {len(non_empty_docs)}개 문서 임베딩 시작...")

    # 고유한 ID 생성 (내용 + 출처 + 인덱스) - 중복제거
    ids = []
    for idx, doc in enumerate(non_empty_docs):
        # 문서 내용, 출처, 인덱스를 조합하여 고유한 ID 생성
        source = doc.metadata.get("source", "unknown")
        unique_string = f"{source}_{idx}_{doc.page_content[:100]}"
        id_hash = hashlib.md5(unique_string.encode()).hexdigest()
        ids.append(id_hash)

    vectorstore = Chroma(
        embedding_function=llm_router.local_embedding,  # 로컬 임베딩 사용 (무료!)
        client=llm_router.chroma_client,  # 서버 모드 클라이언트 사용
    )

    print(f"ChromaDB에 저장 중...")
    vectorstore.add_documents(non_empty_docs, ids=ids)
    print(f"✅ 완료! {len(non_empty_docs)}개 문서가 임베딩되었습니다.")

    return vectorstore
#날짜 조회 tool
@tool
def retriever_vectordb(date: str, reference_len: str) -> str:
    """
    이 도구는 사용자의 요청에서 2026년 07월 09일, 2026_12_03,2026.01.13와 같은 날짜 형식의 데이터를 받으면 chroma_db에서
    그 날짜와 유사도가 높은 문서를 가져오는 도구입니다.
    05월 13일 과같이 년도가 없다면 올해 년도를 측정해서 찾으시요.
    Args:
        date: 사용자가 요청한 날짜데이터. 사용자 메시지에서 날짜 정보를 추출하여 입력하세요.
        reference_len: 사용자가 참조하라고 정한 참조문서의 특성,종류,타겟.사용자 메시지에서 참조하라고 한 정보의 수를 추출하여 입력하세요.
    """
    import re

    reopened = Chroma(
        collection_name="user_hrun",  # 컬렉션 이름 지정!
        embedding_function=llm_router.local_embedding,
        client=llm_router.chroma_client,  # 서버 모드 클라이언트 사용
    )
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
            from langchain_core.documents import Document
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
    except:
        # 메타데이터 검색 실패 시 유사도 검색
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
#일지 파일 저장 tool
@tool
def maker_logfile(date: str, content: str)-> str:
    """
    생성된 일지를 마크다운 파일로 저장합니다.

      Args:
          date: 날짜 (YYYY-MM-DD 형식, 예: 2026-07-09)
          content: 일지 내용 (마크다운 형식)

      Returns:
          저장된 파일 경로 메시지
    """
    os.makedirs("logs",exist_ok=True)
    filename= f"logs/{date.replace('-', '.')}_log.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"✅ 일지 저장 완료: {filename}"

## 사용자별 임베딩 함수 (Git 연동용)
def embedding_file_for_user(user_id: str, path: str) -> str:
    """
    사용자별로 파일을 임베딩 (컬렉션 분리)

    Args:
        user_id: 사용자 식별자 (예: "hrun", "user_123")
        path: 임베딩할 디렉토리 경로

    Returns:
        임베딩 완료 메시지
    """
    all_docs = []

    # 텍스트 파일 로드 (기존 로직과 동일)
    for pattern in ["**/*.md", "**/*.txt"]:
        loader = DirectoryLoader(
            path=path,
            glob=pattern,
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        docs = loader.load()

        # 파일명에서 날짜 추출 (기존 로직)
        import re
        for doc in docs:
            source = doc.metadata.get("source", "")
            date_patterns = [
                r'(\d{4})[_-](\d{1,2})[_-](\d{1,2})',
                r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
            ]

            date_found = None
            for pattern_regex in date_patterns:
                match = re.search(pattern_regex, source)
                if match:
                    year, month, day = match.groups()
                    date_found = f"{year}년 {int(month)}월 {int(day)}일"
                    doc.metadata["date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    break

            if date_found:
                doc.page_content = f"작성 날짜: {date_found}\n\n{doc.page_content}"

        all_docs.extend(docs)

    # JSON 파일 로드 (기존 로직)
    # json_loader = DirectoryLoader(
    #     path=path,
    #     glob="**/*.json",
    #     loader_cls=JSONLoader,
    #     loader_kwargs={
    #         "jq_schema": ".",
    #         "text_content": False
    #     }
    # )
    # json_docs = json_loader.load()

    # for doc in json_docs:
    #     try:
    #         data = json.loads(doc.page_content)
    #         if "conversations" in data or isinstance(data, list):
    #             conversations = data.get("conversations", data) if isinstance(data, dict) else data
    #             for conv in conversations:
    #                 if isinstance(conv, dict):
    #                     messages = conv.get("messages", [])
    #                     conv_text = f"Conversation: {conv.get('name', 'Untitled')}\n\n"
    #                     for msg in messages:
    #                         role = msg.get("role", "unknown")
    #                         content = msg.get("content", "")
    #                         conv_text += f"{role}: {content}\n\n"

    #                     all_docs.append(Document(
    #                         page_content=conv_text,
    #                         metadata={
    #                             "source": doc.metadata.get("source", "unknown"),
    #                             "type": "claude_conversation"
    #                         }
    #                     ))
    #     except:
    #         all_docs.append(doc)

    docs = all_docs

    # 빈 문서 필터링
    non_empty_docs = [doc for doc in docs if doc.page_content.strip()]

    if not non_empty_docs:
        return f"❌ {user_id}: 임베딩할 문서가 없습니다"

    print(f"[{user_id}] 총 {len(non_empty_docs)}개 문서 임베딩 시작...")

    # 고유한 ID 생성
    ids = []
    for idx, doc in enumerate(non_empty_docs):
        source = doc.metadata.get("source", "unknown")
        unique_string = f"{user_id}_{source}_{idx}_{doc.page_content[:100]}"
        id_hash = hashlib.md5(unique_string.encode()).hexdigest()
        ids.append(id_hash)

    # 사용자별 컬렉션 생성
    collection_name = f"user_{user_id}"

    # 기존 컬렉션 삭제 (중복 방지)
    try:
        llm_router.chroma_client.delete_collection(collection_name)
        print(f"[{user_id}] 기존 컬렉션 삭제됨")
    except Exception as e:
        print(f"[{user_id}] 기존 컬렉션 없음 (첫 동기화)")

    vectorstore = Chroma(
        collection_name=collection_name,  # 사용자별 컬렉션!
        embedding_function=llm_router.local_embedding,
        client=llm_router.chromadb.PersistentClient(path="./chroma_db")  # 서버 모드 클라이언트 사용
    )

    print(f"[{user_id}] ChromaDB 컬렉션 '{collection_name}'에 저장 중...")
    vectorstore.add_documents(non_empty_docs, ids=ids)
    print(f"✅ [{user_id}] 완료! {len(non_empty_docs)}개 문서가 임베딩되었습니다.")

    return f"✅ 사용자 '{user_id}': {len(non_empty_docs)}개 문서 임베딩 완료 (컬렉션: {collection_name})"


if __name__ == "__main__":
    result = embedding_file.invoke({"path": "../Yuta_TIL"})
    result = embedding_file.invoke({"path": "/Users/hrun/Downloads/data-5e445e3f-837e-4504-83a7-4d9923c64d11-1783416356-0e00b9b2-batch-0000.zip"})
    print(f"documents result: {result}")