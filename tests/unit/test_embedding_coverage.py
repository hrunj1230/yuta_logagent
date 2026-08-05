"""
소스별 임베딩 현황 집계 단위 테스트

왜 필요한가:
    소스마다 다루는 기간이 다르다 — 실측으로 TIL 은 38일(5/14~8/03), 커밋이력은
    8일(7/09~8/03), 대화로그는 6일(7/27~8/04)이었다. 총계만 보면 "청크 92개"
    지만, 날짜별로 펼치면 '이 날은 커밋은 있는데 TIL 이 없다' 같은 구멍이
    드러난다. 그 구멍이 곧 일지가 빈약해지는 날이다.

    청크에 이미 date·source_id 가 붙어 있으므로 새로 저장할 것은 없고 세기만
    하면 된다. 이 테스트는 '무엇을 세고 무엇을 빼는가'를 못박는다.

    ChromaDB 도 네트워크도 타지 않는다.
"""
import pytest

from src.tools import embedding as embedding_tools


class FakeCollection:
    def __init__(self, metadatas):
        self._metadatas = metadatas

    def get(self, where=None, include=None):
        return {"ids": [str(i) for i in range(len(self._metadatas))],
                "metadatas": self._metadatas}


@pytest.fixture
def collection(monkeypatch):
    state = {"metadatas": []}
    monkeypatch.setattr(embedding_tools, "_get_chroma_collection",
                        lambda user_id: FakeCollection(state["metadatas"]))
    return state


def chunk(source_id, name, stype, date):
    return {"source_id": source_id, "source_name": name,
            "source_type": stype, "date": date}


def coverage(collection):
    return embedding_tools.embedding_coverage("tester")


class TestPerSourceSummary:
    def test_소스별_청크와_날짜_수를_센다(self, collection):
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(6, "TIL", "git", "2026-07-29"),
        ]

        source = coverage(collection)["sources"][0]

        assert source["chunks"] == 3
        assert source["days"] == 2       # 같은 날 두 청크는 하루로 센다

    def test_소스가_다루는_기간을_알려준다(self, collection):
        """소스마다 기간이 달라서, 총계만으로는 어디가 비었는지 안 보인다."""
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-05-14"),
            chunk(6, "TIL", "git", "2026-08-03"),
            chunk(7, "커밋", "git_log", "2026-07-09"),
        ]

        by_id = {s["source_id"]: s for s in coverage(collection)["sources"]}

        assert (by_id[6]["first"], by_id[6]["last"]) == ("2026-05-14", "2026-08-03")
        assert (by_id[7]["first"], by_id[7]["last"]) == ("2026-07-09", "2026-07-09")

    def test_일지는_재료로_세지_않는다(self, collection):
        """일지는 자료가 아니라 자료로 만든 결과물이다."""
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(0, "일지", "journal", "2026-07-28"),
        ]

        sources = coverage(collection)["sources"]

        assert [s["type"] for s in sources] == ["git"]

    def test_날짜가_없는_청크는_세지_않는다(self, collection):
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            {"source_id": 6, "source_name": "TIL", "source_type": "git"},
        ]

        assert coverage(collection)["sources"][0]["chunks"] == 1


class TestDateRows:
    def test_날짜별로_소스별_청크_수를_모은다(self, collection):
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(7, "커밋", "git_log", "2026-07-28"),
        ]

        row = coverage(collection)["rows"][0]

        assert row["counts"] == {6: 2, 7: 1}
        assert row["total"] == 3

    def test_그날_비어_있는_소스를_알려준다(self, collection):
        """구멍이 보여야 '이 날은 왜 일지가 빈약한가'를 설명할 수 있다."""
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(7, "커밋", "git_log", "2026-07-29"),
        ]

        by_date = {r["date"]: r for r in coverage(collection)["rows"]}

        assert by_date["2026-07-28"]["missing"] == [7]
        assert by_date["2026-07-29"]["missing"] == [6]

    def test_최신_날짜가_먼저_온다(self, collection):
        collection["metadatas"] = [
            chunk(6, "TIL", "git", d)
            for d in ("2026-07-28", "2026-08-03", "2026-07-14")
        ]

        dates = [r["date"] for r in coverage(collection)["rows"]]

        assert dates == ["2026-08-03", "2026-07-28", "2026-07-14"]

    def test_기록이_있는_날짜_수를_센다(self, collection):
        collection["metadatas"] = [
            chunk(6, "TIL", "git", "2026-07-28"),
            chunk(7, "커밋", "git_log", "2026-07-28"),
            chunk(6, "TIL", "git", "2026-07-29"),
        ]

        assert coverage(collection)["dates"] == 2


class TestFailureIsQuiet:
    def test_조회에_실패해도_화면을_막지_않는다(self, monkeypatch):
        """현황은 부가 정보다. 못 읽는다고 일지 관리까지 못 쓰게 되면 안 된다."""
        def explode(user_id):
            raise RuntimeError("컬렉션 없음")

        monkeypatch.setattr(embedding_tools, "_get_chroma_collection", explode)

        assert embedding_tools.embedding_coverage("tester") == {
            "sources": [], "rows": [], "dates": 0,
        }
