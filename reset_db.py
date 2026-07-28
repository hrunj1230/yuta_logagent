"""
데이터베이스 재생성 스크립트

기존 users.db를 백업하고 새로운 스키마로 재생성합니다.
"""
import os
import shutil
from datetime import datetime
from src.storage.database import init_db

def reset_database():
    """데이터베이스 백업 및 재생성"""
    db_file = "users.db"

    # 1. 기존 DB가 있으면 백업
    if os.path.exists(db_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"users.db.backup_{timestamp}"
        shutil.copy(db_file, backup_file)
        print(f"✅ 기존 DB 백업: {backup_file}")

        # 2. 기존 DB 삭제
        os.remove(db_file)
        print(f"✅ 기존 DB 삭제: {db_file}")
    else:
        print(f"ℹ️  기존 DB 없음 (새로 생성)")

    # 3. 새 스키마로 DB 생성
    init_db()
    print(f"✅ 새 DB 생성 완료: {db_file}")
    print()
    print("📌 새로 추가된 컬럼:")
    print("  - embedding_status: 임베딩 진행 상태")
    print("  - embedding_error: 임베딩 오류 메시지")
    print("  - embedding_stats: 임베딩 통계 정보")

if __name__ == "__main__":
    print("🔄 데이터베이스 재생성 시작\n")
    reset_database()
    print("\n✅ 완료! 이제 테스트를 다시 실행하세요.")
