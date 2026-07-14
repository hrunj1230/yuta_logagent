# ChromaDB 서버 모드 설정 가이드

> **문제**: 여러 사용자 동시 접근 시 SQLite 잠금 문제
> **해결**: ChromaDB 서버 모드로 전환

---

## 🎯 왜 서버 모드가 필요한가?

### 현재 구조 (로컬 모드)
```
사용자 A → FastAPI → ./chroma_db/chroma.sqlite3 🔒
사용자 B → FastAPI → ./chroma_db/chroma.sqlite3 ❌ 대기
```

### 서버 모드
```
사용자 A → FastAPI ↘
                    → ChromaDB 서버 → 데이터베이스
사용자 B → FastAPI ↗
```

**장점**:
- ✅ 동시 접근 완전 해결
- ✅ 성능 향상
- ✅ 확장 가능

---

## 🚀 빠른 설정 (5분)

### 1단계: ChromaDB 서버 실행

**Docker 사용 (권장)**:
```bash
docker run -d \
  --name chromadb \
  -p 8001:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma \
  chromadb/chroma:latest
```

**또는 직접 실행**:
```bash
pip install chromadb-server
chroma run --path ./chroma_db --port 8001
```

**확인**:
```bash
curl http://localhost:8001/api/v1/heartbeat
# 응답: {"nanosecond heartbeat": ...}
```

### 2단계: 코드 수정

**llm_router.py에 추가**:
```python
import chromadb
from chromadb.config import Settings
import os

# ChromaDB 클라이언트 설정
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8001"))

chroma_client = chromadb.HttpClient(
    host=CHROMADB_HOST,
    port=CHROMADB_PORT,
    settings=Settings(
        anonymized_telemetry=False
    )
)

print(f"[ChromaDB] 서버 연결: {CHROMADB_HOST}:{CHROMADB_PORT}")
```

**tools.py 수정**:

기존 코드:
```python
vectorstore = Chroma(
    collection_name=collection_name,
    embedding_function=llm_router.local_embedding,
    persist_directory="./chroma_db",  # ❌ 로컬
)
```

새 코드:
```python
vectorstore = Chroma(
    collection_name=collection_name,
    embedding_function=llm_router.local_embedding,
    client=llm_router.chroma_client,  # ✅ 서버
)
```

### 3단계: .env 설정

```bash
# .env
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
```

### 4단계: 서버 재시작

```bash
uvicorn main:app --reload
```

**테스트**:
```bash
curl -X POST "http://localhost:8000/sync_git_repo" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","repo_url":"https://github.com/..."}'
```

---

## 📦 Docker Compose로 한 번에 실행

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  # ChromaDB 서버
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb
    ports:
      - "8001:8000"
    volumes:
      - ./chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Log Maker API
  api:
    build: .
    container_name: log-maker-api
    ports:
      - "8000:8000"
    depends_on:
      chromadb:
        condition: service_healthy
    environment:
      - CHROMADB_HOST=chromadb
      - CHROMADB_PORT=8000
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./repos:/app/repos
      - ./logs:/app/logs
    command: uvicorn main:app --host 0.0.0.0 --port 8000
```

**Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY pyproject.toml ./
RUN pip install -e .

# 소스 복사
COPY . .

# 포트 노출
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**실행**:
```bash
docker-compose up -d
```

---

## 🔄 마이그레이션 (기존 데이터 이전)

기존 로컬 ChromaDB → 서버 모드로 이전:

```python
# migrate_to_server.py
import chromadb
from chromadb.config import Settings

# 1. 로컬 ChromaDB 열기
local_client = chromadb.PersistentClient(path="./chroma_db")

# 2. 서버 ChromaDB 연결
server_client = chromadb.HttpClient(
    host="localhost",
    port=8001,
    settings=Settings(anonymized_telemetry=False)
)

# 3. 모든 컬렉션 복사
for collection in local_client.list_collections():
    print(f"마이그레이션: {collection.name}")

    # 로컬에서 데이터 가져오기
    local_coll = local_client.get_collection(collection.name)
    all_data = local_coll.get()

    # 서버에 컬렉션 생성
    server_coll = server_client.get_or_create_collection(collection.name)

    # 데이터 추가
    if all_data['ids']:
        server_coll.add(
            ids=all_data['ids'],
            documents=all_data['documents'],
            metadatas=all_data['metadatas'],
            embeddings=all_data['embeddings']
        )

    print(f"✅ {len(all_data['ids'])}개 문서 이전 완료")

print("마이그레이션 완료!")
```

**실행**:
```bash
python migrate_to_server.py
```

---

## 🛠️ 트러블슈팅

### Q1. "Connection refused" 에러

```bash
# ChromaDB 서버 실행 확인
docker ps | grep chromadb

# 서버 로그 확인
docker logs chromadb

# 포트 확인
netstat -an | grep 8001
```

### Q2. 기존 데이터가 안 보임

**원인**: 로컬 → 서버로 마이그레이션 필요

**해결**: 위 마이그레이션 스크립트 실행

### Q3. 서버 모드가 느림

**원인**: 네트워크 오버헤드

**해결**:
```yaml
# docker-compose.yml
# 같은 네트워크에서 실행
networks:
  default:
    driver: bridge
```

---

## 📊 성능 비교

### 로컬 모드
- 동시 쓰기: 1개
- 지연시간: ~10ms
- 확장성: ❌

### 서버 모드
- 동시 쓰기: 무제한
- 지연시간: ~20ms (네트워크)
- 확장성: ✅

---

## 🎯 결론

### 개발 환경 (소규모)
```
✅ 로컬 모드 OK
- 혼자 사용
- 동시 접근 없음
```

### 프로덕션 (다수 사용자)
```
✅ 서버 모드 필수
- 여러 사용자 동시 접근
- 안정성 중요
```

**추천**: 지금 서버 모드로 전환하세요! (5분 소요)

```bash
docker run -d -p 8001:8000 chromadb/chroma
# llm_router.py 수정
# tools.py 수정
# 완료!
```
