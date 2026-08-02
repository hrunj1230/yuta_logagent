"""
수집 규칙 및 날짜 추출 단위 테스트

이 테스트들은 외부 의존성(ChromaDB, 임베딩 모델, 네트워크) 없이 동작한다.
"""
import subprocess
from pathlib import Path

import pytest

from datetime import datetime

from src.tools.ingest_rules import (
    MAX_FILE_SIZE,
    date_from_filename,
    date_from_frontmatter,
    git_file_dates,
    normalize_date,
    parse_user_date,
    resolve_date,
    should_collect,
)


class TestParseUserDate:
    """사용자 입력 경로 전용. 파일명 파싱보다 관대하다."""

    @pytest.mark.parametrize("raw,expected", [
        ("2026-07-21", "2026-07-21"),
        ("2026년 07월 21일", "2026-07-21"),
        ("2026년 7월 9일", "2026-07-09"),
        ("2026.07.09", "2026-07-09"),
        ("2026 / 7 / 9", "2026-07-09"),
    ])
    def test_parses_korean_and_loose_formats(self, raw, expected):
        assert parse_user_date(raw) == expected

    def test_assumes_current_year_when_omitted(self):
        assert parse_user_date("7월 9일", today=datetime(2026, 8, 2)) == "2026-07-09"
        assert parse_user_date("05월 13일", today=datetime(2026, 8, 2)) == "2026-05-13"

    @pytest.mark.parametrize("raw", [None, "", "어제", "지난주", "2026년 13월 1일"])
    def test_rejects_unparseable(self, raw):
        assert parse_user_date(raw) is None


class TestNormalizeDate:
    @pytest.mark.parametrize("raw,expected", [
        ("2026-05-14", "2026-05-14"),
        ("2026_05_14", "2026-05-14"),
        ("2026.05.14", "2026-05-14"),
        ("20260514", "2026-05-14"),
        ("2026-05-14 00:47:34 +0900", "2026-05-14"),
        ("2026-05-14T00:47:34.713258", "2026-05-14"),
    ])
    def test_accepts_common_formats(self, raw, expected):
        assert normalize_date(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "회고록", "week07", "2026-13-01", "2026-02-30"])
    def test_rejects_invalid(self, raw):
        assert normalize_date(raw) is None


class TestDateFromFilename:
    def test_extracts_from_til_naming(self):
        assert date_from_filename("Today I Learn/2026_05_14.md") == "2026-05-14"

    def test_ignores_extension(self):
        assert date_from_filename("2026-06-29.md") == "2026-06-29"

    def test_returns_none_without_date(self):
        assert date_from_filename("MCP의 Context Isolation.md") is None


class TestDateFromFrontmatter:
    def test_reads_date_field(self):
        content = "---\ntitle: 회고\ndate: 2026-07-15\n---\n\n본문"
        assert date_from_frontmatter(content) == "2026-07-15"

    def test_reads_created_field(self):
        content = "---\ncreated: 2026.07.16\n---\n본문"
        assert date_from_frontmatter(content) == "2026-07-16"

    def test_strips_quotes(self):
        content = '---\ndate: "2026-07-17"\n---\n본문'
        assert date_from_frontmatter(content) == "2026-07-17"

    def test_ignores_dates_in_body(self):
        """본문의 날짜는 작성일이 아닐 수 있으므로 사용하지 않는다."""
        content = "# 제목\n\n2026-01-01 에 시작한 프로젝트"
        assert date_from_frontmatter(content) is None

    def test_returns_none_without_frontmatter(self):
        assert date_from_frontmatter("# 그냥 문서") is None


