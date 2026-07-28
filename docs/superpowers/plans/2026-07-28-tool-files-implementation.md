# Source & Embedding Tools 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 소스 관리 및 임베딩 LangChain Tools 구현 (source.py, embedding.py)

**Architecture:** SQLite에 소스 메타데이터 저장, 파일시스템에 Git clone, ChromaDB에 벡터 임베딩 저장. 증분 업데이트로 중복 임베딩 방지.

**Tech Stack:** LangChain, ChromaDB, SQLAlchemy, Gemini Embedding

---

## 파일 구조

### 생성할 파일
- `src/tools/__init__.py` (비어있음)
- `src/tools/source.py` (4개 LangChain Tools)
- `src/tools/embedding.py` (2개 Tools + 헬퍼 함수들)

### 수정할 파일
- `src/storage/models.py:10-33` (SourceType, EmbeddingStatus, Source 모델)
- `src/controller.py:10,19,135-140` (tools import 및 등록)

---

## Task 1: 데이터베이스 스키마 업데이트

**Files:**
- Modify: `src/storage/models.py:10-33`

- [ ] **Step 1: EmbeddingStatus Enum 추가**

`src/storage/models.py` 파일에서 `SourceType` Enum 아래에 추가:

```python
class EmbeddingStatus(str, enum.Enum):
    """임베딩 진행 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
```

- [ ] **Step 2: SourceType에 GIT_LOG 추가**

`SourceType` Enum 수정:

```python
class SourceType(str, enum.Enum):
    GIT = "git"
    GIT_LOG = "git_log"  # 추가
    LOCAL = "local"
    AGENT_CHATLOG = "agent_chatlog"
    MEMSEARCH = "memsearch"
```

- [ ] **Step 3: Source 모델에 필드 추가**

`Source` 클래스의 `is_active` 필드 아래에 추가:

