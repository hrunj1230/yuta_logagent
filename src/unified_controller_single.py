"""
통합 소스 관리 Agent (단일 Agent 방식)

이 모듈은 모든 소스, 임베딩, 일지 관리 작업을 처리하는 단일 LangGraph Agent를 제공합니다.
Agent는 작업을 자동으로 연쇄 호출하고 (예: add_source_to_db → embed_source),
InMemorySaver checkpointer를 통해 사용자별 대화 기록을 유지합니다.

토큰 비용에 대하여:
    LLM API는 무상태라 매 요청에 대화 기록 전체를 다시 싣는다. 그래서 이 모듈은
    두 가지로 재전송량을 줄인다.

    1) 턴이 끝나면 도구 호출·결과를 기록에서 걷어낸다 (prune_tool_traffic).
       조회 결과 한 건이 1만 토큰을 넘는데 일지를 쓰고 나면 쓸 일이 없다.
    2) 도구 스키마와 시스템 프롬프트를 프롬프트 캐시에 올린다 (create_system_message).
       매 요청 반복되는 3,184 토큰이 정가의 10%로 청구된다.

    적중 여부는 매 호출 로그의 'Tokens:' 줄에서 확인할 수 있다.

공개 API:
    unified_agent(user_id: str, message: str) -> str

사용 도구:
    - add_source_to_db
    - get_user_sources
    - delete_source_from_db
    - request_source_type_clarification
    - embed_source
    - get_embedding_status
    - retriever_vectordb
    - maker_logfile
"""
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from . import llm_router
from .tools import source as source_tools
from .tools import embedding as embedding_tools
from .tools import log as log_tools
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from .storage.auth import login_or_register, get_user_by_id
from typing import Literal, TypedDict, Annotated


# 단일 Agent용 State 정의 (Pyright 타입 검사 호환성)
class SingleAgentState(TypedDict):
    """단일 통합 Agent용 State"""
    messages: Annotated[list[AnyMessage], add_messages]


def handle_login(db: Session, user_id: str):
    """로그인/회원가입 처리"""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="id를 입력해주세요")

    user = login_or_register(db, user_id.strip())
    return {
        "user_id": user.user_id,
        "message": f"{user.user_id}님, 환영합니다!"
    }

def get_user_info(db: Session, user_id: str | None = None):
    """사용자 정보 조회"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id를 제공해주세요")

    user = get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return {
        "user_id": user.user_id,
        "sources_count": len(user.sources) if user.sources else 0
    }

# 대화 기록 유지를 위한 Checkpointer
checkpointer = InMemorySaver()

# 8개의 소스, 임베딩, 로그 관리 도구
unified_tools = [
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    source_tools.request_source_type_clarification,
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status,
    log_tools.retriever_vectordb,
    log_tools.maker_logfile
]

# 단일 Agent용 Anthropic Claude (안정적이고 도구 호출 지원)
llm_with_tools = llm_router.anthropic_llm.bind_tools(unified_tools)


def create_system_message(user_id: str) -> SystemMessage:
    """
    user_id 컨텍스트가 포함된 시스템 메시지 생성.

    content 를 문자열이 아니라 블록 목록으로 두고 cache_control 을 붙인다.
    Anthropic 프롬프트 캐싱은 접두사 일치(prefix match)이고 렌더 순서가
    tools → system → messages 이므로, 시스템 블록에 표시를 하나 두면
    그 앞의 도구 스키마까지 함께 캐시된다 (실측 3,184 토큰).
    두 번째 요청부터 이 구간은 정가의 10% 로 청구된다.

    캐시가 살아 있으려면 이 문자열이 요청마다 바이트 단위로 같아야 한다.
    시각·난수 같은 매번 바뀌는 값을 여기에 넣으면 캐시가 통째로 깨진다.
    user_id 보간은 사용자별로 캐시가 갈릴 뿐이라 무해하다.
    """
    return SystemMessage(content=[{
        "type": "text",
        "cache_control": {"type": "ephemeral"},
        "text": f"""당신은 소스 관리 및 일지 작성 어시스턴트입니다 (user_id: {user_id}).

