# 아키텍처 문서

**최종 갱신:** 2026-07-31
**대상:** yuta_logagent (나의 사관일지)

> 이 문서는 현재 코드베이스를 직접 확인하여 작성한 **현재 구현 기준** 아키텍처 문서입니다.
> (이전 버전은 `docs/정리/ARCHITECTURE.md`에 초안 형태로 보관되어 있으며, Router 방식 시절 설계와
> 실제 구현 사이에 괴리가 있어 이번에 현재 상태 기준으로 다시 작성했습니다.)

---

## 1. 시스템 개요

**나의 사관일지**는 Git 저장소(TIL, 커밋 로그 등) 같은 개발 활동 기록을 벡터DB에 임베딩해두고,
사용자가 자연어로 요청하면 LangGraph 기반 단일 Agent가 필요한 도구를 스스로 호출해
- 소스(Source) 등록/조회/삭제
- 임베딩 실행/상태 조회
- 날짜 기반 검색 + 마크다운 일지 생성

를 처리하는 FastAPI 웹 애플리케이션입니다.

### 전환 히스토리
- Router 기반 멀티 에이전트 → **Single Agent 방식**으로 전환 (현재)
- LLM: Gemini → **Anthropic Claude**로 전환 (커밋 `ab18a51`, 쿼터 문제 회피 목적)
- 관련 상세 내용: [refactoring-cleanup-analysis.md](./refactoring-cleanup-analysis.md)

---

## 2. 전체 구조

```
                         ┌────────────────────────┐
                         │     FastAPI (main.py)    │
                         │  - init_db()             │
                         │  - router 등록            │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │      src/router.py        │
                         │  (HTML 페이지 + REST API)  │
                         └────────────┬─────────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                  │
                    ▼                 ▼                  ▼
         ┌──────────────────┐ ┌──────────────┐  ┌──────────────────┐
         │ storage/database  │ │ unified_     │  │  (레거시/버그 존재) │
         │ storage/models    │ │ controller_  │  │  /sync_git_repo   │
         │ storage/auth      │ │ single.py    │  │  엔드포인트        │
         │  (SQLite, users.db)│ │ (LangGraph  │  └──────────────────┘
         └──────────────────┘ │  단일 Agent) │
                               └──────┬───────┘
                                      │ bind_tools
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
           tools/source.py     tools/embedding.py   tools/log.py
           (소스 CRUD)          (임베딩 실행/상태)    (검색+일지 저장)
                    │                 │                 │
                    └────────┬────────┴────────┬────────┘
                             ▼                 ▼
                     SQLite (users.db)   ChromaDB (./chroma_db,
                     Source/User 테이블    컬렉션명 user_{user_id})
                                              │
                                              ▼
                                    Anthropic Claude (claude-sonnet-4-5)
                                    HuggingFace 로컬 임베딩
                                    (jhgan/ko-sroberta-multitask)
```

---

## 3. 계층별 컴포넌트

### 3.1 진입점 — `main.py`
- FastAPI 앱 생성, 시작 시 `init_db()`로 SQLite 테이블 자동 생성
- `src/router.py`의 `router`를 앱에 등록

### 3.2 API/HTML 레이어 — `src/router.py`
Jinja2 템플릿(`templates/`)과 REST API를 함께 제공하는 단일 라우터입니다.

**활성 엔드포인트**

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 로그인 페이지 |
| POST | `/login-form` | 로그인/자동 회원가입 → `/user/{user_id}`로 리다이렉트 |
| GET | `/user/{user_id}` | 개인 페이지 (AI 어시스턴트 진입점) |
| GET | `/user/{user_id}/settings` | 소스 목록 조회/삭제 페이지 |
| POST | `/user/{user_id}/delete_source/{source_id}` | 소스 삭제 |
| GET | `/log-maker` | Git 동기화 & 일지 생성 UI |
| POST | `/unified_agent` | **메인 챗봇 엔드포인트** — `unified_agent()` 호출 |
| POST | `/call_agent` | `/unified_agent`와 동일 로직(JSON body 방식). `log_maker.html`의 일지 생성 폼이 사용 |
| POST | `/sync_git_repo` | Git 저장소 clone + 임베딩 (⚠️ 아래 "알려진 이슈" 참고) |

> `/source_manager`는 실제로 쓰이지 않아 2026-07-31 정리 작업에서 삭제되었습니다.

### 3.3 Agent 레이어 — `src/unified_controller_single.py`
- LangGraph `StateGraph` 기반 단일 Agent (`agent` ↔ `tools` 순환 구조)
- `InMemorySaver` checkpointer로 **user_id를 thread_id 삼아** 사용자별 대화 맥락 유지
  (단, 인메모리이므로 **서버 재시작 시 대화 기록은 초기화됨**)
