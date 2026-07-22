import os
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from typing import Literal, TypedDict, Annotated
from pydantic import BaseModel, Field
import src.llm_router as llm
from langgraph.graph import MessagesState, StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
import src.tools as tool
from storage.auth import login_or_register, get_user_by_id

# 커스텀 State: route_destination 필드 추가
class UnifiedState(TypedDict):
    """Router Agent를 위한 확장 State"""
    messages: Annotated[list, add_messages]
    route_destination: str

tools = [ tool.retriever_vectordb , tool.embedding_file, tool.maker_logfile]

# Claude Sonnet 4.5 사용 - 최고 성능 + 안정적인 tool calling
llm_with_tools = llm.anthropic_llm.bind_tools(tools)
# llm_with_tools = llm.google_llm.bind_tools(tools)  # Gemini 쿼터 초과
# llm_with_tools = llm.codex_llm.bind_tools(tools)  # Codex는 tool calling 문제 있음

SYSTEM_MESSAGE = SystemMessage(content=
"""당신은 개발자 일지 자동 생성 어시스턴트입니다.

작업 순서 (반드시 따르세요):

1️⃣ 데이터 검색
- 사용자가 날짜를 언급하면 retriever_vectordb 도구를 즉시 호출
- date: 날짜 문자열 (예: "2026-07-09")
- reference_len: "5"

2️⃣ 일지 작성
- 검색 결과의 실제 내용을 바탕으로 상세한 일지 작성
- 검색 결과가 비어있으면 "해당 날짜 기록 없음" 명시
- 반드시 검색된 구체적인 내용 포함 (커밋 메시지, 대화 내용, TIL 항목 등)

형식:
# YYYY.MM.DD 일지

## 주요 활동
- [검색 결과에서 추출한 구체적인 작업 내용]

## 학습 내용
- [검색 결과에서 추출한 학습 개념]

## 성과 및 회고
- [검색 결과 기반 회고]

3️⃣ 파일 저장
- 작성한 일지 전체를 maker_logfile 도구로 저장
- date: 날짜 (YYYY-MM-DD)
- content: 위에서 작성한 전체 마크다운

중요: 플레이스홀더 금지! 검색 결과의 실제 내용을 사용하세요.
"""
)

def agent(state: MessagesState) ->dict:
    messages = [SYSTEM_MESSAGE] + state["messages"]

    # invoke 사용 (tool_calls 자동 보존, 모든 LLM 호환)
    result = llm_with_tools.invoke(messages)

    # 디버깅 로그
    print(f"[DEBUG] Agent 응답:")
    print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
    print(f"  - Has tool_calls: {hasattr(result, 'tool_calls') and bool(result.tool_calls)}")
    if hasattr(result, 'tool_calls') and result.tool_calls:
        print(f"  - Tool calls: {result.tool_calls}")

    return {"messages": [result]}
# graph
def _graph_builder():
    builder = StateGraph(MessagesState)
    tool_node = ToolNode(tools=tools)

    builder.add_node("agent",agent)
    builder.add_node("tools",tool_node)
    
    builder.add_edge(START,"agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools":"tools",
            "__end__":END,
        },
    )
    builder.add_edge("tools","agent")

    return builder.compile()
#graph선언
graph = _graph_builder()

def handle_login(db: Session, user_id: str):
    """로그인/회원가입 처리"""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="id를 입력해주세요")

    user = login_or_register(db, user_id.strip())
    return {
        "user_id": user.user_id,
        "message": f"{user.user_id}님, 환영합니다!"
    }

def get_user_info(db: Session, user_id: str = None):
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

def main(req):
    # QueryReq 객체를 MessagesState 형식으로 변환
    input_dict = {
        "messages": [HumanMessage(content=req.req)]
    }
    res = graph.invoke(input_dict)
    # 마지막 메시지의 content 반환
    return res["messages"][-1].content if res.get("messages") else ""


## ========== 소스 관리 Agent ==========

# 소스 관리 도구
source_tools = [
    tool.add_source_to_db,
    tool.get_user_sources,
    tool.delete_source_from_db
    # embedding_file_for_user는 add_source_to_db 내부에서 사용하는 헬퍼 함수
]

# 소스 관리 전용 LLM (간단한 CRUD → Gemini Flash, tool calling 지원)
llm_source_manager = llm.google_llm.bind_tools(source_tools)

