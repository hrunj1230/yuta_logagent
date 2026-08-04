"""
대화 로그 수집 단위 테스트

임시 디렉토리에 JSONL 을 만들어 돌리므로 실제 트랜스크립트도, 네트워크도,
ChromaDB 도 타지 않는다.

여기서 잠그는 것은 "사람이 친 말만, 빠짐없이, 날짜별로 들어오는가"다.
트랜스크립트 형식이 바뀌면 수집이 0건이 되는데 임베딩은 성공으로 끝나므로,
테스트가 없으면 대화가 통째로 빠져도 드러나지 않는다.
"""
import json
import types
from pathlib import Path

import pytest

from src.tools import chatlog


def entry(text, date="2026-08-04", time="10:00", uid="u1", session="s-abcdef12", type_="user"):
    """트랜스크립트 한 줄을 만든다."""
    return json.dumps({
        "type": type_,
        "uuid": uid,
        "sessionId": session,
        "timestamp": f"{date}T{time}:00.000Z",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }, ensure_ascii=False)


@pytest.fixture
def transcripts(tmp_path: Path):
    """JSONL 줄들을 받아 트랜스크립트 디렉토리를 만드는 헬퍼."""
    def build(*lines: str, name: str = "session.jsonl") -> Path:
        (tmp_path / name).write_text("\n".join(lines), encoding="utf-8")
        return tmp_path
    return build


@pytest.fixture
def source():
    return types.SimpleNamespace(id=3, name="myproject")


class TestReadTurns:
    def test_사람이_친_말을_읽는다(self, transcripts):
        root = transcripts(
            entry("이 함수가 왜 느린지 같이 보자", uid="a"),
            entry("인덱스를 추가하는 쪽으로 가자", uid="b", time="11:00"),
        )
        turns, skipped = chatlog.read_turns(root)

        assert [t["text"] for t in turns] == [
            "이 함수가 왜 느린지 같이 보자",
            "인덱스를 추가하는 쪽으로 가자",
        ]
        assert skipped == {}

    def test_도구가_끼워넣은_텍스트는_제외한다(self, transcripts):
        root = transcripts(
            entry("진짜로 사람이 친 충분히 긴 말", uid="a"),
            entry("<system-reminder>배경 정보입니다</system-reminder>", uid="b"),
            entry("<command-name>clear</command-name>", uid="c"),
            entry("Caveat: 아래 메시지는 자동 생성되었습니다", uid="d"),
        )
        turns, skipped = chatlog.read_turns(root)

        assert len(turns) == 1
        assert skipped["system_text"] == 3

    def test_짧은_맞장구는_제외한다(self, transcripts):
        """'A', '응' 같은 선택지 응답은 그 자체로 아무것도 말해주지 않는다."""
        root = transcripts(
            entry("이 설계로 가는 게 맞을까 고민된다", uid="a"),
            entry("A", uid="b"),
            entry("그렇게 해줘", uid="c"),
        )
        turns, skipped = chatlog.read_turns(root)

        assert len(turns) == 1
        assert skipped["too_short"] == 2

    def test_긴_붙여넣기는_상한까지만_담는다(self, transcripts):
        root = transcripts(entry("로그 붙여넣는다 " + "가나다라마바사" * 500, uid="a"))
        turns, _ = chatlog.read_turns(root)

        assert len(turns[0]["text"]) <= chatlog.MAX_TURN_CHARS + 10
        assert turns[0]["text"].endswith("…(생략)")

    def test_줄바꿈은_한_줄로_편다(self, transcripts):
        """'- 발화' 목록이므로 둘째 줄이 목록 밖으로 흘러나오면 안 된다."""
        root = transcripts(entry("에러가 났다\nTraceback (most recent call last):\n  File x", uid="a"))
        turns, _ = chatlog.read_turns(root)

        assert "\n" not in turns[0]["text"]
        assert turns[0]["text"].startswith("에러가 났다 Traceback")

    def test_사람의_말이_아닌_블록은_건너뛴다(self, transcripts):
        line = json.dumps({
            "type": "user", "uuid": "a", "sessionId": "s", "timestamp": "2026-08-04T10:00:00Z",
            "message": {"content": [
                {"type": "tool_result", "content": "도구 결과 본문"},
                {"type": "text", "text": "그리고 이건 사람이 친 말이다"},
            ]},
        }, ensure_ascii=False)
        turns, _ = chatlog.read_turns(transcripts(line))

        assert [t["text"] for t in turns] == ["그리고 이건 사람이 친 말이다"]

    def test_assistant_항목은_담지_않는다(self, transcripts):
        root = transcripts(
            entry("사람이 물어본 충분히 긴 질문", uid="a"),
            entry("모델이 답한 충분히 긴 대답", uid="b", type_="assistant"),
        )
        turns, _ = chatlog.read_turns(root)

        assert len(turns) == 1

    def test_같은_uuid_는_한_번만_담는다(self, transcripts):
        """세션을 이어 열면 같은 항목이 다시 기록될 수 있다."""
        root = transcripts(
            entry("한 번만 담겨야 하는 발화", uid="same"),
            entry("한 번만 담겨야 하는 발화", uid="same"),
        )
        turns, skipped = chatlog.read_turns(root)

        assert len(turns) == 1
        assert skipped["duplicate"] == 1

    def test_깨진_줄은_사유와_함께_건너뛴다(self, transcripts):
        root = transcripts("{망가진 json", entry("정상적인 발화 한 줄이다", uid="a"))
        turns, skipped = chatlog.read_turns(root)

        assert len(turns) == 1
        assert skipped["bad_json"] == 1

    def test_여러_세션_파일을_시간순으로_모은다(self, transcripts, tmp_path):
        transcripts(entry("나중 세션에서 나눈 발화이다", date="2026-08-04", uid="b", session="s2"),
                    name="b.jsonl")
        root = transcripts(entry("먼저 있었던 세션에서 나눈 발화이다", date="2026-08-01", uid="a", session="s1"),
                           name="a.jsonl")
        turns, _ = chatlog.read_turns(root)

        assert [t["date"] for t in turns] == ["2026-08-01", "2026-08-04"]


