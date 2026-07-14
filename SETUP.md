# 설치 & 실행 가이드 🚀

> 3단계로 끝나는 간단한 설정

---

## 1️⃣ 설치

```bash
# 프로젝트 클론
cd yuta_bot

# 의존성 설치
pip install -e .
```

---

## 2️⃣ API 키 설정

`.env` 파일 생성:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx
```

**API 키 발급 방법**:
1. https://console.anthropic.com/ 접속
2. Settings → API Keys
3. "Create Key" 클릭
4. 생성된 키 복사

---

## 3️⃣ 실행

```bash
uvicorn main:app --reload
```

**예상 출력**:
```
[ChromaDB] 📁 로컬 모드 사용: ./chroma_db
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## ✅ 확인

브라우저에서 http://localhost:8000/ 접속

웹 UI가 보이면 성공! 🎉

---

## 📝 사용 방법

### 1. Git 저장소 동기화

웹 UI에서:
- 사용자 ID: `hrun`
- Git 저장소 URL: `https://github.com/username/til.git`
- "동기화 & 임베딩 시작" 클릭

### 2. 일지 생성

웹 UI에서:
- 사용자 ID: `hrun` (위와 동일)
- 날짜: `2026년 6월 29일`
- "일지 생성" 클릭

### 3. 결과 확인

```bash
cat logs/2026.06.29_log.md
```

---

## 🛠️ 문제 해결

### "Invalid API Key" 에러

`.env` 파일 확인:
```bash
cat .env
```

서버 재시작:
```bash
uvicorn main:app --reload
```

### "해당 날짜 기록 없음"

1. Git 동기화 먼저 실행
2. 파일명 형식 확인 (예: `2026_06_29.md`)

---

## 📚 자세한 문서

- **README.md** - 프로젝트 소개
- **docs/GIT_SYNC_GUIDE.md** - Git 동기화 상세
- **docs/CHROMADB_SERVER_SETUP.md** - 다중 사용자 설정 (선택)

---

**끝! 이제 사용하세요 😊**