def create_source_system_message(user_id: str) -> SystemMessage:
    """사용자 ID를 포함한 SYSTEM_MESSAGE 생성"""
    return SystemMessage(content=f"""You are a source management assistant for user_id: {user_id}

🚨 ABSOLUTE RULES - NO EXCEPTIONS:

1. **Git URL Detection (MANDATORY TOOL CALL)**
   When user message contains ANY of these patterns:
   - github.com, gitlab.com, bitbucket.org
   - ends with .git
   - contains http(s):// with git-like structure

   👉 YOU MUST IMMEDIATELY call add_source_to_db tool:
   - user_id: "{user_id}" (EXACT VALUE, DO NOT MODIFY)
   - name: Extract from URL path (e.g., "Yuta_TIL" from "/user/Yuta_TIL.git")
   - source_type: "git" (EXACT VALUE)
   - location: The EXACT URL user provided (DO NOT MODIFY)

2. **Source List Request**
   Keywords: "목록", "리스트", "소스", "등록", "list", "sources"
   👉 Call get_user_sources(user_id="{user_id}")

3. **Delete Request**
   Keywords: "삭제", "제거", "delete", "remove" + source ID/name
   👉 Call delete_source_from_db(source_id=<id>, user_id="{user_id}")

⚠️ CRITICAL BEHAVIORS:
- NEVER explain what you will do - JUST CALL THE TOOL
- NEVER ask for confirmation - JUST CALL THE TOOL
- NEVER say "I will clone..." - JUST CALL THE TOOL
- The tool handles EVERYTHING (clone, embedding, database)

✅ CORRECT Example:
User: "https://github.com/hrunj1230/Yuta_TIL.git"
You: [Immediately call add_source_to_db with extracted parameters]

❌ WRONG Example:
User: "https://github.com/hrunj1230/Yuta_TIL.git"
You: "I will clone this repository..." (NEVER DO THIS!)

Current user_id: {user_id} (USE THIS EXACT VALUE IN ALL TOOL CALLS)
""")

