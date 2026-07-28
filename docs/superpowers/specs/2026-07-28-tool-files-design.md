# Source & Embedding Tools 설계 문서

**작성일:** 2026-07-28
**프로젝트:** yuta_logagent
**목적:** 소스 관리 및 임베딩 도구 구현

---

## 1. 전체 아키텍처 및 데이터 흐름

### 시스템 구성

```
사용자 요청 (FastAPI)
    ↓
Controller (LangGraph Agent)
    ↓
LangChain Tools (source.py, embedding.py)
    ↓
├─→ SQLite DB (Source 메타데이터)
├─→ File System (./data/sources/{user_id}/{source_name}/)
└─→ ChromaDB (벡터 임베딩, Collection: user_{user_id})
```

### 주요 데이터 흐름

#### 소스 추가 플로우

```
add_source_to_db 호출
  ↓
1. 입력 검증 (URL, 경로 등)
  ↓
2. DB에 Source 레코드 생성 (status=PENDING)
  ↓
3. 사용자에게 즉시 응답 반환
  ↓
[별도로 embed_source 호출 필요]
4. 소스 타입별 파일 수집
5. 증분 업데이트 확인 (해시 비교)
6. 새 파일만 임베딩
7. ChromaDB에 저장
8. Source.status → COMPLETED
9. Source.last_synced_at 갱신
```

#### 임베딩 실행 플로우

```
embed_source 호출
  ↓
1. Source 조회 (DB)
  ↓
2. status → IN_PROGRESS
  ↓
3. 소스 타입 확인
  ↓
4. [git] Clone → 파일 수집
   [git_log] Git log 파싱 → 커밋 리스트
   [local] 디렉토리 스캔
   [agent_chatlog] 대화 로그 파일 읽기
   [memsearch] 메모리 검색 데이터 로드
  ↓
5. 기존 임베딩 확인 (metadata의 file_hash)
  ↓
6. 새 파일/변경된 파일만 청크 분할 (2000/400)
  ↓
7. 임베딩 생성 (google_embedding)
  ↓
8. ChromaDB에 저장 (metadata 포함)
  ↓
9. 통계 수집 (처리 파일, 청크, 시간 등)
  ↓
10. status → COMPLETED, 통계 반환
```

### ChromaDB 메타데이터 구조

#### Git 파일의 경우

```python
{
    "user_id": "hrun",
    "source_id": 123,
    "source_type": "git",
    "source_name": "Yuta_TIL",
    "file_path": "2024/07/daily.md",
    "file_hash": "a3f5b2c...",  # SHA256
    "chunk_index": 0,  # 같은 파일의 몇 번째 청크인지
    "embedded_at": "2026-07-28T12:34:56"
}
```

#### Git log의 경우

```python
{
    "user_id": "hrun",
    "source_id": 456,
    "source_type": "git_log",
    "source_name": "project_commits",
    "commit_sha": "e91d9a4",  # 해시 역할
    "author": "hrun",
    "date": "2026-07-28",
    "message": "gitignore com",
    "embedded_at": "2026-07-28T12:34:56"
}
```

---

## 2. 데이터베이스 스키마 변경

### Source 모델 업데이트

`src/storage/models.py` 수정:

```python
class SourceType(str, enum.Enum):
    GIT = "git"
    GIT_LOG = "git_log"  # 추가
    LOCAL = "local"
    AGENT_CHATLOG = "agent_chatlog"
    MEMSEARCH = "memsearch"

class EmbeddingStatus(str, enum.Enum):
    """임베딩 진행 상태"""
    PENDING = "pending"          # 소스 등록됨, 임베딩 대기 중
    IN_PROGRESS = "in_progress"  # 임베딩 진행 중
    COMPLETED = "completed"      # 임베딩 완료
    FAILED = "failed"            # 임베딩 실패

class Source(Base):
    __tablename__ = "sources"

    # 기존 필드
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    location: Mapped[str] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)

    # 새로 추가되는 필드
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus),
        default=EmbeddingStatus.PENDING
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_stats: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 문자열

    __table_args__ = (UniqueConstraint("user_id", "type", "location"),)
```

### 필드 설명

- **embedding_status**: 임베딩 진행 상태 추적 (PENDING → IN_PROGRESS → COMPLETED/FAILED)
- **embedding_error**: 임베딩 실패 시 에러 메시지 저장
- **embedding_stats**: 임베딩 완료 시 통계 정보 (JSON 형식)
  - 예: `{"files_processed": 45, "chunks_created": 230, "duration_seconds": 23}`

---

## 3. 파일 구조

```
src/tools/
├── __init__.py
├── source.py          # 소스 관리 LangChain Tools
└── embedding.py       # 임베딩 LangChain Tools
```

---

## 4. source.py 상세 설계

### LangChain Tools (4개)