- 사용자별로 `create_system_message(user_id)`가 담긴 그래프를 매 요청마다 새로 빌드
- 바인딩된 8개 도구:
  `add_source_to_db`, `get_user_sources`, `delete_source_from_db`,
  `request_source_type_clarification`, `embed_source`, `get_embedding_status`,
  `retriever_vectordb`, `maker_logfile`
- 시스템 프롬프트에 "Git URL 추가 시 `add_source_to_db` → `embed_source` 연쇄 호출" 규칙을 명시해
  Agent가 소스 등록과 임베딩을 자동으로 이어서 수행하도록 유도

### 3.4 Tools 레이어 — `src/tools/`

| 파일 | 역할 |
|---|---|
| `source.py` | 소스 등록(`add_source_to_db`), 목록 조회, 삭제, 타입 안내. Git URL 정규식 검증 포함 |
| `embedding.py` | 소스 타입별(`git`/`git_log`/`local`/`agent_chatlog`/`memsearch`) 파일 수집 → 청크 분할 → ChromaDB 저장. 파일 해시 기반 **증분 임베딩** 지원 |
| `log.py` | 날짜 기반 ChromaDB 검색(`retriever_vectordb`, 메타데이터 필터 → 유사도 검색 폴백) 및 마크다운 일지 저장(`maker_logfile`) |

세부 사용 예시는 [tools-usage.md](./tools-usage.md), 소스 타입 판단 기준은
[git-source-type-detection.md](./git-source-type-detection.md) 참고.

### 3.5 Storage 레이어 — `src/storage/`
- `database.py`: SQLite(`users.db`) 엔진/세션, `init_db()`, FastAPI `Depends`용 `get_db()`
- `models.py`: `User`(1) — `Source`(N) 관계. `Source`는 `type`(`SourceType` enum)과
  `embedding_status`(`EmbeddingStatus` enum: pending/in_progress/completed/failed) 보유
- `auth.py`: 비밀번호 없는 `user_id` 기반 로그인/자동 회원가입 (`login_or_register`)

### 3.6 LLM/임베딩 설정 — `src/llm_router.py`
- **LLM**: `ChatAnthropic(model="claude-sonnet-4-5-20250929")` — Agent가 실제 사용하는 유일한 LLM
- Google Gemini(`gemini-2.5-flash-lite`)는 `GOOGLE_API_KEY`가 있을 때만 선택적으로 초기화되지만,
  **현재 어떤 코드에서도 호출되지 않음** (예비용)
- **임베딩**: HuggingFace `jhgan/ko-sroberta-multitask` (한국어 특화, 로컬 CPU 실행, 무료)
- **벡터DB**: `chromadb.PersistentClient(path="./chroma_db")` — 로컬 파일 기반 모드로 고정 동작.
  `CHROMADB_HOST`/`CHROMADB_PORT` 환경변수가 있지만 실제로는 참조되지 않아 서버 모드는 동작하지 않음

---

## 4. 데이터 흐름

### 4.1 로그인
```
사용자 → POST /login-form (user_id)
       → login_or_register() : 있으면 로그인, 없으면 즉시 회원가입
       → 303 리다이렉트 → GET /user/{user_id}
```

### 4.2 소스 추가 + 임베딩 (AI 어시스턴트, 정상 동작 경로)
```
"https://github.com/user/til.git 추가해줘"
    → POST /unified_agent (user_id, message)
    → unified_agent() : LangGraph 실행
        1) add_source_to_db 호출 → Source 레코드 생성 (SQLite)
        2) 시스템 프롬프트 규칙에 따라 embed_source 자동 연쇄 호출
             → 소스 타입별 파일 수집 (git: clone, git_log: git log, local: 로컬 경로)
             → 파일 해시로 신규 문서만 필터링 (증분)
             → RecursiveCharacterTextSplitter로 청크 분할
             → ChromaDB 컬렉션 user_{user_id}에 저장
    → 최종 응답 문자열 반환
```

### 4.3 일지 생성 (날짜 검색 → 저장)
```
"2026-07-30 일지 작성해줘"
    → POST /unified_agent
    → retriever_vectordb(date, user_id, end_date="")
        ChromaDB where={"date": ...} 메타데이터 필터만 사용 (유사도 폴백 없음)
        개수 제한 없이 그날 문서를 모두 가져오고, 분량이 넘치면
        커밋의 파일 변경 목록부터 덜어낸다 (MAX_RESULT_CHARS)
    → Claude가 검색 결과를 분석해 마크다운 일지 작성
    → maker_logfile(date, content) → logs/YYYY.MM.DD_log.md 저장
```

