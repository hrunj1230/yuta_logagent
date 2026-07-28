"""
통합 소스 관리 Agent (Router 방식)

이 모듈은 소스 관리, 로그 관리, 임베딩 실행을 분리한 Router 기반 멀티 Agent 시스템을 제공합니다.
Router가 사용자 요청을 분석하여 적절한 전문 Agent에게 작업을 위임합니다.

공개 API:
    unified_agent(user_id: str, message: str) -> str
"""

from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from . import llm_router
from .tools import source as source_tools
from .tools import embedding as embedding_tools
from .tools import log as log_tools


# 대화 기록 유지를 위한 Checkpointer
checkpointer = InMemorySaver()


# 라우팅 정보가 포함된 확장 State
class UnifiedState(TypedDict):
    """Router용 State (라우팅 목적지 필드 포함)"""
    messages: Annotated[list, add_messages]
    route_destination: str


# Router 결정용 Pydantic 모델
class RouteDecision(BaseModel):
    """Router Agent 결정 결과"""
    destination: Literal["source_management", "embedding_execution"] = Field(
        description="소스 CRUD 및 로그 작업은 'source_management', 임베딩 작업은 'embedding_execution'"
    )
    reasoning: str = Field(
        description="이 라우팅 선택에 대한 설명"
    )


# source_agent용 소스 및 로그 관리 도구 (Task 9)
source_management_tools = [
    source_tools.add_source_and_embed,
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    log_tools.retriever_vectordb,
    log_tools.maker_logfile,
]

# embedding_agent용 임베딩 관리 도구 (Task 10)
embedding_management_tools = [
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status,
]


def create_router_agent(user_id: str):
    """요청을 분석하여 Sub-Agent로 라우팅하는 Router Agent 생성"""

    # 라우팅용 Gemini Flash (구조화된 출력)
    router_llm = llm_router.google_llm.with_structured_output(RouteDecision)

    def router_node(state: UnifiedState) -> dict:
        """
        사용자 요청을 분석하여 적절한 Agent로 라우팅

        Returns:
            route_destination 필드를 포함한 딕셔너리
        """
        # 사용자 메시지 추출
        user_message = state["messages"][-1].content

        # Router 시스템 메시지
        router_system = SystemMessage(content=f"""당신은 사용자 요청을 분석하여 적절한 Agent로 라우팅하는 Router입니다.

**현재 사용자 ID: {user_id}**

다음 두 가지 destination 중 하나를 선택하세요:

1. **source_management** (소스 및 로그 관리)
   - 학습 소스 추가/등록 (Git 저장소, 로컬 디렉토리 등)
   - 소스 목록 조회
   - 소스 삭제
   - 소스 타입 확인 요청
   - 일지 작성 및 저장 (날짜 기반 검색 + 파일 저장)
   - 예: "Git 저장소 추가해줘", "내 소스 목록 보여줘", "1번 소스 삭제", "오늘 일지 작성해줘"

2. **embedding_execution** (임베딩 실행/조회)
   - 임베딩 실행 (수동 시작/재시작)
   - 임베딩 상태 조회
   - 예: "1번 소스 임베딩 다시 시작", "임베딩 상태 확인"

**중요**:
- Git URL 추가 요청은 source_management로 라우팅 (자동으로 임베딩까지 처리됨)
- 일지 작성/저장 요청은 source_management로 라우팅
- 단순 임베딩 상태 확인이나 재시작은 embedding_execution으로 라우팅
""")

        # LLM 호출하여 라우팅 결정
        decision = router_llm.invoke([router_system, HumanMessage(content=user_message)])

        print(f"[ROUTER] User request: {user_message[:50]}...")
        print(f"[ROUTER] Decision: {decision.destination}")
        print(f"[ROUTER] Reasoning: {decision.reasoning}")

        # State에 라우팅 결정 반영
        return {"route_destination": decision.destination}

    return router_node


