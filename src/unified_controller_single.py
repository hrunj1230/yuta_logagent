"""
Unified Source Management Agent (Single Agent Approach)

This module provides a single LangGraph agent that handles all source and
embedding management operations. The agent automatically chains operations
(e.g., add_source_to_db → embed_source) and maintains conversation history
per user via InMemorySaver checkpointer.

Public API:
    unified_agent(user_id: str, message: str) -> str

Tools Used:
    - add_source_to_db
    - get_user_sources
    - delete_source_from_db
    - request_source_type_clarification
    - embed_source
    - get_embedding_status
"""
from typing import Annotated
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from . import llm_router
from .tools import source as source_tools
from .tools import embedding as embedding_tools


# Checkpointer for conversation history
checkpointer = InMemorySaver()

# All 6 source management tools
unified_tools = [
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    source_tools.request_source_type_clarification,
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status
]

# Gemini Flash for single agent (fast, supports tool calling)
llm_with_tools = llm_router.google_llm.bind_tools(unified_tools)


def create_system_message(user_id: str) -> SystemMessage:
    """Generate system message with user_id context"""
    return SystemMessage(content=f"""당신은 소스 관리 어시스턴트입니다 (user_id: {user_id}).

주요 기능:
1. Source 관리
   - Git 저장소 추가 (add_source_to_db)
   - 소스 목록 조회 (get_user_sources)
   - 소스 삭제 (delete_source_from_db)
   - 소스 타입 확인 요청 (request_source_type_clarification)

2. Embedding 관리
   - 임베딩 실행 (embed_source)
   - 임베딩 상태 조회 (get_embedding_status)

워크플로우:
- Git URL 추가 시: add_source_to_db를 먼저 호출하여 source_id를 얻은 후, 즉시 embed_source를 호출하여 자동으로 임베딩을 시작하세요.
- 소스 조회/삭제: 해당 도구만 호출
- 임베딩 상태 확인/재시작: 해당 도구만 호출

중요: Git URL이 포함된 추가 요청은 반드시 add_source_to_db → embed_source 순서로 연쇄 호출하세요.
""")


def create_unified_agent(user_id: str):
    """Create agent function with user_id in system message"""
    def unified_agent_node(state: MessagesState) -> dict:
        """Unified agent that handles all source/embedding operations"""
        system_message = create_system_message(user_id)
        messages = [system_message] + state["messages"]

        # Invoke LLM with tools
        result = llm_with_tools.invoke(messages)

        # Debug logging
        print(f"[UNIFIED AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return unified_agent_node


def _build_graph(user_id: str):
    """Build LangGraph for single unified agent"""
    builder = StateGraph(MessagesState)

    # Create agent and tool nodes
    unified_agent_node = create_unified_agent(user_id)
    tool_node = ToolNode(tools=unified_tools)

    # Add nodes
    builder.add_node("agent", unified_agent_node)
    builder.add_node("tools", tool_node)

    # Add edges
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    builder.add_edge("tools", "agent")

    # Compile with checkpointer
    return builder.compile(checkpointer=checkpointer)


def unified_agent(user_id: str, message: str) -> str:
    """
    Unified source management agent entry point.

    Handles all source and embedding operations with conversation history.
    Automatically chains add_source_to_db → embed_source for Git URLs.

    Args:
        user_id: User ID (used as thread_id for conversation persistence)
        message: User message

    Returns:
        Agent response string
    """
    # Build graph for this user
    graph = _build_graph(user_id)

    # Configure with thread_id for conversation history
    config = {"configurable": {"thread_id": user_id}}

    # Prepare input
    input_dict = {
        "messages": [HumanMessage(content=message)]
    }

    # Invoke graph
    result = graph.invoke(input_dict, config=config)

    # Return last message content
    return result["messages"][-1].content if result.get("messages") else ""
