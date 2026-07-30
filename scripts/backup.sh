#!/bin/bash
# 데이터 백업 스크립트
# 사용법: ./scripts/backup.sh

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"

echo "🔄 백업 시작: $DATE"

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# 데이터베이스 백업
if [ -f "users.db" ]; then
    echo "📦 SQLite 백업 중..."
    cp users.db "$BACKUP_DIR/users.db"
    echo "✅ users.db 백업 완료"
else
    echo "⚠️  users.db 파일을 찾을 수 없습니다"
fi

# ChromaDB 백업
if [ -d "chroma_db" ]; then
    echo "📦 ChromaDB 백업 중..."
    cp -r chroma_db "$BACKUP_DIR/chroma_db"
    echo "✅ chroma_db 백업 완료"
else
    echo "⚠️  chroma_db 디렉토리를 찾을 수 없습니다"
fi

# 소스 데이터 백업 (선택사항 - 용량이 큰 경우 주석 처리)
if [ -d "data" ]; then
    echo "📦 소스 데이터 백업 중..."
    cp -r data "$BACKUP_DIR/data"
    echo "✅ data 백업 완료"
else
    echo "⚠️  data 디렉토리를 찾을 수 없습니다"
fi

# 백업 크기 확인
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo ""
echo "✅ 백업 완료!"
echo "📁 위치: $BACKUP_DIR"
echo "📊 크기: $BACKUP_SIZE"

# 오래된 백업 삭제 (30일 이상)
echo ""
echo "🧹 오래된 백업 정리 중..."
find ./backups -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
echo "✅ 정리 완료"
