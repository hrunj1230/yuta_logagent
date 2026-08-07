"""
yuta-logagent MCP 서버

Claude 대화 기록(claude-daily-log 출력)을 받아 ChromaDB에 임베딩합니다.
claude-daily-log 스킬이 파일을 저장한 직후 이 서버의 push_daily_log 도구를
호출해 logagent DB에 자동으로 소스를 추가합니다.

실행 방법:
    cd /Users/hrun/Documents/yuta/yuta_logagent
    .venv/bin/fastmcp run src/mcp_server.py

Cowork MCP 설정 (~/.claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "yuta-logagent": {
                "command": "/Users/hrun/Documents/yuta/yuta_logagent/.venv/bin/fastmcp",
                "args": ["run", "/Users/hrun/Documents/yuta/yuta_logagent/src/mcp_server.py"],
                "cwd": "/Users/hrun/Documents/yuta/yuta_logagent"
            }
        }
    }
"""
import os
import sys
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from langchain_core.documents import Document

mcp = FastMCP(
    "yuta-logagent",
    instructions="jeong의 사관일지 에이전트. Claude 대화 기록을 ChromaDB에 저장해 날짜별 일지 생성 시 소스로 활용합니다.",
)


def _get_store(user_id: str):
    """사용자별 ChromaDB 컬렉션 (지연 임포트로 startup 시간 단축)."""
    from src import llm_router
    from langchain_chroma import Chroma
    return Chroma(
        collection_name=f"user_{user_id}",
        embedding_function=llm_router.embedding_function,
        client=llm_router.chroma_client,
    )


@mcp.tool()
def push_daily_log(date: str, content: str, user_id: str = "jeong") -> str:
    """
    Claude 대화 기록 마크다운을 logagent ChromaDB에 저장합니다.

    claude-daily-log 스킬이 daily/YYYY-MM-DD.md 파일을 저장한 직후
    이 도구를 호출해 logagent가 날짜별 일지를 생성할 때 Claude 채팅 기록을
    소스로 활용할 수 있게 합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식, 예: 2026-08-03)
        content: 마크다운 내용 (claude-daily-log 출력 전문)
        user_id: 사용자 ID (기본값: "jeong")

    Returns:
        저장 결과 메시지
    """
    try:
        store = _get_store(user_id)

        # 같은 날짜의 기존 claude_chat 문서 교체 (중복 누적 방지)
        existing = store.get(where={"$and": [
            {"source_type": "claude_chat"},
            {"date": date},
        ]})
        stale_ids = existing.get("ids", [])
        if stale_ids:
            store.delete(ids=stale_ids)

        store.add_documents([Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": -1,          # 외부 주입 소스는 -1
                "source_type": "claude_chat",
                "source_name": "Claude 대화 기록",
                "date": date,
                "date_origin": "daily_log",
                "embedded_at": datetime.now().isoformat(),
            },
        )])

        replaced = f" (기존 {len(stale_ids)}개 교체)" if stale_ids else ""
        return f"✅ {date} Claude 대화 기록을 logagent DB에 저장했습니다{replaced}."

    except Exception as e:
        return f"❌ 저장 실패: {e}"


@mcp.tool()
def get_log_status(date: str, user_id: str = "jeong") -> str:
    """
    특정 날짜의 logagent DB 저장 현황을 확인합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식)
        user_id: 사용자 ID

    Returns:
        저장된 소스 타입별 문서 수
    """
    try:
        store = _get_store(user_id)
        found = store.get(where={"date": date}, include=["metadatas"])
        metadatas = found.get("metadatas") or []

        if not metadatas:
            return f"📭 {date}에 저장된 문서가 없습니다."

        tally: dict[str, int] = {}
        for meta in metadatas:
            t = (meta or {}).get("source_type", "unknown")
            tally[t] = tally.get(t, 0) + 1

        lines = [f"📋 {date} 저장 현황 (총 {len(metadatas)}개):"]
        for t, count in sorted(tally.items()):
            lines.append(f"  - {t}: {count}개")
        return "\n".join(lines)

    except Exception as e:
        return f"❌ 조회 실패: {e}"


if __name__ == "__main__":
    # 단독 실행 시에만 경로 설정
    PROJECT_ROOT = Path(__file__).parent.parent
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))

    from dotenv import load_dotenv
    load_dotenv()

    mcp.run()
