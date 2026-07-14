# Quick Reference 🚀

> 자주 사용하는 명령어 모음

---

## 🎬 첫 실행

```bash
# 1. 설치
pip install -e .

# 2. API 키 설정 (.env 파일)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# 3. 서버 시작
uvicorn main:app --reload
```

---

## 🌐 웹 UI

```
http://localhost:8000/
```

1. Git 저장소 URL 입력 → "동기화" 클릭
2. 날짜 입력 → "일지 생성" 클릭
3. `logs/YYYY.MM.DD_log.md` 파일 확인

---

## 📡 API 사용

### Git 동기화
```bash
curl -X POST http://localhost:8000/sync_git_repo \
  -H "Content-Type: application/json" \
  -d '{"user_id":"hrun","repo_url":"https://github.com/user/til.git"}'
```

### 일지 생성
```bash
curl -X POST http://localhost:8000/call_agent \
  -H "Content-Type: application/json" \
  -d '{"req":"2026년 6월 29일 일지 작성해줘","thread_id":"test"}'
```

---

## 🐳 Docker

### ChromaDB 서버만
```bash
docker-compose up -d chromadb
```

### 전체 스택
```bash
docker-compose up -d
```

### 중지
```bash
docker-compose down
```

---

## 🗂️ 파일 위치

```
repos/{user_id}/     # Git clone 위치
chroma_db/           # 벡터 DB (로컬 모드)
chroma_data/         # 벡터 DB (서버 모드)
logs/                # 생성된 일지
```

---

## 🔍 확인 명령어

```bash
# 서버 상태
curl http://localhost:8000/

# ChromaDB 서버 상태
curl http://localhost:8001/api/v1/heartbeat

# Git clone 확인
ls -la repos/

# 일지 파일 확인
ls -la logs/
cat logs/2026.06.29_log.md

# 프로세스 확인
ps aux | grep uvicorn
docker ps
```

---

## ⚠️ 트러블슈팅

### "Connection refused"
```bash
# 정상 (자동 로컬 모드)
[ChromaDB] 📁 로컬 모드 사용

# 서버 모드 원하면
docker-compose up -d chromadb
```

### "해당 날짜 기록 없음"
```bash
# Git 동기화 먼저
curl -X POST http://localhost:8000/sync_git_repo ...

# 파일명 형식 확인
ls repos/hrun/
# OK: 2026_06_29.md, 2026-06-29.md
```

### "API Key 에러"
```bash
# .env 파일 확인
cat .env | grep ANTHROPIC

# 서버 재시작
uvicorn main:app --reload
```

### "database is locked"
```bash
# 서버 모드로 전환
docker-compose up -d chromadb
```

---

## 🔄 데이터 마이그레이션

```bash
# 로컬 → 서버 모드
docker-compose up -d chromadb
python migrate_to_server.py
```

---

## 📊 모드 선택

| 상황 | 모드 |
|------|------|
| 혼자 개발 | 로컬 |
| 팀 개발 | 서버 |
| 웹 배포 | 서버 |

---

## 📚 자세한 문서

- **USER_GUIDE.md** - 전체 가이드
- **CHROMADB_QUICKSTART.md** - ChromaDB 설정
- **GIT_SYNC_GUIDE.md** - Git 동기화

---

**Happy Logging! 📝✨**