주요 기능:
1. Source 관리
   - Git 저장소 추가 (add_source_to_db)
   - 소스 목록 조회 (get_user_sources)
   - 소스 삭제 (delete_source_from_db)
   - 소스 타입 확인 요청 (request_source_type_clarification)

2. Embedding 관리
   - 임베딩 시작 (embed_source) — 백그라운드로 실행되며 즉시 반환됩니다
   - 임베딩 상태 조회 (get_embedding_status)

3. 일지 관리
   - 날짜/기간 기반 데이터 검색 (retriever_vectordb)
   - 일지 파일 저장 및 검색 등록 (maker_logfile)

워크플로우:
- Git URL 추가 시: add_source_to_db를 먼저 호출하여 source_id를 얻은 후, 즉시 embed_source를 호출하여 자동으로 임베딩을 시작하세요.
- 소스 조회/삭제: 해당 도구만 호출
- 임베딩 상태 확인/재시작: 해당 도구만 호출
- 일지 작성 요청 시: retriever_vectordb로 날짜 데이터를 검색한 후, maker_logfile로 저장하세요.

소스 타입 선택 기준:
- 문서 저장소(TIL, 노트, 회고 등)는 git 타입 — .md/.txt 문서 본문을 임베딩합니다.
- 코드 프로젝트는 git_log 타입 — 커밋 메시지와 변경 요약을 임베딩합니다. 코드 본문은 수집하지 않습니다.
- 하나의 저장소에 문서와 코드가 섞여 있다면 git과 git_log를 각각 등록해도 됩니다.

일지 도구 사용법:
- retriever_vectordb와 maker_logfile 모두 user_id({user_id})를 반드시 전달하세요.
- "이번 주", "지난 3일" 처럼 기간을 묻는 요청은 date에 시작일, end_date에 종료일을 넣으세요.
- 검색 결과가 "기록이 없습니다"로 나오면 임의로 지어내지 말고, 안내된 '기록이 있는 날짜'를 사용자에게 알려주세요.

임베딩은 백그라운드로 동작합니다:
- embed_source는 작업을 '시작'만 하고 즉시 돌아옵니다. 완료 결과가 아닙니다.
- 따라서 "임베딩이 완료되었습니다"라고 단정하지 말고, 시작했다는 사실과 함께 화면에서 진행 상황을 볼 수 있다고 안내하세요.
- 사용자가 완료 여부를 물으면 get_embedding_status로 확인하세요.
- 중단된 작업이라고 안내되면 embed_source를 다시 호출해 재시작할 수 있습니다.