class TestShouldCollect:
    def test_accepts_markdown(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("내용")
        assert should_collect(f, tmp_path) == (True, "ok")

    def test_rejects_javascript(self, tmp_path):
        """코드 확장자는 수집하지 않는다 — 벡터DB 오염의 원인이었다."""
        f = tmp_path / "main.js"
        f.write_text("console.log(1)")
        ok, reason = should_collect(f, tmp_path)
        assert ok is False
        assert reason.startswith("extension")

    def test_rejects_obsidian_plugin_dir(self, tmp_path):
        """.obsidian 하위는 확장자가 맞아도 제외한다."""
        f = tmp_path / ".obsidian" / "plugins" / "calendar" / "README.md"
        f.parent.mkdir(parents=True)
        f.write_text("플러그인 문서")
        ok, reason = should_collect(f, tmp_path)
        assert ok is False
        assert reason == "excluded_dir:.obsidian"

    @pytest.mark.parametrize("excluded", [".git", "node_modules", "__pycache__", "dist"])
    def test_rejects_excluded_dirs(self, tmp_path, excluded):
        f = tmp_path / excluded / "doc.md"
        f.parent.mkdir(parents=True)
        f.write_text("x")
        assert should_collect(f, tmp_path)[0] is False

    def test_rejects_oversized_file(self, tmp_path):
        f = tmp_path / "huge.md"
        f.write_text("가" * (MAX_FILE_SIZE + 1))
        assert should_collect(f, tmp_path) == (False, "too_large")

    def test_rejects_directory(self, tmp_path):
        d = tmp_path / "sub"
        d.mkdir()
        assert should_collect(d, tmp_path)[0] is False


class TestResolveDate:
    def test_filename_wins_over_frontmatter(self):
        date, origin = resolve_date("2026_05_14.md", "---\ndate: 2020-01-01\n---\n")
        assert (date, origin) == ("2026-05-14", "filename")

    def test_falls_back_to_frontmatter(self):
        date, origin = resolve_date("회고.md", "---\ndate: 2026-07-15\n---\n")
        assert (date, origin) == ("2026-07-15", "frontmatter")

    def test_falls_back_to_git(self):
        date, origin = resolve_date("회고.md", "본문", git_dates={"회고.md": "2026-08-01"})
        assert (date, origin) == ("2026-08-01", "git")

    def test_falls_back_to_mtime(self, tmp_path):
        f = tmp_path / "회고.md"
        f.write_text("본문")
        date, origin = resolve_date("회고.md", "본문", abs_path=f)
        assert origin == "mtime"
        assert date is not None

    def test_returns_none_when_undatable(self):
        """날짜를 못 붙이는 문서는 일지 시스템의 대상이 아니다."""
        assert resolve_date("회고.md", "본문") == (None, "none")


class TestGitFileDates:
    @pytest.fixture
    def repo(self, tmp_path):
        def run(*args):
            subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                           capture_output=True)

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        run("config", "user.email", "t@t.t")
        run("config", "user.name", "t")

        (tmp_path / "old.md").write_text("v1")
        run("add", "-A")
        run("commit", "-q", "-m", "first", "--date=2026-05-14T10:00:00")

        (tmp_path / "new.md").write_text("v1")
        run("add", "-A")
        run("commit", "-q", "-m", "second", "--date=2026-06-20T10:00:00")
        return tmp_path

    def test_maps_each_file_to_its_last_commit_date(self, repo):
        dates = git_file_dates(repo)
        assert dates["old.md"] == "2026-05-14"
        assert dates["new.md"] == "2026-06-20"

    def test_returns_empty_dict_for_non_repo(self, tmp_path):
        assert git_file_dates(tmp_path) == {}

    def test_handles_korean_paths(self, repo):
        """git은 기본 설정에서 한글 경로를 8진수로 이스케이프한다 (core.quotepath)."""
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"],
                       check=True, capture_output=True)
        (repo / "회고록").mkdir()
        (repo / "회고록" / "week05 회고록.md").write_text("회고")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", "회고 추가",
             "--date=2026-07-10T10:00:00"],
            check=True, capture_output=True,
        )

        dates = git_file_dates(repo)
        assert dates["회고록/week05 회고록.md"] == "2026-07-10"
