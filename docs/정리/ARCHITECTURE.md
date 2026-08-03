# 아키텍처 설계 문서

## 1. 시스템 개요

**Log Maker**는 개발자의 다양한 활동 기록(Git Commit, TIL, AI Chat Log 등)을 수집하여 자동으로 구조화된 개발 일지를 생성하는 AI 에이전트 시스템입니다.

### 핵심 목표
- 📝 개발자의 학습/작업 기록을 자동으로 수집하고 분석
- 🤖 AI를 활용한 자동 일지 생성
- 🔍 과거 기록의 빠른 검색 및 참조
- 📊 주간/월간 요약을 통한 성장 추적

---

## 2. 시스템 구조도

### 2.1 전체 데이터 플로우 (설계 목표)

```
                      [나의 사관일지]

                      │
      ┌───────────────┼────────────────┐
      │               │                │
      ▼               ▼                ▼
 Git Commit      TIL(md)         AI Chat Log
      │               │                │
      └───────────────┼────────────────┘
                      │
                MemSearch(md)
                      │
                      ▼
              [Collector Module]
           (파일 읽기 / Git API 등)
                      │
                      ▼
             문서 표준 포맷 변환
         (date, source, content)
                      │
                      ▼
              SQLite(or Postgres)
             원본 문서 저장
                      │
                      ▼
             Embedding Pipeline
          (OpenAI / bge-m3 등)
                      │
                      ▼
              Vector DB(Qdrant)
                      │
      ┌───────────────┼─────────────────┐
      ▼               ▼                 ▼
 Day Summary    Week Summary     Month Summary
      │               │                 │
      └───────────────┼─────────────────┘
                      ▼
             LLM Summary Engine
                      │
                      ▼
             Markdown 문서 생성
          diary/day.md
          diary/week.md
          diary/month.md
                      │
                      ▼
            Chat Recommendation
       (못한 일 / 다음 행동 추천)
```

### 2.2 현재 구현된 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Server                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Router     │→ │ Controller   │→ │ LangGraph    │      │
│  │ (API 엔드포인트)│  │ (비즈니스 로직) │  │   Agent      │      │
│  └──────────────┘  └──────────────┘  └──────┬───────┘      │
└─────────────────────────────────────────────┼──────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────┐
                    │                         │                 │
                    ▼                         ▼                 ▼
            ┌───────────────┐       ┌──────────────┐   ┌──────────────┐
            │  Tools Layer  │       │  ChromaDB    │   │  Claude AI   │
            │               │       │ (Vector DB)  │   │  (Sonnet 4.5)│
            │ - embedding   │←─────→│              │   │              │
            │ - retriever   │       │ - 벡터 검색   │   │ - 일지 생성  │
            │ - maker_log   │       │ - 날짜 필터  │   │ - 내용 분석  │
            └───────────────┘       └──────────────┘   └──────────────┘
                    │                       │                   │
                    └───────────────────────┴───────────────────┘
                                            │
                                            ▼
                                  ┌──────────────────┐
                                  │   Output Files   │
                                  │                  │
                                  │ logs/YYYY.MM.DD  │
                                  │      _log.md     │
                                  └──────────────────┘
```

---

## 3. 핵심 컴포넌트

### 3.1 API Layer (FastAPI)

#### main.py
- FastAPI 애플리케이션 진입점
- Static 파일 서빙 (웹 UI)
- 라우터 등록

#### router.py
- REST API 엔드포인트 정의
  - `POST /call_agent`: AI 에이전트 호출 (일지 생성 요청)
  - `POST /embed`: 파일/디렉토리 임베딩
  - `POST /sync_git_repo`: Git 저장소 동기화 및 임베딩

### 3.2 Agent Layer (LangGraph)

#### controller.py
- **LangGraph Agent 구현**
  - StateGraph 기반 워크플로우
  - Agent → Tools → Agent 순환 구조
  - SystemMessage로 에이전트 동작 정의

- **Agent 동작 순서**
  1. 사용자 요청 수신
  2. retriever_vectordb 도구 호출 (날짜별 검색)
  3. 검색 결과 분석 및 일지 작성
  4. maker_logfile 도구 호출 (파일 저장)

### 3.3 Tools Layer

#### tools.py
1. **embedding_file**
   - 디렉토리의 문서 임베딩
   - 지원 포맷: `.md`, `.txt`, `.json`, `.zip`
   - 파일명에서 날짜 자동 추출 (정규식)
   - Claude 대화 JSON 파싱 및 구조화

2. **retriever_vectordb**
   - 날짜 기반 벡터 검색
   - 메타데이터 필터 우선 → 유사도 검색 폴백
   - LLM 친화적 형식으로 결과 반환
s
3. **maker_logfile**
   - 생성된 일지를 Markdown 파일로 저장
   - 경로: `logs/YYYY.MM.DD_log.md`

### 3.4 LLM Router

#### llm_router.py
- **LLM 선택 및 관리**
  - Claude Sonnet 4.5 (메인)
  - Gemini (대안)
  - Codex (실험적)

- **ChromaDB 클라이언트 관리**
  - 서버 모드 자동 감지 (HttpClient)
  - 로컬 모드 폴백 (PersistentClient)

- **Embedding 모델**
  - HuggingFace `sentence-transformers/all-MiniLM-L6-v2`
  - 로컬 실행 (무료)

---

## 4. 데이터 플로우

### 4.1 Git 저장소 동기화

```
User Request
    │
    ▼
