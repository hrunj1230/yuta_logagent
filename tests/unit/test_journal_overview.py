"""
일지 관리 화면 데이터 조립 단위 테스트

왜 필요한가:
    일지는 두 곳에 있다 — 파일(logs/*.md)과 벡터DB 색인. 둘은 어긋날 수 있고
    실제로 어긋나 있었다. 실측으로 파일 9건 중 7건이 색인에 없었다. 파일은
    있는데 색인이 없으면 일지를 썼는데도 나중에 물어보면 "기록이 없습니다"가
    나온다 — 사용자가 알아챌 방법이 없는 조용한 고장이다.

    그래서 진실은 파일로 삼고, 색인 여부를 나란히 보여준다. 이 테스트는 그
    판정과 '어떤 소스가 일지에 들어갔는가'를 못박는다.

    ChromaDB 도 네트워크도 타지 않는다 — 컬렉션과 파일시스템을 대역으로 바꾼다.
"""
import json

import pytest

from src.tools import log as log_tools


class FakeStore:
    """벡터DB 대역. where 필터 중 이 테스트가 쓰는 형태만 흉내 낸다."""

    def __init__(self, metadatas):
        self._metadatas = metadatas

    def get(self, where=None, include=None):
        rows = self._metadatas
        if where and "source_type" in where:
            rows = [m for m in rows if m.get("source_type") == where["source_type"]]
        elif where and "date" in where:
            rows = [m for m in rows if m.get("date") == where["date"]]
        return {"ids": [str(i) for i in range(len(rows))], "metadatas": rows}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """logs 디렉토리와 벡터DB를 통째로 대역으로 바꾼다."""
    monkeypatch.setattr(log_tools, "LOGS_DIR", str(tmp_path))

    state = {"metadatas": []}
    monkeypatch.setattr(log_tools, "_open_collection",
                        lambda user_id: FakeStore(state["metadatas"]))

    def write(date: str, body: str):
        (tmp_path / f"{date.replace('-', '.')}_log.md").write_text(body, encoding="utf-8")

    state["write"] = write
    return state


def overview(world):
    return log_tools.journal_overview("tester")


class TestIndexDrift:
    """파일은 있는데 색인이 없으면 검색에서 통째로 빠진다."""

    def test_색인이_없으면_미등록으로_표시한다(self, world):
        world["write"]("2026-07-28", "# 일지\n내용")

        result = overview(world)

        assert result["unindexed"] == 1
        assert result["journals"][0]["indexed"] is False

    def test_색인이_있으면_등록됨으로_표시한다(self, world):
        world["write"]("2026-07-28", "# 일지\n내용")
        world["metadatas"] = [{"source_type": "journal", "date": "2026-07-28"}]

        result = overview(world)

        assert result["unindexed"] == 0
        assert result["journals"][0]["indexed"] is True

    def test_파일이_없으면_목록에도_없다(self, world):
        """색인만 남은 것은 지워진 일지다 — 목록의 진실은 파일이다."""
        world["metadatas"] = [{"source_type": "journal", "date": "2026-07-28"}]

        assert overview(world)["journals"] == []

    def test_최신_날짜가_먼저_온다(self, world):
        for date in ("2026-07-28", "2026-08-03", "2026-07-14"):
            world["write"](date, "# 일지")

        dates = [j["date"] for j in overview(world)["journals"]]

        assert dates == ["2026-08-03", "2026-07-28", "2026-07-14"]

    def test_일지가_아닌_파일은_무시한다(self, world, tmp_path):
        world["write"]("2026-07-28", "# 일지")
        (tmp_path / "README.md").write_text("문서", encoding="utf-8")

        assert len(overview(world)["journals"]) == 1


class TestContributingSources:
    """'이 일지가 무엇으로 만들어졌는가'는 화면의 핵심 정보다."""

    def test_그날_기록이_있는_소스를_센다(self, world):
        world["write"]("2026-07-28", "# 일지")
        world["metadatas"] = [
            {"source_type": "git", "source_name": "TIL", "source_id": 6, "date": "2026-07-28"},
            {"source_type": "git", "source_name": "TIL", "source_id": 6, "date": "2026-07-28"},
            {"source_type": "git_log", "source_name": "커밋", "source_id": 7, "date": "2026-07-28"},
        ]

        sources = overview(world)["journals"][0]["sources"]

        assert sources[0] == {"source_id": 6, "name": "TIL", "type": "git", "chunks": 2}
        assert sources[1]["chunks"] == 1

    def test_일지_자신은_재료로_세지_않는다(self, world):
        world["write"]("2026-07-28", "# 일지")
        world["metadatas"] = [
            {"source_type": "journal", "source_name": "일지", "source_id": 0, "date": "2026-07-28"},
            {"source_type": "git", "source_name": "TIL", "source_id": 6, "date": "2026-07-28"},
        ]

        sources = overview(world)["journals"][0]["sources"]

        assert [s["type"] for s in sources] == ["git"]

    def test_기록해_둔_것이_있으면_그것을_쓴다(self, world):
        """일지는 쓰던 시점의 자료로 만들어졌다. 나중에 늘어난 소스를 섞으면 거짓이 된다."""
        world["write"]("2026-07-28", "# 일지")
        world["metadatas"] = [
            {
                "source_type": "journal", "date": "2026-07-28",
                "contributors": json.dumps(
                    [{"source_id": 6, "name": "TIL", "type": "git", "chunks": 1}]),
            },
            # 일지를 쓴 뒤에 추가된 소스 — 재료가 아니다
            {"source_type": "agent_chatlog", "source_name": "대화", "source_id": 9,
             "date": "2026-07-28"},
        ]

        journal = overview(world)["journals"][0]

        assert [s["name"] for s in journal["sources"]] == ["TIL"]
        assert journal["sources_estimated"] is False

    def test_기록이_없는_옛_일지는_추정이라고_밝힌다(self, world):
        world["write"]("2026-07-28", "# 일지")
        world["metadatas"] = [
            {"source_type": "journal", "date": "2026-07-28"},
            {"source_type": "git", "source_name": "TIL", "source_id": 6, "date": "2026-07-28"},
        ]

        journal = overview(world)["journals"][0]

        assert journal["sources_estimated"] is True
        assert [s["name"] for s in journal["sources"]] == ["TIL"]

    def test_기록이_깨져_있으면_추정으로_되돌아간다(self, world):
        world["write"]("2026-07-28", "# 일지")
        world["metadatas"] = [
            {"source_type": "journal", "date": "2026-07-28", "contributors": "깨진 JSON{"},
            {"source_type": "git", "source_name": "TIL", "source_id": 6, "date": "2026-07-28"},
        ]

        journal = overview(world)["journals"][0]

        assert journal["sources_estimated"] is True
        assert [s["name"] for s in journal["sources"]] == ["TIL"]


class TestTitle:
    def test_첫_제목_줄을_뽑는다(self, world):
        world["write"]("2026-07-28", "# 2026년 7월 28일 일지\n\n## 한 일\n- 작업")

        assert overview(world)["journals"][0]["title"] == "2026년 7월 28일 일지"

    def test_제목이_없으면_첫_줄을_쓴다(self, world):
        world["write"]("2026-07-28", "\n\n오늘은 통합 에이전트를 만들었다.")

        assert overview(world)["journals"][0]["title"] == "오늘은 통합 에이전트를 만들었다."

    def test_빈_파일도_넘어간다(self, world):
        world["write"]("2026-07-28", "")

        assert overview(world)["journals"][0]["title"] == ""
