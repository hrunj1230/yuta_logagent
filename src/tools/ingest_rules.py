"""
소스 수집 규칙 및 날짜 추출 모듈

이 모듈은 "어떤 파일을 임베딩 대상으로 삼을 것인가"와
"그 파일에 어떤 날짜를 붙일 것인가"를 결정합니다.

일지 시스템의 대상은 '날짜를 붙일 수 있는 문서'입니다.
따라서 날짜 추출 실패는 그 자체로 수집 제외 사유가 됩니다.

제공 함수:
    - should_collect: 파일이 수집 대상인지 판단
    - normalize_date: 다양한 날짜 표기를 YYYY-MM-DD로 정규화
    - date_from_filename: 파일명에서 날짜 추출
    - date_from_frontmatter: 마크다운 frontmatter에서 날짜 추출
    - git_file_dates: 저장소 전체의 파일별 최종 커밋 날짜 조회
    - resolve_date: 우선순위에 따라 문서 날짜 확정
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path

# 일지 대상이 되는 문서 확장자만 허용한다.
# 코드 확장자(.js, .py 등)는 제외한다 — 코드 저장소는 git_log 타입으로 커밋 이력을 수집한다.
DOC_EXTENSIONS = {".md", ".txt", ".markdown"}

# 순회에서 통째로 건너뛸 디렉토리.
# .obsidian 은 Obsidian 플러그인 소스가 들어있어 반드시 제외해야 한다.
EXCLUDE_DIRS = {
    ".git", ".obsidian", ".vscode", ".idea",
    "node_modules", ".venv", "venv", "site-packages",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "out", "target", ".next", ".cache",
}

# 단일 파일 크기 상한 (bytes). 이보다 큰 문서는 일지 소스로 보지 않는다.
MAX_FILE_SIZE = 200_000

# 파일명에 흔히 쓰이는 날짜 표기: 2026_05_14, 2026-05-14, 2026.05.14, 20260514
_FILENAME_DATE = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")

# 사용자 입력용 관대한 표기: '2026년 7월 9일', '2026 / 7 / 9'
_LOOSE_YMD = re.compile(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})")
# 연도가 생략된 표기: '7월 9일', '05월 13일'
_LOOSE_MD = re.compile(r"^\D*(\d{1,2})\D{1,3}(\d{1,2})\D*$")

# YAML frontmatter 의 date/created 필드
_FRONTMATTER_BLOCK = re.compile(r"\A﻿?---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_FRONTMATTER_DATE = re.compile(
    r"^\s*(?:date|created)\s*:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def normalize_date(raw: str | None) -> str | None:
    """
    다양한 날짜 표기를 YYYY-MM-DD 로 정규화한다.

    허용 예: '2026-05-14', '2026_05_14', '2026.05.14', '20260514',
             '2026-05-14 00:47:34 +0900', '2026-05-14T00:47:34'

    Returns:
        정규화된 'YYYY-MM-DD' 문자열. 유효한 날짜를 찾지 못하면 None.
    """
    if not raw:
        return None

    match = _FILENAME_DATE.search(str(raw))
    if not match:
        return None

    year, month, day = match.groups()
    try:
        # 실제로 존재하는 날짜인지 검증한다 (2026-13-45 같은 값 배제)
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_user_date(raw: str | None, today: "datetime | None" = None) -> str | None:
    """
    사용자가 입력한 자유로운 날짜 표기를 YYYY-MM-DD 로 해석한다.

    normalize_date 보다 관대하다. '2026년 7월 9일' 처럼 구분자가 한글이거나
    월/일이 한 자리인 표기, 연도가 생략된 '7월 9일' 을 처리한다.
    연도가 없으면 올해로 간주한다.

    파일명·메타데이터 파싱에는 오탐 위험이 있으므로 쓰지 않는다.
    사용자 입력 경로에서만 사용한다.
    """
    if not raw:
        return None

    strict = normalize_date(raw)
    if strict:
        return strict

    text = str(raw)

    match = _LOOSE_YMD.search(text)
    if match:
        year, month, day = match.groups()
    else:
        match = _LOOSE_MD.search(text)
        if not match:
            return None
        month, day = match.groups()
        year = str((today or datetime.now()).year)

    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def date_from_filename(file_path: str | Path) -> str | None:
    """파일명(확장자 제외)에서 날짜를 추출한다."""
    return normalize_date(Path(file_path).stem)


def date_from_frontmatter(content: str) -> str | None:
    """
    마크다운 frontmatter 의 date/created 필드에서 날짜를 추출한다.

    문서 맨 앞의 --- 블록만 검사한다. 본문에 등장하는 날짜는 작성일이 아닐 수
    있으므로 사용하지 않는다.
    """
    if not content:
        return None

    block = _FRONTMATTER_BLOCK.match(content)
    if not block:
        return None

    field = _FRONTMATTER_DATE.search(block.group(1))
    return normalize_date(field.group(1)) if field else None


def git_file_dates(repo_dir: str | Path) -> dict[str, str]:
    """
    저장소의 파일별 '마지막으로 커밋된 날짜'를 한 번의 git log 호출로 수집한다.

    파일마다 git log 를 개별 실행하면 파일 수만큼 프로세스가 뜨므로,
    --name-only 로 전체를 한 번에 훑고 경로별로 최신 날짜를 기록한다.
    git log 는 최신순이므로 각 경로의 첫 등장이 곧 최종 수정일이다.

    Returns:
        {상대경로: 'YYYY-MM-DD'} 매핑. 실패 시 빈 dict.
    """
    marker = "__COMMIT__"
    try:
        result = subprocess.run(
            [
                # core.quotepath=false 없이는 git이 한글 경로를 8진수로 이스케이프해
                # 실제 파일 경로와 매칭되지 않는다
                "git", "-C", str(repo_dir), "-c", "core.quotepath=false", "log",
                f"--pretty=format:{marker}%ad", "--date=short", "--name-only",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"git log 날짜 조회 실패 ({repo_dir}): {e}")
        return {}

    if result.returncode != 0:
        print(f"git log 날짜 조회 실패 ({repo_dir}): {result.stderr.strip()}")
        return {}

    dates: dict[str, str] = {}
    current: str | None = None

    for line in result.stdout.splitlines():
        if line.startswith(marker):
            current = normalize_date(line[len(marker):])
        elif line.strip() and current:
            # 최신 커밋부터 순회하므로 이미 기록된 경로는 덮어쓰지 않는다
            dates.setdefault(line.strip(), current)

    return dates


def resolve_date(
    rel_path: str | Path,
    content: str,
    git_dates: dict[str, str] | None = None,
    abs_path: str | Path | None = None,
) -> tuple[str | None, str]:
    """
    문서의 날짜를 우선순위에 따라 확정한다.

    우선순위:
        1. 파일명       — 'Today I Learn/2026_05_14.md' 처럼 가장 명시적
        2. frontmatter  — 문서가 스스로 선언한 작성일
        3. git 커밋일   — 저장소가 기록한 실제 작업일
        4. 파일 mtime   — 로컬 소스의 최후 수단 (복사/이동 시 부정확)

    Returns:
        (날짜 또는 None, 출처 라벨). 날짜를 찾지 못하면 (None, 'none').
    """
    found = date_from_filename(rel_path)
    if found:
        return found, "filename"

    found = date_from_frontmatter(content)
    if found:
        return found, "frontmatter"

    if git_dates:
        found = git_dates.get(str(rel_path))
        if found:
            return found, "git"

    if abs_path:
        try:
            mtime = Path(abs_path).stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"), "mtime"
        except OSError:
            pass

    return None, "none"


def should_collect(abs_path: str | Path, root: str | Path) -> tuple[bool, str]:
    """
    파일이 임베딩 수집 대상인지 판단한다.

    Args:
        abs_path: 검사할 파일의 절대 경로
        root: 소스 루트 (제외 디렉토리 판정을 루트 기준 상대경로로 수행)

    Returns:
        (수집 여부, 사유). 수집 대상이면 (True, 'ok').
    """
    path = Path(abs_path)

    if not path.is_file():
        return False, "not_a_file"

    try:
        rel = path.relative_to(root)
    except ValueError:
        return False, "outside_root"

    # 경로 어딘가에 제외 디렉토리가 있으면 건너뛴다
    for part in rel.parts[:-1]:
        if part in EXCLUDE_DIRS:
            return False, f"excluded_dir:{part}"

    if path.suffix.lower() not in DOC_EXTENSIONS:
        return False, f"extension:{path.suffix or 'none'}"

    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return False, "too_large"
    except OSError:
        return False, "stat_failed"

    return True, "ok"
