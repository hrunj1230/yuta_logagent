# 나의 사관일지 📝

> Git 저장소(TIL, 커밋 로그 등)를 임베딩해두고, 대화로 요청하면 AI가 자동으로 개발 일지를 써주는 에이전트

로그인만 하면 챗봇 한 화면에서 "소스 등록", "임베딩", "날짜별 일지 작성"을 모두 대화로 처리합니다.
내부적으로는 LangGraph 기반 단일 Agent가 상황에 맞는 도구를 스스로 연쇄 호출합니다.

## ✨ 주요 기능

- 🤖 **AI 어시스턴트 (단일 Agent)**: "이 저장소 추가해줘", "7월 30일 일지 작성해줘" 같은 대화로 소스 관리 + 일지 생성을 모두 처리
- 🔗 **Git 저장소 등록 + 자동 임베딩**: 소스를 추가하면 Agent가 곧바로 임베딩까지 이어서 실행 (증분 업데이트 지원)
- 📊 **날짜 기반 벡터 검색**: ChromaDB 메타데이터 필터 → 유사도 검색 폴백
- 📄 **일지 자동 생성**: Claude Sonnet 4.5가 검색 결과를 분석해 마크다운 일지 작성 (`logs/YYYY.MM.DD_log.md`)
- 👥 **다중 사용자**: `user_id` 기반 로그인/자동 회원가입, 사용자별 ChromaDB 컬렉션 분리
- 🌐 **웹 UI**: 로그인 → 개인 페이지(AI 어시스턴트) → 설정(소스 목록/삭제) 흐름

## 🚀 빠른 시작

```bash
# 1. 의존성 설치 (uv 사용)
uv sync

# 2. API 키 설정 (.env 파일)
echo "ANTHROPIC_API_KEY=sk-ant-api03-xxxxx" > .env

# 3. 실행
uv run uvicorn main:app --reload
```

브라우저에서 http://localhost:8000/ 접속 → `user_id` 입력하면 바로 시작됩니다.
자세한 설치 과정은 [SETUP.md](SETUP.md) 참고.

## 📚 문서

- **[SETUP.md](SETUP.md)** - 설치 & 실행 가이드 (시작하기!)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - 전체 아키텍처, 데이터 흐름, 알려진 이슈
- [docs/tools-usage.md](docs/tools-usage.md) - 소스/임베딩 도구 사용 예시
- [docs/git-source-type-detection.md](docs/git-source-type-detection.md) - GIT vs GIT_LOG 소스 타입 판단 기준
- [docs/cicd-setup.md](docs/cicd-setup.md) - CI/CD (GitHub Actions → ECR → EC2) 배포 파이프라인

## 🎯 사용 예시

가장 확실하게 동작하는 경로는 웹 UI의 **AI 어시스턴트** 채팅창입니다. 로그인 후 `/user/{user_id}` 페이지에서:

```
"https://github.com/username/til.git 추가해줘"
→ Agent가 소스 등록 후 자동으로 임베딩 시작

"내 소스 목록 보여줘"
→ 등록된 소스와 임베딩 상태 확인

"2026-07-30 일지 작성해줘"
→ 벡터DB 검색 → Claude가 일지 작성 → logs/2026.07.30_log.md 저장
```

같은 요청을 API로 직접 보내려면 (내부적으로 채팅창이 호출하는 것과 동일한 엔드포인트):

```bash
curl -X POST "http://localhost:8000/unified_agent" \
  -F "user_id=hrun" \
  -F "message=2026-07-30 일지 작성해줘"
```

> ⚠️ `log-maker` 페이지의 "Git 동기화"/"일지 생성" 폼(`/sync_git_repo`, `/call_agent`)은
> 현재 알려진 버그로 정상 동작하지 않습니다. 자세한 내용은 [docs/ARCHITECTURE.md의 "알려진 이슈"](docs/ARCHITECTURE.md#7-알려진-이슈-2026-07-31-검증-중-발견)를 참고하세요.

## 🏗️ 아키텍처

```
사용자 → 웹 UI (로그인/개인페이지/설정) → FastAPI (src/router.py)
                                              ↓ /unified_agent
                                  LangGraph 단일 Agent (Claude Sonnet 4.5)
                                              ↓ 도구 호출
                          소스 CRUD · 임베딩 실행 · 날짜 검색+일지 저장
                                              ↓
                        SQLite (사용자/소스 메타데이터) · ChromaDB (벡터, 사용자별 컬렉션)
```

세부 컴포넌트와 데이터 흐름은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에 정리되어 있습니다.

## 🛠️ 기술 스택

- **FastAPI + Jinja2**: 웹 서버 & HTML UI
- **LangGraph**: 단일 Agent 워크플로우 (StateGraph)
- **Claude Sonnet 4.5** (Anthropic): LLM
- **HuggingFace `jhgan/ko-sroberta-multitask`**: 임베딩 모델 (한국어 특화, 로컬 무료 실행)
- **ChromaDB**: 벡터 데이터베이스 (로컬 persistent)
- **SQLite + SQLAlchemy**: 사용자/소스 메타데이터

## ✅ 구현 완료

- ✅ AI 어시스턴트 대화형 소스 관리 (등록 → 자동 임베딩 연쇄 호출)
- ✅ 날짜 기반 일지 자동 생성 (메타데이터 필터 + 유사도 검색 폴백)
- ✅ 다중 사용자 로그인/자동 회원가입 및 데이터 격리
- ✅ 소스 타입별 수집 (git 파일, git 커밋 로그, 로컬 디렉토리)
- ✅ 증분 임베딩 (파일 해시 비교로 변경분만 처리)
- ✅ 웹 UI (로그인/개인페이지/설정 페이지)

## 🔮 향후 계획

- [ ] `/sync_git_repo`, `/call_agent` 버그 수정 (상세: docs/ARCHITECTURE.md 알려진 이슈)
- [ ] 소스 삭제 시 ChromaDB 임베딩도 함께 정리 (현재는 SQLite 레코드만 삭제됨)
- [ ] 프롬프트 커스터마이징
- [ ] Private 저장소 지원 (GitHub Token)
- [ ] 일지 템플릿 설정


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