```python
    # 새로 추가되는 필드
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus),
        default=EmbeddingStatus.PENDING
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_stats: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: DB 재초기화 확인**

Run: `rm users.db && python -c "from src.storage.database import init_db; init_db()"`
Expected: "db준비완료" 출력

- [ ] **Step 5: Commit**

```bash
git add src/storage/models.py
git commit -m "feat: add EmbeddingStatus and Source model fields"
```

---

## Task 2: source.py - 기본 구조 및 add_source_to_db

**Files:**
- Create: `src/tools/__init__.py`
- Create: `src/tools/source.py`

- [ ] **Step 1: __init__.py 생성**

빈 파일 생성:

```python
# src/tools/__init__.py
```

- [ ] **Step 2: source.py import 및 상수 정의**

```python
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
import re
from datetime import datetime
```

- [ ] **Step 3: add_source_to_db 구현 - 입력 검증**

```python
@tool
def add_source_to_db(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    소스를 데이터베이스에 추가합니다.

    주의: 이 함수는 소스를 등록만 하고 임베딩은 시작하지 않습니다.
    임베딩을 시작하려면 embed_source를 별도로 호출해야 합니다.

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: 소스 타입 (git, git_log, local, agent_chatlog, memsearch)
        location: 소스 위치 (Git URL, 로컬 경로 등)

    Returns:
        성공/실패 메시지
    """
    # 입력 검증
    if not location.strip():
        return "❌ 오류: 소스 위치가 비어있습니다."

    try:
        source_type_enum = SourceType(source_type.lower())
    except ValueError:
        return f"❌ 오류: 지원하지 않는 소스 타입입니다. (지원: git, git_log, local, agent_chatlog, memsearch)"

    # Git URL 검증
    if source_type_enum in [SourceType.GIT, SourceType.GIT_LOG]:
        git_pattern = r'(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+(?:\.git)?|.*\.git)'
        if not re.match(git_pattern, location, re.IGNORECASE):
            return f"❌ 오류: 올바른 Git URL이 아닙니다. 예: https://github.com/user/repo.git"

    # DB 저장
    db = SessionLocal()
    try:
        # 중복 확인
        existing = db.query(Source).filter_by(
            user_id=user_id,
            type=source_type_enum,
            location=location
        ).first()

        if existing:
            return f"❌ 이미 등록된 소스입니다: {existing.name} (ID: {existing.id})"

        # 새 소스 생성
        source = Source(
            user_id=user_id,
            name=name,
            type=source_type_enum,
            location=location,
            embedding_status=EmbeddingStatus.PENDING
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        return f"""✅ 소스가 추가되었습니다.
- 이름: {name}
- 타입: {source_type}
- 위치: {location}
- ID: {source.id}
- 상태: 임베딩 대기 중 (embed_source를 호출하여 시작하세요)"""

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"소스 추가 중 시스템 오류: {str(e)}")
    finally:
        db.close()
```

- [ ] **Step 4: 수동 테스트**

Python REPL에서 테스트:
```python
from src.tools.source import add_source_to_db
result = add_source_to_db("test_user", "test_repo", "git", "https://github.com/test/repo.git")
print(result)
```
Expected: "✅ 소스가 추가되었습니다..." 메시지

- [ ] **Step 5: Commit**

```bash
git add src/tools/__init__.py src/tools/source.py
git commit -m "feat: implement add_source_to_db tool"
```

---

## Task 3: source.py - get_user_sources

**Files:**
- Modify: `src/tools/source.py`

- [ ] **Step 1: get_user_sources 구현**

`add_source_to_db` 함수 아래에 추가:

```python
@tool
def get_user_sources(user_id: str) -> str:
    """
    사용자의 모든 소스 목록을 조회합니다.

    Args:
        user_id: 사용자 ID

    Returns:
        소스 목록 (포맷팅된 문자열)
    """
    db = SessionLocal()
    try:
        sources = db.query(Source).filter_by(user_id=user_id, is_active=True).all()

        if not sources:
            return "📭 등록된 소스가 없습니다."

        result = f"📚 총 {len(sources)}개의 소스가 등록되어 있습니다:\n\n"

        for src in sources:
            status_emoji = {
                EmbeddingStatus.PENDING: "⏳",
                EmbeddingStatus.IN_PROGRESS: "🔄",
                EmbeddingStatus.COMPLETED: "✅",
                EmbeddingStatus.FAILED: "❌"
            }.get(src.embedding_status, "❓")

            result += f"{status_emoji} [{src.id}] {src.name}\n"
            result += f"   타입: {src.type.value}\n"
            result += f"   위치: {src.location}\n"
            result += f"   상태: {src.embedding_status.value}\n"

            if src.last_synced_at:
                result += f"   마지막 동기화: {src.last_synced_at.strftime('%Y-%m-%d %H:%M')}\n"

            if src.embedding_status == EmbeddingStatus.FAILED and src.embedding_error:
                result += f"   ⚠️ 오류: {src.embedding_error}\n"

            result += "\n"

        return result.strip()

    finally:
        db.close()
```

- [ ] **Step 2: 수동 테스트**

```python
from src.tools.source import get_user_sources
result = get_user_sources("test_user")
print(result)
```
Expected: 소스 목록 출력 (이전에 추가한 test_repo 표시)

- [ ] **Step 3: Commit**

```bash
git add src/tools/source.py
git commit -m "feat: implement get_user_sources tool"
```

---

## Task 4: source.py - delete_source_from_db 및 request_source_type_clarification

**Files:**
- Modify: `src/tools/source.py`

- [ ] **Step 1: delete_source_from_db 구현 (ChromaDB 부분 스텁)**

```python
@tool
def delete_source_from_db(source_id: int, user_id: str) -> str:
    """
    소스를 삭제합니다 (DB + ChromaDB 임베딩).

    Args:
        source_id: 소스 ID
        user_id: 사용자 ID (권한 확인용)

    Returns:
        성공/실패 메시지
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        source_name = source.name

        # ChromaDB에서 해당 소스의 임베딩 삭제 (embedding.py 완성 후 구현)
        deleted_count = 0  # TODO: _delete_source_embeddings 호출

        # DB에서 삭제
        db.delete(source)
        db.commit()

        return f"""✅ 소스가 삭제되었습니다.
- 이름: {source_name}
- ID: {source_id}
- 삭제된 임베딩: {deleted_count}개"""

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"소스 삭제 중 시스템 오류: {str(e)}")
    finally:
        db.close()
