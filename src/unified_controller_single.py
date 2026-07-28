"""
통합 소스 관리 Agent (단일 Agent 방식)

이 모듈은 모든 소스, 임베딩, 일지 관리 작업을 처리하는 단일 LangGraph Agent를 제공합니다.
Agent는 작업을 자동으로 연쇄 호출하고 (예: add_source_to_db → embed_source),
InMemorySaver checkpointer를 통해 사용자별 대화 기록을 유지합니다.

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
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
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
    """user_id 컨텍스트가 포함된 시스템 메시지 생성"""
    return SystemMessage(content=f"""당신은 소스 관리 및 일지 작성 어시스턴트입니다 (user_id: {user_id}).

주요 기능:
1. Source 관리
   - Git 저장소 추가 (add_source_to_db)
   - 소스 목록 조회 (get_user_sources)
   - 소스 삭제 (delete_source_from_db)
   - 소스 타입 확인 요청 (request_source_type_clarification)

2. Embedding 관리
   - 임베딩 실행 (embed_source)
   - 임베딩 상태 조회 (get_embedding_status)

3. 일지 관리
   - 날짜 기반 데이터 검색 (retriever_vectordb)
   - 일지 파일 저장 (maker_logfile)

워크플로우:
- Git URL 추가 시: add_source_to_db를 먼저 호출하여 source_id를 얻은 후, 즉시 embed_source를 호출하여 자동으로 임베딩을 시작하세요.
- 소스 조회/삭제: 해당 도구만 호출
- 임베딩 상태 확인/재시작: 해당 도구만 호출
- 일지 작성 요청 시: retriever_vectordb로 날짜 데이터를 검색한 후, maker_logfile로 저장하세요.

중요: Git URL이 포함된 추가 요청은 반드시 add_source_to_db → embed_source 순서로 연쇄 호출하세요.
""")


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

        return {"messages": [result]}

    return unified_agent_node


def _build_graph(user_id: str):
    """단일 통합 Agent를 위한 LangGraph 구성"""
    builder = StateGraph(SingleAgentState)

    # Agent 및 도구 노드 생성
    unified_agent_node = create_unified_agent(user_id)
    tool_node = ToolNode(tools=unified_tools)

    # 노드 추가
    builder.add_node("agent", unified_agent_node)
    builder.add_node("tools", tool_node)

    # 엣지 추가 
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
