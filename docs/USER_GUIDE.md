# Log Maker 사용자 가이드 📚

> TIL 기록을 자동으로 일지로 변환하는 AI 에이전트

---

## 📑 목차

1. [시스템 개요](#-시스템-개요)
2. [초기 세팅](#-초기-세팅)
3. [사용 방법](#-사용-방법)
4. [내부 동작 원리](#-내부-동작-원리)
5. [트러블슈팅](#-트러블슈팅)
6. [FAQ](#-faq)

---

## 🎯 시스템 개요

### 무엇을 하는 프로그램인가요?

GitHub에 저장된 TIL(Today I Learned) 마크다운 파일들을 읽고, 특정 날짜의 기록을 바탕으로 구조화된 개발 일지를 자동으로 생성합니다.

### 전체 프로세스
```
┌─────────────────┐
│  1. Git 저장소  │  사용자 TIL 저장소
│     동기화      │  (GitHub)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. 파일 임베딩 │  벡터 DB 저장
│  & 벡터 저장    │  (ChromaDB)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. 일지 생성   │  AI Agent가
│     요청        │  도구 자동 호출
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. 일지 파일   │  logs/YYYY.MM.DD
│     생성        │  _log.md
└─────────────────┘
```

### 기술 스택

- **FastAPI**: 웹 서버 & API
- **LangGraph**: AI Agent 워크플로우
- **ChromaDB**: 벡터 데이터베이스
- **Claude Sonnet 4.5**: LLM (일지 생성)
- **HuggingFace**: 임베딩 모델 (무료)

---

## 🚀 초기 세팅

### 1. 시스템 요구사항

```bash
# 필수
- Python 3.12 이상
- Git
- 4GB 이상 RAM

# 선택 (서버 모드 사용 시)
- Docker & Docker Compose
```

### 2. 프로젝트 설치

```bash
# 1. 저장소 클론
git clone <repository_url>
cd yuta_bot

# 2. 의존성 설치
pip install -e .

# 3. 환경 변수 설정
cp .env.example .env
```

### 3. API 키 설정

**필수**: `.env` 파일 편집

```bash
# 필수 - Anthropic API 키
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx

# 선택 - 다른 LLM 사용 시
GOOGLE_API_KEY=your_key_here

# 선택 - ChromaDB 서버 모드 (기본값 사용 가능)
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
```

**API 키 발급 방법**:
1. [Anthropic Console](https://console.anthropic.com/) 접속
2. Settings → API Keys
3. "Create Key" 클릭
4. 생성된 키를 `.env`에 복사

### 4. 서버 실행

#### 옵션 1: 로컬 모드 (권장 - 개발용)

```bash
uvicorn main:app --reload
```

**예상 출력**:
```
[ChromaDB] 📁 로컬 모드 사용: ./chroma_db
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

#### 옵션 2: 서버 모드 (선택 - 다중 사용자)

```bash
# ChromaDB 서버 실행
docker-compose up -d chromadb

# 애플리케이션 실행
uvicorn main:app --reload
```

**예상 출력**:
```
[ChromaDB] ✅ 서버 연결 성공: localhost:8001
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 5. 접속 확인

```bash
# 브라우저에서
http://localhost:8000/

# 또는 터미널에서
curl http://localhost:8000/
```

✅ 웹 UI가 보이면 설정 완료!

---

## 💻 사용 방법

### 방법 1: 웹 UI 사용 (권장)

#### A. Git 저장소 동기화

1. **브라우저에서 http://localhost:8000/ 접속**

2. **"1단계: Git 저장소 동기화" 폼 작성**
   - **사용자 ID**: `hrun` (원하는 ID 입력)
   - **Git 저장소 URL**: `https://github.com/username/til.git`
   - **브랜치**: `main` (기본값)

3. **"동기화 & 임베딩 시작" 버튼 클릭**

4. **완료 메시지 확인** (10-30초 소요)
   ```
   ✅ 동기화 성공!
   사용자: hrun
   저장소: https://github.com/username/til.git
   결과: ✅ 사용자 'hrun': 12개 문서 임베딩 완료
   ```

#### B. 일지 생성

1. **"2단계: 일지 생성" 폼 작성**
   - **사용자 ID**: `hrun` (위와 동일!)
   - **날짜**: `2026년 6월 29일`

2. **"일지 생성" 버튼 클릭**

3. **완료 메시지 확인** (5-10초 소요)
   ```
   ✅ 일지 생성 완료!

   2026년 6월 29일의 일지를 성공적으로 작성했습니다!
   파일 위치: logs/2026.06.29_log.md
   ```

4. **생성된 파일 확인**
   ```bash
   cat logs/2026.06.29_log.md
   ```

### 방법 2: API 직접 호출

#### A. Git 동기화

```bash
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hrun",
    "repo_url": "https://github.com/username/til.git",
    "branch": "main"
  }'
```

**성공 응답**:
```json
{
  "success": true,
  "message": "Git 동기화 및 임베딩 완료",
  "user_id": "hrun",
  "embedding_result": "✅ 사용자 'hrun': 12개 문서 임베딩 완료"
}
```

#### B. 일지 생성

```bash
curl -X POST "http://localhost:8000/call_agent" \
  -H "Content-Type: application/json" \
  -d '{
    "req": "2026년 6월 29일 일지 작성해줘",
    "thread_id": "user_hrun_001"
  }'
```

**성공 응답**:
```
2026년 6월 29일의 일지를 성공적으로 작성했습니다!

파일 위치: logs/2026.06.29_log.md

이 날은 ChromaDB 서버 모드 구현과 관련된 작업을 진행하셨네요...
```

### 생성된 일지 파일 예시

**파일**: `logs/2026.06.29_log.md`

```markdown
# 2026년 6월 29일 개발 일지

## 🎯 주요 활동

### ChromaDB 서버 모드 구현
- 다중 사용자 동시 접근 문제 해결
- HttpClient 자동 감지 + 로컬 모드 폴백 구현
- Docker Compose 설정 완료

## 📝 상세 내용

### 1. llm_router.py 수정
ChromaDB 클라이언트를 서버 모드와 로컬 모드로 자동 전환...

### 2. tools.py 업데이트
3개 함수에서 persist_directory를 client로 변경...

## 🔍 배운 점
- SQLite는 동시 쓰기 제한이 있음
- ChromaDB 서버 모드로 해결 가능
- 자동 폴백 기능으로 개발/프로덕션 모두 지원

## 📌 다음 할 일
- [ ] 검색 시 user_id 전달 구현
- [ ] 인증 시스템 추가
- [ ] 프로덕션 배포 준비
```

---

## ⚙️ 내부 동작 원리

### 1단계: Git Clone & 임베딩

```
사용자 요청
    ↓
┌──────────────────────────────────┐
│  POST /sync_git_repo             │
│  {user_id, repo_url, branch}     │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  git clone                       │
│  → ./repos/{user_id}/            │
│     ├─ 2026_06_29.md             │
│     ├─ 2026_07_09.md             │
│     └─ README.md                 │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  embedding_file_for_user()       │
│  1. 파일 스캔 (*.md, *.txt)      │
│  2. 날짜 추출 (파일명에서)        │
│  3. 메타데이터 생성               │
│  4. 고유 ID 생성 (MD5)           │
│  5. 벡터 임베딩 (HuggingFace)    │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  ChromaDB 저장                   │
│  Collection: "user_{user_id}"    │
│  ├─ Document 1                   │
│  │  ├─ id: a1b2c3d4...           │
│  │  ├─ content: "작성 날짜:..."   │
│  │  ├─ metadata: {date, source}  │
│  │  └─ embedding: [0.123, ...]   │
│  └─ Document 2...                │
└──────────────────────────────────┘
```

### 2단계: Agent 워크플로우

```
사용자 요청: "2026년 6월 29일 일지 작성해줘"
    ↓
┌────────────────────────────────────────┐
│  START → agent (1차)                   │
│  SystemMessage: "당신은 일지 생성 AI..." │
│  HumanMessage: "2026년 6월 29일..."    │
│                                        │
│  Claude 판단:                          │
│  "먼저 해당 날짜 기록을 검색해야겠다"    │
│                                        │
│  tool_calls = [retriever_vectordb]    │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  tools → retriever_vectordb()          │
│  1. ChromaDB 연결                      │
│  2. 날짜 정규화 (2026-06-29)           │
│  3. 메타데이터 필터 검색                │
│     where={"date": "2026-06-29"}      │
│  4. 실패 시 유사도 검색                 │
│  5. 결과 포맷팅 (LLM이 읽기 쉽게)       │
│                                        │
│  return: "검색 결과 (2개 문서):\n..."   │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  agent (2차)                           │
│  ToolMessage: "검색 결과..."            │
│                                        │
│  Claude 판단:                          │
│  "이제 일지를 작성하고 파일로 저장"      │
│                                        │
│  tool_calls = [maker_logfile]         │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  tools → maker_logfile()               │
│  1. logs/ 디렉토리 생성                 │
│  2. 파일명 생성                         │
│     "logs/2026.06.29_log.md"          │
│  3. 마크다운 내용 작성                  │
│     (Claude가 생성한 일지)              │
│  4. 파일 저장                          │
│                                        │
│  return: "✅ 일지 저장 완료: ..."       │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  agent (3차)                           │
│  ToolMessage: "✅ 일지 저장 완료..."     │
│                                        │
│  Claude 판단:                          │
│  "작업 완료! 사용자에게 보고"           │
│                                        │
│  tool_calls = [] (더 이상 도구 호출 X)  │
│  content = "완료했습니다!"              │
└────────────┬───────────────────────────┘
             │
             ▼
          END → 사용자에게 응답
```

### 핵심 구성 요소

#### A. LangGraph 그래프 (controller.py)

```python
builder = StateGraph(MessagesState)

# 노드 추가
builder.add_node("agent", agent)      # AI가 판단
builder.add_node("tools", tool_node)  # 도구 실행

# 엣지 설정
builder.add_edge(START, "agent")      # 시작 → agent

# 조건부 엣지 (agent → tools or END)
builder.add_conditional_edges(
    "agent",
    tools_condition,  # tool_calls 있으면 "tools", 없으면 END
    {
        "tools": "tools",
        "__end__": END,
    }
)

builder.add_edge("tools", "agent")    # tools → agent (반복)
```

#### B. 도구 (tools.py)

**도구 1: retriever_vectordb**
```python
@tool
def retriever_vectordb(date: str, reference_len: str) -> str:
    """ChromaDB에서 특정 날짜 기록 검색"""
    # 1차: 메타데이터 필터
    docs = chroma.get(where={"date": date_normalized})

    # 2차: 유사도 검색 (폴백)
    if not docs:
        docs = chroma.similarity_search(f"작성 날짜: {date}")

    return formatted_result
```

**도구 2: maker_logfile**
```python
@tool
def maker_logfile(date: str, content: str) -> str:
    """일지를 마크다운 파일로 저장"""
    filename = f"logs/{date.replace('-', '.')}_log.md"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    return f"✅ 일지 저장 완료: {filename}"
```

#### C. ChromaDB 데이터 구조

```
ChromaDB Server
│
├─ Collection: "user_hrun"
│  ├─ Document: a1b2c3d4e5f6...
│  │  ├─ content: "작성 날짜: 2026년 6월 29일\n\n오늘은..."
│  │  ├─ metadata: {
│  │  │    "source": "./repos/hrun/2026_06_29.md",
│  │  │    "date": "2026-06-29"
│  │  │  }
│  │  └─ embedding: [0.123, -0.456, 0.789, ...] (384차원)
│  │
│  └─ Document: b2c3d4e5f6g7...
│     └─ ...
│
└─ Collection: "user_alice"
   └─ ...
```

---

## 🛠️ 트러블슈팅

### Q1. "Connection refused" 에러

**증상**:
```
requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=8001)
```

**원인**: ChromaDB 서버가 실행되지 않음

**해결**:
```bash
# 자동 폴백 확인
# 출력에 "[ChromaDB] 📁 로컬 모드 사용" 나오면 정상

# 서버 모드 원하면
docker-compose up -d chromadb
uvicorn main:app --reload
```

### Q2. "해당 날짜 기록을 찾을 수 없습니다"

**증상**:
```
'2026년 6월 29일' 날짜와 관련된 기록을 찾을 수 없습니다.
```

**원인**:
1. Git 동기화를 안 했거나
2. 파일명에 날짜가 없거나
3. user_id가 다르거나

**해결**:
```bash
# 1. Git 동기화 확인
ls -la repos/hrun/

# 2. 파일명 형식 확인 (YYYY_MM_DD.md 또는 YYYY-MM-DD.md)
# 올바른 예: 2026_06_29.md, 2026-06-29.md
# 잘못된 예: 0629.md, june29.md

# 3. user_id 확인
# Git 동기화 시: user_id="hrun"
# 일지 생성 시: user_id="hrun" (동일해야 함!)
```

### Q3. API 키 에러

**증상**:
```
anthropic.AuthenticationError: Invalid API Key
```

**원인**: `.env` 파일에 API 키 누락 또는 잘못됨

**해결**:
```bash
# .env 파일 확인
cat .env | grep ANTHROPIC_API_KEY

# 올바른 형식
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx

# 서버 재시작 필수
uvicorn main:app --reload
```

### Q4. "database is locked" 에러

**증상**:
```
sqlite3.OperationalError: database is locked
```

**원인**: 로컬 모드에서 동시 쓰기 시도

**해결**:
```bash
# 옵션 1: 순차적으로 실행 (한 번에 하나씩)

# 옵션 2: 서버 모드로 전환
docker-compose up -d chromadb
uvicorn main:app --reload
```

### Q5. 웹 UI가 안 보임

**증상**: http://localhost:8000/ 접속 시 404 에러

**원인**: `static/` 디렉토리 누락

**해결**:
```bash
# static 디렉토리 확인
ls -la static/index.html

# 없으면 Git에서 다시 받기
git pull origin main

# 서버 재시작
uvicorn main:app --reload
```

---

## ❓ FAQ

### Q1. Private 저장소도 사용 가능한가요?

**현재**: ❌ Public 저장소만 지원

**향후 업데이트 예정**:
```json
{
  "user_id": "hrun",
  "repo_url": "https://github.com/hrun/private-til.git",
  "github_token": "ghp_xxxxxxxxxxxxx"
}
```

### Q2. 여러 저장소를 동시에 사용할 수 있나요?

**가능합니다!** user_id를 다르게 하세요:

```bash
# 저장소 1
POST /sync_git_repo
{"user_id": "til_work", "repo_url": "https://github.com/me/work-til.git"}

# 저장소 2
POST /sync_git_repo
{"user_id": "til_personal", "repo_url": "https://github.com/me/personal-til.git"}
```

### Q3. 일지 형식을 커스터마이징할 수 있나요?

**현재**: ❌ Claude가 자동으로 생성

**향후 업데이트 예정**:
- 템플릿 설정 기능
- 프롬프트 커스터마이징
- 스타일 옵션 (간단, 상세, 기술 중심 등)

### Q4. 다른 날짜 형식도 지원하나요?

**지원하는 형식**:

파일명:
- `2026_06_29.md` ✅
- `2026-06-29.md` ✅
- `2026년 6월 29일.md` ✅

일지 요청:
- "2026년 6월 29일" ✅
- "6월 29일" ✅ (현재 연도로 자동 인식)
- "2026-06-29" ✅

### Q5. 다른 LLM(GPT, Gemini)도 사용 가능한가요?

**가능합니다!** `llm_router.py`에 설정:

```python
# Gemini 사용
from langchain_google_genai import ChatGoogleGenerativeAI
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")

# Codex (GPT) 사용
from langchain_codex_oauth import ChatCodexOAuth
llm = ChatCodexOAuth(model="gpt-5.4-mini")
```

`.env`에 API 키 추가:
```bash
GOOGLE_API_KEY=your_key_here
```

### Q6. 로컬 모드와 서버 모드 중 뭘 써야 하나요?

| 상황 | 권장 모드 |
|------|----------|
| 혼자 개발/테스트 | 로컬 모드 |
| 팀 개발 (3-5명) | 서버 모드 |
| 웹 서비스 배포 | 서버 모드 |
| 읽기만 (검색) | 둘 다 OK |
| 동시 쓰기 필요 | 서버 모드 |

**결론**: 혼자 쓰면 로컬 모드, 여럿이 쓰면 서버 모드!

---

## 📂 디렉토리 구조

```
yuta_bot/
├── main.py                    # FastAPI 앱 진입점
├── src/
│   ├── router.py              # API 엔드포인트
│   ├── controller.py          # LangGraph Agent
│   ├── llm_router.py          # LLM & ChromaDB 설정
│   └── tools.py               # Agent 도구들
├── static/
│   └── index.html             # 웹 UI
├── repos/                     # Git 저장소 clone 위치
│   ├── hrun/                  # 사용자별 디렉토리
│   │   ├── 2026_06_29.md
│   │   └── 2026_07_09.md
│   └── alice/
├── chroma_db/                 # ChromaDB 로컬 모드
│   └── chroma.sqlite3
├── chroma_data/               # ChromaDB 서버 모드 (Docker)
├── logs/                      # 생성된 일지 파일
│   ├── 2026.06.29_log.md
│   └── 2026.07.09_log.md
├── docker-compose.yml         # Docker 설정
├── Dockerfile                 # API 컨테이너
├── .env                       # 환경 변수 (시크릿)
├── .env.example               # 환경 변수 템플릿
├── pyproject.toml             # Python 의존성
└── README.md                  # 프로젝트 소개
```

---

## 🔗 관련 문서

- **CHROMADB_QUICKSTART.md**: ChromaDB 서버 모드 빠른 시작
- **CHROMADB_SERVER_SETUP.md**: ChromaDB 서버 모드 상세 가이드
- **GIT_SYNC_GUIDE.md**: Git 동기화 기능 가이드
- **IMPLEMENTATION_SUMMARY.md**: 구현 세부사항
- **DEVELOPMENT_LOG.md**: 개발 이력

---

## 📞 지원

문제가 발생하면:
1. 이 문서의 [트러블슈팅](#-트러블슈팅) 섹션 확인
2. [FAQ](#-faq) 섹션 확인
3. GitHub Issues에 질문 등록

---

**Happy Logging! 📝✨**
