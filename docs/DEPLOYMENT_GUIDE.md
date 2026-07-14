# 서버 배포 가이드

> **문제**: 로컬 파일 시스템 접근 → 서버 배포 시 사용자 파일 접근 불가
> **해결**: 파일 업로드 + 사용자별 ChromaDB 분리

---

## 📋 목차
1. [현재 구조의 한계](#현재-구조의-한계)
2. [방법 1: 파일 업로드 API](#방법-1-파일-업로드-api)
3. [방법 2: 클라우드 스토리지 연동](#방법-2-클라우드-스토리지-연동)
4. [방법 3: 웹훅 통합](#방법-3-웹훅-통합)
5. [사용자별 데이터 격리](#사용자별-데이터-격리)
6. [배포 시나리오](#배포-시나리오)

---

## 현재 구조의 한계

### 로컬 개발 환경 (현재)
```python
# src/tools.py
@tool
def embedding_file(path: str) -> str:
    # ❌ 서버에서는 작동 안 함
    loader = DirectoryLoader(path="../Yuta_TIL")  # 로컬 경로
```

**문제점**:
1. `../Yuta_TIL`은 당신의 PC에만 존재
2. 서버에 배포하면 다른 사용자는 자기 파일 접근 불가
3. ChromaDB가 하나라서 모든 사용자 데이터 섞임

---

## 방법 1: 파일 업로드 API

### 아키텍처

```
사용자 → 파일 업로드 → 서버 임시 저장 → 임베딩 → 사용자별 ChromaDB
```

### 1단계: 파일 업로드 엔드포인트 추가

**router.py 수정**:

```python
from fastapi import APIRouter, UploadFile, File
from typing import List
import shutil
import os

router = APIRouter()

@router.post("/upload_files")
async def upload_files(
    user_id: str,
    files: List[UploadFile] = File(...)
):
    """
    사용자 파일 업로드 및 임베딩

    Args:
        user_id: 사용자 식별자 (예: email, user_123)
        files: 업로드할 파일 리스트 (.md, .txt, .json)
    """
    # 사용자별 임시 디렉토리 생성
    user_upload_dir = f"./uploads/{user_id}"
    os.makedirs(user_upload_dir, exist_ok=True)

    # 파일 저장
    saved_files = []
    for file in files:
        file_path = f"{user_upload_dir}/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file_path)

    # 임베딩 (사용자별 컬렉션)
    from src.tools import embedding_file_for_user
    result = embedding_file_for_user(user_id, user_upload_dir)

    # 임시 파일 삭제 (옵션)
    # shutil.rmtree(user_upload_dir)

    return {
        "message": f"{len(saved_files)}개 파일 업로드 및 임베딩 완료",
        "user_id": user_id,
        "files": saved_files,
        "result": result
    }
```

### 2단계: 사용자별 ChromaDB 컬렉션

**tools.py 수정**:

```python
@tool
def embedding_file_for_user(user_id: str, path: str) -> str:
    """
    사용자별로 파일을 임베딩 (컬렉션 분리)

    Args:
        user_id: 사용자 식별자
        path: 업로드된 파일 경로
    """
    # ... (기존 로딩 로직) ...

    # 사용자별 컬렉션 이름
    collection_name = f"user_{user_id}"

    vectorstore = Chroma(
        collection_name=collection_name,  # 사용자별 컬렉션
        embedding_function=llm_router.local_embedding,
        persist_directory="./chroma_db",
    )

    vectorstore.add_documents(non_empty_docs, ids=ids)

    return f"✅ {user_id} 사용자: {len(non_empty_docs)}개 문서 임베딩 완료"


@tool
def retriever_vectordb_for_user(user_id: str, date: str, reference_len: str) -> str:
    """
    사용자별 ChromaDB에서 검색

    Args:
        user_id: 사용자 식별자
        date: 검색할 날짜
        reference_len: 검색할 문서 수
    """
    collection_name = f"user_{user_id}"

    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=llm_router.local_embedding,
        persist_directory="./chroma_db",
    )

    # ... (기존 검색 로직) ...
```

### 3단계: 에이전트에 user_id 전달

**router.py**:

```python
class QueryReq(BaseModel):
    req: str
    thread_id: str
    user_id: str  # 추가!

@router.post("/call_agent")
async def call_agent(req: QueryReq):
    res = controller.main(req)
    return res
```

**controller.py**:

```python
# user_id를 상태에 추가
class LogMakerState(MessagesState):
    user_id: str  # 사용자 식별자

def main(req):
    input_dict = {
        "messages": [HumanMessage(content=req.req)],
        "user_id": req.user_id  # 전달
    }
    res = graph.invoke(input_dict)
    return res["messages"][-1].content
```

**시스템 프롬프트 수정**:

```python
SYSTEM_MESSAGE_TEMPLATE = """당신은 개발자 일지 자동 생성 어시스턴트입니다.

현재 사용자 ID: {user_id}

작업 순서:
1. retriever_vectordb_for_user(user_id="{user_id}", date="...", reference_len="5") 호출
2. 일지 작성
3. maker_logfile로 저장
"""

def agent(state: LogMakerState) -> dict:
    user_id = state.get("user_id", "anonymous")
    system_prompt = SYSTEM_MESSAGE_TEMPLATE.format(user_id=user_id)
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    # ...
```

### 4단계: 프론트엔드 예시

**HTML (파일 업로드)**:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Log Maker - 파일 업로드</title>
</head>
<body>
    <h1>TIL 파일 업로드</h1>

    <form id="uploadForm">
        <label>사용자 ID:</label>
        <input type="text" id="userId" value="user_123" required><br><br>

        <label>파일 선택 (.md, .txt, .json):</label>
        <input type="file" id="files" multiple accept=".md,.txt,.json" required><br><br>

        <button type="submit">업로드 & 임베딩</button>
    </form>

    <div id="result"></div>

    <hr>

    <h2>일지 생성</h2>
    <form id="logForm">
        <label>사용자 ID:</label>
        <input type="text" id="logUserId" value="user_123" required><br><br>

        <label>날짜:</label>
        <input type="text" id="date" value="2026년 5월 14일" required><br><br>

        <button type="submit">일지 생성</button>
    </form>

    <div id="logResult"></div>

    <script>
        // 파일 업로드
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const userId = document.getElementById('userId').value;
            const files = document.getElementById('files').files;

            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }

            const response = await fetch(`/upload_files?user_id=${userId}`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            document.getElementById('result').innerText = JSON.stringify(result, null, 2);
        });

        // 일지 생성
        document.getElementById('logForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const userId = document.getElementById('logUserId').value;
            const date = document.getElementById('date').value;

            const response = await fetch('/call_agent', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    req: `${date} 일지 작성해줘`,
                    thread_id: 'web_' + Date.now(),
                    user_id: userId
                })
            });

            const result = await response.text();
            document.getElementById('logResult').innerText = result;
        });
    </script>
