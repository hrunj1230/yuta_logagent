"""
종결 도구 뒤의 LLM 호출을 건너뛰는 로직 단위 테스트

왜 필요한가:
    일지 한 건을 쓰는 데 LLM 이 세 번 불렸다. 첫 번째는 "자료를 찾자", 두 번째는
    자료를 읽고 일지를 쓰는 진짜 작업, 세 번째는 "저장했습니다" 한 줄이었다.

    문제는 세 번째의 위치다. 그 시점 대화에는 자료 원문(하루치 1만 토큰↑)과
    방금 쓴 일지 본문이 둘 다 올라와 있다. API 는 무상태라 그걸 전부 다시 실어
    보내고, 돌아오는 것은 maker_logfile 이 이미 돌려준 문장의 재작성이었다.

    그래서 종결 도구가 성공하면 그 결과를 그대로 답변으로 세운다. 다만 '언제
    건너뛰어도 되는가'를 잘못 잡으면 연쇄 호출이 끊기거나 실패가 조용히 성공처럼
    보고된다. 그 경계를 여기서 못박는다.

    API 도 네트워크도 타지 않는다 — 순수 함수만 부른다.
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.unified_controller_single import (
    TERMINAL_TOOLS,
    finalize_from_tool,
    route_after_tools,
)

SAVED = "✅ 일지 저장 완료: logs/2026.08.03_log.md\n🔎 일지를 검색 대상에 등록했습니다."


def after_saving_journal(status: str = "success"):
    """일지를 막 저장한 직후의 대화 기록."""
    return [
        HumanMessage(content="2026-08-03 일지 써줘", id="h1"),
        AIMessage(content="", id="a1", tool_calls=[
            {"name": "retriever_vectordb", "args": {"date": "2026-08-03"}, "id": "t1"},
        ]),
        ToolMessage(content="커밋 42건 ..." * 500, tool_call_id="t1", id="t1msg"),
        AIMessage(content="", id="a2", tool_calls=[
            {"name": "maker_logfile", "args": {"content": "# 일지"}, "id": "t2"},
        ]),
        ToolMessage(content=SAVED, tool_call_id="t2", id="t2msg", status=status),
    ]


def route(messages) -> str:
    return route_after_tools({"messages": messages})


class TestWhenToSkip:
    def test_일지를_저장했으면_LLM을_부르지_않는다(self):
        """대화가 가장 무거운 시점이다. 왕복 한 번이 1만 토큰을 넘는다."""
        assert route(after_saving_journal()) == "finalize"

    def test_자료를_찾은_직후에는_부른다(self):
        """일지를 아직 안 썼다. 여기서 끊으면 아무것도 만들어지지 않는다."""
        messages = after_saving_journal()[:3]

        assert route(messages) == "agent"

    def test_소스를_추가한_직후에는_부른다(self):
        """add_source_to_db → embed_source 연쇄가 끊기면 임베딩이 시작되지 않는다."""
        messages = [
            HumanMessage(content="이 저장소 추가해줘", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[
                {"name": "add_source_to_db", "args": {}, "id": "t1"}]),
            ToolMessage(content="✅ 소스가 추가되었습니다. (ID: 3)", tool_call_id="t1", id="t1msg"),
        ]

        assert route(messages) == "agent"

    def test_저장이_실패했으면_부른다(self):
        """실패는 사정을 설명하고 다음 수를 제안해야 한다 — 판단이 필요하다."""
        assert route(after_saving_journal(status="error")) == "agent"

    def test_종결_도구와_다른_도구를_함께_불렀으면_부른다(self):
        """하나라도 이어져야 할 것이 섞여 있으면 건너뛰지 않는다."""
        messages = [
            HumanMessage(content="일지 쓰고 소스도 정리해줘", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[
                {"name": "maker_logfile", "args": {}, "id": "t1"},
                {"name": "get_user_sources", "args": {}, "id": "t2"}]),
            ToolMessage(content=SAVED, tool_call_id="t1", id="t1msg"),
            ToolMessage(content="소스 2개", tool_call_id="t2", id="t2msg"),
        ]

        assert route(messages) == "agent"

    def test_도구를_쓰지_않았으면_부른다(self):
        messages = [HumanMessage(content="안녕", id="h1")]

        assert route(messages) == "agent"

    def test_연쇄를_끊는_도구는_종결_목록에_없다(self):
        """이 목록에 무엇이 들어가는지가 이 최적화의 안전선이다."""
        assert TERMINAL_TOOLS == {"maker_logfile"}


class TestFinalAnswer:
    def test_도구_결과를_그대로_답변으로_세운다(self):
        """prune 이 도구 기록을 걷어내므로 여기서 답변을 남기지 않으면 대화가 비어 버린다."""
        result = finalize_from_tool({"messages": after_saving_journal()})
        answer = result["messages"][0]

        assert isinstance(answer, AIMessage)
        assert answer.content == SAVED

    def test_답변에는_도구_호출이_붙지_않는다(self):
        """tool_calls 가 붙으면 prune 이 이 답변까지 지워 버린다."""
        answer = finalize_from_tool({"messages": after_saving_journal()})["messages"][0]

        assert not answer.tool_calls

    def test_자료_원문은_답변에_섞이지_않는다(self):
        """1만 토큰짜리 조회 결과가 화면에 쏟아지면 안 된다."""
        answer = finalize_from_tool({"messages": after_saving_journal()})["messages"][0]

        assert "커밋 42건" not in answer.content
