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
from datetime import datetime
from sqlalchemy.orm import Session
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
# @tool 제거: 이것은 Agent가 직접 호출하는 도구가 아니라 내부 헬퍼 함수
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
        client=llm_router.chroma_client  # 기존 클라이언트 사용 (일관성 유지)
    )

    print(f"[{user_id}] ChromaDB 컬렉션 '{collection_name}'에 저장 중...")
    vectorstore.add_documents(non_empty_docs, ids=ids)
    print(f"✅ [{user_id}] 완료! {len(non_empty_docs)}개 문서가 임베딩되었습니다.")

    return f"✅ 사용자 '{user_id}': {len(non_empty_docs)}개 문서 임베딩 완료 (컬렉션: {collection_name})"


## Source 관리 Tool들

@tool
def add_source_to_db(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    학습 소스를 추가합니다. Git URL을 받으면 자동으로 클론하고 임베딩합니다.

    **중요**: Git 저장소 URL(https://github.com/..., .git)을 받으면:
    1. 자동으로 git clone 실행
    2. 클론된 파일들을 임베딩하여 벡터DB에 저장
    3. 데이터베이스에 소스 정보 저장

    사용자가 로컬에 클론할 필요 없습니다! URL만 제공하면 모든 것이 자동 처리됩니다.

    Args:
        user_id: 사용자 ID
        name: 소스 이름 (예: "Yuta_TIL", "내 노트")
        source_type: "git" (Git 저장소) 또는 "local_til" (로컬 경로)
        location: Git 저장소 URL (예: https://github.com/user/repo.git) 또는 로컬 경로

    Returns:
        성공 메시지 (클론 및 임베딩 완료 포함)

    Examples:
        >>> add_source_to_db("hrun", "Yuta_TIL", "git", "https://github.com/hrunj1230/Yuta_TIL.git")
        "✅ Git 저장소 추가 완료! 자동으로 클론 및 임베딩이 완료되었습니다."
    """
    import subprocess
    import shutil
    from storage.models import Source, SourceType
    from storage.database import SessionLocal

    db = SessionLocal()

    try:
        # 소스 타입 변환
        type_mapping = {
            "git": SourceType.GIT,
            "local_til": SourceType.LOCAL_TIL,
            "agent_chatlog": SourceType.AGENT_CHATLOG,
            "memsearch": SourceType.MEMSEARCH,
        }

        if source_type.lower() not in type_mapping:
            return f"❌ 잘못된 소스 타입: {source_type}. 사용 가능한 타입: git, local_til, agent_chatlog, memsearch"

        # 중복 체크
        existing = db.query(Source).filter(
            Source.user_id == user_id,
            Source.type == type_mapping[source_type.lower()],
            Source.location == location
        ).first()

        if existing:
            return f"⚠️ 이미 등록된 소스입니다: {existing.name} ({location})"

        # 1️⃣ 먼저 Source를 DB에 저장 (임베딩 실패해도 저장 보장)
        new_source = Source(
            user_id=user_id,
            name=name,
            type=type_mapping[source_type.lower()],
            location=location,
            last_synced_at=datetime.now(),
            is_active=True
        )

        db.add(new_source)
        db.commit()
        db.refresh(new_source)
        print(f"✅ Source 저장 완료: {name} (ID: {new_source.id})")

        # 2️⃣ Git 저장소인 경우 클론 및 임베딩 시도
        embedding_success = False
        embedding_error = None

        if source_type.lower() == "git":
            try:
                # 사용자별 저장 디렉토리
                user_dir = f"./repos/{user_id}"
                repo_name = location.rstrip('/').split('/')[-1].replace('.git', '')
                local_path = f"{user_dir}/{repo_name}"

                # 기존 디렉토리 삭제
                if os.path.exists(local_path):
                    shutil.rmtree(local_path)

                # 사용자 디렉토리 생성
                os.makedirs(user_dir, exist_ok=True)

                # Git clone (shallow clone으로 빠르게)
                print(f"[Git Sync] Cloning {location} to {local_path}...")
                subprocess.run(
                    ["git", "clone", "--depth", "1", location, local_path],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print(f"[Git Sync] Clone 완료!")

                # 임베딩 (사용자별 컬렉션)
                print(f"[Embedding] Starting embedding for {local_path}...")
                embedding_result = embedding_file_for_user(user_id, local_path)
                print(f"[Embedding] 완료! {embedding_result}")
                embedding_success = True

            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                embedding_error = f"Git clone 실패: {error_msg}"
                print(f"❌ {embedding_error}")
            except Exception as e:
                embedding_error = f"임베딩 실패: {str(e)}"
                print(f"❌ {embedding_error}")

        # 3️⃣ 결과 메시지 반환
        if source_type.lower() == "git":
            if embedding_success:
                return f"✅ Git 저장소 추가 완료!\n이름: {name}\n위치: {location}\n\n🔄 자동으로 클론 및 임베딩이 완료되었습니다.\n이제 일지 작성 시 이 저장소의 내용을 참조할 수 있습니다!"
            else:
                return f"⚠️ Git 저장소 추가 완료 (임베딩 실패)\n이름: {name}\n위치: {location}\n\n저장소는 등록되었지만 임베딩 중 오류가 발생했습니다:\n{embedding_error}\n\n나중에 다시 동기화를 시도해주세요."
        else:
            return f"✅ 소스 추가 완료!\n이름: {name}\n타입: {source_type}\n위치: {location}"

    except Exception as e:
        db.rollback()
        return f"❌ 소스 저장 실패: {str(e)}"
    finally:
        db.close()


@tool
def get_user_sources(user_id: str) -> str:
    """
    사용자의 등록된 소스 목록을 조회합니다.

    Args:
        user_id: 사용자 ID

    Returns:
        소스 목록 (텍스트 형식)
    """
    from storage.models import Source
    from storage.database import SessionLocal

    db = SessionLocal()
    try:
        sources = db.query(Source).filter(
            Source.user_id == user_id,
            Source.is_active == True
        ).all()

        if not sources:
            return f"📭 '{user_id}' 사용자의 등록된 소스가 없습니다."

        result = f"📚 '{user_id}' 사용자의 등록된 소스 ({len(sources)}개):\n\n"

        for idx, source in enumerate(sources, 1):
            result += f"{idx}. {source.name}\n"
            result += f"   - 타입: {source.type.value}\n"
            result += f"   - 위치: {source.location}\n"
            result += f"   - 마지막 동기화: {source.last_synced_at.strftime('%Y-%m-%d %H:%M') if source.last_synced_at else '없음'}\n"
            result += f"   - ID: {source.id}\n\n"

        return result

    except Exception as e:
        return f"❌ 소스 조회 실패: {str(e)}"
    finally:
        db.close()


@tool
def delete_source_from_db(source_id: int, user_id: str) -> str:
    """
    등록된 소스를 삭제합니다.

    Args:
        source_id: 삭제할 소스의 ID
        user_id: 사용자 ID (권한 확인용)

    Returns:
        삭제 결과 메시지
    """
    from storage.models import Source
    from storage.database import SessionLocal

    db = SessionLocal()
    try:
        # 소스 조회 (권한 확인 포함)
        source = db.query(Source).filter(
            Source.id == source_id,
            Source.user_id == user_id
        ).first()

        if not source:
            return f"❌ 소스를 찾을 수 없거나 삭제 권한이 없습니다. (ID: {source_id})"

        source_name = source.name
        source_location = source.location

        # 소스 삭제
        db.delete(source)
        db.commit()

        return f"✅ 소스 삭제 완료!\n이름: {source_name}\n위치: {source_location}"

    except Exception as e:
        db.rollback()
        return f"❌ 소스 삭제 실패: {str(e)}"
    finally:
        db.close()


if __name__ == "__main__":
    result = embedding_file.invoke({"path": "../Yuta_TIL"})
    result = embedding_file.invoke({"path": "/Users/hrun/Downloads/data-5e445e3f-837e-4504-83a7-4d9923c64d11-1783416356-0e00b9b2-batch-0000.zip"})
    print(f"documents result: {result}")