```

- [ ] **Step 2: request_source_type_clarification 구현**

```python
@tool
def request_source_type_clarification() -> str:
    """
    사용자에게 소스 타입을 명확히 요청합니다.
    SourceType 판단이 애매할 때 호출합니다.

    Returns:
        소스 타입 선택 안내 메시지
    """
    return """🤔 소스 타입을 명확히 지정해주세요:

1️⃣ **git** - Git 저장소를 clone하고 파일을 임베딩
   예: https://github.com/user/repo.git

2️⃣ **git_log** - Git 커밋 히스토리를 임베딩
   예: https://github.com/user/repo.git (커밋 로그만)

3️⃣ **local** - 서버의 로컬 디렉토리 사용
   예: /path/to/local/directory

4️⃣ **agent_chatlog** - 에이전트 대화 로그 파일
   예: /logs/chat_history.json

5️⃣ **memsearch** - 기존 메모리 검색 데이터 연결
   예: /data/memsearch/index

소스를 추가할 때 타입을 함께 지정해주세요."""
```

- [ ] **Step 3: 수동 테스트**

```python
from src.tools.source import request_source_type_clarification
print(request_source_type_clarification())
```
Expected: 소스 타입 안내 메시지 출력

- [ ] **Step 4: Commit**

```bash
git add src/tools/source.py
git commit -m "feat: implement delete_source and clarification tools"
```

---

## Task 5: embedding.py - 기본 구조 및 상수

**Files:**
- Create: `src/tools/embedding.py`

- [ ] **Step 1: import 및 상수 정의**

```python
from langchain_core.tools import tool
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from sqlalchemy.orm import Session
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
from ..llm_router import google_embedding
import os
import hashlib
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time

# 설정
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 400
DATA_DIR = Path("./data/sources")
CHROMA_DIR = Path("./chroma_db")
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: add embedding.py structure and constants"
```

---

## Task 6: embedding.py - ChromaDB 헬퍼 함수

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: _get_chroma_collection 구현**

```python
def _get_chroma_collection(user_id: str):
    """사용자별 ChromaDB Collection 가져오기"""
    collection_name = f"user_{user_id}"

    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=google_embedding,
        persist_directory=str(CHROMA_DIR)
    )

    return vectorstore._collection
```

- [ ] **Step 2: _save_to_chromadb 구현**

```python
def _save_to_chromadb(chunks: list[Document], user_id: str):
    """청크를 ChromaDB에 저장"""
    if not chunks:
        return

    collection_name = f"user_{user_id}"

    Chroma.from_documents(
        documents=chunks,
        embedding=google_embedding,
        collection_name=collection_name,
        persist_directory=str(CHROMA_DIR)
    )
```

- [ ] **Step 3: _delete_source_embeddings 구현**

```python
def _delete_source_embeddings(user_id: str, source_id: int) -> int:
    """특정 소스의 모든 임베딩 삭제"""
    try:
        collection = _get_chroma_collection(user_id)

        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )

        ids_to_delete = results.get("ids", [])

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)

        return len(ids_to_delete)
    except Exception as e:
        print(f"ChromaDB 삭제 중 오류: {e}")
        return 0
```

- [ ] **Step 4: source.py의 delete_source_from_db 업데이트**

`src/tools/source.py`의 `delete_source_from_db` 함수에서:

```python
# 변경 전:
deleted_count = 0  # TODO: _delete_source_embeddings 호출

