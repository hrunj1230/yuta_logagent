# Log Maker 📝

> TIL 기록을 자동으로 일지로 변환하는 AI 에이전트

GitHub에 저장된 TIL(Today I Learned) 마크다운 파일들을 AI가 분석하여 구조화된 개발 일지를 자동으로 생성합니다.

## ✨ 주요 기능

- 🔄 **Git 자동 동기화**: GitHub 저장소 URL만 입력하면 자동으로 TIL 가져오기
- 🤖 **AI 에이전트**: LangGraph 기반 자동 워크플로우
- 📊 **벡터 검색**: ChromaDB로 날짜별 기록 빠른 검색
- 📄 **일지 자동 생성**: Claude Sonnet 4.5가 구조화된 마크다운 일지 작성
- 👥 **다중 사용자**: 사용자별 데이터 격리 및 컬렉션 분리
- 🌐 **웹 UI**: 브라우저에서 간편하게 사용

## 🚀 빠른 시작 (3단계)

```bash
# 1. 설치
pip install -e .

# 2. API 키 설정 (.env 파일 생성)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# 3. 실행
uvicorn main:app --reload
```

브라우저에서 http://localhost:8000/ 접속하면 끝!

## 📚 문서

- **[SETUP.md](SETUP.md)** - 설치 & 실행 가이드 (시작하기!)
- [docs/GIT_SYNC_GUIDE.md](docs/GIT_SYNC_GUIDE.md) - Git 동기화 상세
- [docs/CHROMADB_SERVER_SETUP.md](docs/CHROMADB_SERVER_SETUP.md) - 다중 사용자 설정 (선택)

## 🎯 사용 예시

### 1. Git 저장소 동기화
```bash
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hrun",
    "repo_url": "https://github.com/username/til.git"
  }'
```

### 2. 일지 생성
```bash
curl -X POST "http://localhost:8000/call_agent" \
  -H "Content-Type: application/json" \
  -d '{
    "req": "2026년 6월 29일 일지 작성해줘",
    "thread_id": "user001"
  }'
```

### 3. 결과 확인
```bash
cat logs/2026.06.29_log.md
```

## 🏗️ 아키텍처

```
사용자 → FastAPI → LangGraph Agent → Tools
                         ↓
                    ChromaDB (벡터 검색)
                         ↓
                    Claude AI (일지 생성)
                         ↓
                    logs/YYYY.MM.DD_log.md
```

## 🛠️ 기술 스택

- **FastAPI**: 웹 서버 & REST API
- **LangGraph**: AI Agent 워크플로우
- **ChromaDB**: 벡터 데이터베이스
- **Claude Sonnet 4.5**: LLM (Anthropic)
- **HuggingFace**: 임베딩 모델 (무료, 로컬)

## ✅ 구현 완료

- ✅ 특정 날짜의 daily_log 자동 생성
- ✅ 벡터 DB 조회 후 AI 분석/요약
- ✅ Git 저장소 자동 동기화 & 임베딩
- ✅ 날짜별 검색 (메타데이터 + 유사도)
- ✅ 웹 UI (브라우저에서 간편 사용)

## 🔮 향후 계획

- [ ] 프롬프트 커스터마이징
- [ ] Private 저장소 지원 (GitHub Token)
- [ ] 일지 템플릿 설정
- [ ] JSON/PDF 파일 지원


## 개발 일지

### 2026.07.08
- 프로젝트 세팅
- 구조 작성
- 순서도
- tools정리
- main - router -controller : design pattern 작성
- llm_router 추가 (embedding model - gemini,llm - codex, gemini, claude)
### 2026.07.09
- test graph 구성, 확인
- git
* codexoauth - messages 가 streaming으로 온다. 
* UNSTRUCTURED loader - 15000페이지 무료 데이터 처리? 서비스 정확히 파악 해보면 좋을듯 싶다.

### 2026.07.12
- graph구조 버그 수정
- system_prompt 추가

### 2026.07.13
- maker_logfile tool생성
- 시스템 프롬프트 추가
- 2026.07.09의 codexoauth 의 스트리밍 처리시 tool_calls정보 손실 다시 invoke로 변경
- 벡터 db저장시 TIL파일명의 날짜를 추출하여 내용에 추가(유사도 검색 오류 수정)
- 날짜 벡터 유사도 만으로 검색이 어려워서 메타데이터 필터 추가
- **ChromaDB 서버 모드 구현** (다중 사용자 동시 접근 지원)
  - llm_router.py: HttpClient 자동 감지 + 로컬 모드 폴백
  - tools.py: 서버/로컬 모드 자동 전환
  - docker-compose.yml, Dockerfile 추가
  - migrate_to_server.py: 데이터 마이그레이션 스크립트
  - CHROMADB_QUICKSTART.md: 빠른 시작 가이드

### 2026.07.14
- chromadb
- alex 멘토링 내용 
  - 네이밍 사관원 //추가 사항 이벨류에이션 검증 답안 // 진행해 나갈것들 정리 기록
  - ---------------- mac 키보드 스트로크 추적 / 브라우저 트레킹 /2기 git 코드보고 내일 할일 한 팀이 있었다. / / 
