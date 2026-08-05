"""
일지 뷰어(마크다운 렌더)와 다운로드 단위 테스트

왜 필요한가:
    일지는 LLM 이 쓰지만 그 재료는 사용자 저장소의 문서와 커밋 메시지다.
    남의 저장소를 소스로 등록하면 임의의 HTML 이 일지에 흘러들 수 있으므로,
    렌더할 때 원시 HTML 을 반드시 막아야 한다.

    다운로드는 렌더된 HTML 이 아니라 원문 마크다운을 줘야 한다 — 옵시디언이나
    노션으로 그대로 옮기는 것이 목적이기 때문이다.

    ChromaDB 도 네트워크도 타지 않는다.
"""
import io
import zipfile

import pytest

from src.tools import log as log_tools


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(log_tools, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(log_tools, "journal_overview", lambda user_id: {
        "journals": [
            {"date": d, "path": str(tmp_path / f"{d.replace('-', '.')}_log.md"),
             "indexed": True, "sources": [], "sources_estimated": False,
             "title": "", "chars": 0}
            for d in sorted(state["dates"], reverse=True)
        ],
        "unindexed": 0,
    })

    state = {"dates": []}

    def write(date: str, body: str):
        (tmp_path / f"{date.replace('-', '.')}_log.md").write_text(body, encoding="utf-8")
        state["dates"].append(date)

    state["write"] = write
    return state


class TestMarkdownRendering:
    def test_제목과_목록을_렌더한다(self, world):
        world["write"]("2026-07-28", "# 제목\n\n- 첫째\n- 둘째")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert "<h1>제목</h1>" in html
        assert "<li>첫째</li>" in html

    def test_표를_렌더한다(self, world):
        """CommonMark 기본이 아니라 enable('table') 로 켠 기능이다."""
        world["write"]("2026-07-28", "| 날짜 | 커밋 |\n|---|---|\n| 7/28 | 42건 |")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert "<table>" in html and "<td>42건</td>" in html

    def test_코드에_색을_입힌다(self, world):
        world["write"]("2026-07-28", "```python\ndef hello():\n    pass\n```")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert 'class="hl"' in html

    def test_모르는_언어는_그냥_코드_블록으로_둔다(self, world):
        world["write"]("2026-07-28", "```없는언어\n어떤 코드\n```")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert "어떤 코드" in html and 'class="hl"' not in html

    def test_체크박스를_바꾼다(self, world):
        """CommonMark 는 GFM 체크박스를 모른다 — 렌더 뒤에 치환한다."""
        world["write"]("2026-07-28", "- [ ] 할 일\n- [x] 끝난 일")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert 'class="task"' in html
        assert 'class="task done"' in html
        assert "[ ]" not in html


class TestUntrustedContentIsBlocked:
    """일지의 재료는 사용자가 등록한 남의 저장소일 수 있다."""

    def test_스크립트_태그를_이스케이프한다(self, world):
        world["write"]("2026-07-28", "# 일지\n\n<script>alert(1)</script>")

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_이벤트_핸들러가_붙은_태그도_막는다(self, world):
        world["write"]("2026-07-28", '<img src=x onerror="alert(1)">')

        html = log_tools.render_journal("tester", "2026-07-28")["html"]

        assert "<img" not in html


class TestDownloadPayload:
    def test_원문을_그대로_돌려준다(self, world):
        """다운로드는 렌더된 HTML 이 아니라 마크다운이어야 한다."""
        source = "# 제목\n\n- 항목"
        world["write"]("2026-07-28", source)

        assert log_tools.render_journal("tester", "2026-07-28")["raw"] == source

    def test_글자_수는_바이트가_아니라_글자로_센다(self, world):
        """한글은 UTF-8 에서 3바이트라 파일 크기를 쓰면 세 배로 부풀려진다."""
        world["write"]("2026-07-28", "한글다섯글자")

        assert log_tools.render_journal("tester", "2026-07-28")["chars"] == 6

    def test_없는_일지는_None_이다(self, world):
        assert log_tools.render_journal("tester", "2026-07-28") is None

    def test_날짜가_아니면_None_이다(self, world):
        assert log_tools.render_journal("tester", "어제쯤") is None


class TestNavigation:
    def test_앞뒤_일지로_이동할_수_있다(self, world):
        for date in ("2026-07-14", "2026-07-28", "2026-08-03"):
            world["write"](date, "# 일지")

        view = log_tools.render_journal("tester", "2026-07-28")

        assert view["newer"] == "2026-08-03"
        assert view["older"] == "2026-07-14"

    def test_양_끝에서는_한쪽이_비어_있다(self, world):
        for date in ("2026-07-28", "2026-08-03"):
            world["write"](date, "# 일지")

        newest = log_tools.render_journal("tester", "2026-08-03")
        oldest = log_tools.render_journal("tester", "2026-07-28")

        assert newest["newer"] == "" and newest["older"] == "2026-07-28"
        assert oldest["newer"] == "2026-08-03" and oldest["older"] == ""


class TestArchive:
    def test_모든_일지를_zip_으로_묶는다(self, world):
        world["write"]("2026-07-28", "# 첫째")
        world["write"]("2026-08-03", "# 둘째")

        data, count = log_tools.journal_archive("tester")

        assert count == 2
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert sorted(names) == ["2026.07.28_log.md", "2026.08.03_log.md"]

    def test_원문_마크다운을_담는다(self, world):
        world["write"]("2026-07-28", "# 제목\n\n본문")

        data, _ = log_tools.journal_archive("tester")
        inside = zipfile.ZipFile(io.BytesIO(data)).read("2026.07.28_log.md").decode()

        assert inside == "# 제목\n\n본문"

    def test_일지가_없으면_빈_zip_이다(self, world):
        data, count = log_tools.journal_archive("tester")

        assert count == 0
        assert zipfile.ZipFile(io.BytesIO(data)).namelist() == []