# 변경 후:
from .embedding import _delete_source_embeddings
deleted_count = _delete_source_embeddings(user_id, source_id)
```

- [ ] **Step 5: Commit**

```bash
git add src/tools/embedding.py src/tools/source.py
git commit -m "feat: implement ChromaDB helper functions"
```

---

## Task 7: embedding.py - 문서 처리 헬퍼 함수

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: _split_documents 구현**

```python
def _split_documents(documents: list[Document]) -> list[Document]:
    """문서를 청크로 분할"""
    if not documents:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = []
    for doc in documents:
        doc_chunks = splitter.split_documents([doc])

        # 청크 인덱스 추가
        for idx, chunk in enumerate(doc_chunks):
            chunk.metadata["chunk_index"] = idx
            chunks.append(chunk)

    return chunks
```

- [ ] **Step 2: _filter_new_documents 구현**

```python
def _filter_new_documents(documents: list[Document], user_id: str, source_id: int) -> tuple[list[Document], int]:
    """기존 임베딩과 비교하여 새 문서만 반환"""
    try:
        collection = _get_chroma_collection(user_id)

        # 기존 해시 목록 가져오기
        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )
        existing_hashes = set()
        for metadata in results.get("metadatas", []):
            if "file_hash" in metadata:
                existing_hashes.add(metadata["file_hash"])
            elif "commit_sha" in metadata:
                existing_hashes.add(metadata["commit_sha"])
    except Exception as e:
        print(f"기존 임베딩 조회 중 오류 (새 Collection 생성): {e}")
        existing_hashes = set()

    # 새 문서 필터링
    new_docs = []
    skipped = 0

    for doc in documents:
        doc_hash = doc.metadata.get("file_hash") or doc.metadata.get("commit_sha")
        if doc_hash not in existing_hashes:
            new_docs.append(doc)
        else:
            skipped += 1

    return new_docs, skipped
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement document processing helpers"
```

---

## Task 8: embedding.py - Git 파일 수집

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: _collect_git_files 구현**

```python
def _collect_git_files(source: Source, user_id: str) -> list[Document]:
    """Git 저장소를 clone하고 텍스트 파일 수집"""
    repo_dir = DATA_DIR / user_id / source.name

    # Clone 또는 Pull
    if repo_dir.exists():
        # Git pull
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "pull"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git pull 실패: {result.stderr}")
    else:
        # Git clone
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", source.location, str(repo_dir)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git clone 실패: {result.stderr}")

    # 텍스트 파일 수집
    documents = []

    for file_path in repo_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in TEXT_EXTENSIONS:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 파일 해시 계산
                file_hash = hashlib.sha256(content.encode()).hexdigest()

                # 상대 경로
                rel_path = file_path.relative_to(repo_dir)

                doc = Document(
                    page_content=content,
                    metadata={
                        "user_id": user_id,
                        "source_id": source.id,
                        "source_type": source.type.value,
                        "source_name": source.name,
                        "file_path": str(rel_path),
                        "file_hash": file_hash,
                        "embedded_at": datetime.now().isoformat()
                    }
                )
                documents.append(doc)

            except Exception as e:
                print(f"파일 읽기 실패 {file_path}: {e}")
                continue

    return documents
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement Git file collection"
```

---

## Task 9: embedding.py - Git log 및 로컬 파일 수집

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: _collect_git_log 구현**

```python
def _collect_git_log(source: Source, user_id: str) -> list[Document]:
    """Git 커밋 히스토리 수집 (message + author + date)"""
    repo_dir = DATA_DIR / user_id / source.name

    # Clone (로그 조회용)
    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", source.location, str(repo_dir)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git clone 실패: {result.stderr}")

    # Git log 가져오기
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--pretty=format:%H|%an|%ad|%s", "--date=iso"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Git log 실패: {result.stderr}")

    documents = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("|", 3)
        if len(parts) != 4:
            continue

        sha, author, date, message = parts

        content = f"Commit: {message}\nAuthor: {author}\nDate: {date}"

        doc = Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": source.id,
                "source_type": "git_log",
                "source_name": source.name,
                "commit_sha": sha,
                "author": author,
                "date": date,
                "message": message,
                "embedded_at": datetime.now().isoformat()
            }
        )
        documents.append(doc)

    return documents
