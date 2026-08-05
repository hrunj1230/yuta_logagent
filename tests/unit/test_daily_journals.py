"""
기간 일지 생성 단위 테스트

왜 필요한가:
    기간을 한 번에 조회하면 분량 예산에 걸려 문서가 통째로 빠진다. 실측으로
    일주일치가 49,728자였고 예산 40,000자를 넘어 문서 1개가 사라졌다. 날짜별로
    쪼개면 가장 큰 날도 24,113자라 예산에 닿지 않는다.

    여기서 잠그는 것은 "언제 작업을 시작하고 언제 멈춰 물어보는가"다. 사용자가
    손으로 고친 일지를 조용히 덮어쓰면 되돌릴 방법이 없다.

    LLM 도 네트워크도 타지 않는다 — 스레드 시작과 하루 작성은 대역으로 바꾼다.
"""
import pytest

from src.tools import log as log_tools


@pytest.fixture(autouse=True)
def clean_progress():
    """진행률은 모듈 수준 dict 라 테스트끼리 새어 나간다."""
    log_tools._journal_jobs.clear()
    yield
    log_tools._journal_jobs.clear()


@pytest.fixture
def fake_world(monkeypatch, tmp_path):
    """벡터DB·파일시스템·백그라운드 스레드를 전부 대역으로 바꾼다."""
    state = {"records": [], "journals": set(), "started": None}

    monkeypatch.setattr(log_tools, "_dates_with_records",
                        lambda user_id, targets: [d for d in targets if d in state["records"]])
    monkeypatch.setattr(log_tools.os.path, "exists",
                        lambda path: path in state["journals"])

    class FakeThread:
        def __init__(self, target=None, args=(), **kwargs):
            state["started"] = args[1]      # 실제로 작성하기로 한 날짜 목록

        def start(self):
            pass

    monkeypatch.setattr(log_tools.threading, "Thread", FakeThread)
    return state


def call(start, end, existing=""):
    return log_tools.generate_daily_journals.invoke({
        "start_date": start, "end_date": end, "user_id": "tester", "existing": existing,
    })


class TestWhenItStarts:
    def test_기록이_있는_날만_작업한다(self, fake_world):
        """기록 없는 날까지 부르면 '자료가 없습니다' 일지가 생긴다."""
        fake_world["records"] = ["2026-07-28", "2026-07-30"]

        result = call("2026-07-28", "2026-07-31")

        assert fake_world["started"] == ["2026-07-28", "2026-07-30"]
        assert "2일" in result

    def test_기록이_아예_없으면_시작하지_않는다(self, fake_world):
        fake_world["records"] = []

        result = call("2026-07-28", "2026-07-31")

        assert fake_world["started"] is None
        assert "자료가 없어" in result

    def test_이미_돌고_있으면_두_번_시작하지_않는다(self, fake_world):
        fake_world["records"] = ["2026-07-28"]
        log_tools._set_progress("tester", phase="writing", done=1, total=5, date="2026-07-29")

        result = call("2026-07-28", "2026-07-31")

        assert fake_world["started"] is None
        assert "이미 일지를 만드는 중" in result

    def test_날짜를_해석하지_못하면_거절한다(self, fake_world):
        result = call("어제쯤", "그저께")

        assert fake_world["started"] is None
        assert "❌" in result


class TestExistingJournals:
    """사용자가 손으로 고친 일지를 조용히 덮어쓰면 되돌릴 수 없다."""

    def test_겹치면_시작하지_않고_물어본다(self, fake_world):
        fake_world["records"] = ["2026-07-28", "2026-07-29"]
        fake_world["journals"] = {log_tools._journal_path("2026-07-28")}

        result = call("2026-07-28", "2026-07-29")

        assert fake_world["started"] is None
        assert "이미 일지가 있습니다" in result
        assert "2026-07-28" in result

    def test_skip_이면_겹치는_날을_빼고_시작한다(self, fake_world):
        fake_world["records"] = ["2026-07-28", "2026-07-29"]
        fake_world["journals"] = {log_tools._journal_path("2026-07-28")}

        result = call("2026-07-28", "2026-07-29", existing="skip")

        assert fake_world["started"] == ["2026-07-29"]
        assert "건너뜁니다" in result

    def test_overwrite_이면_전부_다시_쓴다(self, fake_world):
        fake_world["records"] = ["2026-07-28", "2026-07-29"]
        fake_world["journals"] = {log_tools._journal_path("2026-07-28")}

        call("2026-07-28", "2026-07-29", existing="overwrite")

        assert fake_world["started"] == ["2026-07-28", "2026-07-29"]

    def test_전부_이미_있고_skip_이면_할_일이_없다(self, fake_world):
        fake_world["records"] = ["2026-07-28"]
        fake_world["journals"] = {log_tools._journal_path("2026-07-28")}

        result = call("2026-07-28", "2026-07-28", existing="skip")

        assert fake_world["started"] is None
        assert "새로 만들 것이 없습니다" in result

    def test_겹치지_않으면_묻지_않고_시작한다(self, fake_world):
        fake_world["records"] = ["2026-07-29"]
        fake_world["journals"] = {log_tools._journal_path("2026-07-28")}

        call("2026-07-29", "2026-07-29")

        assert fake_world["started"] == ["2026-07-29"]


class TestProgressReporting:
    def test_작성_중에는_날짜와_진행률을_보여준다(self):
        log_tools._set_progress("tester", phase="writing", done=3, total=7, date="2026-07-31")

        text = log_tools.describe_journal_progress(log_tools.journal_progress("tester"))

        assert "2026-07-31" in text and "3/7" in text and "42%" in text

    def test_완료되면_작성_건수를_보여준다(self):
        log_tools._set_progress("tester", phase="done", done=2, total=2,
                                written=["2026-07-28", "2026-07-29"], failed=[])

        assert "완료 (2건 작성)" == log_tools.describe_journal_progress(
            log_tools.journal_progress("tester"))

    def test_실패가_있으면_숨기지_않는다(self):
        log_tools._set_progress("tester", phase="done", done=2, total=2,
                                written=["2026-07-28"], failed=["2026-07-29(오류)"])

        assert "실패 1건" in log_tools.describe_journal_progress(
            log_tools.journal_progress("tester"))
