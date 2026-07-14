# Git 동기화 기능 사용 가이드

> **새로운 기능**: Git 저장소 URL만 입력하면 자동으로 TIL을 가져와서 임베딩합니다!

---

## ✨ 추가된 기능

### 1. Git 저장소 동기화 API
- 엔드포인트: `POST /sync_git_repo`
- Git 저장소를 clone하고 자동으로 임베딩
- 사용자별 ChromaDB 컬렉션 생성

### 2. 웹 UI
- URL: `http://localhost:8000/`
- Git 저장소 URL 입력만으로 간편 동기화
- 일지 생성까지 한 페이지에서 완료

---

## 🚀 빠른 시작

### 1단계: 서버 실행

```bash
uvicorn main:app --reload
```

### 2단계: 웹 브라우저 열기

```
http://localhost:8000/
```

### 3단계: Git 저장소 동기화

**입력 항목**:
- **사용자 ID**: `hrun` (또는 원하는 ID)
- **Git 저장소 URL**: `https://github.com/username/Yuta_TIL.git`
- **브랜치**: `main` (기본값)

**"동기화 & 임베딩 시작" 버튼 클릭**

### 4단계: 일지 생성

**입력 항목**:
- **사용자 ID**: `hrun` (위와 동일)
- **날짜**: `2026년 5월 14일`

**"일지 생성" 버튼 클릭**

**결과**: `logs/2026.05.14_log.md` 파일 생성!

---

## 📡 API 사용법

### Git 동기화 API

**엔드포인트**:
```
POST /sync_git_repo
```

**요청 본문**:
```json
{
  "user_id": "hrun",
  "repo_url": "https://github.com/username/Yuta_TIL.git",
  "branch": "main"
}
```

**cURL 예시**:
```bash
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hrun",
    "repo_url": "https://github.com/username/Yuta_TIL.git",
    "branch": "main"
  }'
```

**성공 응답**:
```json
{
  "success": true,
  "message": "Git 동기화 및 임베딩 완료",
  "user_id": "hrun",
  "repo_url": "https://github.com/username/Yuta_TIL.git",
  "branch": "main",
  "local_path": "./repos/hrun",
  "embedding_result": "✅ 사용자 'hrun': 41개 문서 임베딩 완료 (컬렉션: user_hrun)"
}
```

**실패 응답**:
```json
{
  "success": false,
  "error": "Git clone 실패",
  "details": "fatal: repository 'https://...' not found"
}
```

---

## 🗂️ 디렉토리 구조

```
yuta_bot/
├── repos/              # Git 저장소 clone 위치
│   ├── hrun/          # 사용자별 디렉토리
│   │   ├── 2026_05_14.md
│   │   ├── 2026_06_29.md
│   │   └── README.md
│   └── user_alice/
├── chroma_db/          # 벡터 DB
│   ├── user_hrun/     # 사용자별 컬렉션
│   └── user_alice/
├── logs/               # 생성된 일지
│   ├── 2026.05.14_log.md
│   └── 2026.06.29_log.md
└── static/             # 웹 UI
    └── index.html
```

---

## 🔄 기존 기능과의 관계

### 기존 기능 (유지됨)
```python
# 1. 로컬 경로 임베딩 (기존 방식)
POST /embed
{
  "path": "../Yuta_TIL"
}

# 2. 일지 생성 (기존 방식)
POST /call_agent
{
  "req": "2026년 5월 14일 일지 작성해줘",
  "thread_id": "test123"
}
```

### 새로운 기능 (추가됨)
```python
# 3. Git 동기화 (새 기능!)
POST /sync_git_repo
{
  "user_id": "hrun",
  "repo_url": "https://github.com/username/Yuta_TIL.git"
}
```

**두 방식 모두 사용 가능합니다!**

---

## 📝 사용자별 데이터 격리

### ChromaDB 컬렉션 구조

**사용자별로 완전히 분리됨**:

```
chroma_db/
├── user_hrun/          # hrun 사용자 데이터
│   ├── 2026_05_14.md
│   └── 2026_06_29.md
└── user_alice/         # alice 사용자 데이터
    └── 2026_07_01.md
```

### 검색 시 자동 필터링

**현재 구현 (자동 격리 없음)**:
```python
# 모든 사용자가 같은 ChromaDB 조회
retriever_vectordb(date="2026-05-14")
```