```

- [ ] **Step 2: _collect_local_files 구현**

```python
def _collect_local_files(source: Source, user_id: str) -> list[Document]:
    """로컬 디렉토리의 텍스트 파일 수집"""
    local_path = Path(source.location)

    if not local_path.exists():
        raise FileNotFoundError(f"로컬 경로가 존재하지 않습니다: {source.location}")

    documents = []

    for file_path in local_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in TEXT_EXTENSIONS:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                file_hash = hashlib.sha256(content.encode()).hexdigest()
                rel_path = file_path.relative_to(local_path)

                doc = Document(
                    page_content=content,
                    metadata={
                        "user_id": user_id,
                        "source_id": source.id,
                        "source_type": "local",
                        "source_name": source.name,
                        "file_path": str(rel_path),
                        "file_hash": file_hash,
                        "embedded_at": datetime.now().isoformat()
                    }
                )
                documents.append(doc)
            except Exception as e:
                print(f"파일 읽기 실패 {file_path}: {e}")
                continue

    return documents
```

- [ ] **Step 3: _collect_chatlog 및 _collect_memsearch 스텁**

```python
def _collect_chatlog(source: Source, user_id: str) -> list[Document]:
    """에이전트 대화 로그 수집 (추후 구현)"""
    return []

def _collect_memsearch(source: Source, user_id: str) -> list[Document]:
    """Memsearch 데이터 수집 (추후 구현)"""
    return []
```

- [ ] **Step 4: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement git_log and local file collection"
```

---

## Task 10: embedding.py - 소스 타입별 처리 오케스트레이션

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: _process_source_by_type 구현**

```python
def _process_source_by_type(source: Source, user_id: str) -> dict:
    """소스 타입에 따라 적절한 처리 함수 호출"""
    start_time = time.time()

    # 소스 타입별 파일 수집
    if source.type == SourceType.GIT:
        documents = _collect_git_files(source, user_id)
    elif source.type == SourceType.GIT_LOG:
        documents = _collect_git_log(source, user_id)
    elif source.type == SourceType.LOCAL:
        documents = _collect_local_files(source, user_id)
    elif source.type == SourceType.AGENT_CHATLOG:
        documents = _collect_chatlog(source, user_id)
    elif source.type == SourceType.MEMSEARCH:
        documents = _collect_memsearch(source, user_id)
    else:
        raise ValueError(f"지원하지 않는 소스 타입: {source.type}")

    # 증분 업데이트 (기존 임베딩 확인)
    new_docs, skipped_count = _filter_new_documents(documents, user_id, source.id)

    # 청크 분할
    chunks = _split_documents(new_docs)

    # ChromaDB에 저장
    if chunks:
        _save_to_chromadb(chunks, user_id)

    duration = time.time() - start_time

    return {
        "stats": {
            "files_processed": len(documents),
            "chunks_created": len(chunks),
            "new_chunks": len(chunks),
            "skipped_chunks": skipped_count,
            "duration_seconds": round(duration, 2)
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement source type processing orchestration"
```

---

## Task 11: embedding.py - embed_source Tool

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: embed_source 구현**