#### 1. add_source_to_db

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
        name: 소스 이름 (예: "Yuta_TIL")
        source_type: 소스 타입 (git, git_log, local, agent_chatlog, memsearch)
        location: 소스 위치 (Git URL, 로컬 경로 등)

    Returns:
        성공/실패 메시지
    """
```

**기능:**
1. 입력 검증 (location 비어있는지, source_type 유효한지)
2. Git URL 패턴 검증 (git, git_log 타입인 경우)
3. DB 중복 확인
4. Source 레코드 생성 (status=PENDING)
5. 상세 성공 메시지 반환 (임베딩 시작 안내 포함)

**에러 처리:**
- 예상 가능한 에러 (빈 location, 잘못된 URL, 중복 소스): 에러 메시지 반환
- 시스템 에러 (DB 연결 실패 등): RuntimeError raise

#### 2. get_user_sources

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
```

**기능:**
1. user_id로 소스 목록 조회 (is_active=True만)
2. 각 소스의 상태를 이모지로 표시 (⏳ PENDING, 🔄 IN_PROGRESS, ✅ COMPLETED, ❌ FAILED)
3. 소스 정보 포맷팅:
   - ID, 이름, 타입, 위치
   - 임베딩 상태
   - 마지막 동기화 시간
   - 실패 시 에러 메시지

#### 3. delete_source_from_db

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
```

**기능:**
1. Source 조회 및 권한 확인 (user_id 일치)
2. ChromaDB에서 해당 소스의 모든 임베딩 삭제
3. DB에서 Source 레코드 삭제
4. 삭제된 임베딩 개수 포함한 결과 반환

#### 4. request_source_type_clarification

```python
@tool
def request_source_type_clarification() -> str:
    """
    사용자에게 소스 타입을 명확히 요청합니다.
    SourceType 판단이 애매할 때 호출합니다.

    Returns:
        소스 타입 선택 안내 메시지
    """
```

**기능:**
- 5가지 소스 타입 설명 및 예시 제공
- Agent가 소스 타입 판단이 어려울 때 사용

---

## 5. embedding.py 상세 설계

### 설정 상수

```python
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 400
DATA_DIR = Path("./data/sources")
CHROMA_DIR = Path("./chroma_db")
```

### LangChain Tools (2개)

#### 1. embed_source

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
```

**기능:**
1. Source 조회 및 검증
2. 진행 중 상태 확인 (중복 실행 방지)
3. status → IN_PROGRESS 업데이트
4. 소스 타입별 처리 함수 호출
5. 성공 시:
   - status → COMPLETED
   - last_synced_at 갱신
   - embedding_stats 저장
   - 상세 통계 반환
6. 실패 시:
   - status → FAILED
   - embedding_error 저장
   - 에러 메시지 반환

**반환 형식:**
```
✅ 임베딩 완료: Yuta_TIL
- 처리된 파일: 45개
- 생성된 청크: 230개
- 소요 시간: 23초
- 새로 추가: 12개
- 스킵: 33개
```

#### 2. get_embedding_status

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
```

**기능:**
1. Source 조회
2. 상태 이모지 + 정보 포맷팅
3. 통계 정보 파싱 및 표시
4. 실패 시 에러 메시지 표시

### 핵심 헬퍼 함수

#### _process_source_by_type

- 소스 타입에 따라 적절한 수집 함수 호출
- 타이밍 측정 및 통계 수집
- 증분 업데이트 처리

#### _collect_git_files

**기능:**
1. Git clone 또는 pull
2. 텍스트 파일만 수집 (.txt, .md, .py, .js, .tsx, .jsx, .java, .go, .rs, .c, .cpp, .h)
3. 각 파일의 SHA256 해시 계산
4. Document 객체 생성 (content + metadata)

**저장 위치:** `./data/sources/{user_id}/{source_name}/`

#### _collect_git_log

**기능:**
1. Git clone (로그 조회용)
2. `git log --pretty=format:"%H|%an|%ad|%s" --date=iso` 실행
3. 각 커밋을 Document로 변환
   - content: "Commit: {message}\nAuthor: {author}\nDate: {date}"
   - metadata: commit_sha, author, date, message

#### _collect_local_files

**기능:**
1. 로컬 경로 검증 (존재 여부)
2. 텍스트 파일 재귀 탐색
3. 파일 해시 계산 및 Document 생성

#### _collect_chatlog / _collect_memsearch

- 추후 구현 (현재는 빈 리스트 반환)

#### _filter_new_documents

**증분 업데이트 핵심 로직:**

1. ChromaDB에서 해당 소스의 기존 임베딩 조회
2. 기존 file_hash/commit_sha 목록 추출
3. 새 문서 중 해시가 기존에 없는 것만 필터링
4. (새 문서 리스트, 스킵된 개수) 반환

#### _split_documents

**기능:**
1. RecursiveCharacterTextSplitter 사용
2. chunk_size=2000, chunk_overlap=400
3. 각 청크에 chunk_index 메타데이터 추가

#### _save_to_chromadb

**기능:**
1. Collection 이름: `user_{user_id}`
2. Chroma.from_documents 사용
3. google_embedding 함수로 임베딩 생성
4. persist_directory: `./chroma_db`

#### _delete_source_embeddings

**기능:**
1. ChromaDB Collection에서 source_id로 필터링
2. 해당하는 모든 임베딩 ID 조회
3. collection.delete(ids=...) 호출
4. 삭제된 개수 반환

---

## 6. 에러 처리 전략

### 원칙

- **예상 가능한 실패**: `return "❌ 에러 메시지"`
  - 잘못된 URL
  - 파일 없음
  - 중복 소스
  - Git clone 실패
- **시스템 오류**: `raise Exception`
  - DB 연결 실패
  - 메모리 부족
  - ChromaDB 오류

### 예시

```python
# 예상 가능한 실패
if not is_valid_git_url(location):
    return "❌ 오류: 올바른 Git URL이 아닙니다."

# 시스템 오류
try:
    db.add(source)
    db.commit()
except Exception as e:
    db.rollback()
    raise RuntimeError(f"소스 추가 중 시스템 오류: {str(e)}")
```

---

## 7. 비동기 처리

### 2단계 접근 방식

LangChain Tools는 Agent가 호출하므로 FastAPI BackgroundTasks를 직접 전달할 수 없습니다.
대신 2단계로 처리합니다:

**1단계: 소스 등록**
```python
# Agent가 호출
result = add_source_to_db(user_id, name, source_type, location)
# → Source 레코드 생성 (status=PENDING)
# → 즉시 반환
```

**2단계: 임베딩 실행**
```python
# Agent가 별도로 호출 (또는 FastAPI 엔드포인트에서 호출)
result = embed_source(user_id, source_id)
# → 임베딩 진행 (동기 실행)
# → 완료 후 반환
```

### 선택적 백그라운드 처리 (향후 개선)

필요 시 FastAPI 엔드포인트에서 embed_source를 백그라운드로 실행:

```python
from fastapi import BackgroundTasks

@app.post("/sources/{source_id}/embed")
async def start_embedding(
    source_id: int,
    user_id: str,
    background_tasks: BackgroundTasks
):
    # 백그라운드에서 임베딩 실행
    background_tasks.add_task(embed_source, user_id, source_id)
    return {"message": "임베딩이 백그라운드에서 시작되었습니다."}
```

**동작 방식:**
1. Agent가 add_source_to_db 호출 → 소스 등록
2. Agent가 embed_source 호출 → 임베딩 시작 (동기 또는 비동기)
3. 사용자는 get_embedding_status로 진행 상황 확인

---

## 8. 테스트 전략

### 단위 테스트

**source.py:**
- add_source_to_db: 유효한 입력, 잘못된 URL, 중복 소스
- get_user_sources: 빈 리스트, 여러 소스, 상태별 필터링
- delete_source_from_db: 성공, 존재하지 않는 소스, 권한 없음

**embedding.py:**
- _collect_git_files: clone 성공, pull 성공, 실패
- _collect_git_log: 로그 파싱 정확도
- _filter_new_documents: 증분 업데이트 로직
- _split_documents: 청크 분할 정확도

### 통합 테스트

1. 소스 추가 → 임베딩 → 검색
2. 소스 삭제 → ChromaDB 정리 확인
3. 증분 업데이트 시나리오 (파일 수정 후 재임베딩)

---

## 9. 구현 순서

1. **models.py 수정** (SourceType, EmbeddingStatus 추가)
2. **source.py 구현**
   - add_source_to_db
   - get_user_sources
   - delete_source_from_db
   - request_source_type_clarification
3. **embedding.py 구현**
   - 헬퍼 함수들 (_collect_git_files, _collect_git_log, _collect_local_files)
   - _filter_new_documents
   - _split_documents
   - _save_to_chromadb
   - embed_source
   - get_embedding_status
4. **controller.py 통합**
   - tools 리스트에 새 도구 추가
5. **테스트 작성 및 실행**
6. **문서화**

---

## 10. 향후 개선 사항

1. **agent_chatlog, memsearch 구현**
2. **진행률 추적** (웹소켓 또는 SSE)
3. **파일 타입 확장** (.pdf, .docx 등)
4. **재시도 로직** (임베딩 실패 시 자동 재시도)
5. **배치 임베딩** (여러 소스 동시 처리)
6. **임베딩 업데이트 스케줄링** (cron job)

---

## 부록: 의존성

- `langchain-chroma`: ChromaDB 통합
- `langchain-text-splitters`: 텍스트 청크 분할
- `chromadb`: 벡터 데이터베이스
- `sqlalchemy`: DB ORM
- `fastapi`: 백그라운드 태스크
- `google_embedding` (llm_router.py에서 import)