POST /sync_git_repo
    │
    ├─ 1. Git Clone (shallow, branch 지정)
    │     └─ repos/{user_id}/ 에 저장
    │
    ├─ 2. embedding_file_for_user() 호출
    │     ├─ DirectoryLoader로 .md, .txt, .json 로드
    │     ├─ 파일명에서 날짜 추출 (정규식)
    │     ├─ 문서 내용에 날짜 정보 추가
    │     └─ 메타데이터 설정
    │
    └─ 3. ChromaDB 저장
          ├─ 컬렉션: user_{user_id}
          ├─ Embedding: HuggingFace 로컬 모델
          └─ 고유 ID 생성 (MD5 해시)
```

### 4.2 일지 생성

```
User: "2026년 7월 9일 일지 작성해줘"
    │
    ▼
POST /call_agent
    │
    ▼
LangGraph Agent
    │
    ├─ 1. retriever_vectordb 호출
    │     ├─ 날짜 정규화: "2026-07-09"
    │     ├─ 메타데이터 필터: where={"date": "2026-07-09"}
    │     └─ 유사도 검색 폴백
    │
    ├─ 2. Claude AI 분석
    │     ├─ 검색된 문서 내용 분석
    │     ├─ 주요 활동 추출
    │     ├─ 학습 내용 정리
    │     └─ 마크다운 형식 일지 작성
    │
    └─ 3. maker_logfile 호출
          └─ logs/2026.07.09_log.md 저장
```

### 4.3 벡터 검색 전략

```
날짜 검색 요청
    │
    ▼
1차: 메타데이터 필터 검색
    ├─ reopened.get(where={"date": "YYYY-MM-DD"})
    ├─ 정확한 날짜 매칭
    └─ 성공 → 결과 반환
    │
    ▼ (실패 시)
2차: 유사도 검색
    ├─ reopened.similarity_search("작성 날짜: YYYY-MM-DD")
    ├─ 임베딩 유사도 기반
    └─ 결과 반환
```

---

## 5. 기술 스택

### Backend
- **FastAPI**: 웹 서버 & REST API
- **LangGraph**: AI Agent 워크플로우 (StateGraph)
- **LangChain**: LLM 추상화 및 도구 통합

### AI/ML
- **Claude Sonnet 4.5**: LLM (Anthropic)
  - 최고 성능 + 안정적인 tool calling
- **HuggingFace Transformers**: 로컬 임베딩 모델
  - `sentence-transformers/all-MiniLM-L6-v2`

### Database
- **ChromaDB**: 벡터 데이터베이스
  - 서버 모드 지원 (다중 사용자)
  - 로컬 모드 폴백
  - 메타데이터 필터링

### Data Processing
- **LangChain Document Loaders**
  - DirectoryLoader
  - TextLoader (md, txt)
  - JSONLoader (Claude 대화 내역)

### Deployment
- **Docker**: ChromaDB 서버 컨테이너화
- **uvicorn**: ASGI 서버

---

## 6. 주요 설계 결정

### 6.1 왜 LangGraph를 사용했는가?
- **도구 호출 자동화**: Agent가 필요한 도구를 자율적으로 선택
- **상태 관리**: MessagesState로 대화 컨텍스트 유지
- **순환 워크플로우**: Agent ↔ Tools 무한 반복 가능

### 6.2 왜 ChromaDB를 선택했는가?
- **간단한 설정**: Python native, 별도 서버 불필요 (로컬 모드)
- **메타데이터 필터링**: 날짜 기반 정확한 검색
- **서버 모드 지원**: 다중 사용자 동시 접근 가능

### 6.3 날짜 추출 전략
- **파일명 기반 정규식**: `YYYY_MM_DD`, `YYYY-MM-DD`, `YYYY년 MM월 DD일`
- **문서 내용에 날짜 추가**: 벡터 검색 정확도 향상
- **메타데이터 저장**: 정확한 날짜 필터링

### 6.4 사용자별 컬렉션 분리
- **컬렉션 네이밍**: `user_{user_id}`
- **데이터 격리**: 사용자 간 검색 결과 혼재 방지
- **확장성**: 다중 사용자 지원

---

## 7. 디렉토리 구조

```
yuta_bot/
├── main.py                   # FastAPI 앱 진입점
├── src/
│   ├── router.py            # API 엔드포인트
│   ├── controller.py        # LangGraph Agent
│   ├── tools.py             # LangChain Tools
│   └── llm_router.py        # LLM & ChromaDB 설정
├── static/                  # 웹 UI
│   └── index.html
├── logs/                    # 생성된 일지 저장
│   └── YYYY.MM.DD_log.md
├── repos/                   # Git 동기화된 저장소
│   └── {user_id}/
├── chroma_db/              # ChromaDB 로컬 데이터
└── docs/
    ├── ARCHITECTURE.md     # 이 문서
    ├── SETUP.md
    └── aidocs/
        └── CHROMADB_SERVER_SETUP.md