### 4.4 소스 삭제
```
GET /user/{user_id}/settings → 소스 목록 표시
POST /user/{user_id}/delete_source/{source_id} → DB에서 Source 삭제
```
(주의: 이 경로는 SQLite 레코드만 삭제하며 ChromaDB에 이미 저장된 임베딩은 그대로 남습니다.
 `tools/embedding.py`에는 `_delete_source_embeddings()` 헬퍼가 있지만 이 삭제 API에서 호출되지 않음)

---

## 5. 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 웹 서버 | FastAPI + Jinja2Templates + uvicorn |
| Agent 워크플로우 | LangGraph `StateGraph` (단일 Agent, ToolNode) |
| LLM | Anthropic Claude Sonnet 4.5 |
| 임베딩 모델 | HuggingFace `jhgan/ko-sroberta-multitask` (로컬 CPU) |
| 벡터DB | ChromaDB (로컬 persistent, `./chroma_db`) |
| 메타DB | SQLite (`users.db`) + SQLAlchemy ORM |
| 배포 | Docker (`Dockerfile`, `docker-compose*.yml`), GitHub Actions → ECR → EC2(SSM) |

---

## 6. 디렉토리 구조 (현재)

```
yuta_logagent/
├── main.py
├── src/
│   ├── router.py                  # HTML 페이지 + REST API
│   ├── unified_controller_single.py  # LangGraph 단일 Agent
│   ├── llm_router.py               # LLM / 임베딩 / ChromaDB 설정
│   ├── tools/
│   │   ├── source.py               # 소스 CRUD
│   │   ├── embedding.py            # 임베딩 실행
│   │   └── log.py                  # 검색 + 일지 저장
│   └── storage/
│       ├── database.py             # SQLite 엔진/세션
│       ├── models.py               # User, Source 모델
│       └── auth.py                 # 로그인/회원가입
├── templates/                      # login, user_page, settings, log_maker
├── logs/                           # 생성된 일지 (YYYY.MM.DD_log.md)
├── data/sources/                   # Git clone/로컬 소스 원본 파일
├── chroma_db/                      # ChromaDB 로컬 데이터
├── backups/                        # DB 백업 (users.db.backup_*)
├── scripts/                        # 배포/운영 스크립트
├── tests/                          # (현재 비어있는 pytest 스캐폴드)
├── check_embeddings.py, reset_db.py,
│   test_date_search.py, test_log_tools.py  # 개발/디버깅용 실행 스크립트 (pytest 아님)
└── docs/
```

---

## 7. 알려진 이슈 (2026-07-31 검증 중 발견)

이번 정리 작업 중 코드를 직접 대조 검증하며 발견한, 아직 해결되지 않은 문제입니다.

1. **`/sync_git_repo` 사용 불가 상태**
   `src/router.py`의 `/sync_git_repo` 핸들러가 `from tools import embedding_file_for_user`를
   import하는데, 이 함수는 코드베이스 어디에도 존재하지 않습니다(레거시 흔적으로 추정).
   `log_maker.html`의 "Git 동기화" 폼이 이 엔드포인트를 실제로 호출하지만, 매 요청마다
   저장소를 clone한 뒤 import 실패로 `{"success": false}`를 반환할 것으로 보입니다.
   → 소스 등록/임베딩은 현재 `/unified_agent` 대화형 경로(4.2)로만 정상 동작합니다.

2. **`/call_agent`의 요청 필드 불일치**
   `log_maker.html`의 일지 생성 폼이 `/call_agent`에 `{req, thread_id}` 형태로 body를 보내지만,
   서버는 `QueryReq(message, user_id)`를 기대합니다. 필드명이 맞지 않아 항상 422 오류가
   발생할 가능성이 높습니다.

이 두 항목은 이번 정리 작업 범위 밖이라 코드는 그대로 두었습니다. 상세 논의는
[refactoring-cleanup-analysis.md](./refactoring-cleanup-analysis.md)를 참고하세요.

---

## 8. 참고 문서
- [refactoring-cleanup-analysis.md](./refactoring-cleanup-analysis.md) — 리팩토링 후 정리 내역
- [tools-usage.md](./tools-usage.md) — 소스/임베딩 도구 사용 예시
- [git-source-type-detection.md](./git-source-type-detection.md) — GIT vs GIT_LOG 판단 기준
- [cicd-setup.md](./cicd-setup.md) — CI/CD 파이프라인 설정
- [docs/정리/](./정리/) — 이전 초안 문서 보관 (Router 방식 시절 등, 참고용)
