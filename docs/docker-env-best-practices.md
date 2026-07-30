# Docker 환경 변수 관리 베스트 프랙티스

**핵심 원칙:** `.env` 파일은 절대 Docker 이미지에 포함하지 않는다

---

## 🚫 하지 말아야 할 것

### ❌ 안티패턴 1: 이미지에 .env 포함

```dockerfile
# 나쁜 예
FROM python:3.12
COPY .env /app/.env  # ❌ 절대 금지!
```

**문제점:**
- 🔓 API 키가 이미지에 하드코딩됨
- 🔓 누구나 이미지에서 추출 가능
- 🔓 Docker Hub 공개 시 비밀 정보 노출
- 🔓 환경별 설정 변경 불가

---

### ❌ 안티패턴 2: ENV로 하드코딩

```dockerfile
# 나쁜 예
FROM python:3.12
ENV GOOGLE_API_KEY="AIza..."  # ❌ 하드코딩 금지!
```

**문제점:**
- 동일한 보안 문제
- `docker history` 명령으로 값 노출

---

## ✅ 올바른 방법들

### 방법 1: `.dockerignore` + 런타임 주입 (가장 일반적 ⭐)

**1단계: `.dockerignore`에 추가**
```
# .dockerignore
.env
.env.*
!.env.example
```

**2단계: Docker Compose로 주입**
```yaml
# docker-compose.yml
services:
  app:
    build: .
    env_file:
      - .env  # 런타임에 주입 ✅
```

**3단계: 프로덕션에서**
```bash
# 환경 변수로 직접 전달
docker run -e GOOGLE_API_KEY="$GOOGLE_API_KEY" myapp

# 또는 파일에서 로드
docker run --env-file .env myapp
```

**장점:**
- ✅ 이미지에 비밀 정보 없음
- ✅ 환경별로 다른 설정 사용 가능
- ✅ CI/CD에서 안전하게 주입 가능

---

### 방법 2: Docker Secrets (Swarm/Compose v3.1+)

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  app:
    image: myapp
    secrets:
      - google_api_key
      - anthropic_api_key

secrets:
  google_api_key:
    file: ./secrets/google_api_key.txt
  anthropic_api_key:
    file: ./secrets/anthropic_api_key.txt
```

**코드에서 읽기:**
```python
# src/config.py
def read_secret(secret_name):
    try:
        with open(f'/run/secrets/{secret_name}') as f:
            return f.read().strip()
    except FileNotFoundError:
        return os.getenv(secret_name.upper())

GOOGLE_API_KEY = read_secret('google_api_key')
```

**장점:**
- ✅ 암호화된 저장
- ✅ 권한 관리 가능
- ✅ 프로덕션급 보안

**단점:**
- ❌ Docker Swarm 필요 (또는 Compose v2의 제한적 지원)
- ❌ 로컬 개발 복잡도 증가

---

### 방법 3: 빌드 ARG vs 런타임 ENV 구분

**빌드 시점에 필요한 변수:**
```dockerfile
# Dockerfile
ARG NODE_ENV=production  # 빌드 시점
RUN npm install --only=${NODE_ENV}

# 런타임 환경 변수
ENV PORT=8000
```

**사용:**
```bash
# 빌드
docker build --build-arg NODE_ENV=development -t myapp .

# 실행
docker run -e GOOGLE_API_KEY="..." myapp
```

**중요:**
- `ARG`: 빌드 시 사용, 이미지에 저장 안됨
- `ENV`: 런타임 환경 변수, 이미지에 저장됨

---

## 📁 환경별 파일 관리

### 구조

```
project/
├── .env.example          # 템플릿 (Git에 포함 ✅)
├── .env                  # 로컬 개발 (Git 제외 ❌)
├── .env.development      # 개발 환경 (Git 제외 ❌)
├── .env.staging          # 스테이징 (Git 제외 ❌)
├── .env.production       # 프로덕션 (Git 제외 ❌)
└── .dockerignore
```

**`.env.example` (템플릿):**
```bash
# API Keys
GOOGLE_API_KEY=your_google_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# LangSmith (optional)
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=your_project_name
```

**`.gitignore`:**
```
.env
.env.*
!.env.example
```

---

## 🏗️ 환경별 배포 전략

### 로컬 개발

```bash
# .env 파일 생성
cp .env.example .env
# API 키 입력

# Docker Compose 실행
docker-compose up
```

---

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build image
        run: docker build -t myapp .

      - name: Run with secrets
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          docker run -d \
            -e GOOGLE_API_KEY \
            -e ANTHROPIC_API_KEY \
            myapp
```

**GitHub Secrets 설정:**
- Repository → Settings → Secrets and variables → Actions
- New repository secret 클릭
- `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY` 등 추가

---

### AWS (ECS/Fargate)

**방법 1: Parameter Store**
```bash
# AWS Systems Manager Parameter Store에 저장
aws ssm put-parameter \
  --name "/myapp/google_api_key" \
  --value "AIza..." \
  --type SecureString

# ECS Task Definition에서 참조
{
  "secrets": [
    {
      "name": "GOOGLE_API_KEY",
      "valueFrom": "/myapp/google_api_key"
    }
  ]
}
```

**방법 2: Secrets Manager**
```json
{
  "secrets": [
    {
      "name": "GOOGLE_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:region:account:secret:myapp-secrets"
    }
  ]
}
```

---

### Kubernetes

