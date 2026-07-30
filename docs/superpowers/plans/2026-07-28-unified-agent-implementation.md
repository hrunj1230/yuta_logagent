# Unified Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two source management agent approaches - single unified agent and router-based multi-agent system

**Architecture:** Phase 1 creates a single agent handling all 6 source/embedding tools with automatic chaining (add → embed). Phase 2 creates a router system with separate source and embedding sub-agents, plus an integrated add_source_and_embed tool.

**Tech Stack:** LangGraph, Gemini Flash, Claude Sonnet, InMemorySaver, Pydantic

---

## File Structure

### Phase 1 (Single Agent):
- **Create:** `src/unified_controller_single.py` - Single agent with 6 tools, checkpointer, unified_agent() function

### Phase 2 (Router):
- **Modify:** `src/tools/source.py` - Add add_source_and_embed integrated tool
- **Create:** `src/unified_controller_router.py` - Router agent, source/embedding sub-agents, RouteDecision model

---

## Task 1: Single Agent - Setup and Imports

**Files:**
- Create: `src/unified_controller_single.py`

- [ ] **Step 1: Create file with imports**

```python
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
```

- [ ] **Step 2: Verify imports**

Run: `python -c "import src.unified_controller_single"`
Expected: No import errors

- [ ] **Step 3: Commit**

```bash
git add src/unified_controller_single.py
git commit -m "feat: add unified controller single agent scaffolding

- Import LangGraph components and tools
- Set up InMemorySaver checkpointer"
```

---

## Task 2: Single Agent - Tool Configuration

**Files:**
- Modify: `src/unified_controller_single.py`

- [ ] **Step 1: Define tool list**

```python
# All 6 source management tools
unified_tools = [
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    source_tools.request_source_type_clarification,
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status
]
```

- [ ] **Step 2: Bind tools to LLM**

```python
# Gemini Flash for single agent (fast, supports tool calling)
llm_with_tools = llm_router.google_llm.bind_tools(unified_tools)
```

- [ ] **Step 3: Verify tool binding**

Run: `python -c "from src.unified_controller_single import llm_with_tools; print(len(llm_with_tools.bound_tools))"`
Expected: Output "6"

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_single.py
git commit -m "feat: configure 6 tools for single agent

- Add all source and embedding tools to list
- Bind tools to Gemini Flash LLM"
```

---

## Task 3: Single Agent - System Message and Agent Function

**Files:**
- Modify: `src/unified_controller_single.py`

- [ ] **Step 1: Create system message generator**

```python
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
```

- [ ] **Step 2: Create agent function**

```python
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
```

- [ ] **Step 3: Verify function creation**

Run: `python -c "from src.unified_controller_single import create_unified_agent; agent = create_unified_agent('test_user'); print(agent)"`
Expected: Function object printed

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_single.py
git commit -m "feat: add system message and agent function

- Create dynamic system message with user_id
- Implement unified agent node with tool invocation
- Add debug logging for tool calls"
```

---

## Task 4: Single Agent - Graph Construction

**Files:**
- Modify: `src/unified_controller_single.py`

- [ ] **Step 1: Create graph builder function**

```python
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
```

- [ ] **Step 2: Verify graph compilation**

Run: `python -c "from src.unified_controller_single import _build_graph; graph = _build_graph('test'); print(graph)"`
Expected: CompiledGraph object

- [ ] **Step 3: Commit**

```bash
git add src/unified_controller_single.py
git commit -m "feat: implement graph builder for single agent

- Create graph with agent and tool nodes
- Configure conditional edges for tool routing
- Compile with InMemorySaver checkpointer"
```

---

## Task 5: Single Agent - Public API Function

**Files:**
- Modify: `src/unified_controller_single.py`

- [ ] **Step 1: Implement unified_agent function**

```python
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
```

- [ ] **Step 2: Test function signature**

Run: `python -c "from src.unified_controller_single import unified_agent; import inspect; print(inspect.signature(unified_agent))"`
Expected: `(user_id: str, message: str) -> str`

- [ ] **Step 3: Add module docstring**

```python
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
```

