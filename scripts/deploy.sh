#!/bin/bash
# EC2에서 SSM Run Command로 실행되는 배포 스크립트.
# __IMAGE_TAG__는 GitHub Actions 워크플로우가 실제 값(커밋 SHA)으로 치환한다.
set -e

REGION="ap-southeast-2"
ECR_REGISTRY="394281571346.dkr.ecr.ap-southeast-2.amazonaws.com"
ECR_REPOSITORY="yuta-logagent"
IMAGE_TAG="__IMAGE_TAG__"
IMAGE="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
DATA_DIR="/home/ec2-user/yuta-logagent-data"

echo "Deploying ${IMAGE}"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$IMAGE"

# SSM Parameter Store(/yuta-logagent/prod/*)의 시크릿을 런타임에 -e 플래그로 주입
ENV_ARGS=""
for name in $(aws ssm get-parameters-by-path --path /yuta-logagent/prod/ --with-decryption \
    --query 'Parameters[*].Name' --output text --region "$REGION"); do
  key=$(basename "$name")
  value=$(aws ssm get-parameter --name "$name" --with-decryption \
    --query 'Parameter.Value' --output text --region "$REGION")
  ENV_ARGS="$ENV_ARGS -e ${key}=${value}"
done

# logs/*.md가 일지의 진실 공급원이고 chroma_db는 파생 색인이므로,
# 색인만 남고 원본이 사라지지 않도록 logs도 같이 영구 마운트한다.
mkdir -p "$DATA_DIR/chroma_db" "$DATA_DIR/data" "$DATA_DIR/logs"
touch "$DATA_DIR/users.db"

docker rm -f yuta-logagent 2>/dev/null || true

# shellcheck disable=SC2086
docker run -d \
  --name yuta-logagent \
  --restart unless-stopped \
  -p 8000:8000 \
  -v "$DATA_DIR/users.db:/app/users.db" \
  -v "$DATA_DIR/chroma_db:/app/chroma_db" \
  -v "$DATA_DIR/data:/app/data" \
  -v "$DATA_DIR/logs:/app/logs" \
  $ENV_ARGS \
  "$IMAGE"

# 모델 로딩 등으로 기동에 시간이 걸릴 수 있어 최대 2분간 재시도
echo "Waiting for service to become healthy..."
for i in $(seq 1 24); do
  CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" http://localhost:8000 || true)
  if [ "$CODE" = "200" ]; then
    echo "health check: HTTP 200 (attempt $i)"
    # 커밋 SHA 태그를 매번 새로 pull하므로, 헬스체크 통과 후 지금
    # 컨테이너가 쓰지 않는 이전 태그 이미지를 전부 정리해야 디스크가
    # 안 찬다 (dangling만 지우는 -f로는 부족해서 -a로 태그된 것도 정리).
    docker image prune -af
    echo "Deployed ${IMAGE}"
    exit 0
  fi
  sleep 5
done

echo "health check: service did not become healthy in time (last code: $CODE)"
exit 1