</body>
</html>
```

---

## 방법 2: 클라우드 스토리지 연동

### Google Drive 연동 예시

```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

@router.post("/sync_google_drive")
async def sync_google_drive(
    user_id: str,
    access_token: str
):
    """Google Drive에서 TIL 폴더 동기화"""

    # Google Drive API 인증
    creds = Credentials(token=access_token)
    service = build('drive', 'v3', credentials=creds)

    # 'TIL' 폴더 찾기
    results = service.files().list(
        q="name='TIL' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()

    folder_id = results['files'][0]['id']

    # 폴더 내 파일 다운로드
    files = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()

    user_dir = f"./uploads/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    for file in files['files']:
        # 파일 다운로드
        request = service.files().get_media(fileId=file['id'])
        with open(f"{user_dir}/{file['name']}", 'wb') as f:
            f.write(request.execute())

    # 임베딩
    result = embedding_file_for_user(user_id, user_dir)

    return {"message": "Google Drive 동기화 완료", "result": result}
```

### Notion 연동 예시

```python
from notion_client import Client

@router.post("/sync_notion")
async def sync_notion(
    user_id: str,
    notion_token: str,
    database_id: str
):
    """Notion 데이터베이스에서 일지 동기화"""

    notion = Client(auth=notion_token)

    # 데이터베이스 쿼리
    results = notion.databases.query(database_id=database_id)

    user_dir = f"./uploads/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    # 페이지를 마크다운으로 변환 후 저장
    for page in results['results']:
        page_id = page['id']
        # ... (Notion API로 내용 가져오기)
        # ... (마크다운 변환)

    # 임베딩
    result = embedding_file_for_user(user_id, user_dir)

    return {"message": "Notion 동기화 완료"}
```

---

## 방법 3: 웹훅 통합

### GitHub 웹훅으로 자동 동기화

```python
@router.post("/webhook/github")
async def github_webhook(
    payload: dict,
    signature: str = Header(None)
):
    """
    GitHub push 이벤트 수신
    TIL 저장소가 업데이트되면 자동으로 임베딩
    """

    # 서명 검증 (보안)
    # verify_github_signature(payload, signature)

    event = payload.get('event')
    if event == 'push':
        repo_url = payload['repository']['clone_url']
        user_id = payload['repository']['owner']['login']

        # Git clone
        user_dir = f"./uploads/{user_id}"
        os.system(f"git clone {repo_url} {user_dir}")

        # 임베딩
        result = embedding_file_for_user(user_id, user_dir)

        return {"message": "GitHub 동기화 완료", "result": result}
```

---

## 사용자별 데이터 격리

### ChromaDB 컬렉션 구조

```
chroma_db/
├── user_alice/      # alice 사용자 데이터
│   ├── 2026_05_14.md
│   └── 2026_06_29.md
├── user_bob/        # bob 사용자 데이터
│   └── 2026_07_01.md
└── metadata.db
```

### 보안 고려사항

```python
def verify_user_access(user_id: str, requested_user_id: str):
    """사용자가 자신의 데이터만 접근하는지 확인"""
    if user_id != requested_user_id:
        raise HTTPException(status_code=403, detail="접근 권한 없음")

@router.post("/call_agent")
async def call_agent(req: QueryReq, current_user: str = Depends(get_current_user)):
    verify_user_access(current_user, req.user_id)
    # ...
```

---

## 배포 시나리오

### 시나리오 1: 개인 사용 (현재 구조 유지)

**배포 방식**: Docker + 로컬 볼륨 마운트

```yaml
# docker-compose.yml
version: '3.8'
services:
  log-maker:
    build: .
    volumes:
      - ~/Yuta_TIL:/app/TIL:ro  # 로컬 TIL을 읽기 전용으로 마운트
      - ./chroma_db:/app/chroma_db
    ports:
      - "8000:8000"
```

**장점**: 간단, 추가 개발 불필요
**단점**: 다른 사용자 사용 불가

---

### 시나리오 2: 팀 내부 사용

**배포 방식**: 서버 + 파일 업로드 API

1. 팀원들이 웹 인터페이스로 TIL 업로드
2. 사용자별 ChromaDB 컬렉션
3. 각자 자기 일지만 생성

**구현**:
- 방법 1 (파일 업로드) 사용
- 간단한 인증 (사용자 ID/이메일)

---

### 시나리오 3: 공개 서비스

**배포 방식**: 클라우드 + 인증 + 스토리지

**필요한 추가 구현**:
1. **인증**: JWT, OAuth (Google, GitHub 로그인)
2. **파일 스토리지**: AWS S3, Google Cloud Storage
3. **사용자별 ChromaDB**: 컬렉션 분리 또는 별도 DB
4. **요금제**: API 호출 횟수 제한

```python
# 인증 예시
from fastapi import Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

def get_current_user(token: str = Depends(security)):
    # JWT 검증
    payload = jwt.decode(token.credentials, SECRET_KEY)
    return payload['user_id']

@router.post("/call_agent")
async def call_agent(
    req: QueryReq,
    current_user: str = Depends(get_current_user)
):
    req.user_id = current_user  # 토큰에서 추출한 user_id 강제 적용
    # ...
```

---

## 추천 접근 방법

### Phase 1: 개인/팀 내부용 (빠른 구축)
1. ✅ Docker로 배포 (로컬 볼륨 마운트)
2. ✅ 파일 업로드 API 추가
3. ✅ 사용자별 컬렉션 분리

### Phase 2: 소규모 공개 (MVP)
1. ✅ 간단한 로그인 (이메일)
2. ✅ 파일 업로드 + 사이즈 제한
3. ✅ 일지 생성 횟수 제한

### Phase 3: 확장 (프로덕션)
1. ✅ Google Drive/Notion 연동
2. ✅ GitHub 웹훅 자동 동기화
3. ✅ 프리미엄 요금제
4. ✅ 주간/월간 요약 기능

---

## 다음 단계

### 지금 바로 구현 가능한 것:

**1. 파일 업로드 API 추가** (30분):
```bash
# router.py에 /upload_files 엔드포인트 추가
# tools.py에 user_id 매개변수 추가
```

**2. 사용자별 컬렉션 분리** (20분):
```python
# ChromaDB collection_name에 user_id 포함
vectorstore = Chroma(collection_name=f"user_{user_id}", ...)
```

**3. 간단한 웹 UI** (1시간):
```html
<!-- static/index.html -->
<!-- 파일 업로드 + 일지 생성 폼 -->
```

---

**다음 구현할 기능은 무엇인가요?**
1. 파일 업로드 API 구현
2. 사용자별 ChromaDB 분리
3. 웹 인터페이스 추가
4. 클라우드 스토리지 연동

어느 방향으로 진행하시겠어요?