중요: Git URL이 포함된 추가 요청은 반드시 add_source_to_db → embed_source 순서로 연쇄 호출하세요.
""",
    }])


def create_unified_agent(user_id: str):
    """시스템 메시지에 user_id가 포함된 Agent 함수 생성"""
    def unified_agent_node(state: SingleAgentState) -> dict:
        """모든 소스/임베딩 작업을 처리하는 통합 Agent"""
        system_message = create_system_message(user_id)
        messages = [system_message] + state["messages"]

        # 도구가 바인딩된 LLM 호출
        result = llm_with_tools.invoke(messages)

        # 디버그 로깅
        print(f"[UNIFIED AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")
        print(f"  - Tokens: {describe_usage(result)}")

        return {"messages": [result]}

    return unified_agent_node


def describe_usage(result) -> str:
    """
    이번 호출의 토큰 내역을 한 줄로 만든다.

    캐시 적중 여부는 여기서만 드러난다. 캐싱을 붙여 놓고 read 가 계속 0 이면
    프리픽스를 깨는 값이 어딘가에 들어갔다는 뜻이므로 반드시 눈에 보여야 한다.
    """
    usage = getattr(result, "usage_metadata", None) or {}
    if not usage:
        return "정보 없음"

    detail = usage.get("input_token_details") or {}
    read, write = detail.get("cache_read", 0), detail.get("cache_creation", 0)

    parts = [f"입력 {usage.get('input_tokens', 0):,}", f"출력 {usage.get('output_tokens', 0):,}"]
    if write:
        parts.append(f"캐시기록 {write:,}")
    parts.append(f"캐시적중 {read:,}" if read else "캐시적중 없음")
    return " · ".join(parts)


def prune_tool_traffic(state: SingleAgentState) -> dict:
    """
    턴이 끝나면 도구 호출과 그 결과를 대화 기록에서 걷어낸다.

    왜 필요한가:
        LLM API 는 무상태라 매 요청에 대화 기록 전체를 다시 싣는다. 그런데
        retriever_vectordb 의 결과는 하루치가 1만 토큰을 넘기고, 일지를 쓰고
        나면 다시 쓸 일이 없는데도 기록에 남아 이후 모든 호출에 따라다녔다.

        실측(일지 5건, 같은 thread_id): 275,265 토큰 중 81% 가 재전송이었고,
        5번째 요청 하나가 첫 요청의 7.7배였다.

    무엇을 남기는가:
        사람의 말과 에이전트의 최종 답변은 그대로 둔다. 버리는 것은 도구를
        부른 기록과 도구가 돌려준 원문뿐이다. 답변에 이미 요약돼 있으므로
        "그중 두 번째 거 지워줘" 같은 후속 대화는 계속 통한다.

    왜 짝으로 지우는가:
        tool_use 블록만 남고 tool_result 가 사라지면 (혹은 그 반대) Anthropic
        API 가 400 으로 거절한다. 반드시 양쪽을 함께 걷어내야 한다.
    """
    doomed = [
        message.id
        for message in state["messages"]
        if message.id and (
            isinstance(message, ToolMessage)
            or (isinstance(message, AIMessage) and message.tool_calls)
        )
    ]

    if doomed:
        print(f"[UNIFIED AGENT] 도구 기록 {len(doomed)}건을 대화에서 제외했습니다.")

    return {"messages": [RemoveMessage(id=message_id) for message_id in doomed]}


def _build_graph(user_id: str):
    """단일 통합 Agent를 위한 LangGraph 구성"""
    builder = StateGraph(SingleAgentState)

    # Agent 및 도구 노드 생성
    unified_agent_node = create_unified_agent(user_id)
    tool_node = ToolNode(tools=unified_tools)

    # 노드 추가
    builder.add_node("agent", unified_agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("prune", prune_tool_traffic)

    # 엣지 추가.
    # 도구를 더 부르지 않으면 곧바로 끝내지 않고 prune 을 거친다 —
    # 이번 턴에 쌓인 도구 호출·결과를 저장 전에 걷어내기 위해서다.
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "prune",
        },
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("prune", END)

    # Checkpointer와 함께 컴파일
    return builder.compile(checkpointer=checkpointer)


def unified_agent(user_id: str, message: str) -> str:
    """
    통합 소스 관리 Agent 진입점.

    대화 기록을 유지하면서 모든 소스 및 임베딩 작업을 처리합니다.
    Git URL의 경우 add_source_to_db → embed_source를 자동으로 연쇄 호출합니다.

    Args:
        user_id: 사용자 ID (대화 지속성을 위한 thread_id로 사용됨)
        message: 사용자 메시지

    Returns:
        Agent 응답 문자열
    """
    # 사용자별 그래프 구성
    graph = _build_graph(user_id)

    # 대화 기록 유지를 위한 thread_id 설정
    config = {"configurable": {"thread_id": user_id}}

    # 입력 준비
    input_dict = {
        "messages": [HumanMessage(content=message)]
    }

    # 그래프 실행
    result = graph.invoke(input_dict, config=config)

    # 마지막 메시지 내용 반환
    return result["messages"][-1].content if result.get("messages") else ""