Add this at the top of the file after imports.

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_single.py
git commit -m "feat: implement unified_agent public API

- Add unified_agent(user_id, message) entry point
- Configure thread_id for conversation persistence
- Add module docstring with API documentation"
```

---

## Task 6: Router - Integrated Tool (add_source_and_embed)

**Files:**
- Modify: `src/tools/source.py`

- [ ] **Step 1: Import embed_source internally**

Add to imports section of `src/tools/source.py`:

```python
# Import at module level (after existing imports)
from .embedding import embed_source as _embed_source_tool
```

- [ ] **Step 2: Implement add_source_and_embed tool**

Add at end of `src/tools/source.py`:

```python
@tool
def add_source_and_embed(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    소스를 추가하고 즉시 임베딩을 시작합니다 (통합 도구).

    이 도구는 add_source_to_db와 embed_source를 연쇄적으로 호출하여
    한 번의 요청으로 소스 등록과 임베딩 시작을 모두 처리합니다.

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: 소스 타입 (git, git_log, local, agent_chatlog, memsearch)
        location: 소스 위치 (Git URL, 로컬 경로 등)

    Returns:
        통합 작업 결과 메시지
    """
    # Step 1: Add source to database
    add_result = add_source_to_db.invoke({
        "user_id": user_id,
        "name": name,
        "source_type": source_type,
        "location": location
    })

    # Check if source addition failed
    if add_result.startswith("❌"):
        return add_result

    # Extract source_id from success message
    # Format: "...ID: {source.id}..."
    import re
    match = re.search(r'ID: (\d+)', add_result)
    if not match:
        return f"❌ 오류: 소스는 추가되었으나 ID를 찾을 수 없습니다.\n{add_result}"

    source_id = int(match.group(1))

    # Step 2: Start embedding immediately
    embed_result = _embed_source_tool.invoke({
        "user_id": user_id,
        "source_id": source_id
    })

    # Return combined result
    return f"""{add_result}

🚀 임베딩 자동 시작:
{embed_result}"""
```

- [ ] **Step 3: Verify tool creation**

Run: `python -c "from src.tools.source import add_source_and_embed; print(add_source_and_embed.name)"`
Expected: `add_source_and_embed`

- [ ] **Step 4: Commit**

```bash
git add src/tools/source.py
git commit -m "feat: add add_source_and_embed integrated tool

- Combine add_source_to_db + embed_source in single tool
- Extract source_id from add result and auto-start embedding
- Return combined success message"
```

---

## Task 7: Router - Setup and Models

**Files:**
- Create: `src/unified_controller_router.py`

- [ ] **Step 1: Create file with imports and checkpointer**

```python
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
```

- [ ] **Step 2: Define state and decision models**

```python
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
```

- [ ] **Step 3: Verify imports and models**

Run: `python -c "from src.unified_controller_router import UnifiedState, RouteDecision; print(RouteDecision.model_fields.keys())"`
Expected: `dict_keys(['destination', 'reasoning'])`

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: add router controller scaffolding

- Import LangGraph and tool modules
- Define UnifiedState with route_destination
- Define RouteDecision Pydantic model"
```

---

## Task 8: Router - Router Agent Implementation

**Files:**
- Modify: `src/unified_controller_router.py`

- [ ] **Step 1: Implement router agent creator**

```python
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
```

- [ ] **Step 2: Test router agent creation**

Run: `python -c "from src.unified_controller_router import create_router_agent; router = create_router_agent('test'); print(router)"`
Expected: Function object printed

- [ ] **Step 3: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: implement router agent

- Create router_node with Gemini Flash + structured output
- Define routing criteria for source_management vs embedding_execution
- Add debug logging for routing decisions"
```

---

## Task 9: Router - Source Agent Implementation

**Files:**
- Modify: `src/unified_controller_router.py`

- [ ] **Step 1: Define source management tools**

```python
# Source management tools (includes integrated add_source_and_embed)
source_management_tools = [
    source_tools.add_source_and_embed,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    source_tools.request_source_type_clarification
]
```

- [ ] **Step 2: Implement source agent creator**

```python
def create_source_agent(user_id: str):
    """Create source management agent with CRUD tools"""

    # Gemini Flash for source management
    llm_source = llm_router.google_llm.bind_tools(source_management_tools)

    def source_agent_node(state: UnifiedState) -> dict:
        """Handle source CRUD operations"""
        system_message = SystemMessage(content=f"""당신은 소스 관리 전문 Agent입니다 (user_id: {user_id}).

담당 작업:
1. Git 저장소 추가 (add_source_and_embed) - 자동으로 임베딩까지 시작됨
2. 소스 목록 조회 (get_user_sources)
3. 소스 삭제 (delete_source_from_db)
4. 소스 타입 확인 요청 (request_source_type_clarification)

중요:
- Git URL 추가 시 add_source_and_embed를 사용하세요 (소스 추가 + 임베딩 자동 시작)
- 사용자 ID는 반드시 {user_id}를 사용하세요
""")

        messages = [system_message] + state["messages"]
        result = llm_source.invoke(messages)

        print(f"[SOURCE AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return source_agent_node
```

- [ ] **Step 3: Test source agent creation**

Run: `python -c "from src.unified_controller_router import create_source_agent; agent = create_source_agent('test'); print(agent)"`
Expected: Function object printed

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: implement source agent

- Define source_management_tools with integrated tool
- Create source_agent_node with Gemini Flash
- Add system message for CRUD operations"
```

---

## Task 10: Router - Embedding Agent Implementation

**Files:**
- Modify: `src/unified_controller_router.py`

- [ ] **Step 1: Define embedding tools**

```python
# Embedding management tools
embedding_management_tools = [
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status
]
```

- [ ] **Step 2: Implement embedding agent creator**

```python
def create_embedding_agent(user_id: str):
    """Create embedding management agent with execution/status tools"""

    # Anthropic Sonnet for embedding (more capable for longer-running tasks)
    llm_embedding = llm_router.anthropic_llm.bind_tools(embedding_management_tools)

    def embedding_agent_node(state: UnifiedState) -> dict:
        """Handle embedding execution and status queries"""
        system_message = SystemMessage(content=f"""당신은 임베딩 관리 전문 Agent입니다 (user_id: {user_id}).

담당 작업:
1. 임베딩 실행 (embed_source) - 수동 시작 또는 재시작
2. 임베딩 상태 조회 (get_embedding_status)

중요:
- 사용자 ID는 반드시 {user_id}를 사용하세요
- 임베딩 실행 시 source_id가 필요합니다
""")

        messages = [system_message] + state["messages"]
        result = llm_embedding.invoke(messages)

        print(f"[EMBEDDING AGENT] Response:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {result.tool_calls if hasattr(result, 'tool_calls') else 'None'}")

        return {"messages": [result]}

    return embedding_agent_node
```

- [ ] **Step 3: Test embedding agent creation**

Run: `python -c "from src.unified_controller_router import create_embedding_agent; agent = create_embedding_agent('test'); print(agent)"`
Expected: Function object printed

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: implement embedding agent

- Define embedding_management_tools
- Create embedding_agent_node with Anthropic Sonnet
- Add system message for embedding operations"
```

---

## Task 11: Router - Routing Logic and Graph Construction

**Files:**
- Modify: `src/unified_controller_router.py`

- [ ] **Step 1: Implement routing conditional edge**

```python
def route_to_agent(state: UnifiedState) -> str:
    """
    Determine which agent to route to based on router decision.

    Returns:
        "source_agent" or "embedding_agent"
    """
    destination = state.get("route_destination", "source_management")

    print(f"[ROUTE] State keys: {list(state.keys())}")
    print(f"[ROUTE] Destination: {destination}")

    if destination == "source_management":
        print(f"[ROUTE] → Routing to source_agent")
        return "source_agent"
    else:
        print(f"[ROUTE] → Routing to embedding_agent")
        return "embedding_agent"
```

- [ ] **Step 2: Implement graph builder**

```python
def _build_graph(user_id: str):
    """Build LangGraph for router-based multi-agent system"""
    builder = StateGraph(UnifiedState)

    # Create agent nodes
    router_node = create_router_agent(user_id)
    source_agent_node = create_source_agent(user_id)
    embedding_agent_node = create_embedding_agent(user_id)

    # Create tool nodes
    source_tool_node = ToolNode(tools=source_management_tools)
    embedding_tool_node = ToolNode(tools=embedding_management_tools)

    # Add nodes
    builder.add_node("router", router_node)
    builder.add_node("source_agent", source_agent_node)
    builder.add_node("embedding_agent", embedding_agent_node)
    builder.add_node("source_tools", source_tool_node)
    builder.add_node("embedding_tools", embedding_tool_node)

    # START → Router
    builder.add_edge(START, "router")

    # Router → Conditional routing to agents
    builder.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "source_agent": "source_agent",
            "embedding_agent": "embedding_agent",
        }
    )

    # Source agent flow: source_agent ↔ source_tools → END
    builder.add_conditional_edges(
        "source_agent",
        tools_condition,
        {
            "tools": "source_tools",
            "__end__": END,
        }
    )
    builder.add_edge("source_tools", "source_agent")

    # Embedding agent flow: embedding_agent ↔ embedding_tools → END
    builder.add_conditional_edges(
        "embedding_agent",
        tools_condition,
        {
            "tools": "embedding_tools",
            "__end__": END,
        }
    )
    builder.add_edge("embedding_tools", "embedding_agent")

    # Compile with checkpointer
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 3: Verify graph compilation**

Run: `python -c "from src.unified_controller_router import _build_graph; graph = _build_graph('test'); print(graph)"`
Expected: CompiledGraph object

- [ ] **Step 4: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: implement routing logic and graph

- Add route_to_agent conditional edge function
- Build complete graph with router and sub-agents
- Configure tool nodes and conditional edges
- Compile with InMemorySaver checkpointer"
```

---

## Task 12: Router - Public API Function

**Files:**
- Modify: `src/unified_controller_router.py`

- [ ] **Step 1: Implement unified_agent function**

```python
def unified_agent(user_id: str, message: str) -> str:
    """
    Router-based unified source management agent entry point.

    Routes user requests to specialized sub-agents:
    - source_management: CRUD operations (uses add_source_and_embed for Git URLs)
    - embedding_execution: Embedding status and manual execution

    Maintains conversation history per user via InMemorySaver checkpointer.

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
```

- [ ] **Step 2: Verify function signature**

Run: `python -c "from src.unified_controller_router import unified_agent; import inspect; print(inspect.signature(unified_agent))"`
Expected: `(user_id: str, message: str) -> str`

- [ ] **Step 3: Commit**

```bash
git add src/unified_controller_router.py
git commit -m "feat: implement router unified_agent public API

- Add unified_agent(user_id, message) entry point
- Configure thread_id for conversation persistence
- Complete router-based implementation"
```

---

## Self-Review Checklist

**Spec Coverage:**
- [x] Single agent with 6 tools - Task 1-5
- [x] Single agent checkpointer and conversation history - Task 1, 4
- [x] Single agent automatic chaining (add → embed) - Task 3
- [x] Integrated add_source_and_embed tool - Task 6
- [x] Router agent with structured output - Task 7-8
- [x] Source agent with 4 tools - Task 9
- [x] Embedding agent with 2 tools - Task 10
- [x] Router graph with conditional routing - Task 11
- [x] Router checkpointer and conversation history - Task 7, 11
- [x] Public API functions for both approaches - Task 5, 12

**Placeholder Scan:**
- No TBD, TODO, or incomplete sections
- All code blocks contain complete implementations
- All system messages fully specified
- All tool lists explicitly defined

**Type Consistency:**
- `unified_agent(user_id: str, message: str) -> str` - consistent across both files
- `UnifiedState` fields match usage in router implementation
- `RouteDecision.destination` Literal values match routing logic
- Tool function names match imports from tools modules

**File Paths:**
- All paths use exact locations: `src/unified_controller_single.py`, `src/unified_controller_router.py`, `src/tools/source.py`
- Imports use relative imports (`.` for same package)
- Test commands include full module paths

---

## Execution Summary

Plan complete and saved to `docs/superpowers/plans/2026-07-28-unified-agent-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
