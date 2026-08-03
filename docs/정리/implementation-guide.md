# LangGraph 기반 통합 Agent 구현 가이드

**작성일**: 2026-07-28
**대상**: 멀티 Agent 시스템을 처음 구축하는 개발자
**목표**: 설계부터 테스트까지 체계적인 구현 프로세스 제시

---

## 📚 목차

1. [구현 철학](#구현-철학)
2. [전체 구현 순서](#전체-구현-순서)
3. [Phase 1: 설계 및 계획](#phase-1-설계-및-계획)
4. [Phase 2: 기초 도구 구현](#phase-2-기초-도구-구현)
5. [Phase 3: 통합 Agent 구현](#phase-3-통합-agent-구현)
6. [Phase 4: 테스트 및 검증](#phase-4-테스트-및-검증)
7. [Phase 5: 기능 확장](#phase-5-기능-확장)
8. [베스트 프랙티스](#베스트-프랙티스)
9. [일반적인 실수와 해결책](#일반적인-실수와-해결책)

---

## 구현 철학

### 핵심 원칙

1. **설계 우선 (Design First)**
   - 코드 작성 전에 반드시 설계 문서 작성
   - 여러 접근 방법 비교 및 장단점 분석
   - 사용자/팀원과 설계 검토 및 승인

2. **점진적 구현 (Incremental Implementation)**
   - 작은 단위로 구현하고 검증
   - 각 단계마다 테스트 작성
   - 동작 확인 후 다음 단계 진행

3. **문서화와 테스트 (Documentation & Testing)**
   - 코드와 문서는 함께 작성
   - 테스트는 선택이 아닌 필수
   - 예제와 사용법 명시

4. **확장 가능성 (Extensibility)**
   - 새로운 기능 추가가 쉬운 구조
   - 기존 코드 수정 최소화
   - 명확한 인터페이스 정의

---

## 전체 구현 순서

```
Phase 1: 설계 및 계획
  ├─ 1.1 요구사항 분석
  ├─ 1.2 설계 문서 작성
  └─ 1.3 구현 계획 수립

Phase 2: 기초 도구 구현
  ├─ 2.1 LLM Router 설정
  ├─ 2.2 개별 도구 함수 작성
  └─ 2.3 도구 단위 테스트

Phase 3: 통합 Agent 구현
  ├─ 3.1 단일 Agent 방식
  ├─ 3.2 Router Agent 방식
  └─ 3.3 대화 기록 유지 (Checkpointer)

Phase 4: 테스트 및 검증
  ├─ 4.1 통합 테스트 작성
  ├─ 4.2 워크플로우 검증
  └─ 4.3 비교 분석

Phase 5: 기능 확장
  ├─ 5.1 새 도구 추가
  ├─ 5.2 Agent 통합
  └─ 5.3 테스트 업데이트
```

---

## Phase 1: 설계 및 계획

### 1.1 요구사항 분석

**목적**: 무엇을 만들 것인지 명확히 정의

#### 체크리스트
- [ ] 핵심 기능 목록 작성
- [ ] 사용자 시나리오 정의
- [ ] 필요한 도구/라이브러리 파악
- [ ] 제약사항 및 전제조건 확인

#### 예시: 통합 소스 관리 Agent
```markdown
**핵심 기능**:
1. Git 저장소 추가 및 관리
2. 자동 임베딩 실행
3. 소스 목록 조회/삭제
4. 대화 기록 유지

**사용자 시나리오**:
- "https://github.com/user/repo.git 추가해줘"
  → 소스 추가 + 자동 임베딩
- "내 소스 목록 보여줘"
  → 등록된 소스 조회

**필요 도구**:
- LangGraph: Agent 오케스트레이션
- LangChain: LLM 통합
- ChromaDB: 벡터 DB
```

### 1.2 설계 문서 작성

**위치**: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`

#### 설계 문서 구조
```markdown
# [기능명] 설계 문서

## 개요
- 목적
- 범위
- 핵심 개념

## 아키텍처
### 접근 방법 1: [이름]
- 구조 다이어그램
- 장점
- 단점
- 사용 사례

### 접근 방법 2: [이름]
(동일 구조)

## 비교 및 권장사항
| 항목 | 방법1 | 방법2 |
|-----|------|------|
| 복잡도 | ... | ... |

**권장**: [이유와 함께]

## 데이터 플로우
- 입력 → 처리 → 출력

## 컴포넌트 정의
- 각 클래스/함수의 책임
- 인터페이스 명세

## 에러 핸들링
- 예상 오류 시나리오
- 처리 방법

## 파일 구조
src/
├── tools/
│   ├── source.py
│   └── embedding.py
└── unified_controller_single.py
```

#### 실제 예시
참고: `docs/superpowers/specs/2026-07-28-unified-agent-design.md`

**핵심 결정 사항**:
1. **두 가지 방식 모두 구현**: Router vs 단일 Agent
2. **대화 기록 유지**: InMemorySaver checkpointer 사용
3. **도구 분리**: source.py, embedding.py로 모듈화

### 1.3 구현 계획 수립

**위치**: `docs/superpowers/plans/YYYY-MM-DD-<topic>-implementation.md`

#### 계획 문서 구조
```markdown
# [기능명] 구현 계획

> **For agentic workers**: 이 계획을 task-by-task로 실행

**Goal**: [한 문장 요약]
**Architecture**: [2-3 문장]
**Tech Stack**: [핵심 기술]

---

### Task 1: [컴포넌트명]

**Files**:
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`

- [ ] **Step 1: 테스트 작성**
```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**
```bash
pytest tests/path/test.py::test_name -v
```

- [ ] **Step 3: 최소 구현**
```python
def function(input):
    return expected
```

- [ ] **Step 4: 테스트 통과 확인**

- [ ] **Step 5: 커밋**
```bash
git add ... && git commit -m "feat: ..."
```

(각 Task마다 반복)
```

#### 태스크 분해 원칙

1. **한 Task = 한 기능**: 명확한 경계
2. **2-5분 내 완료**: 너무 크면 분할
3. **독립적 실행 가능**: 순서 중요하지만 각각 완결성
4. **검증 가능**: 테스트로 성공/실패 판단

#### 실제 예시
```markdown
### Task 1: 단일 Agent용 도구 리스트 정의

**Files**:
- Create: `src/unified_controller_single.py`

- [ ] Step 1: 모듈 docstring 및 import 작성
- [ ] Step 2: checkpointer 및 도구 리스트 정의
- [ ] Step 3: LLM에 도구 바인딩
- [ ] Step 4: import 테스트
- [ ] Step 5: 커밋
```

---

## Phase 2: 기초 도구 구현

### 2.1 LLM Router 설정

**파일**: `src/llm_router.py`

#### 목적
- 여러 LLM을 한 곳에서 관리
- Agent들이 공통으로 사용할 LLM 인스턴스 제공
- API 키 관리

#### 구현 순서

```python
# Step 1: 환경 변수 로드
from dotenv import load_dotenv
import os
load_dotenv()

# Step 2: LLM 인스턴스 생성
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

anthropic_llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
)

google_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# Step 3: 임베딩 모델 설정
from langchain_huggingface import HuggingFaceEmbeddings

local_embedding = HuggingFaceEmbeddings(
    model_name="jhgan/ko-sroberta-multitask",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# 별칭 생성 (다른 모듈에서 사용하기 쉽게)
embedding_function = local_embedding

# Step 4: VectorDB 클라이언트
import chromadb

chroma_client = chromadb.PersistentClient(path="./chroma_db")
```

#### 베스트 프랙티스

✅ **DO**:
- 환경 변수로 API 키 관리
- 명확한 변수명 사용 (`anthropic_llm`, `google_llm`)
- 한 파일에서 모든 LLM 관리

❌ **DON'T**:
- API 키 하드코딩
- 매번 새로운 LLM 인스턴스 생성
- 여러 파일에 LLM 설정 분산

### 2.2 개별 도구 함수 작성

**파일**: `src/tools/source.py`, `src/tools/embedding.py`

#### 도구 작성 원칙

1. **명확한 책임**: 한 도구 = 한 가지 작업
2. **완전한 docstring**: LLM이 이해할 수 있도록
3. **에러 처리**: 예외 상황 대비
4. **타입 힌트**: 입력/출력 타입 명시

#### 도구 함수 템플릿

```python
from langchain_core.tools import tool

@tool
def tool_name(
    user_id: str,
    param1: str,
    param2: int
) -> str:
    """
    도구 설명 (LLM이 읽음).

    이 도구는 [무엇을 하는지] 설명합니다.
    [언제 사용하는지] 명시합니다.

    Args:
        user_id: 사용자 식별자 (권한 체크용)
        param1: [설명]
        param2: [설명]

    Returns:
        성공/실패 메시지

    Raises:
        ValueError: [언제]
        RuntimeError: [언제]
    """
    # Step 1: 입력 검증
    if not user_id:
        return "❌ 오류: user_id가 필요합니다."

    # Step 2: 비즈니스 로직
    try:
        result = do_something(user_id, param1, param2)
        return f"✅ 성공: {result}"
    except Exception as e:
        return f"❌ 오류: {str(e)}"
```

#### 실제 예시: source.py

```python
@tool
def add_source_to_db(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    새로운 소스를 데이터베이스에 추가합니다.

    Git 저장소, 로컬 디렉토리 등을 학습 소스로 등록합니다.
    임베딩은 자동으로 시작되지 않습니다 (수동 실행 필요).

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: 'git', 'local', 'web' 중 하나
        location: Git URL, 로컬 경로, 웹 URL

    Returns:
        등록 결과 메시지 (source_id 포함)
    """
    # 입력 검증
    valid_types = ["git", "local", "web"]
    if source_type not in valid_types:
        return f"❌ 오류: source_type은 {valid_types} 중 하나여야 합니다."

    # DB 저장
    try:
        # ... 실제 DB 로직 ...
        source_id = saved_source.id
        return f"✅ 소스 추가 완료 (ID: {source_id})"
    except Exception as e:
        return f"❌ DB 오류: {str(e)}"
```

#### 도구 설계 체크리스트

- [ ] docstring에 "언제 사용하는지" 명시
- [ ] 필수 파라미터 검증
- [ ] user_id로 권한 체크
- [ ] 명확한 성공/실패 메시지
- [ ] 예외 처리 (try-except)
- [ ] 타입 힌트 완전히 작성

### 2.3 도구 단위 테스트

**원칙**: 도구 작성 직후 즉시 테스트

#### 테스트 파일 구조

```python
# tests/tools/test_source.py

import pytest
from src.tools.source import add_source_to_db

def test_add_source_success():
    """정상 케이스: 소스 추가 성공"""
    result = add_source_to_db.invoke({
        "user_id": "test_user",
        "name": "test_repo",
        "source_type": "git",
        "location": "https://github.com/user/repo.git"
    })
    assert "✅" in result
    assert "ID:" in result

def test_add_source_invalid_type():
    """오류 케이스: 잘못된 source_type"""
    result = add_source_to_db.invoke({
        "user_id": "test_user",
        "name": "test",
        "source_type": "invalid",
        "location": "path"
    })
    assert "❌" in result
    assert "source_type" in result

def test_add_source_missing_user_id():
    """오류 케이스: user_id 누락"""
    result = add_source_to_db.invoke({
        "user_id": "",
        "name": "test",
        "source_type": "git",
        "location": "path"
    })
    assert "❌" in result
```

#### 테스트 실행

```bash
# 개별 테스트
pytest tests/tools/test_source.py::test_add_source_success -v

# 전체 도구 테스트
pytest tests/tools/ -v

# 커버리지 확인
pytest --cov=src/tools tests/tools/
```

---

## Phase 3: 통합 Agent 구현

### 3.1 단일 Agent 방식

**파일**: `src/unified_controller_single.py`

#### 아키텍처

```
사용자 요청
    ↓
Unified Agent (6-8개 도구)
    ↓
Tool Node (도구 실행)
    ↓
Agent (결과 확인 및 연쇄 호출)
    ↓
END
```

#### 구현 순서

**Step 1: 기본 구조**

```python
"""
통합 소스 관리 Agent (단일 Agent 방식)

모든 소스, 임베딩, 로그 관리 작업을 처리하는 단일 LangGraph Agent.
"""
from typing import Annotated
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from . import llm_router
from .tools import source as source_tools
from .tools import embedding as embedding_tools

# Checkpointer 생성
checkpointer = InMemorySaver()

# 도구 리스트
unified_tools = [
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status,
]

# LLM에 도구 바인딩
llm_with_tools = llm_router.google_llm.bind_tools(unified_tools)
```

**Step 2: 시스템 메시지 생성**

```python
def create_system_message(user_id: str) -> SystemMessage:
    """user_id 컨텍스트가 포함된 시스템 메시지 생성"""
    return SystemMessage(content=f"""당신은 소스 관리 어시스턴트입니다 (user_id: {user_id}).

주요 기능:
1. Source 관리
   - Git 저장소 추가
   - 소스 목록 조회
   - 소스 삭제

2. Embedding 관리
   - 임베딩 실행
   - 임베딩 상태 조회

워크플로우:
- Git URL 추가 시: add_source_to_db → embed_source 순서로 연쇄 호출
- 소스 조회/삭제: 해당 도구만 호출
""")
```

**Step 3: Agent 노드 생성**

```python
def create_unified_agent(user_id: str):
    """시스템 메시지에 user_id가 포함된 Agent 함수 생성"""
    def unified_agent_node(state: MessagesState) -> dict:
        """모든 소스/임베딩 작업을 처리하는 통합 Agent"""
        system_message = create_system_message(user_id)
        messages = [system_message] + state["messages"]

        # 도구가 바인딩된 LLM 호출
        result = llm_with_tools.invoke(messages)

        return {"messages": [result]}

    return unified_agent_node
```

**Step 4: 그래프 구성**

```python
def _build_graph(user_id: str):
    """단일 통합 Agent를 위한 LangGraph 구성"""
    builder = StateGraph(MessagesState)

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
```

**Step 5: 공개 API**

```python
def unified_agent(user_id: str, message: str) -> str:
    """
    통합 소스 관리 Agent 진입점.

    Args:
        user_id: 사용자 ID (thread_id로 사용)
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
```

#### 핵심 포인트

1. **InMemorySaver**: 대화 기록 유지
   - `thread_id`로 사용자별 세션 분리
   - 이전 대화 참조 가능

2. **tools_condition**: 자동 분기
   - Agent가 도구 호출 → `"tools"` 노드
   - 도구 호출 없음 → `END`

3. **연쇄 호출**: Agent가 자동 처리
   - `add_source_to_db` 결과에서 `source_id` 추출
   - `embed_source(source_id)` 자동 호출

### 3.2 Router Agent 방식

**파일**: `src/unified_controller_router.py`

#### 아키텍처

```
사용자 요청
    ↓
Router Agent (요청 분석)
    ↓
┌─────────────────┐
│ route_to_agent  │
└─────────────────┘
    ↓         ↓
Source    Embedding
Agent      Agent
    ↓         ↓
  END       END
```

#### 구현 순서

**Step 1: State 정의**

```python
from typing import Annotated, Literal, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import add_messages

class UnifiedState(TypedDict):
    """Router용 State (라우팅 목적지 필드 포함)"""
    messages: Annotated[list, add_messages]
    route_destination: str

class RouteDecision(BaseModel):
    """Router Agent 결정 결과"""
    destination: Literal["source_management", "embedding_execution"] = Field(
        description="소스 CRUD는 'source_management', 임베딩은 'embedding_execution'"
    )
    reasoning: str = Field(
        description="이 라우팅 선택에 대한 설명"
    )
```

**Step 2: 도구 분리**

```python
# source_agent용 도구
source_management_tools = [
    source_tools.add_source_and_embed,  # 통합 도구
    source_tools.add_source_to_db,
    source_tools.get_user_sources,
    source_tools.delete_source_from_db,
]

# embedding_agent용 도구
embedding_management_tools = [
    embedding_tools.embed_source,
    embedding_tools.get_embedding_status,
]
```

**Step 3: Router Agent**

```python
def create_router_agent(user_id: str):
    """요청을 분석하여 Sub-Agent로 라우팅하는 Router Agent 생성"""

    # Gemini Flash + 구조화된 출력
    router_llm = llm_router.google_llm.with_structured_output(RouteDecision)

    def router_node(state: UnifiedState) -> dict:
        user_message = state["messages"][-1].content

        router_system = SystemMessage(content=f"""당신은 Router입니다.

다음 중 하나를 선택:
1. source_management - 소스 추가/조회/삭제
2. embedding_execution - 임베딩 실행/상태 확인

중요:
- Git URL 추가 → source_management
- 임베딩 상태 확인 → embedding_execution
""")

        # 라우팅 결정
        decision = router_llm.invoke([router_system, HumanMessage(content=user_message)])

        return {"route_destination": decision.destination}

    return router_node
```

**Step 4: Sub-Agents**

```python
def create_source_agent(user_id: str):
    """소스 관리 Agent 생성"""
    source_agent_llm = llm_router.google_llm.bind_tools(source_management_tools)

    def source_agent_node(state: UnifiedState) -> dict:
        source_system = SystemMessage(content=f"""소스 관리 전문 에이전트 (user_id: {user_id})

주요 책임:
- add_source_and_embed: 소스 추가 + 자동 임베딩
- get_user_sources: 소스 목록
- delete_source_from_db: 소스 삭제
""")

        messages = [source_system] + state["messages"]
        result = source_agent_llm.invoke(messages)

        return {"messages": [result]}

    return source_agent_node

def create_embedding_agent(user_id: str):
    """임베딩 관리 Agent 생성"""
    embedding_agent_llm = llm_router.anthropic_llm.bind_tools(embedding_management_tools)

    def embedding_agent_node(state: UnifiedState) -> dict:
        embedding_system = SystemMessage(content=f"""임베딩 실행 전문 에이전트

주요 책임:
- embed_source: 임베딩 시작/재시작
- get_embedding_status: 상태 조회
""")

        messages = [embedding_system] + state["messages"]
        result = embedding_agent_llm.invoke(messages)

        return {"messages": [result]}

    return embedding_agent_node
```

**Step 5: 라우팅 함수**

```python
def route_to_agent(state: UnifiedState) -> Literal["source_agent", "embedding_agent"]:
    """route_destination 기반으로 Agent 선택"""
    destination = state["route_destination"]

    if destination == "source_management":
        return "source_agent"
    else:
        return "embedding_agent"
```

**Step 6: 그래프 구성**

```python
def _build_graph(user_id: str):
    """Router 아키텍처를 가진 완전한 LangGraph 구성"""
    builder = StateGraph(UnifiedState)

    # Agent 노드 생성
    router_node = create_router_agent(user_id)
    source_agent_node = create_source_agent(user_id)
    embedding_agent_node = create_embedding_agent(user_id)

    # 도구 노드 생성
    source_tool_node = ToolNode(tools=source_management_tools)
    embedding_tool_node = ToolNode(tools=embedding_management_tools)

    # 노드 추가
    builder.add_node("router", router_node)
    builder.add_node("source_agent", source_agent_node)
    builder.add_node("embedding_agent", embedding_agent_node)
    builder.add_node("source_tools", source_tool_node)
    builder.add_node("embedding_tools", embedding_tool_node)

    # 엣지 추가
    builder.add_edge(START, "router")

    # Router → Sub-Agent
    builder.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "source_agent": "source_agent",
            "embedding_agent": "embedding_agent",
        },
    )

    # Sub-Agent → Tools or END
    builder.add_conditional_edges(
        "source_agent",
        tools_condition,
        {"source_tools": "source_tools", "__end__": END},
    )
    builder.add_conditional_edges(
        "embedding_agent",
        tools_condition,
        {"embedding_tools": "embedding_tools", "__end__": END},
    )

    # Tools → Agent (루프백)
    builder.add_edge("source_tools", "source_agent")
    builder.add_edge("embedding_tools", "embedding_agent")

    # Checkpointer와 함께 컴파일
    return builder.compile(checkpointer=checkpointer)
```

#### Router 방식의 장점

1. **책임 분리**: 각 Agent가 명확한 역할
2. **확장성**: 새 Agent 추가 쉬움
3. **LLM 선택**: Agent별 다른 LLM 사용 가능

#### Router 방식의 단점

1. **복잡도 증가**: 코드량 2배
2. **라우팅 오류 가능성**: 잘못된 Agent로 전달 위험

### 3.3 대화 기록 유지 (Checkpointer)

#### 개념

- **InMemorySaver**: 메모리 기반 대화 저장소
- **thread_id**: 사용자별 대화 세션 구분
- **자동 저장**: 매 턴마다 State 저장

#### 사용법

```python
# 1. Checkpointer 생성
from langgraph.checkpoint.memory import InMemorySaver
checkpointer = InMemorySaver()

# 2. 그래프 컴파일 시 전달
graph = builder.compile(checkpointer=checkpointer)

# 3. 실행 시 thread_id 설정
config = {"configurable": {"thread_id": user_id}}
result = graph.invoke(input_dict, config=config)
```

#### 대화 기록 활용 예시

```python
# 첫 번째 대화
response1 = unified_agent("user1", "소스 목록 보여줘")
# 응답: "등록된 소스가 3개 있습니다..."

# 두 번째 대화 (이전 대화 참조)
response2 = unified_agent("user1", "첫 번째 소스 삭제해줘")
# Agent는 이전 대화에서 본 목록을 기억하고 있음
```

---

## Phase 4: 테스트 및 검증

### 4.1 통합 테스트 작성

**파일**: `test_unified_agents.py`

#### 테스트 구조

```python
"""
통합 Agent 테스트 스크립트

두 가지 구현 방식을 테스트:
1. Single Agent 방식
2. Router 방식
"""

def test_single_agent():
    """단일 Agent 방식 테스트"""
    user_id = "test_user_single"

    # 테스트 1: 소스 목록 조회
    response = single_agent(user_id, "소스 목록 보여줘")
    assert response  # 응답 있음

    # 테스트 2: 소스 타입 확인
    response = single_agent(user_id, "소스 타입이 뭐가 있어?")
    assert "git" in response.lower()

def test_router_agent():
    """Router 방식 테스트"""
    user_id = "test_user_router"

    # 테스트 1: source_agent로 라우팅
    response = router_agent(user_id, "내 소스 목록 보여줘")
    assert response

    # 테스트 2: embedding_agent로 라우팅
    response = router_agent(user_id, "임베딩 상태 알려줘")
    assert response

def test_conversation_history():
    """대화 기록 유지 테스트"""
    user_id = "test_user_history"

    # 첫 번째 대화
    response1 = single_agent(user_id, "내 소스 목록 보여줘")

    # 두 번째 대화 (이전 대화 참조)
    response2 = single_agent(user_id, "방금 보여준 목록 중 첫 번째는 뭐야?")
    # Agent가 이전 응답을 기억해야 함
    assert response2

def compare_both_agents():
    """두 방식 비교 테스트"""
    test_message = "소스 목록 보여줘"

    response_single = single_agent("compare_user", test_message)
    response_router = router_agent("compare_user", test_message)

    # 두 응답 모두 있어야 함
    assert response_single
    assert response_router
```

### 4.2 워크플로우 검증

#### Git URL 자동 임베딩 테스트

```python
def test_auto_embedding_workflow():
    """Git URL 추가 시 자동 임베딩 테스트"""
    user_id = "test_auto_embed"

    # Git URL 추가 요청
    response = single_agent(
        user_id,
        "https://github.com/test/repo.git 추가해줘"
    )

    # 응답에 "소스 추가 완료"와 "임베딩 시작" 모두 포함되어야 함
    assert "추가" in response
    assert "임베딩" in response or "embedding" in response.lower()
```

#### 오류 처리 테스트

```python
def test_invalid_source_type():
    """잘못된 source_type 처리 테스트"""
    user_id = "test_error"

    response = single_agent(
        user_id,
        "invalid_type으로 소스 추가해줘"
    )

    # 오류 메시지 또는 타입 확인 요청이 있어야 함
    assert "오류" in response or "타입" in response
```

### 4.3 비교 분석

#### 성능 비교

```python
import time

def test_performance_comparison():
    """두 방식 응답 시간 비교"""
    message = "소스 목록 보여줘"

    # Single Agent
    start = time.time()
    single_agent("perf_test", message)
    single_time = time.time() - start

    # Router Agent
    start = time.time()
    router_agent("perf_test", message)
    router_time = time.time() - start

    print(f"Single Agent: {single_time:.2f}s")
    print(f"Router Agent: {router_time:.2f}s")
```

---

## Phase 5: 기능 확장

### 5.1 새 도구 추가

#### 예시: 로그 관리 도구

**Step 1: 도구 파일 생성**

```python
# src/tools/log.py

@tool
def retriever_vectordb(date: str, reference_len: str) -> str:
    """날짜 기반 VectorDB 검색"""
    # 구현...

@tool
def maker_logfile(date: str, content: str) -> str:
    """일지 파일 저장"""
    # 구현...
```

**Step 2: 필요 시 의존성 추가**

```python
# llm_router.py에 추가
embedding_function = local_embedding  # log.py에서 사용
```

### 5.2 Agent 통합

#### 단일 Agent에 추가

```python
# unified_controller_single.py

from .tools import log as log_tools

unified_tools = [
    # 기존 도구들...
    log_tools.retriever_vectordb,
    log_tools.maker_logfile,
]

# 시스템 메시지 업데이트
def create_system_message(user_id: str) -> SystemMessage:
    return SystemMessage(content=f"""...

3. 일지 관리
   - 날짜 기반 데이터 검색 (retriever_vectordb)
   - 일지 파일 저장 (maker_logfile)

워크플로우:
- 일지 작성 요청 시: retriever_vectordb → maker_logfile
""")
```

#### Router Agent에 추가

```python
# unified_controller_router.py

# source_agent에 추가 (로그도 소스 관련이므로)
source_management_tools = [
    # 기존 도구들...
    log_tools.retriever_vectordb,
    log_tools.maker_logfile,
]

# Router 시스템 메시지 업데이트
router_system = SystemMessage(content=f"""...

1. source_management
   - 소스 CRUD
   - 일지 작성 및 저장 (새로 추가)
""")
```

### 5.3 테스트 업데이트

```python
# test_log_tools.py

def test_retriever_vectordb():
    """날짜 검색 도구 테스트"""
    result = retriever_vectordb.invoke({
        "date": "2026-07-28",
        "reference_len": "3"
    })
    assert result

def test_maker_logfile():
    """일지 저장 도구 테스트"""
    result = maker_logfile.invoke({
        "date": "2026-07-28",
        "content": "# 테스트 일지\n내용..."
    })
    assert "저장 완료" in result

def test_log_workflow_single():
    """단일 Agent 로그 워크플로우"""
    response = single_agent("test", "2026년 7월 28일 일지 작성해줘")
    assert response

def test_log_workflow_router():
    """Router Agent 로그 워크플로우"""
    response = router_agent("test", "오늘 일지 작성해줘")
    assert response
```

---

## 베스트 프랙티스

### 1. 설계 패턴

#### ✅ DO: 명확한 책임 분리

```python
# GOOD: 각 도구가 한 가지 일만 함
@tool
def add_source_to_db(...) -> str:
    """소스만 추가"""

@tool
def embed_source(...) -> str:
    """임베딩만 실행"""

@tool
def add_source_and_embed(...) -> str:
    """소스 추가 + 임베딩 (통합 도구)"""
```

#### ❌ DON'T: 모호한 책임

```python
# BAD: 하나의 도구가 너무 많은 일을 함
@tool
def manage_source(...) -> str:
    """추가/수정/삭제/임베딩 모두 처리"""
    # 너무 복잡!
```

### 2. 에러 처리

#### ✅ DO: 명확한 에러 메시지

```python
@tool
def add_source_to_db(...) -> str:
    if not user_id:
        return "❌ 오류: user_id가 필요합니다."

    if source_type not in ["git", "local", "web"]:
        return f"❌ 오류: source_type은 git, local, web 중 하나여야 합니다. 현재: {source_type}"

    try:
        # 비즈니스 로직
        return "✅ 성공: ..."
    except DatabaseError as e:
        return f"❌ DB 오류: {str(e)}"
    except Exception as e:
        return f"❌ 예상치 못한 오류: {str(e)}"
```

#### ❌ DON'T: 애매한 에러

```python
# BAD
@tool
def add_source_to_db(...) -> str:
    try:
        # 모든 로직
        return "success"
    except:
        return "error"  # 무엇이 잘못되었는지 알 수 없음!
```

### 3. 시스템 메시지

#### ✅ DO: 구체적인 가이드

```python
SystemMessage(content=f"""당신은 소스 관리 어시스턴트입니다.

주요 기능:
1. add_source_to_db - Git 저장소 등록
2. embed_source - 임베딩 실행

워크플로우:
- Git URL 추가 시: add_source_to_db를 먼저 호출하여 source_id를 얻은 후,
  즉시 embed_source(source_id)를 호출하여 자동으로 임베딩을 시작하세요.

중요: Git URL이 포함된 요청은 반드시 두 도구를 연쇄 호출하세요.
""")
```

#### ❌ DON'T: 모호한 지시

```python
# BAD
SystemMessage(content="소스를 관리하세요. 필요한 도구를 사용하세요.")
```

### 4. 대화 기록

#### ✅ DO: thread_id 일관성 유지

```python
# GOOD: user_id를 thread_id로 사용
def unified_agent(user_id: str, message: str) -> str:
    config = {"configurable": {"thread_id": user_id}}
    result = graph.invoke(input_dict, config=config)
```

#### ❌ DON'T: thread_id 랜덤 생성

```python
# BAD: 매번 다른 thread_id → 대화 기록 분리됨
import uuid
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
```

### 5. 테스트

#### ✅ DO: 다양한 케이스

```python
def test_add_source():
    # 정상 케이스
    test_success()

    # 오류 케이스
    test_invalid_type()
    test_missing_user_id()
    test_duplicate_source()

    # 경계 케이스
    test_empty_name()
    test_very_long_location()
```

#### ❌ DON'T: Happy Path만 테스트

```python
# BAD: 성공 케이스만
def test_add_source():
    result = add_source_to_db.invoke({...})
    assert "✅" in result
```

---

## 일반적인 실수와 해결책

### 실수 1: Checkpointer 없이 대화 기록 기대

**문제**:
```python
# Checkpointer 없음
graph = builder.compile()  # checkpointer 누락!

# 대화 기록이 유지되지 않음
response1 = unified_agent("user1", "소스 목록")
response2 = unified_agent("user1", "첫 번째 소스는?")  # 이전 대화 기억 못함
```

**해결**:
```python
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": user_id}}
result = graph.invoke(input_dict, config=config)
```

### 실수 2: 도구 파라미터 검증 누락

**문제**:
```python
@tool
def add_source_to_db(user_id: str, source_type: str, ...) -> str:
    # 검증 없이 바로 사용
    db.save(source_type, ...)  # source_type이 invalid면 DB 오류!
```

**해결**:
```python
@tool
def add_source_to_db(user_id: str, source_type: str, ...) -> str:
    # 먼저 검증
    valid_types = ["git", "local", "web"]
    if source_type not in valid_types:
        return f"❌ source_type은 {valid_types} 중 하나여야 합니다."

    # 검증 통과 후 실행
    db.save(source_type, ...)
```

### 실수 3: Router 라우팅 조건 불명확

**문제**:
```python
router_system = SystemMessage(content="""
1. source_management - 소스 관련
2. embedding_execution - 임베딩 관련
""")
# "소스 임베딩 시작해줘" → 어디로 가야 할지 애매!
```

**해결**:
```python
router_system = SystemMessage(content="""
1. source_management
   - 소스 추가/조회/삭제
   - 예: "Git 저장소 추가", "소스 목록"

2. embedding_execution
   - 임베딩 시작/재시작
   - 임베딩 상태 조회
   - 예: "1번 소스 임베딩 시작", "임베딩 상태"

중요:
- Git URL 추가 → source_management (자동으로 임베딩까지 처리)
- 수동 임베딩 재시작 → embedding_execution
""")
```

### 실수 4: 시스템 메시지에 user_id 미포함

**문제**:
```python
# user_id 없는 시스템 메시지
SystemMessage(content="당신은 소스 관리 어시스턴트입니다.")

# 도구 호출 시 user_id를 어디서 가져올지 모름
```

**해결**:
```python
def create_system_message(user_id: str) -> SystemMessage:
    return SystemMessage(content=f"""당신은 소스 관리 어시스턴트입니다 (user_id: {user_id}).

도구 호출 시 반드시 user_id={user_id}를 전달하세요.
""")
```

### 실수 5: 통합 도구 vs 연쇄 호출 혼동

**상황 1: 통합 도구가 필요한 경우**
```python
# Router 방식에서는 Sub-Agent 간 데이터 전달이 어려움
# → 통합 도구 사용

@tool
def add_source_and_embed(...) -> str:
    """소스 추가 + 임베딩 (한 번에)"""
    source_id = add_source_to_db(...)
    embed_result = embed_source(source_id)
    return f"소스 추가: {source_id}\n임베딩: {embed_result}"
```

**상황 2: 연쇄 호출로 충분한 경우**
```python
# 단일 Agent는 자동으로 연쇄 호출 가능
# → 별도 통합 도구 불필요

# Agent가 자동으로:
# 1. add_source_to_db 호출 → source_id 획득
# 2. embed_source(source_id) 호출
```

---

## 체크리스트

### 설계 단계
- [ ] 요구사항 문서화
- [ ] 여러 접근 방법 비교
- [ ] 설계 문서 작성 및 검토
- [ ] 구현 계획 수립 (Task 단위)

### 구현 단계
- [ ] LLM Router 설정
- [ ] 개별 도구 함수 작성
- [ ] 도구 docstring 완전히 작성
- [ ] 단위 테스트 작성
- [ ] 통합 Agent 구현
- [ ] Checkpointer 설정
- [ ] 시스템 메시지 명확히 작성

### 테스트 단계
- [ ] 정상 케이스 테스트
- [ ] 오류 케이스 테스트
- [ ] 대화 기록 유지 테스트
- [ ] 워크플로우 검증
- [ ] 성능 확인

### 확장 단계
- [ ] 새 도구 파일 생성
- [ ] Agent에 통합
- [ ] 시스템 메시지 업데이트
- [ ] 테스트 추가

---

## 결론

이 가이드는 실제 구현 경험을 바탕으로 작성되었습니다. 핵심은:

1. **설계 먼저**: 코드 작성 전 충분히 고민
2. **작은 단위**: Task 단위로 점진적 구현
3. **테스트 필수**: 각 단계마다 검증
4. **명확한 인터페이스**: docstring, 시스템 메시지, 타입 힌트
5. **확장 고려**: 새 기능 추가가 쉬운 구조

이 순서를 따르면 안정적이고 유지보수 가능한 멀티 Agent 시스템을 구축할 수 있습니다.

---

**작성자**: Claude Sonnet 4.5
**참고 프로젝트**: yuta_logagent (2026-07-28)
