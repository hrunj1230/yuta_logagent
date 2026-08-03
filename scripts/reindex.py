"""
벡터DB 재인덱싱 스크립트

수집 규칙이나 날짜 추출 로직이 바뀌면 기존 임베딩은 새 메타데이터를 갖지 못한다.
이 스크립트는 사용자의 ChromaDB 컬렉션을 비우고 등록된 소스를 처음부터 다시 임베딩한다.

원문은 data/sources 와 원격 저장소에 그대로 있으므로 복구 위험은 없다.
실행 전 chroma_db 디렉토리를 backups/ 로 백업한다.

사용법:
    uv run python -m scripts.reindex <user_id>
    uv run python -m scripts.reindex <user_id> --keep   # 기존 컬렉션 유지, 증분만
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

from src import llm_router
from src.storage.database import SessionLocal
from src.storage.models import Source
from src.tools.embedding import embed_source

CHROMA_DIR = Path("./chroma_db")
BACKUP_DIR = Path("./backups")


def backup_chroma() -> Path | None:
    """chroma_db 디렉토리를 타임스탬프와 함께 backups/ 로 복사한다."""
    if not CHROMA_DIR.exists():
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"chroma_db.backup_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copytree(CHROMA_DIR, target)
    return target


def drop_collection(user_id: str) -> bool:
    """사용자 컬렉션을 삭제한다. 없으면 False."""
    name = f"user_{user_id}"
    try:
        llm_router.chroma_client.delete_collection(name)
        return True
    except Exception as e:
        print(f"   컬렉션 '{name}' 삭제 건너뜀: {e}")
        return False


def main(user_id: str, drop: bool = True) -> int:
    print(f"🔁 재인덱싱 대상 사용자: {user_id}\n")

    db = SessionLocal()
    try:
        sources = db.query(Source).filter_by(user_id=user_id, is_active=True).all()
        # 세션이 닫힌 뒤에도 쓸 수 있도록 필요한 값만 미리 꺼낸다
        targets = [(s.id, s.name, s.type.value) for s in sources]
    finally:
        db.close()

    if not targets:
        print("❌ 등록된 소스가 없습니다. 소스를 먼저 등록한 뒤 다시 실행하세요.")
        return 1

    print(f"등록된 소스 {len(targets)}개:")
    for source_id, name, source_type in targets:
        print(f"   [{source_id}] {name} ({source_type})")
    print()

    if drop:
        backup = backup_chroma()
        if backup:
            print(f"💾 백업 완료: {backup}")
        print("🗑️  기존 컬렉션 삭제 중...")
        drop_collection(user_id)
        print()

    for source_id, name, _ in targets:
        print(f"⏳ 임베딩: {name} (id={source_id})")
        print(embed_source.invoke({"user_id": user_id, "source_id": source_id}))
        print()

    print("✅ 재인덱싱 완료")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], drop="--keep" not in sys.argv))