**Secret 생성:**
```bash
kubectl create secret generic api-keys \
  --from-literal=google-api-key='AIza...' \
  --from-literal=anthropic-api-key='sk-ant-...'
```

**Pod에서 사용:**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  containers:
  - name: app
    image: myapp
    env:
    - name: GOOGLE_API_KEY
      valueFrom:
        secretKeyRef:
          name: api-keys
          key: google-api-key
    - name: ANTHROPIC_API_KEY
      valueFrom:
        secretKeyRef:
          name: api-keys
          key: anthropic-api-key
```

---

## 🔒 보안 체크리스트

### 빌드 시점
- [ ] `.env`가 `.dockerignore`에 포함되어 있는가?
- [ ] `.env`가 `.gitignore`에 포함되어 있는가?
- [ ] `.env.example` 템플릿만 Git에 포함되어 있는가?
- [ ] Dockerfile에 하드코딩된 비밀 정보가 없는가?

### 런타임
- [ ] 환경 변수로 비밀 정보를 주입하는가?
- [ ] 프로덕션에서 안전한 비밀 관리 시스템을 사용하는가? (Secrets Manager 등)
- [ ] 로그에 비밀 정보가 출력되지 않는가?

### 이미지 검증
```bash
# 이미지에 비밀 정보가 포함되었는지 확인
docker history myapp:latest | grep -i "api_key"  # 비어있어야 함
docker run --rm myapp env | grep -i "api_key"    # 값이 없어야 함
```

---

## 📊 방법별 비교

| 방법 | 로컬 개발 | CI/CD | 프로덕션 | 보안 | 복잡도 |
|------|----------|-------|---------|------|--------|
| **env_file** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ |
| **Docker Secrets** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **K8s Secrets** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **AWS Secrets Mgr** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **환경 변수 직접** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

---

## 🎯 프로젝트별 추천

### 개인 프로젝트 / MVP
```
✅ docker-compose.yml + env_file
✅ .env (로컬)
✅ 환경 변수 직접 전달 (프로덕션)
```

### 스타트업 / 중소 프로젝트
```
✅ docker-compose.yml + env_file (개발)
✅ GitHub Secrets (CI/CD)
✅ AWS Parameter Store (프로덕션)
```

### 엔터프라이즈
```
✅ Kubernetes Secrets
✅ HashiCorp Vault
✅ AWS Secrets Manager
✅ 감사 로그 & 자동 로테이션
```

---

## 💡 yuta_logagent 프로젝트 현재 상태

### 현재 구성 ✅
```
1. .dockerignore에 .env 포함 ✅
2. docker-compose.yml에서 env_file 사용 ✅
3. .env.example 템플릿 제공 ✅
```

### 개선 제안

**1. `.env.example` 업데이트**
```bash
# .env.example

# LLM API Keys
GOOGLE_API_KEY=your_google_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# LangSmith (선택사항 - 디버깅용)
LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=yuta-rag

# HuggingFace (선택사항 - rate limit 증가)
HF_TOKEN=your_huggingface_token_here

# ChromaDB (멀티 컨테이너 구성 시)
CHROMADB_HOST=localhost
CHROMADB_PORT=8001
```

**2. README.md에 설정 가이드 추가**
```markdown
## 환경 설정

1. `.env` 파일 생성:
   ```bash
   cp .env.example .env
   ```

2. API 키 입력:
   - ANTHROPIC_API_KEY: https://console.anthropic.com/
   - GOOGLE_API_KEY (선택): https://makersuite.google.com/app/apikey

3. 실행:
   ```bash
   docker-compose up -d
   ```
```

**3. 프로덕션 배포 시**
```bash
# AWS EC2/Fargate
# Parameter Store에 저장 후 환경 변수로 주입

# 또는 직접 전달
docker run -d \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
  -p 8000:8000 \
  yuta-logagent
```

---

## 🔍 디버깅

### 환경 변수가 주입되었는지 확인

```bash
# 컨테이너 내부 환경 변수 확인
docker exec yuta-logagent env | grep API_KEY

# 예상 출력:
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...

# 출력이 없다면 주입 실패
```

### .env 파일 로드 확인

```bash
# docker-compose.yml 검증
docker-compose config

# env_file이 올바르게 설정되었는지 확인
```

---

## 📚 참고 자료

- [Docker Environment Variables](https://docs.docker.com/compose/environment-variables/)
- [Docker Secrets](https://docs.docker.com/engine/swarm/secrets/)
- [12 Factor App - Config](https://12factor.net/config)
- [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

---

## ⚡ Quick Reference

| 상황 | 해결 방법 |
|------|----------|
| **로컬 개발** | `docker-compose.yml` + `env_file: - .env` |
| **CI/CD** | GitHub Secrets → 환경 변수로 주입 |
| **AWS** | Parameter Store/Secrets Manager |
| **Kubernetes** | `kubectl create secret` |
| **이미지 공유** | 절대 .env 포함 금지! 런타임 주입만 |

---

**핵심 원칙 요약:**
1. ❌ 이미지에 비밀 정보 포함 금지
2. ✅ `.dockerignore`에 `.env` 추가
3. ✅ 런타임에 환경 변수로 주입
4. ✅ 환경별로 다른 설정 파일 사용
5. ✅ 프로덕션은 안전한 비밀 관리 시스템 사용

---

**작성일:** 2026-07-29
**프로젝트:** yuta_logagent
