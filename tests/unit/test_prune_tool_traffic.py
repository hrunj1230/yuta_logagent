"""
대화 기록에서 도구 트래픽을 걷어내는 로직 단위 테스트

왜 필요한가:
    LLM API 는 무상태라 매 요청에 대화 기록 전체를 다시 싣는다. retriever_vectordb
    의 결과는 하루치가 1만 토큰을 넘는데, 일지를 쓰고 나면 다시 쓸 일이 없으면서도
    기록에 남아 이후 모든 호출에 따라다녔다. 실측으로 일지 5건에 275,265 토큰이
    들었고 그중 81% 가 재전송이었다.

    조용히 새는 비용이라 화면에도 로그에도 드러나지 않는다. 그래서 "무엇을 지우고
    무엇을 남기는가"를 테스트로 못박는다.

    API 도 네트워크도 타지 않는다 — 순수 함수만 부른다.
"""
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from src.unified_controller_single import describe_usage, prune_tool_traffic


def conversation():
    """일지 한 건을 만든 뒤의 전형적인 대화 기록."""
    return [
        HumanMessage(content="2026-07-28 일지 써줘", id="h1"),
        AIMessage(content="", id="a1", tool_calls=[
            {"name": "retriever_vectordb", "args": {"date": "2026-07-28"}, "id": "t1"},
        ]),
        ToolMessage(content="커밋 42건 ..." * 500, tool_call_id="t1", id="t1msg"),
        AIMessage(content="일지를 저장했습니다.", id="a2"),
    ]


def removed_ids(messages) -> set[str]:
    result = prune_tool_traffic({"messages": messages})
    assert all(isinstance(m, RemoveMessage) for m in result["messages"])
    return {m.id for m in result["messages"]}


class TestWhatGetsRemoved:
    def test_도구_결과를_지운다(self):
        """1만 토큰짜리 조회 결과가 이후 모든 요청에 따라다니면 안 된다."""
        assert "t1msg" in removed_ids(conversation())

    def test_도구를_부른_기록도_함께_지운다(self):
        """tool_use 만 남고 tool_result 가 사라지면 API 가 400 으로 거절한다."""
        gone = removed_ids(conversation())

        assert "a1" in gone and "t1msg" in gone

    def test_사람의_말은_남긴다(self):
        assert "h1" not in removed_ids(conversation())

    def test_최종_답변은_남긴다(self):
        """답변에 요약이 들어 있어야 '그중 두 번째 거' 같은 후속 대화가 통한다."""
        assert "a2" not in removed_ids(conversation())

    def test_도구를_쓰지_않은_턴은_아무것도_지우지_않는다(self):
        messages = [
            HumanMessage(content="안녕", id="h1"),
            AIMessage(content="안녕하세요", id="a1"),
        ]

        assert removed_ids(messages) == set()

    def test_도구를_여러_번_부른_턴도_전부_짝으로_지운다(self):
        messages = [
            HumanMessage(content="소스 추가하고 임베딩해줘", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[
                {"name": "add_source_to_db", "args": {}, "id": "t1"}]),
            ToolMessage(content="추가됨", tool_call_id="t1", id="t1msg"),
            AIMessage(content="", id="a2", tool_calls=[
                {"name": "embed_source", "args": {}, "id": "t2"}]),
            ToolMessage(content="시작됨", tool_call_id="t2", id="t2msg"),
            AIMessage(content="등록하고 임베딩을 시작했습니다.", id="a3"),
        ]

        assert removed_ids(messages) == {"a1", "t1msg", "a2", "t2msg"}


class TestUsageReporting:
    """캐시가 실제로 적중하는지는 이 문구로만 드러난다."""

    def test_적중을_보고한다(self):
        result = AIMessage(content="", usage_metadata={
            "input_tokens": 3260, "output_tokens": 12, "total_tokens": 3272,
            "input_token_details": {"cache_read": 3184},
        })

        assert "캐시적중 3,184" in describe_usage(result)

    def test_적중하지_않으면_그렇다고_말한다(self):
        """캐싱을 붙여 놓고 계속 0 이면 프리픽스를 깨는 값이 들어간 것이다."""
        result = AIMessage(content="", usage_metadata={
            "input_tokens": 3260, "output_tokens": 12, "total_tokens": 3272,
            "input_token_details": {"cache_read": 0},
        })

        assert "캐시적중 없음" in describe_usage(result)

    def test_사용량_정보가_없으면_조용히_넘어간다(self):
        assert describe_usage(AIMessage(content="hi")) == "정보 없음"
