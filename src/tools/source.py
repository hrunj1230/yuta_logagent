from langchain_core.tools import tool
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
import re


@tool
def add_source_to_db(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    소스를 데이터베이스에 추가합니다.

    주의: 이 함수는 소스를 등록만 하고 임베딩은 시작하지 않습니다.
    임베딩을 시작하려면 embed_source를 별도로 호출해야 합니다.

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: 소스 타입 (git, git_log, local, agent_chatlog, memsearch)
        location: 소스 위치 (Git URL, 로컬 경로 등)

    Returns:
        성공/실패 메시지
    """
    # 입력 검증
    if not location.strip():
        return "❌ 오류: 소스 위치가 비어있습니다."

    try:
        source_type_enum = SourceType(source_type.lower())
    except ValueError:
        return f"❌ 오류: 지원하지 않는 소스 타입입니다. (지원: git, git_log, local, agent_chatlog, memsearch)"

    # Git URL 검증
    if source_type_enum in [SourceType.GIT, SourceType.GIT_LOG]:
        git_pattern = r'(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+(?:\.git)?|.*\.git)'
        if not re.match(git_pattern, location, re.IGNORECASE):
            return f"❌ 오류: 올바른 Git URL이 아닙니다. 예: https://github.com/user/repo.git"

    # DB 저장
    db = SessionLocal()
    try:
        # 중복 확인
        existing = db.query(Source).filter_by(
            user_id=user_id,
            type=source_type_enum,
            location=location
        ).first()

        if existing:
            return f"❌ 이미 등록된 소스입니다: {existing.name} (ID: {existing.id})"

        # 새 소스 생성
        source = Source(
            user_id=user_id,
            name=name,
            type=source_type_enum,
            location=location,
            embedding_status=EmbeddingStatus.PENDING
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        return f"""✅ 소스가 추가되었습니다.
- 이름: {name}
- 타입: {source_type}
- 위치: {location}
- ID: {source.id}
- 상태: 임베딩 대기 중 (embed_source를 호출하여 시작하세요)"""

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"소스 추가 중 시스템 오류: {str(e)}")
    finally:
        db.close()
