"""
Unified Source Management Agent (Router Approach)

This module provides a router-based multi-agent system with separate
source management and embedding execution sub-agents. The router analyzes
user requests and delegates to the appropriate specialized agent.

Public API:
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


# Checkpointer for conversation history
checkpointer = InMemorySaver()


# Extended state with routing information
class UnifiedState(TypedDict):
    """State for router agent with routing destination field"""
    messages: Annotated[list, add_messages]
    route_destination: str


# Pydantic model for router decision
class RouteDecision(BaseModel):
    """Router agent decision output"""
    destination: Literal["source_management", "embedding_execution"] = Field(
        description="'source_management' for CRUD operations or 'embedding_execution' for embedding tasks"
    )
    reasoning: str = Field(
        description="Explanation for this routing choice"
    )


# Task 9: Source management tools for source_agent
source_management_tools = [
    source_tools.add_source_and_embed,
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
]


def create_router_agent(user_id: str):
    """Create router agent that analyzes requests and routes to sub-agents"""

    # Use Gemini Flash with structured output for routing
    router_llm = llm_router.google_llm.with_structured_output(RouteDecision)

    def router_node(state: UnifiedState) -> dict:
        """
        Analyze user request and route to appropriate agent.

        Returns:
            Dictionary with route_destination field
        """
        # Get user's message
        user_message = state["messages"][-1].content

        # Router system message
        router_system = SystemMessage(content=f"""당신은 사용자 요청을 분석하여 적절한 Agent로 라우팅하는 Router입니다.

**현재 사용자 ID: {user_id}**

다음 두 가지 destination 중 하나를 선택하세요:

1. **source_management** (소스 관리)
   - 학습 소스 추가/등록 (Git 저장소, 로컬 디렉토리 등)
   - 소스 목록 조회
   - 소스 삭제
   - 소스 타입 확인 요청
   - 예: "Git 저장소 추가해줘", "내 소스 목록 보여줘", "1번 소스 삭제"

2. **embedding_execution** (임베딩 실행/조회)
   - 임베딩 실행 (수동 시작/재시작)
   - 임베딩 상태 조회
   - 예: "1번 소스 임베딩 다시 시작", "임베딩 상태 확인"

**중요**:
- Git URL 추가 요청은 source_management로 라우팅 (자동으로 임베딩까지 처리됨)
- 단순 임베딩 상태 확인이나 재시작은 embedding_execution으로 라우팅
""")

        # Invoke LLM for routing decision
        decision = router_llm.invoke([router_system, HumanMessage(content=user_message)])

        print(f"[ROUTER] User request: {user_message[:50]}...")
        print(f"[ROUTER] Decision: {decision.destination}")
        print(f"[ROUTER] Reasoning: {decision.reasoning}")

        # Update state with routing decision
        return {"route_destination": decision.destination}

    return router_node


def create_source_agent(user_id: str):
    """
    Task 9: Create source management agent using Gemini Flash.

    Handles CRUD operations on sources:
    - add_source_and_embed: Add source and start embedding
    - add_source_to_db: Add source only
    - get_user_sources: List all sources
    - delete_source_from_db: Delete a source

    Args:
        user_id: User ID for context and authorization

    Returns:
        Agent function that processes source management requests
    """
    # Bind tools to Gemini Flash
    source_agent_llm = llm_router.google_llm.bind_tools(source_management_tools)

    def source_agent_node(state: UnifiedState) -> dict:
        """
        Process source management requests.

        Returns:
            Dictionary with messages field containing agent response
        """
        # Get user's message
        user_message = state["messages"][-1].content

        # Source management system message (Korean)
        source_system = SystemMessage(content=f"""당신은 소스 관리 전문 에이전트입니다 (user_id: {user_id}).

**주요 책임:**
소스 생명주기 관리 (CRUD):
1. add_source_and_embed - Git 저장소 추가 후 즉시 임베딩 시작
2. add_source_to_db - 소스만 등록 (임베딩 미포함)
3. get_user_sources - 등록된 모든 소스 목록 조회
4. delete_source_from_db - 소스 및 관련 임베딩 삭제

**사용 규칙:**
- 사용자가 Git URL을 추가하고 "임베딩도 해줘"라고 하면: add_source_and_embed 사용
- Git URL을 추가하되 수동으로 임베딩하고 싶다면: add_source_to_db만 사용
- 소스 목록을 보고 싶다면: get_user_sources 사용
- 소스를 제거하려면: delete_source_from_db 사용

**항상 사용자가 제공한 정보를 먼저 요청하세요:**
- 소스 이름, 타입, 위치 등이 부족하면 물어봐주세요.
""")

        messages = [source_system] + state["messages"]

        # Invoke LLM with tools
        result = source_agent_llm.invoke(messages)

        # Debug logging
        print(f"[SOURCE AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return source_agent_node