```

---

## 8. 향후 개선 방향 (설계 목표)

### 8.1 데이터 수집 확장
현재는 Git 저장소의 TIL 마크다운만 수집하지만, 향후 다음 소스를 추가:

- **Git Commit 이력**: Git API를 통한 커밋 메시지 수집
- **MemSearch 통합**: 기존 검색 기록 활용
- **AI Chat Log**: Claude, GPT, Gemini 대화 이력 자동 수집

### 8.2 데이터베이스 이중화

```
원본 문서 저장: SQLite or Postgres
    │
    ├─ 문서 메타데이터 (id, date, source, type)
    ├─ 원본 텍스트 (content)
    └─ 편집 이력 추적
    │
    ▼
임베딩 저장: ChromaDB → Qdrant
    │
    ├─ 벡터 임베딩 (OpenAI or bge-m3)
    ├─ 유사도 검색
    └─ 대규모 확장성
```

**이점**:
- 원본 데이터 영구 보존 (SQL)
- 빠른 벡터 검색 (Qdrant)
- 데이터 복구 및 재임베딩 가능

### 8.3 다단계 요약 시스템

```
Daily Summary (매일 자정)
    ├─ 당일 모든 기록 수집
    ├─ LLM 요약 (Claude)
    └─ diary/YYYY-MM-DD.md 생성
    │
    ▼
Weekly Summary (매주 일요일)
    ├─ 지난 7일 Daily Summary 통합
    ├─ 주간 학습 패턴 분석
    └─ diary/week/YYYY-WW.md 생성
    │
    ▼
Monthly Summary (매월 말일)
    ├─ 지난 한 달 Weekly Summary 통합
    ├─ 월간 성장 지표 생성
    └─ diary/month/YYYY-MM.md 생성
```

### 8.4 행동 추천 시스템

```
못한 일 추적
    ├─ TODO 항목 자동 추출
    ├─ 미완료 작업 우선순위 산정
    └─ 알림/리마인더
    │
    ▼
다음 행동 추천
    ├─ 학습 패턴 분석 (ML)
    ├─ 성장 방향 제시
    └─ 커리큘럼 자동 생성
```

### 8.5 임베딩 모델 업그레이드

- **현재**: HuggingFace `all-MiniLM-L6-v2` (로컬, 무료)
- **향후 옵션**:
  - OpenAI `text-embedding-3-small` (성능 향상)
  - `bge-m3` (다국어 지원)
  - Cohere (재랭킹)

### 8.6 벡터 DB 마이그레이션

- **현재**: ChromaDB (간단, Python native)
- **향후**: Qdrant
  - 더 빠른 검색 속도
  - 클라우드 배포 용이
  - 고급 필터링 기능

---

## 9. 보안 및 확장성 고려사항

### 9.1 보안
- **API 키 관리**: `.env` 파일 (git ignore)
- **사용자 인증**: 향후 OAuth 2.0 통합
- **Private Repo 지원**: GitHub Token 인증

### 9.2 확장성
- **다중 사용자**: 컬렉션 분리 (이미 구현)
- **비동기 처리**: FastAPI 비동기 엔드포인트
- **캐싱**: 벡터 검색 결과 캐싱 (Redis)

### 9.3 모니터링
- **로깅**: 각 레이어별 디버그 로그
- **메트릭**: 응답 시간, 임베딩 성능
- **에러 트래킹**: Sentry 통합 (향후)

---

## 10. 참고 문서

- [SETUP.md](../SETUP.md): 설치 및 실행 가이드
- [docs/aidocs/CHROMADB_SERVER_SETUP.md](./aidocs/CHROMADB_SERVER_SETUP.md): ChromaDB 서버 모드 설정
- [README.md](../README.md): 프로젝트 개요 및 사용법

---

## 문서 히스토리
- **2026-07-19**: 초안 작성 (설계 목표 및 현재 구현 상태 문서화)