```python
@tool
def embed_source(user_id: str, source_id: int) -> str:
    """
    소스의 모든 파일을 임베딩합니다 (증분 업데이트).

    Args:
        user_id: 사용자 ID
        source_id: 소스 ID

    Returns:
        임베딩 결과 (상세 통계)
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        if source.embedding_status == EmbeddingStatus.IN_PROGRESS:
            return f"⏳ 소스 '{source.name}'는 이미 임베딩 진행 중입니다."

        # 상태 업데이트
        source.embedding_status = EmbeddingStatus.IN_PROGRESS
        source.embedding_error = None
        db.commit()

        try:
            # 소스 타입별 처리
            result = _process_source_by_type(source, user_id)

            # 성공 처리
            source.embedding_status = EmbeddingStatus.COMPLETED
            source.last_synced_at = datetime.now()
            source.embedding_stats = json.dumps(result["stats"])
            source.embedding_error = None
            db.commit()

            return f"""✅ 임베딩 완료: {source.name}
- 처리된 파일: {result['stats']['files_processed']}개
- 생성된 청크: {result['stats']['chunks_created']}개
- 소요 시간: {result['stats']['duration_seconds']}초
- 새로 추가: {result['stats']['new_chunks']}개
- 스킵: {result['stats']['skipped_chunks']}개"""

        except Exception as e:
            # 실패 처리
            source.embedding_status = EmbeddingStatus.FAILED
            source.embedding_error = str(e)
            db.commit()

            return f"❌ 임베딩 실패: {source.name}\n오류: {str(e)}"

    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement embed_source tool"
```

---

## Task 12: embedding.py - get_embedding_status Tool

**Files:**
- Modify: `src/tools/embedding.py`

- [ ] **Step 1: get_embedding_status 구현**

```python
@tool
def get_embedding_status(user_id: str, source_id: int) -> str:
    """
    소스의 임베딩 상태를 조회합니다.

    Args:
        user_id: 사용자 ID
        source_id: 소스 ID

    Returns:
        임베딩 상태 정보
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        status_emoji = {
            EmbeddingStatus.PENDING: "⏳",
            EmbeddingStatus.IN_PROGRESS: "🔄",
            EmbeddingStatus.COMPLETED: "✅",
            EmbeddingStatus.FAILED: "❌"
        }.get(source.embedding_status, "❓")

        result = f"{status_emoji} 소스: {source.name}\n"
        result += f"상태: {source.embedding_status.value}\n"

        if source.last_synced_at:
            result += f"마지막 동기화: {source.last_synced_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if source.embedding_stats:
            stats = json.loads(source.embedding_stats)
            result += f"\n통계:\n"
            result += f"- 처리된 파일: {stats.get('files_processed', 0)}개\n"
            result += f"- 생성된 청크: {stats.get('chunks_created', 0)}개\n"

        if source.embedding_status == EmbeddingStatus.FAILED and source.embedding_error:
            result += f"\n⚠️ 오류: {source.embedding_error}"

        return result

    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/embedding.py
git commit -m "feat: implement get_embedding_status tool"
```

---

## Task 13: controller.py 통합

**Files:**
- Modify: `src/controller.py:10,19,135-140`

- [ ] **Step 1: source tools import 추가**

`src/controller.py` 파일 상단의 import 섹션에 추가:

```python
from . import tools as tool
from .tools import source as source_tools  # 추가
from .tools import embedding as embedding_tools  # 추가
```

- [ ] **Step 2: source_tools 리스트에 도구 추가**

기존 `source_tools` 리스트(135-140줄) 수정:

```python
# 소스 관리 도구
source_tools = [
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    source_tools.request_source_type_clarification,
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status
]
```

- [ ] **Step 3: Commit**

```bash
git add src/controller.py
git commit -m "feat: integrate source and embedding tools in controller"
```

---

## Task 14: 통합 테스트

**Files:**
- Test: manual testing via Python REPL

- [ ] **Step 1: FastAPI 서버 시작**

Run: `uvicorn main:app --reload`
Expected: 서버 정상 시작

- [ ] **Step 2: 소스 추가 테스트**

브라우저에서 `http://localhost:8000` 접속 후 로그인, 채팅창에 입력:

```
https://github.com/hrunj1230/Yuta_TIL.git
```

Expected: Agent가 add_source_to_db 호출, "✅ 소스가 추가되었습니다..." 응답

- [ ] **Step 3: 소스 목록 조회 테스트**

채팅창에 입력:
```
내 소스 목록 보여줘
```

Expected: get_user_sources 호출, 등록된 소스 목록 표시

- [ ] **Step 4: 임베딩 실행 테스트**

채팅창에 입력:
```
1번 소스 임베딩해줘
```

