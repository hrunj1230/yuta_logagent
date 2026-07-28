from langchain_core.tools import tool
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
import re

# Import at module level (after existing imports)
from .embedding import embed_source as _embed_source_tool


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
        return request_source_type_clarification.invoke({})

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


@tool
def get_user_sources(user_id: str) -> str:
    """
    사용자의 모든 소스 목록을 조회합니다.

    Args:
        user_id: 사용자 ID

    Returns:
        소스 목록 (포맷팅된 문자열)
    """
    db = SessionLocal()
    try:
        sources = db.query(Source).filter_by(user_id=user_id, is_active=True).all()

        if not sources:
            return "📭 등록된 소스가 없습니다."

        result = f"📚 총 {len(sources)}개의 소스가 등록되어 있습니다:\n\n"

        for src in sources:
            status_emoji = {
                EmbeddingStatus.PENDING: "⏳",
                EmbeddingStatus.IN_PROGRESS: "🔄",
                EmbeddingStatus.COMPLETED: "✅",
                EmbeddingStatus.FAILED: "❌"
            }.get(src.embedding_status, "❓")

            result += f"{status_emoji} [{src.id}] {src.name}\n"
            result += f"   타입: {src.type.value}\n"
            result += f"   위치: {src.location}\n"
            result += f"   상태: {src.embedding_status.value}\n"

            if src.last_synced_at:
                result += f"   마지막 동기화: {src.last_synced_at.strftime('%Y-%m-%d %H:%M')}\n"

            if src.embedding_status == EmbeddingStatus.FAILED and src.embedding_error:
                result += f"   ⚠️ 오류: {src.embedding_error}\n"

            result += "\n"

        return result.strip()

    finally:
        db.close()


@tool
def delete_source_from_db(source_id: int, user_id: str) -> str:
    """
    소스를 삭제합니다 (DB + ChromaDB 임베딩).

    Args:
        source_id: 소스 ID
        user_id: 사용자 ID (권한 확인용)

    Returns:
        성공/실패 메시지
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        source_name = source.name

        # ChromaDB에서 해당 소스의 임베딩 삭제
        from .embedding import _delete_source_embeddings
        deleted_count = _delete_source_embeddings(user_id, source_id)

        # DB에서 삭제
        db.delete(source)
        db.commit()

        return f"""✅ 소스가 삭제되었습니다.
- 이름: {source_name}
- ID: {source_id}
- 삭제된 임베딩: {deleted_count}개"""

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"소스 삭제 중 시스템 오류: {str(e)}")
    finally:
        db.close()


@tool
def request_source_type_clarification() -> str:
    """
    사용자에게 소스 타입을 명확히 요청합니다.
    SourceType 판단이 애매할 때 호출합니다.

    Returns:
        소스 타입 선택 안내 메시지
    """
    return """🤔 소스 타입을 명확히 지정해주세요:
**git** - Git 저장소를 clone하고 파일을 임베딩
   예: https://github.com/user/repo.git

**git_log** - Git 커밋 히스토리를 임베딩
   예: https://github.com/user/repo.git (커밋 로그만)

**local** - 서버의 로컬 디렉토리 사용
   예: /path/to/local/directory

**agent_chatlog** - 에이전트 대화 로그 파일
   예: /logs/chat_history.json

**memsearch** - 기존 메모리 검색 데이터 연결
   예: /.memsearch

소스를 추가할 때 타입을 함께 지정해주세요."""


@tool
def add_source_and_embed(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    소스를 추가하고 즉시 임베딩을 시작합니다 (통합 도구).

    이 도구는 add_source_to_db와 embed_source를 연쇄적으로 호출하여
    한 번의 요청으로 소스 등록과 임베딩 시작을 모두 처리합니다.

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: 소스 타입 (git, git_log, local, agent_chatlog, memsearch)
        location: 소스 위치 (Git URL, 로컬 경로 등)

    Returns:
        통합 작업 결과 메시지
    """
    # Step 1: Add source to database
    add_result = add_source_to_db.invoke({
        "user_id": user_id,
        "name": name,
        "source_type": source_type,
        "location": location
    })

    # Check if source addition failed
    if add_result.startswith("❌"):
        return add_result

    # Extract source_id from success message
    # Format: "...ID: {source.id}..."
    match = re.search(r'ID: (\d+)', add_result)
    if not match:
        return f"❌ 오류: 소스는 추가되었으나 ID를 찾을 수 없습니다.\n{add_result}"

    source_id = int(match.group(1))

    # Step 2: Start embedding immediately
    embed_result = _embed_source_tool.invoke({
        "user_id": user_id,
        "source_id": source_id
    })

    # Return combined result
    return f"""{add_result}

🚀 임베딩 자동 시작:
{embed_result}"""