def create_source_agent(user_id: str):
    """
    Task 9: Gemini Flash를 사용하는 소스 및 로그 관리 Agent 생성

    소스 CRUD 작업 처리:
    - add_source_and_embed: 소스 추가 후 임베딩 시작
    - add_source_to_db: 소스만 추가
    - get_user_sources: 모든 소스 목록 조회
    - delete_source_from_db: 소스 삭제

    로그 관리 작업 처리:
    - retriever_vectordb: 날짜 기반 데이터 검색
    - maker_logfile: 일지 파일 저장

    Args:
        user_id: 컨텍스트 및 권한 부여를 위한 사용자 ID

    Returns:
        소스 및 로그 관리 요청을 처리하는 Agent 함수
    """
    # Gemini Flash에 도구 바인딩
    source_agent_llm = llm_router.google_llm.bind_tools(source_management_tools)

    def source_agent_node(state: UnifiedState) -> dict:
        """
        소스 관리 요청 처리

        Returns:
            Agent 응답을 포함한 messages 필드가 있는 딕셔너리
        """
        # 사용자 메시지 추출
        user_message = state["messages"][-1].content

        # 소스 및 로그 관리 시스템 메시지 (한국어)
        source_system = SystemMessage(content=f"""당신은 소스 및 로그 관리 전문 에이전트입니다 (user_id: {user_id}).

**주요 책임:**
1. 소스 생명주기 관리 (CRUD):
   - add_source_and_embed - Git 저장소 추가 후 즉시 임베딩 시작
   - add_source_to_db - 소스만 등록 (임베딩 미포함)
   - get_user_sources - 등록된 모든 소스 목록 조회
   - delete_source_from_db - 소스 및 관련 임베딩 삭제

2. 일지 관리:
   - retriever_vectordb - 날짜 기반 VectorDB 데이터 검색
   - maker_logfile - 일지 파일 저장

**사용 규칙:**
- 사용자가 Git URL을 추가하고 "임베딩도 해줘"라고 하면: add_source_and_embed 사용
- Git URL을 추가하되 수동으로 임베딩하고 싶다면: add_source_to_db만 사용
- 소스 목록을 보고 싶다면: get_user_sources 사용
- 소스를 제거하려면: delete_source_from_db 사용
- 일지 작성 요청 시: retriever_vectordb로 날짜 데이터 검색 → maker_logfile로 저장

**항상 사용자가 제공한 정보를 먼저 요청하세요:**
- 소스 이름, 타입, 위치 등이 부족하면 물어봐주세요.
""")

        messages = [source_system] + state["messages"]

        # 도구가 바인딩된 LLM 호출
        result = source_agent_llm.invoke(messages)

        # 디버그 로깅
        print(f"[SOURCE AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return source_agent_node


def create_embedding_agent(user_id: str):
    """
    Task 10: Anthropic Sonnet을 사용하는 임베딩 관리 Agent 생성

    임베딩 작업 처리:
    - embed_source: 소스의 임베딩 시작 또는 재시작
    - get_embedding_status: 임베딩 상태 확인

    Args:
        user_id: 컨텍스트 및 권한 부여를 위한 사용자 ID

    Returns:
        임베딩 관리 요청을 처리하는 Agent 함수
    """
    # Anthropic Sonnet에 도구 바인딩
    embedding_agent_llm = llm_router.anthropic_llm.bind_tools(embedding_management_tools)

    def embedding_agent_node(state: UnifiedState) -> dict:
        """
        임베딩 관리 요청 처리

        Returns:
            Agent 응답을 포함한 messages 필드가 있는 딕셔너리
        """
        # 사용자 메시지 추출
        user_message = state["messages"][-1].content

        # 임베딩 관리 시스템 메시지 (한국어)
        embedding_system = SystemMessage(content=f"""당신은 임베딩 실행 전문 에이전트입니다 (user_id: {user_id}).

**주요 책임:**
임베딩 생명주기 관리:
1. embed_source - 소스의 임베딩 시작 또는 재시작
2. get_embedding_status - 임베딩 상태 조회 및 통계 확인

**사용 규칙:**
- 사용자가 "임베딩 시작해줘"라고 하면: embed_source 사용 (source_id 필수)
- 사용자가 "임베딩 상태 확인"이라고 하면: get_embedding_status 사용
- 임베딩 재시작도 embed_source로 처리

**중요:**
- source_id는 필수입니다. 모르면 사용자에게 물어보세요.
- 임베딩은 시간이 걸릴 수 있으니 사용자에게 알려주세요.
- 임베딩 완료 후에는 통계를 사용자에게 제시해주세요.
""")

        messages = [embedding_system] + state["messages"]

        # 도구가 바인딩된 LLM 호출
        result = embedding_agent_llm.invoke(messages)

        # 디버그 로깅
        print(f"[EMBEDDING AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return embedding_agent_node


def route_to_agent(state: UnifiedState) -> Literal["source_agent", "embedding_agent"]:
    """
    Task 11: route_destination을 기반으로 라우팅하는 조건부 엣지 함수

    Router의 결정에 따라 어떤 Agent가 요청을 처리할지 결정합니다.

    Args:
        state: route_destination을 포함한 현재 State

    Returns:
        Agent 이름 ("source_agent" 또는 "embedding_agent")
    """
    destination = state["route_destination"]
    print(f"[ROUTING] Routing to: {destination}")

    if destination == "source_management":
        return "source_agent"
    else:
        return "embedding_agent"


def _build_graph(user_id: str):
    """
    Task 11: Router 아키텍처를 가진 완전한 LangGraph 구성

    다음을 포함한 그래프 생성:
    - router 노드 (요청 분석 및 목적지 결정)
    - source_agent 노드 (소스 관리 처리)
    - embedding_agent 노드 (임베딩 실행 처리)
    - 두 Agent용 도구 노드
    - 라우팅 결정 기반 조건부 엣지
    - Agent 도구 루프용 도구 조건 엣지

    Args:
        user_id: 컨텍스트 및 권한 부여를 위한 사용자 ID

    Returns:
        checkpointer와 함께 컴파일된 LangGraph
    """
    builder = StateGraph(UnifiedState)

    # 모든 Agent 노드 생성
    router_node = create_router_agent(user_id)
    source_agent_node = create_source_agent(user_id)
    embedding_agent_node = create_embedding_agent(user_id)

    # 두 Agent용 도구 노드 생성
    source_tool_node = ToolNode(tools=source_management_tools)
    embedding_tool_node = ToolNode(tools=embedding_management_tools)

    # 그래프에 모든 노드 추가
    builder.add_node("router", router_node)
    builder.add_node("source_agent", source_agent_node)
    builder.add_node("embedding_agent", embedding_agent_node)
    builder.add_node("source_tools", source_tool_node)
    builder.add_node("embedding_tools", embedding_tool_node)

    # 엣지 추가
    # Start → router
    builder.add_edge(START, "router")

    # Router → route_to_agent 함수 기반으로 source_agent 또는 embedding_agent
    builder.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "source_agent": "source_agent",
            "embedding_agent": "embedding_agent",
        },
    )

    # source_agent → tool_condition 기반으로 source_tools 또는 END
    builder.add_conditional_edges(
        "source_agent",
        tools_condition,
        {
            "source_tools": "source_tools",
            "__end__": END,
        },
    )

    # embedding_agent → tool_condition 기반으로 embedding_tools 또는 END
    builder.add_conditional_edges(
        "embedding_agent",
        tools_condition,
        {
            "embedding_tools": "embedding_tools",
            "__end__": END,
        },
    )

    # 도구에서 Agent로 루프백
    builder.add_edge("source_tools", "source_agent")
    builder.add_edge("embedding_tools", "embedding_agent")

    # Checkpointer와 함께 컴파일
    return builder.compile(checkpointer=checkpointer)


def unified_agent(user_id: str, message: str) -> str:
    """
    Task 12: 통합 소스 관리 Agent 진입점

    라우팅을 통해 모든 소스 및 임베딩 작업을 처리하는 공개 API.
    Router를 사용하여 source_agent 또는 embedding_agent 중 어느 것을 사용할지 결정합니다.
    checkpointer를 통해 사용자별 대화 기록을 유지합니다.

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

    # 초기 route_destination 필드를 포함한 입력 준비
    input_dict = {
        "messages": [HumanMessage(content=message)],
        "route_destination": "",
    }

    # 그래프 실행
    result = graph.invoke(input_dict, config=config)

    # 마지막 메시지 내용 반환
    return result["messages"][-1].content if result.get("messages") else ""
