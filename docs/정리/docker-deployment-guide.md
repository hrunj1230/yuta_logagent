# Docker 배포 가이드

**프로젝트:** yuta_logagent (FastAPI + LangGraph AI 일지 작성 시스템)
**작성일:** 2026-07-29

---

## 📋 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [Docker 구성 전략](#docker-구성-전략)
3. [파일 구성](#파일-구성)
4. [배포 시나리오별 구성](#배포-시나리오별-구성)
5. [프로덕션 최적화](#프로덕션-최적화)

---

## 🏗️ 아키텍처 개요

### 현재 구성 요소

```
yuta_logagent/
├── FastAPI 애플리케이션 (main.py)
├── SQLite 데이터베이스 (users.db) - 20KB
├── ChromaDB 벡터 저장소 (chroma_db/) - 12MB
├── Git 소스 데이터 (data/sources/) - 4.8MB
├── 템플릿 (templates/)
└── 의존성 (pyproject.toml + uv.lock)
```

### 영구 데이터 (Volume Mount 필요)

| 항목 | 경로 | 크기 | 설명 |
|------|------|------|------|
| 사용자 DB | `./users.db` | 20KB | SQLite (사용자, 소스 메타데이터) |
| 벡터 DB | `./chroma_db/` | 12MB | ChromaDB (임베딩 데이터) |
| 소스 데이터 | `./data/sources/` | 4.8MB | Git clone된 TIL 저장소 |

---

## 🐳 Docker 구성 전략

### 옵션 1: 단일 컨테이너 (간단한 배포)

**특징:**
- FastAPI 앱 + SQLite + ChromaDB 모두 하나의 컨테이너
- 가장 간단한 구성
- 소규모 서비스에 적합

**장점:**
- 배포 간단 (docker run 한 번)
- 네트워크 설정 불필요
- 로컬 개발 환경과 유사

**단점:**
- 확장성 제한
- 백업/복구 시 전체 컨테이너 재시작 필요

**권장 대상:**
- 개인 프로젝트
- PoC/MVP
- 1-10명 사용자

---

### 옵션 2: 멀티 컨테이너 (docker-compose)

**특징:**
- FastAPI 앱 + ChromaDB 서버 분리
- SQLite는 앱 컨테이너에 포함 (작은 용량)

**구성:**
```
services:
  app:        FastAPI 애플리케이션
  chromadb:   ChromaDB 서버 (선택사항)
```

**장점:**
- ChromaDB를 독립적으로 스케일링
- 앱 재시작 시 벡터 DB 영향 없음
- 프로덕션 환경에 가까움

**단점:**
- 설정 복잡도 증가
- 네트워크 설정 필요

**권장 대상:**
- 스타트업 서비스
- 10-100명 사용자
- 향후 확장 계획 있는 경우

---

## 📁 파일 구성

### 1. Dockerfile

```dockerfile
# 멀티스테이지 빌드: 빌드 단계
FROM python:3.12-slim AS builder

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 의존성 파일만 먼저 복사 (캐싱 최적화)
COPY pyproject.toml uv.lock ./

# 의존성 설치 (가상환경 생성)
RUN uv sync --frozen --no-dev

# 애플리케이션 코드 복사
COPY . .

# ============================================
# 실행 단계: 최소 이미지
FROM python:3.12-slim

WORKDIR /app

# Git 설치 (Git clone 기능에 필요)
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 빌드 단계에서 가상환경 복사
COPY --from=builder /app/.venv /app/.venv

# 애플리케이션 코드 복사
COPY --from=builder /app /app

# 환경 변수 설정
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# 데이터 디렉토리 생성
RUN mkdir -p /app/data/sources /app/chroma_db

# 포트 노출
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/', timeout=2)"

# Uvicorn 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**최적화 포인트:**
- 멀티스테이지 빌드로 이미지 크기 최소화 (~200MB 절감)
- uv 공식 이미지 활용으로 빠른 의존성 설치
- 레이어 캐싱 최적화 (의존성 변경 시만 재설치)

---

### 2. docker-compose.yml (단일 컨테이너)

```yaml
version: '3.8'

services:
  app:
    build: .
    container_name: yuta-logagent
    ports:
      - "8000:8000"
    environment:
      # .env 파일에서 자동 로드
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LANGSMITH_API_KEY=${LANGSMITH_API_KEY}
      - LANGSMITH_PROJECT=${LANGSMITH_PROJECT}
      - LANGSMITH_TRACING=${LANGSMITH_TRACING:-false}
    env_file:
      - .env
    volumes:
      # 영구 데이터 마운트
      - ./users.db:/app/users.db
      - ./chroma_db:/app/chroma_db
      - ./data:/app/data
    restart: unless-stopped
    networks:
      - yuta-network

networks:
  yuta-network:
    driver: bridge
```

**사용법:**
```bash
# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

---

### 3. docker-compose.yml (멀티 컨테이너 + ChromaDB 서버)

```yaml
version: '3.8'

services:
  # ChromaDB 서버 (선택사항 - 대규모 임베딩 시 권장)
  chromadb:
    image: ghcr.io/chroma-core/chroma:latest
    container_name: yuta-chromadb
    ports:
      - "8001:8000"
    volumes:
      - chromadb_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE
    networks:
      - yuta-network
    restart: unless-stopped

  # FastAPI 애플리케이션
  app:
    build: .
    container_name: yuta-logagent
    depends_on:
      - chromadb
    ports:
      - "8000:8000"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LANGSMITH_API_KEY=${LANGSMITH_API_KEY}
      - LANGSMITH_PROJECT=${LANGSMITH_PROJECT}
      - LANGSMITH_TRACING=${LANGSMITH_TRACING:-false}
      # ChromaDB 서버 연결
      - CHROMADB_HOST=chromadb
      - CHROMADB_PORT=8000
    env_file:
      - .env
    volumes:
      - ./users.db:/app/users.db
      - ./data:/app/data
      # ChromaDB는 별도 컨테이너 사용
    restart: unless-stopped
    networks:
      - yuta-network

volumes:
  chromadb_data:
    driver: local

networks:
  yuta-network:
    driver: bridge
```

---

### 4. .dockerignore

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/

# 개발 파일
.git/
.gitignore
.pytest_cache/
.coverage
*.log

# 문서
docs/
*.md
!README.md

# IDE
.vscode/
.idea/
*.swp

# 테스트
tests/
test_*.py
check_*.py

# 환경 변수 (런타임에 주입)
.env
.env.*

# 영구 데이터 (볼륨 마운트로 처리)
users.db
users.db.*
chroma_db/
data/

# 백업
*.backup_*
```

---

## 🚀 배포 시나리오별 구성

### 시나리오 1: 로컬 개발 (Docker Desktop)

```bash
# 1. 이미지 빌드
docker build -t yuta-logagent:dev .

# 2. 컨테이너 실행
docker run -d \
  --name yuta-dev \
  -p 8000:8000 \
  -v $(pwd)/users.db:/app/users.db \
  -v $(pwd)/chroma_db:/app/chroma_db \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  yuta-logagent:dev

# 3. 접속
open http://localhost:8000
```

---

### 시나리오 2: AWS EC2 배포

**1. EC2 인스턴스 설정**
```bash
# 권장 스펙
- t3.small (2 vCPU, 2GB RAM) 이상
- Ubuntu 22.04 LTS
- 스토리지: 20GB (데이터 증가 고려)
```

**2. Docker 설치 및 실행**
```bash
# Docker & Docker Compose 설치
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# 프로젝트 클론
git clone <your-repo> yuta_logagent
cd yuta_logagent

# .env 파일 생성
cp .env.example .env
nano .env  # API 키 입력

# 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

**3. 보안 그룹 설정**
- 인바운드 규칙: TCP 8000 (Your IP 또는 특정 대역)
- SSH: TCP 22 (관리용)

**4. NGINX 리버스 프록시 (선택사항)**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

### 시나리오 3: Fly.io / Render.com (PaaS)

**Fly.io 배포**
```bash
# fly.toml 생성
fly launch

# 환경 변수 설정
fly secrets set ANTHROPIC_API_KEY=your_key
fly secrets set GOOGLE_API_KEY=your_key

# 볼륨 생성 (영구 데이터용)
fly volumes create yuta_data --size 1

# 배포
fly deploy
```

**Render.com 배포**
- Dockerfile 자동 인식
- 환경 변수 웹 UI에서 설정
- 무료 티어: 512MB RAM, sleep 모드 (15분 비활성 시)

---

## ⚡ 프로덕션 최적화

### 1. 리소스 제한 (docker-compose)

```yaml
services:
  app:
    # ...
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 2. 로깅 설정

```yaml
services:
  app:
    # ...
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 3. 자동 재시작 정책

```yaml
services:
  app:
    restart: unless-stopped  # 개발
    # restart: always        # 프로덕션
```

### 4. 백업 스크립트

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"

mkdir -p $BACKUP_DIR

# 데이터베이스 백업
cp users.db $BACKUP_DIR/

# ChromaDB 백업
cp -r chroma_db $BACKUP_DIR/

# 소스 데이터 백업 (선택사항)
cp -r data $BACKUP_DIR/

echo "백업 완료: $BACKUP_DIR"
```

**Cron 설정 (매일 새벽 3시)**
```bash
0 3 * * * /path/to/backup.sh
```

---

## 🔧 환경별 권장 구성

| 환경 | 구성 | 이유 |
|------|------|------|
| **로컬 개발** | 단일 컨테이너 | 빠른 빌드/테스트 |
| **스테이징** | 멀티 컨테이너 | 프로덕션과 유사한 환경 |
| **프로덕션** | 멀티 컨테이너 + Reverse Proxy | 확장성, 보안, 모니터링 |
| **개인 프로젝트** | 단일 컨테이너 | 단순성 우선 |
| **팀 프로젝트** | 멀티 컨테이너 | 각 서비스 독립 관리 |

---

## 📊 성능 예측

### 예상 리소스 사용량

**단일 컨테이너 (현재 데이터 기준)**
```
- CPU: 0.5-1.0 vCPU (유휴 시 < 0.1)
- RAM: 500MB-1GB (ChromaDB 포함)
- Disk: 50MB (베이스 이미지) + 20MB (데이터)
- Network: < 100MB/day (API 호출 위주)
```

**멀티 컨테이너**
```
- App 컨테이너: 300-500MB RAM
- ChromaDB 컨테이너: 200-500MB RAM
- 총합: ~1GB RAM
```

### 확장성 목표

| 사용자 수 | 권장 구성 | 인스턴스 |
|-----------|----------|---------|
| 1-10명 | t3.small (1GB) | 단일 |
| 10-50명 | t3.medium (2GB) | 단일 |
| 50-200명 | t3.large (4GB) + Load Balancer | 다중 |

---

## 🛡️ 보안 체크리스트

- [ ] `.env` 파일을 `.gitignore`에 포함
- [ ] 프로덕션에서 `DEBUG=False` 설정
- [ ] API 키를 환경 변수로만 관리 (코드에 하드코딩 금지)
- [ ] HTTPS 설정 (Let's Encrypt + NGINX)
- [ ] Rate Limiting 설정 (FastAPI Middleware)
- [ ] CORS 정책 설정 (필요한 도메인만 허용)
- [ ] 정기 백업 자동화
- [ ] 컨테이너 이미지 보안 스캔 (Docker Scout)

---

## 🚀 빠른 시작 (권장)

**1분 배포 (로컬 테스트)**
```bash
# 1. .env 파일 생성
cp .env.example .env
# API 키 입력

# 2. 빌드 & 실행
docker-compose up --build -d

# 3. 접속
open http://localhost:8000
```

**프로덕션 배포 (AWS EC2)**
```bash
# 1. EC2 인스턴스 접속
ssh ubuntu@your-ec2-ip

# 2. Docker 설치
sudo apt update && sudo apt install -y docker.io docker-compose

# 3. 프로젝트 배포
git clone <repo> yuta_logagent && cd yuta_logagent
cp .env.example .env && nano .env
docker-compose -f docker-compose.prod.yml up -d

# 4. 헬스체크
curl http://localhost:8000/
```

---

## 📚 다음 단계

1. **모니터링 추가**: Prometheus + Grafana
2. **CI/CD 구축**: GitHub Actions으로 자동 배포
3. **스케일링**: Kubernetes로 전환 (사용자 500명 이상 시)
4. **데이터베이스 업그레이드**: SQLite → PostgreSQL (동시 쓰기 성능 향상)

---

## 🔗 참고 자료

- [FastAPI 공식 Docker 가이드](https://fastapi.tiangolo.com/deployment/docker/)
- [uv Docker 사용법](https://github.com/astral-sh/uv#docker)
- [ChromaDB 배포 가이드](https://docs.trychroma.com/deployment)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