**향후 개선 (user_id로 자동 필터링)**:
```python
# 사용자별 ChromaDB 조회
retriever_vectordb_for_user(user_id="hrun", date="2026-05-14")
```

> **참고**: 현재는 사용자별 임베딩만 구현되었습니다. 일지 생성 시 사용자 필터링은 추후 업데이트 예정입니다.

---

## 🛠️ 추가 구현 사항

### 추가된 파일

**1. src/router.py**
- `/sync_git_repo` 엔드포인트 추가
- `GitSyncReq` Pydantic 모델 추가

**2. src/tools.py**
- `embedding_file_for_user()` 함수 추가
- 사용자별 컬렉션 생성 로직

**3. static/index.html**
- Git 동기화 웹 UI
- 일지 생성 폼

**4. main.py**
- Static 파일 서빙 설정
- 루트 경로 (`/`) → `index.html`

### 기존 코드 변경사항

**❌ 없음!** - 모든 기존 기능은 그대로 유지됩니다.

---

## 🎯 사용 시나리오

### 시나리오 1: 개인 사용 (Public 저장소)

```bash
# 1. Git 동기화
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hrun",
    "repo_url": "https://github.com/hrun/Yuta_TIL.git"
  }'

# 2. 일지 생성
curl -X POST "http://localhost:8000/call_agent" \
  -H "Content-Type: application/json" \
  -d '{
    "req": "2026년 6월 29일 일지 작성해줘",
    "thread_id": "test123"
  }'

# 3. 결과 확인
cat logs/2026.06.29_log.md
```

### 시나리오 2: Private 저장소 (Personal Access Token)

**현재 미지원** - 추후 업데이트 예정

향후 구현 시:
```bash
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hrun",
    "repo_url": "https://github.com/hrun/private-til.git",
    "github_token": "ghp_xxxxxxxxxxxx"
  }'
```

### 시나리오 3: 정기적 동기화

**Cron 작업으로 자동화**:

```bash
# crontab -e
# 매일 오전 9시에 동기화
0 9 * * * curl -X POST "http://localhost:8000/sync_git_repo" -H "Content-Type: application/json" -d '{"user_id":"hrun","repo_url":"https://github.com/hrun/Yuta_TIL.git"}'
```

---

## 🐛 트러블슈팅

### Q1. "Git clone 실패" 에러

**증상**:
```json
{
  "error": "Git clone 실패",
  "details": "fatal: repository 'https://...' not found"
}
```

**해결**:
1. 저장소 URL 확인 (오타, 존재 여부)
2. Public 저장소인지 확인
3. Git 설치 확인: `git --version`

### Q2. 임베딩은 되는데 검색이 안 됨

**원인**: 사용자별 컬렉션 분리 때문

**현재 상황**:
- 임베딩: `user_hrun` 컬렉션에 저장 ✅
- 검색: 기본 컬렉션에서 조회 ❌

**임시 해결책**:
- 로컬 개발 시 같은 user_id 사용
- 또는 기존 `/embed` 엔드포인트 사용

**완전한 해결책** (추후 업데이트):
- `retriever_vectordb_for_user()` 구현
- controller.py에서 user_id 전달

### Q3. 웹 페이지가 안 열림

**확인**:
```bash
# Static 디렉토리 존재 확인
ls -la static/

# 서버 재시작
uvicorn main:app --reload

# 브라우저에서
http://localhost:8000/
```

---

## 🔮 향후 개선 계획

### Phase 1 (완료)
- [x] Git clone 기본 구현
- [x] 사용자별 임베딩
- [x] 웹 UI

### Phase 2 (예정)
- [ ] Private 저장소 지원 (GitHub Token)
- [ ] 사용자별 일지 생성 (user_id 필터링)
- [ ] 증분 동기화 (변경된 파일만)

### Phase 3 (예정)
- [ ] GitHub 웹훅 자동 동기화
- [ ] GitLab, Bitbucket 지원
- [ ] 동기화 이력 조회

---

## 📚 참고 자료

- [Git 기본 명령어](https://git-scm.com/docs)
- [FastAPI Static Files](https://fastapi.tiangolo.com/tutorial/static-files/)
- [ChromaDB Collections](https://docs.trychroma.com/guides/collections)

---

**질문이나 문제가 있으면 이슈를 남겨주세요!**
