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
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/', timeout=2)"

# Uvicorn 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