def create_source_agent(user_id: str):
    """사용자 ID를 포함한 Agent 생성"""
    import re
    from langchain_core.messages import HumanMessage, ToolMessage

    def source_agent(state: MessagesState) -> dict:
        """소스 관리 Agent (Git URL 강제 도구 호출)"""
        system_message = create_source_system_message(user_id)
        messages = [system_message] + state["messages"]

        # 마지막 메시지 확인
        last_message = state["messages"][-1] if state["messages"] else None

        # ⚠️ 중요: 도구 실행 결과(ToolMessage) 이후에는 Git URL 감지 안 함!
        is_after_tool_execution = isinstance(last_message, ToolMessage)

        # 사용자 메시지(HumanMessage)에서만 Git URL 패턴 감지
        has_git_url = False
        if isinstance(last_message, HumanMessage):
            user_message = last_message.content
            git_url_pattern = r'(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+(?:\.git)?|.*\.git)'
            has_git_url = re.search(git_url_pattern, user_message, re.IGNORECASE)

        if has_git_url and not is_after_tool_execution:
            # Git URL 감지 시 add_source_to_db 도구 강제 호출
            print(f"[SOURCE AGENT] 🔍 Git URL 감지! 도구 강제 호출 모드")

            # tool_choice로 add_source_to_db 강제 (Gemini Flash - tool calling 지원)
            llm_forced = llm.google_llm.bind_tools(
                source_tools,
                tool_choice="add_source_to_db"  # 이 도구를 반드시 호출
            )
            result = llm_forced.invoke(messages)
        else:
            # 일반 모드 (도구 선택은 LLM이 결정)
            if is_after_tool_execution:
                print(f"[SOURCE AGENT] ✅ 도구 실행 완료, 최종 응답 생성")
            result = llm_source_manager.invoke(messages)

        print(f"[SOURCE AGENT] 응답:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return source_agent

def _source_graph_builder(user_id: str):
    """소스 관리 Graph"""
    builder = StateGraph(MessagesState)
    tool_node = ToolNode(tools=source_tools)

    # 사용자 ID를 포함한 Agent 생성
    source_agent = create_source_agent(user_id)

    builder.add_node("source_agent", source_agent)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "source_agent")
    builder.add_conditional_edges(
        "source_agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    builder.add_edge("tools", "source_agent")

    return builder.compile()

def source_manager(user_id: str, message: str):
    """
    소스 관리 대화형 함수

    Args:
        user_id: 사용자 ID (URL에서 가져옴)
        message: 사용자 메시지

    Returns:
        Agent 응답
    """
    # 사용자별 Graph 생성 (user_id가 SYSTEM_MESSAGE에 포함됨)
    source_graph = _source_graph_builder(user_id)

    input_dict = {
        "messages": [HumanMessage(content=message)]
    }
    res = source_graph.invoke(input_dict)
    return res["messages"][-1].content if res.get("messages") else ""


## ========== Router Agent System (LangGraph 기반) ==========

# Step 1: Pydantic 모델로 Router 결과 정의
class RouteDecision(BaseModel):
    """Router Agent의 판단 결과"""
    destination: Literal["source_management", "log_making"] = Field(
        description="'source_management' (소스 관리) 또는 'log_making' (일지 작성/조회)"
    )
    reasoning: str = Field(
        description="이 destination을 선택한 이유"
    )

# Step 2: Router Agent - 요청을 분석하여 어느 Agent로 갈지 결정
def create_router_agent(user_id: str):
    """사용자 ID를 포함한 Router Agent 생성"""

    # Structured Output을 사용하여 명확한 라우팅 결과 얻기
    # 단순 분류 작업 → Gemini Flash (structured output + tool calling 지원)
    router_llm = llm.google_llm.with_structured_output(RouteDecision)

    def router_node(state: UnifiedState) -> dict:
        """
        사용자 요청을 분석하여 적절한 Agent 선택

        Returns:
            state에 "route_destination" 키 추가
        """
        # 사용자의 마지막 메시지 가져오기
        user_message = state["messages"][-1].content

        # Router 시스템 메시지
        router_system = SystemMessage(content=f"""당신은 사용자 요청을 분석하여 적절한 Agent로 라우팅하는 Router입니다.

**현재 사용자 ID: {user_id}**

다음 두 가지 destination 중 하나를 선택하세요:

1. **source_management** (소스 관리)
   - 학습 소스 추가/등록
   - 소스 목록 조회
   - 소스 삭제
   - 예: "Git 저장소 추가해줘", "내 소스 목록 보여줘", "1번 소스 삭제"

2. **log_making** (일지 작성/조회)
   - 특정 날짜의 일지 작성
   - 데이터 검색 및 조회
   - TIL 작성
   - 예: "2026-07-20 일지 작성해줘", "오늘 한 일 정리해줘", "내일 할 일 알려줘"

**중요**: 사용자 요청의 핵심 의도를 파악하여 가장 적합한 destination을 선택하세요.
""")

        # LLM 호출하여 라우팅 결정
        decision = router_llm.invoke([router_system, HumanMessage(content=user_message)])

        print(f"[ROUTER] 사용자 요청: {user_message[:50]}...")
        print(f"[ROUTER] 선택된 destination: {decision.destination}")
        print(f"[ROUTER] 이유: {decision.reasoning}")

        # State에 라우팅 결정 저장
        result = {"route_destination": decision.destination}
        print(f"[ROUTER] 🔄 State 업데이트: {result}")
        return result

    return router_node

# Step 3: Conditional Edge - Router 결과에 따라 분기
def route_to_agent(state: UnifiedState) -> str:
    """
    Router의 결정에 따라 적절한 Agent로 분기

    Returns:
        "source_subgraph" 또는 "log_subgraph"
    """
    destination = state.get("route_destination", "log_making")

    # 디버깅: State 전체 출력
    print(f"[ROUTE_TO_AGENT] State keys: {list(state.keys())}")
    print(f"[ROUTE_TO_AGENT] route_destination value: {destination}")

    if destination == "source_management":
        print(f"[ROUTE_TO_AGENT] 🎯 라우팅: source_agent로 이동")
        return "source_subgraph"
    else:
        print(f"[ROUTE_TO_AGENT] 🎯 라우팅: log_agent로 이동")
        return "log_subgraph"

# Step 4: Unified Graph Builder - Router + Source Agent + Log Agent
def _unified_graph_builder(user_id: str):
    """
    통합 Graph 생성: Router → Conditional Edge → Specialized Agents

    구조:
        START
          ↓
        router_node (요청 분석)
          ↓
        conditional_edges (route_to_agent)
          ├─→ source_subgraph (소스 관리) → END
          └─→ log_subgraph (일지 작성) → END
    """
    builder = StateGraph(UnifiedState)

    # Router Node 추가
    router_node = create_router_agent(user_id)
    builder.add_node("router", router_node)

    # Source Management Subgraph (기존 source_graph를 node로 추가)
    source_agent_func = create_source_agent(user_id)
    source_tool_node = ToolNode(tools=source_tools)

    builder.add_node("source_agent", source_agent_func)
    builder.add_node("source_tools", source_tool_node)

    # Log Making Subgraph (기존 log_graph를 node로 추가)
    log_tool_node = ToolNode(tools=tools)

    builder.add_node("log_agent", agent)
    builder.add_node("log_tools", log_tool_node)

    # START → Router
    builder.add_edge(START, "router")

    # Router → Conditional Edge (요청 분석 결과에 따라 분기)
    builder.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "source_subgraph": "source_agent",
            "log_subgraph": "log_agent",
        }
    )

    # Source Agent 흐름: source_agent ↔ source_tools → END
    builder.add_conditional_edges(
        "source_agent",
        tools_condition,
        {
            "tools": "source_tools",
            "__end__": END,
        }
    )
    builder.add_edge("source_tools", "source_agent")

    # Log Agent 흐름: log_agent ↔ log_tools → END
    builder.add_conditional_edges(
        "log_agent",
        tools_condition,
        {
            "tools": "log_tools",
            "__end__": END,
        }
    )
    builder.add_edge("log_tools", "log_agent")

    return builder.compile()

# Step 5: 통합 함수 - 하나의 엔드포인트로 모든 작업 처리
def unified_agent(user_id: str, message: str):
    """
    Router Agent 기반 통합 처리

    - 사용자 요청을 자동으로 분석
    - 소스 관리 또는 일지 작성 Agent로 라우팅
    - 하나의 채팅창에서 모든 작업 가능

    Args:
        user_id: 사용자 ID
        message: 사용자 메시지

    Returns:
        Agent 응답
    """
    # 사용자별 Unified Graph 생성
    unified_graph = _unified_graph_builder(user_id)

    input_dict = {
        "messages": [HumanMessage(content=message)]
    }

    res = unified_graph.invoke(input_dict)
    return res["messages"][-1].content if res.get("messages") else ""