class TestDailyDocuments:
    def test_날짜별로_문서가_하나씩_생긴다(self, transcripts, source):
        root = transcripts(
            entry("첫날에 나눈 이야기 내용이다", date="2026-08-01", uid="a"),
            entry("둘째날 이야기 그 첫 번째이다", date="2026-08-02", uid="b"),
            entry("둘째날 이야기 그 두 번째이다", date="2026-08-02", uid="c", time="11:00"),
        )
        turns, _ = chatlog.read_turns(root)
        docs = chatlog.daily_documents(turns, source, "someone")
        by_date = {d.metadata["date"]: d for d in docs}

        assert len(docs) == 2
        assert by_date["2026-08-01"].metadata["turn_count"] == 1
        assert by_date["2026-08-02"].metadata["turn_count"] == 2

    def test_하루_안에서는_시간순으로_적는다(self, transcripts, source):
        root = transcripts(
            entry("나중에 하게 된 이야기이다", uid="b", time="15:00"),
            entry("먼저 꺼내 놓은 이야기이다", uid="a", time="09:00"),
        )
        turns, _ = chatlog.read_turns(root)
        body = chatlog.daily_documents(turns, source, "someone")[0].page_content

        assert body.index("먼저 꺼내 놓은") < body.index("나중에 하게 된")

    def test_원본과_대조할_수_있다(self, transcripts, source):
        """세션 id 를 남겨야 대화가 빠졌는지 검산할 수 있다."""
        root = transcripts(
            entry("세션 하나에서 나온 발화이다", uid="a", session="aaaaaaaa-1111"),
            entry("세션 둘에서 나온 발화이다", uid="b", session="bbbbbbbb-2222", time="12:00"),
        )
        turns, _ = chatlog.read_turns(root)
        meta = chatlog.daily_documents(turns, source, "someone")[0].metadata

        assert set(meta["session_ids"].split(",")) == {"aaaaaaaa", "bbbbbbbb"}
        assert meta["turn_count"] == 2

    def test_교체용_키가_붙는다(self, transcripts, source):
        """하루치를 통째로 갈아끼우려면 안정적인 키와 내용 해시가 필요하다."""
        root = transcripts(entry("어떤 발화 하나가 여기 있다", date="2026-08-01", uid="a"))
        turns, _ = chatlog.read_turns(root)
        meta = chatlog.daily_documents(turns, source, "someone")[0].metadata

        assert meta["file_path"] == "chat/2026-08-01"
        assert len(meta["file_hash"]) == 64
        assert meta["source_type"] == "agent_chatlog"
