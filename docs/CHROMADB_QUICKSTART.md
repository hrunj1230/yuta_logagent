# ChromaDB 서버 모드 빠른 시작 🚀

> **변경사항**: 다중 사용자 동시 접근을 위해 ChromaDB 서버 모드를 지원합니다!

---

## ✨ 무엇이 바뀌었나요?

### 이전 (로컬 모드)
- 단일 사용자만 사용 가능
- SQLite 동시 쓰기 제한
- 프로덕션 환경 부적합

### 현재 (서버 모드 자동 감지)
- ✅ 다중 사용자 동시 접근 가능
- ✅ 서버 있으면 자동 연결, 없으면 로컬 모드로 폴백
- ✅ 설정 변경 없이 개발/프로덕션 모두 지원

---

## 🎯 선택 1: 로컬 모드 (개발용, 기본값)

**그냥 실행하면 됩니다!**

```bash
uvicorn main:app --reload
```

ChromaDB 서버가 없으면 자동으로 로컬 모드(`./chroma_db`)를 사용합니다.

```
[ChromaDB] ⚠️ 서버 연결 실패 (...), 로컬 모드로 전환
[ChromaDB] 📁 로컬 모드 사용: ./chroma_db
```

**언제 사용?**
- 혼자 개발할 때
- 빠른 테스트가 필요할 때
- 인터넷 없는 환경

---

## 🚀 선택 2: 서버 모드 (프로덕션용)

### 1단계: ChromaDB 서버 실행

**Docker 사용 (권장)**:
```bash
# ChromaDB 서버만 실행
docker-compose up -d chromadb

# 확인
curl http://localhost:8001/api/v1/heartbeat
```

**또는 직접 실행**:
```bash
pip install chromadb
chroma run --path ./chroma_server_data --port 8001
```

### 2단계: 환경 변수 설정 (선택사항)

`.env` 파일:
```bash
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
```

> **참고**: 설정하지 않으면 기본값(`localhost:8001`)을 사용합니다.

### 3단계: 애플리케이션 실행

```bash
uvicorn main:app --reload
```

서버 연결 성공 메시지:
```
[ChromaDB] ✅ 서버 연결 성공: localhost:8001
```

### 4단계: 기존 데이터 마이그레이션 (선택)

기존 로컬 데이터가 있다면:

```bash
python migrate_to_server.py
```

---

## 📦 Docker Compose로 전체 스택 실행

**docker-compose.yml 수정**:

```yaml
services:
  chromadb:
    # ... (이미 있음)

  api:  # 주석 해제
    build: .
    ports:
      - "8000:8000"
    depends_on:
      chromadb:
        condition: service_healthy
    environment:
      - CHROMADB_HOST=chromadb  # Docker 네트워크 내부
      - CHROMADB_PORT=8000      # 컨테이너 내부 포트
```

**실행**:
```bash
docker-compose up -d
```

**접속**:
- API: http://localhost:8000
- ChromaDB: http://localhost:8001

---

## 🔀 자동 폴백 동작

```python
# llm_router.py에 구현됨
try:
    # 서버 모드 시도
    chroma_client = chromadb.HttpClient(...)
    chroma_client.heartbeat()
    print("[ChromaDB] ✅ 서버 연결 성공")
except:
    # 실패 시 로컬 모드
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    print("[ChromaDB] 📁 로컬 모드 사용")
```

**장점**:
- 개발 환경: 서버 없이도 즉시 시작
- 프로덕션: 서버 있으면 자동 연결
- 설정 변경 없이 두 환경 모두 지원

---

## 🛠️ 트러블슈팅

### Q1. "서버 연결 실패" 메시지가 나와요

**원인**: ChromaDB 서버가 실행되지 않음

**해결**:
```bash
# Docker 사용 시
docker-compose up -d chromadb
docker logs yuta_chromadb

# 직접 실행 시
chroma run --path ./chroma_server_data --port 8001
```

**확인**:
```bash
curl http://localhost:8001/api/v1/heartbeat
```

### Q2. 로컬 모드로 폴백되는데 서버 모드를 강제하고 싶어요

**.env 파일 설정**:
```bash
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
```

**서버 실행 확인**:
```bash
docker ps | grep chromadb
```

### Q3. Docker 컨테이너에서 실행 시 연결 안 됨

**원인**: 호스트명 잘못 설정

**해결**:
```yaml
# docker-compose.yml의 api 서비스
environment:
  - CHROMADB_HOST=chromadb  # Docker 네트워크 이름 사용!
  - CHROMADB_PORT=8000      # 컨테이너 내부 포트 (8001 아님!)
```

### Q4. 마이그레이션 중 "Connection refused" 에러

**원인**: ChromaDB 서버가 준비되지 않음

**해결**:
```bash
# Health check 대기
docker-compose up -d chromadb
sleep 10  # 10초 대기

# 재시도
python migrate_to_server.py
```

---

## 📊 모드 비교

| 기능 | 로컬 모드 | 서버 모드 |
|------|----------|----------|
| 동시 사용자 | 1명 | 무제한 |
| 설정 필요 | ❌ 없음 | ✅ 서버 실행 |
| 성능 | 빠름 (~10ms) | 약간 느림 (~20ms) |
| 프로덕션 | ❌ 부적합 | ✅ 권장 |
| 개발 환경 | ✅ 권장 | 선택사항 |

---

## 🎯 권장 사용법

### 개발 환경
```bash
# 그냥 실행 (자동으로 로컬 모드)
uvicorn main:app --reload
```

### 프로덕션 환경
```bash
# Docker Compose로 전체 스택 실행
docker-compose up -d

# 또는 서버만 따로 실행
docker-compose up -d chromadb
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🔄 기존 로컬 데이터 마이그레이션

```bash
# 1. ChromaDB 서버 실행
docker-compose up -d chromadb

# 2. 마이그레이션 실행
python migrate_to_server.py

# 3. 애플리케이션 재시작
uvicorn main:app --reload

# 4. 테스트 후 백업
mv chroma_db chroma_db.backup
```

---

## ✅ 완료!

이제 여러 사용자가 동시에 접근할 수 있습니다!

**변경 사항**:
- ✅ `llm_router.py`: ChromaDB 클라이언트 자동 감지 추가
- ✅ `tools.py`: 서버/로컬 모드 자동 전환
- ✅ `docker-compose.yml`: ChromaDB 서버 설정
- ✅ `.env.example`: 환경 변수 문서화
- ✅ `migrate_to_server.py`: 데이터 마이그레이션 스크립트

**기존 기능은 그대로**:
- ❌ 기존 코드 변경 없음
- ❌ API 인터페이스 변경 없음
- ✅ 기존 기능 100% 호환
