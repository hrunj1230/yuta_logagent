"""
yuta-logagent MCP 서버

Claude 대화 기록(claude-daily-log 출력)을 파일로 저장합니다.
저장 위치: PROJECT_ROOT/claude_logs/YYYY-MM-DD.md

실행 방법:
    cd /Users/hrun/Documents/yuta/yuta_logagent
    .venv/bin/fastmcp run src/mcp_server.py

Cowork MCP 설정 (~/.claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "yuta-logagent": {
                "command": "npx",
                "args": ["-y", "mcp-remote", "http://3.106.155.36:8000/mcp/", "--allow-http"]
            }
        }
    }
"""
import os
import sys
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP(
    "yuta-logagent",
    instructions="jeong의 사관일지 에이전트. Claude 대화 기록을 파일로 저장해 날짜별 일지 생성 시 소스로 활용합니다.",
)

# PROJECT_ROOT/claude_logs/ — Docker 컨테이너에서 볼륨 마운트 권장
_LOGS_DIR: Path | None = None


def _get_logs_dir() -> Path:
    global _LOGS_DIR
    if _LOGS_DIR is None:
        # src/mcp_server.py → 상위가 PROJECT_ROOT
        _LOGS_DIR = Path(__file__).parent.parent / "claude_logs"
        _LOGS_DIR.mkdir(exist_ok=True)
    return _LOGS_DIR


@mcp.tool()
def push_daily_log(date: str, content: str, user_id: str = "jeong") -> str:
    """
    Claude 대화 기록 마크다운을 파일로 저장합니다.

    claude-daily-log 스킬이 daily/YYYY-MM-DD.md 파일을 저장한 직후
    이 도구를 호출해 logagent가 날짜별 일지를 생성할 때 소스로 활용합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식, 예: 2026-08-03)
        content: 마크다운 내용 전문
        user_id: 사용자 ID (기본값: "jeong", 현재 미사용 — 향후 다중 사용자 확장용)

    Returns:
        저장 결과 메시지
    """
    try:
        logs_dir = _get_logs_dir()
        file_path = logs_dir / f"{date}.md"
        existed = file_path.exists()
        file_path.write_text(content, encoding="utf-8")
        action = "덮어씀" if existed else "새로 저장"
        size = file_path.stat().st_size
        return f"✅ {date} Claude 대화 기록 {action} ({size:,} bytes) → {file_path}"
    except Exception as e:
        return f"❌ 저장 실패: {e}"


@mcp.tool()
def get_log_status(date: str, user_id: str = "jeong") -> str:
    """
    특정 날짜의 파일 저장 현황을 확인합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식)
        user_id: 사용자 ID

    Returns:
        파일 존재 여부, 크기, 수정 시각
    """
    try:
        logs_dir = _get_logs_dir()
        file_path = logs_dir / f"{date}.md"
        if file_path.exists():
            stat = file_path.stat()
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            return f"✅ {date} 파일 존재: {size:,} bytes (수정: {modified})"
        else:
            return f"📭 {date} 파일 없음"
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