Expected: embed_source 호출, "✅ 임베딩 완료..." 메시지 (처리 시간 약 10-30초)

- [ ] **Step 5: 임베딩 상태 확인**

채팅창에 입력:
```
1번 소스 상태 알려줘
```

Expected: get_embedding_status 호출, "✅ 소스: Yuta_TIL\n상태: completed..." 표시

- [ ] **Step 6: 증분 업데이트 테스트**

채팅창에 입력:
```
1번 소스 다시 임베딩해줘
```

Expected: "스킵: N개" 표시 (이미 임베딩된 파일들)

- [ ] **Step 7: 소스 삭제 테스트**

채팅창에 입력:
```
1번 소스 삭제해줘
```

Expected: delete_source_from_db 호출, "✅ 소스가 삭제되었습니다..." 메시지

- [ ] **Step 8: ChromaDB 확인**

Run: `ls -lh chroma_db/`
Expected: `user_<user_id>` 디렉토리 존재

- [ ] **Step 9: 모든 테스트 통과 확인 및 Commit**

```bash
git add .
git commit -m "test: verify end-to-end source and embedding workflow"
```

---

## Task 15: 문서화 및 정리

**Files:**
- Create: `docs/tools-usage.md`

- [ ] **Step 1: 사용 가이드 작성**

```markdown
# Source & Embedding Tools 사용 가이드

## 개요

소스 관리 및 임베딩 도구를 통해 Git 저장소, 로컬 파일, 커밋 로그 등을 벡터DB에 임베딩할 수 있습니다.

## 도구 목록

### 소스 관리
- `add_source_to_db`: 소스 등록
- `get_user_sources`: 소스 목록 조회
- `delete_source_from_db`: 소스 삭제
- `request_source_type_clarification`: 소스 타입 안내

### 임베딩
- `embed_source`: 소스 임베딩 실행
- `get_embedding_status`: 임베딩 상태 조회

## 사용 예시

### 1. Git 저장소 임베딩
```
사용자: https://github.com/user/repo.git
Agent: add_source_to_db 호출 → 소스 등록
사용자: 1번 소스 임베딩해줘
Agent: embed_source 호출 → 파일 수집 및 임베딩
```

### 2. 증분 업데이트
- 같은 소스를 다시 임베딩하면 변경된 파일만 처리
- 파일 해시(SHA256)로 중복 감지

### 3. 지원 파일 타입
- .txt, .md, .py, .js, .tsx, .jsx, .java, .go, .rs, .c, .cpp, .h

## 내부 구조

- **DB**: SQLite (Source 메타데이터)
- **파일시스템**: `./data/sources/{user_id}/{source_name}/`
- **벡터DB**: ChromaDB (`./chroma_db/user_{user_id}/`)
```

- [ ] **Step 2: README 업데이트 (선택사항)**

프로젝트 루트 README.md에 새 기능 추가 섹션 작성

- [ ] **Step 3: Commit**

```bash
git add docs/tools-usage.md
git commit -m "docs: add tools usage guide"
```

---

## 완료 체크리스트

- [ ] Task 1: 데이터베이스 스키마 업데이트
- [ ] Task 2: source.py - add_source_to_db
- [ ] Task 3: source.py - get_user_sources
- [ ] Task 4: source.py - delete 및 clarification
- [ ] Task 5: embedding.py - 기본 구조
- [ ] Task 6: embedding.py - ChromaDB 헬퍼
- [ ] Task 7: embedding.py - 문서 처리 헬퍼
- [ ] Task 8: embedding.py - Git 파일 수집
- [ ] Task 9: embedding.py - Git log 및 로컬 수집
- [ ] Task 10: embedding.py - 타입별 처리 오케스트레이션
- [ ] Task 11: embedding.py - embed_source Tool
- [ ] Task 12: embedding.py - get_embedding_status Tool
- [ ] Task 13: controller.py 통합
- [ ] Task 14: 통합 테스트
- [ ] Task 15: 문서화
