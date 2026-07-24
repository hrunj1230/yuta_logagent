# Yuta Bot 리팩토링 설계서

**작성일**: 2026-07-24
**목표**: 코드 구조 개선, 디자인 패턴 적용, 타입 안정성 강화, 테스트 가능성 향상

---

## 목차

1. [전체 아키텍처 개요](#1-전체-아키텍처-개요)
2. [계층별 역할과 책임](#2-계층별-역할과-책임)
3. [현재 코드 → 새 구조 매핑](#3-현재-코드--새-구조-매핑)
4. [적용할 디자인 패턴](#4-적용할-디자인-패턴)
5. [타입 안정성 강화](#5-타입-안정성-강화)
6. [테스트 전략](#6-테스트-전략)
7. [마이그레이션 계획](#7-마이그레이션-계획)

---

## 1. 전체 아키텍처 개요

### 1.1 계층형 아키텍처 (Layered Architecture) 채택

**의존성 방향 규칙 (Dependency Rule):**
```
presentation → application → domain ← infrastructure
     ↓              ↓           ↑            ↑
  router.py    services/   models/      llm/, db/
              agents/                   (외부 세계)
```

**핵심 원칙:**
- 외부 계층은 내부 계층에 의존 (역방향 금지)
- 도메인 계층은 어떤 계층에도 의존하지 않음 (순수성)
- 인프라 계층은 도메인 인터페이스를 구현

### 1.2 새 디렉토리 구조

```
yuta_bot/
├── src/
│   ├── presentation/          # 🆕 표현 계층 (FastAPI)
│   │   └── api/
│   │       └── routes/
│   │           ├── __init__.py
│   │           ├── auth_routes.py      # 로그인/사용자
│   │           ├── log_routes.py       # 일지 생성 API
│   │           └── source_routes.py    # 소스 관리 API
│   │
│   ├── application/           # 🆕 응용 계층 (비즈니스 흐름)
│   │   ├── services/          # Use Case 패턴
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── log_service.py
│   │   │   └── source_service.py
│   │   └── agents/            # LangGraph Agents
│   │       ├── __init__.py
│   │       ├── log_agent.py
│   │       ├── source_agent.py
│   │       ├── router_agent.py
│   │       └── tools/
│   │           ├── __init__.py
│   │           ├── log_tools.py
│   │           └── source_tools.py
│   │
│   ├── domain/                # 🆕 도메인 계층 (비즈니스 규칙)
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── log.py
│   │       ├── source.py
│   │       └── auth.py
│   │
│   └── infrastructure/        # 🆕 인프라 계층 (외부 의존성)
│       ├── llm/               # LLM 추상화
│       │   ├── __init__.py
│       │   ├── factory.py            # Factory Pattern
│       │   ├── base.py               # Abstract Base Class
│       │   └── providers/
│       │       ├── __init__.py
│       │       ├── claude_provider.py
│       │       ├── gemini_provider.py
│       │       └── codex_provider.py
│       ├── vectordb/          # Vector DB 추상화
│       │   ├── __init__.py
│       │   ├── repository.py         # Repository Pattern
│       │   ├── chroma_client.py
│       │   └── embedder.py
│       └── storage/           # 기존 storage/ 이동
│           ├── __init__.py
│           ├── database.py
│           ├── models.py
│           └── auth.py
│
├── storage/                   # 🗑️ 삭제 (infrastructure/storage로 이동)
├── templates/                 # 유지
├── main.py                    # 수정 (새 라우터 import)
└── tests/                     # 🆕 테스트 디렉토리
    ├── unit/
    ├── integration/
    └── conftest.py
```

---

## 2. 계층별 역할과 책임

### 2.1 Presentation Layer (표현 계층)

**역할:**
- HTTP 요청/응답 처리
- 요청 데이터 검증 (FastAPI Pydantic)
- 응답 직렬화

**책임:**
- ✅ FastAPI 라우터 정의
- ✅ HTTP 상태 코드 관리
- ✅ API 문서화 (OpenAPI)
- ❌ 비즈니스 로직 (Service에 위임)
- ❌ DB/LLM 직접 호출 (Service를 통해 간접 호출)

**예시:**
```python
# presentation/api/routes/log_routes.py
@router.post("/logs", response_model=LogResponse)
async def create_log(
    request: LogRequest,
    service: LogService = Depends(get_log_service)  # 의존성 주입
):
    """일지 생성 API - HTTP 처리만"""
    return await service.create_log(request)
```

### 2.2 Application Layer (응용 계층)

**역할:**
- 비즈니스 흐름 조율 (Use Case 실행)
- LangGraph Agent 워크플로우 관리
- 여러 인프라 서비스 조합

**책임:**
- ✅ Use Case 구현 (Services)
- ✅ Agent 정의 및 실행
- ✅ 트랜잭션 관리
- ❌ HTTP 처리 (Presentation에 위임)
- ❌ DB/LLM 직접 구현 (Infrastructure 사용)

**예시:**
```python
# application/services/log_service.py
class LogService:
    def __init__(self, log_agent: LogAgent):
        self.log_agent = log_agent

    async def create_log(self, request: LogRequest) -> LogResponse:
        """Use Case: 일지 생성 흐름"""
        thread_id = request.thread_id or str(uuid.uuid4())
        content = await self.log_agent.run(request.message, thread_id)
        return LogResponse(content=content, thread_id=thread_id)
```

### 2.3 Domain Layer (도메인 계층)

**역할:**
- 비즈니스 규칙 정의
- 엔티티 및 Value Object
- 도메인 검증 로직

**책임:**
- ✅ Pydantic 모델 정의
- ✅ 비즈니스 Validation
- ✅ 도메인 불변식 (Invariant)
- ❌ 외부 의존성 (DB, API 등)
- ❌ 프레임워크 의존성 (FastAPI, LangChain)

**예시:**
```python
# domain/models/log.py
class LogRequest(BaseModel):
    """일지 생성 요청 - 도메인 규칙"""
    message: str = Field(..., min_length=1)
    thread_id: Optional[str] = None

    @validator('message')
    def validate_message(cls, v):
        if len(v.strip()) == 0:
            raise ValueError("메시지는 비어있을 수 없습니다")
        return v
```

### 2.4 Infrastructure Layer (인프라 계층)

**역할:**
- 외부 시스템 연동 (DB, API, 파일)
- 기술적 구현 세부사항
- 인터페이스 구현

**책임:**
- ✅ LLM API 호출
- ✅ ChromaDB 연결 및 쿼리
- ✅ 파일 I/O
- ✅ PostgreSQL ORM
- ❌ 비즈니스 로직 (Domain/Application에 위임)

**예시:**
```python
# infrastructure/llm/providers/claude_provider.py
class ClaudeProvider(LLMProvider):
    """Claude API 구현 - 기술 세부사항"""
    def __init__(self, api_key: str):
        self.client = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            anthropic_api_key=api_key
        )

    def invoke(self, messages: list) -> str:
        return self.client.invoke(messages)
```

---

## 3. 현재 코드 → 새 구조 매핑

### 3.1 router.py (286줄) → 4개 파일

#### 현재 구조 분석

```python
# router.py의 현재 내용
# [줄 20-44] Pydantic 모델 (도메인)
class QueryReq(BaseModel): ...
class GitSyncReq(BaseModel): ...
class LoginRequest(BaseModel): ...

# [줄 46-132] 로그인/사용자 라우트 (표현)
@router.get("/")
@router.post("/login-form")
@router.get("/user/{user_id}")

# [줄 193-197] 일지 API (표현)
@router.post("/call_agent")

# [줄 199-216] 소스 관리 API (표현)
@router.post("/unified_agent")

# [줄 225-285] Git 동기화 로직 (응용 + 인프라)
async def sync_git_repo(req: GitSyncReq):
    # Git clone (인프라)
    subprocess.run(["git", "clone", ...])
    # 임베딩 (인프라)
    embedding_result = embedding_file_for_user(...)
```

#### 이동 계획

**1. 도메인 모델 분리**

```python
# domain/models/log.py (새 파일)
from pydantic import BaseModel, Field
from typing import Optional

class LogRequest(BaseModel):
    """일지 생성 요청"""
    message: str = Field(..., description="사용자 메시지")
    thread_id: Optional[str] = Field(None, description="대화 스레드 ID")

class LogResponse(BaseModel):
    """일지 생성 응답"""
    content: str
    thread_id: str


# domain/models/source.py (새 파일)
from pydantic import BaseModel, HttpUrl

class SourceSyncRequest(BaseModel):
    """Git 저장소 동기화 요청"""
    user_id: str
    repo_url: HttpUrl  # URL 자동 검증
    branch: str = "main"

class SourceSyncResponse(BaseModel):
    """동기화 응답"""
    success: bool
    message: str
    user_id: str
    repo_url: str
    embedding_result: Optional[str] = None


# domain/models/auth.py (새 파일)
class LoginRequest(BaseModel):
    """로그인 요청"""
    user_id: str = Field(..., min_length=1)

class UserInfoResponse(BaseModel):
    """사용자 정보 응답"""
    user_id: str
    sources_count: int
```

**2. 표현 계층 분리**

```python
# presentation/api/routes/auth_routes.py (새 파일)
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from application.services.auth_service import AuthService
from domain.models.auth import LoginRequest, UserInfoResponse

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def login_page(request: Request):
    """로그인 페이지"""
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )

@router.post("/login-form")
async def login_form(
    user_id: str = Form(...),
    auth_service: AuthService = Depends()
):
    """로그인 처리"""
    result = await auth_service.login_or_register(user_id)
    return RedirectResponse(
        url=f"/user/{result.user_id}",
        status_code=303
    )

@router.get("/user/{user_id}")
async def get_user_page(
    request: Request,
    user_id: str,
    auth_service: AuthService = Depends()
):
    """사용자 페이지"""
    user_info = await auth_service.get_user_info(user_id)
    return templates.TemplateResponse(
        request=request,
        name="user_page.html",
        context={
            "user_id": user_info.user_id,
            "sources_count": user_info.sources_count
        }
    )


# presentation/api/routes/log_routes.py (새 파일)
from fastapi import APIRouter, Depends
from domain.models.log import LogRequest, LogResponse
from application.services.log_service import LogService

router = APIRouter(prefix="/logs", tags=["logs"])

@router.post("/", response_model=LogResponse)
async def create_log(
    request: LogRequest,
    service: LogService = Depends()
):
    """일지 생성 API"""
    return await service.create_log(request)


# presentation/api/routes/source_routes.py (새 파일)
from fastapi import APIRouter, Depends
from domain.models.source import SourceSyncRequest, SourceSyncResponse
from application.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])

@router.post("/sync", response_model=SourceSyncResponse)
async def sync_git_repo(
    request: SourceSyncRequest,
    service: SourceService = Depends()
):
    """Git 저장소 동기화"""
    return await service.sync_repository(request)
```

**3. 응용 계층 추가 (새 비즈니스 로직)**

```python
# application/services/auth_service.py (새 파일)
from domain.models.auth import LoginRequest, UserInfoResponse
from infrastructure.storage.auth import login_or_register, get_user_by_id
from infrastructure.storage.database import get_db
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

class AuthService:
    """인증 비즈니스 로직"""

    def __init__(self, db: Session = Depends(get_db)):
        self.db = db

    async def login_or_register(self, user_id: str) -> UserInfoResponse:
        """로그인 또는 회원가입"""
        if not user_id or not user_id.strip():
            raise HTTPException(
                status_code=400,
                detail="ID를 입력해주세요"
            )

        user = login_or_register(self.db, user_id.strip())

        return UserInfoResponse(
            user_id=user.user_id,
            sources_count=len(user.sources) if user.sources else 0
        )

    async def get_user_info(self, user_id: str) -> UserInfoResponse:
        """사용자 정보 조회"""
        user = get_user_by_id(self.db, user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail="사용자를 찾을 수 없습니다"
            )

        return UserInfoResponse(
            user_id=user.user_id,
            sources_count=len(user.sources) if user.sources else 0
        )
```

**변경 요약:**

| 항목 | 변경 전 | 변경 후 | 이유 |
|------|---------|---------|------|
| **파일 수** | 1개 (router.py) | 7개 (모델 3 + 라우트 3 + 서비스 1) | 단일 책임 원칙 |
| **코드 길이** | 286줄 | 각 30-60줄 | 가독성 향상 |
| **의존성** | HTTP + 모델 + 로직 혼재 | 계층별 분리 | 테스트 가능 |
| **재사용성** | 낮음 (router에 종속) | 높음 (모델 독립적) | 도메인 재사용 |

---

### 3.2 controller.py (465줄) → 6개 파일

#### 현재 구조 분석

```python
# controller.py의 현재 내용
# [줄 19-23] 도구 목록
tools = [retriever_vectordb, embedding_file, maker_logfile]

# [줄 26-60] 시스템 메시지
SYSTEM_MESSAGE = SystemMessage(content="...")

# [줄 62-75] Agent 함수
def agent(state: MessagesState) -> dict: ...

# [줄 77-97] Graph 빌더
def _graph_builder(): ...
graph = _graph_builder()

# [줄 99-123] 인증 로직
def handle_login(db: Session, user_id: str): ...
def get_user_info(db: Session, user_id: str): ...

# [줄 125-132] main() - 비즈니스 로직
def main(req): ...

# [줄 138-189] Source Agent 시스템 메시지
def create_source_system_message(user_id: str): ...

# [줄 191-260] Source Agent
def create_source_agent(user_id: str): ...
def _source_graph_builder(user_id: str): ...

# [줄 262-280] Source 비즈니스 로직
def source_manager(user_id: str, message: str): ...

# [줄 286-438] Router Agent
class RouteDecision(BaseModel): ...
def create_router_agent(user_id: str): ...
def route_to_agent(state: UnifiedState) -> str: ...
def _unified_graph_builder(user_id: str): ...

# [줄 441-464] Unified 비즈니스 로직
def unified_agent(user_id: str, message: str): ...
```

#### 이동 계획

**1. Agent 클래스로 리팩토링**

```python
# application/agents/log_agent.py (새 파일)
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, HumanMessage
from infrastructure.llm.base import LLMProvider
from application.agents.tools.log_tools import (
    retriever_vectordb,
    maker_logfile
)

SYSTEM_MESSAGE = SystemMessage(content="""
당신은 개발자 일지 자동 생성 어시스턴트입니다.

작업 순서:
1️⃣ 데이터 검색 - retriever_vectordb 도구 호출
2️⃣ 일지 작성 - 검색 결과 기반 상세 일지 작성
3️⃣ 파일 저장 - maker_logfile 도구로 저장

중요: 플레이스홀더 금지! 검색 결과의 실제 내용을 사용하세요.
""")

class LogAgent:
    """일지 생성 Agent (LangGraph)"""

    def __init__(self, llm_provider: LLMProvider):
        """
        Args:
            llm_provider: LLM 구현 (의존성 주입)
        """
        self.llm = llm_provider
        self.tools = [retriever_vectordb, maker_logfile]
        self.llm_with_tools = llm_provider.bind_tools(self.tools)
        self._graph = self._build_graph()

    def _agent_node(self, state: MessagesState) -> dict:
        """Agent 노드 - LLM 호출 및 도구 결정"""
        messages = [SYSTEM_MESSAGE] + state["messages"]
        result = self.llm_with_tools.invoke(messages)

        print(f"[LogAgent] 응답:")
        print(f"  - Content: {result.content[:100] if result.content else 'None'}...")
        print(f"  - Tool calls: {bool(result.tool_calls) if hasattr(result, 'tool_calls') else False}")

        return {"messages": [result]}

    def _build_graph(self):
        """LangGraph 워크플로우 구축"""
        builder = StateGraph(MessagesState)
        tool_node = ToolNode(tools=self.tools)

        # 노드 추가
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", tool_node)

        # 엣지 추가
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            tools_condition,
            {
                "tools": "tools",
                "__end__": END
            }
        )
        builder.add_edge("tools", "agent")

        return builder.compile()

    async def run(self, message: str, thread_id: str) -> str:
        """
        Agent 실행

        Args:
            message: 사용자 메시지
            thread_id: 대화 스레드 ID

        Returns:
            Agent 응답 (일지 내용)
        """
        input_dict = {
            "messages": [HumanMessage(content=message)]
        }

        result = self._graph.invoke(input_dict)

        return result["messages"][-1].content if result.get("messages") else ""


# application/agents/source_agent.py (새 파일)
import re
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from infrastructure.llm.base import LLMProvider
from application.agents.tools.source_tools import (
    add_source_to_db,
    get_user_sources,
    delete_source_from_db
)

class SourceAgent:
    """소스 관리 Agent"""

    def __init__(self, user_id: str, llm_provider: LLMProvider):
        self.user_id = user_id
        self.llm = llm_provider
        self.tools = [
            add_source_to_db,
            get_user_sources,
            delete_source_from_db
        ]
        self.llm_with_tools = llm_provider.bind_tools(self.tools)
        self._graph = self._build_graph()

    def _create_system_message(self) -> SystemMessage:
        """사용자 ID가 포함된 시스템 메시지"""
        return SystemMessage(content=f"""
You are a source management assistant for user_id: {self.user_id}

🚨 ABSOLUTE RULES:

1. Git URL Detection (MANDATORY TOOL CALL)
   When user message contains:
   - github.com, gitlab.com, bitbucket.org
   - ends with .git

   👉 IMMEDIATELY call add_source_to_db:
   - user_id: "{self.user_id}"
   - name: Extract from URL
   - source_type: "git"
   - location: EXACT URL

2. Source List Request
   Keywords: "목록", "리스트", "list"
   👉 Call get_user_sources(user_id="{self.user_id}")

3. Delete Request
   Keywords: "삭제", "delete" + source ID
   👉 Call delete_source_from_db(source_id=<id>, user_id="{self.user_id}")

⚠️ NEVER explain - JUST CALL THE TOOL
""")

    def _agent_node(self, state: MessagesState) -> dict:
        """소스 관리 Agent 노드 (Git URL 강제 감지)"""
        system_message = self._create_system_message()
        messages = [system_message] + state["messages"]

        last_message = state["messages"][-1] if state["messages"] else None
        is_after_tool_execution = isinstance(last_message, ToolMessage)

        # Git URL 패턴 감지 (사용자 메시지만)
        has_git_url = False
        if isinstance(last_message, HumanMessage):
            git_url_pattern = r'(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+(?:\.git)?|.*\.git)'
            has_git_url = re.search(git_url_pattern, last_message.content, re.IGNORECASE)

        if has_git_url and not is_after_tool_execution:
            # Git URL 감지 시 add_source_to_db 강제 호출
            print(f"[SourceAgent] Git URL 감지! 도구 강제 호출")
            llm_forced = self.llm.bind_tools(
                self.tools,
                tool_choice="add_source_to_db"
            )
            result = llm_forced.invoke(messages)
        else:
            result = self.llm_with_tools.invoke(messages)

        return {"messages": [result]}

    def _build_graph(self):
        """Graph 빌더"""
        builder = StateGraph(MessagesState)
        tool_node = ToolNode(tools=self.tools)

        builder.add_node("source_agent", self._agent_node)
        builder.add_node("tools", tool_node)

        builder.add_edge(START, "source_agent")
        builder.add_conditional_edges(
            "source_agent",
            tools_condition,
            {"tools": "tools", "__end__": END}
        )
        builder.add_edge("tools", "source_agent")

        return builder.compile()

    async def run(self, message: str) -> str:
        """Agent 실행"""
        input_dict = {"messages": [HumanMessage(content=message)]}
        result = self._graph.invoke(input_dict)
        return result["messages"][-1].content if result.get("messages") else ""


# application/agents/router_agent.py (새 파일)
from typing import Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from infrastructure.llm.base import LLMProvider

class RouteDecision(BaseModel):
    """Router 판단 결과"""
    destination: Literal["source_management", "log_making"] = Field(
        description="'source_management' (소스 관리) 또는 'log_making' (일지 작성)"
    )
    reasoning: str = Field(description="선택 이유")

class UnifiedState(BaseModel):
    """Router State"""
    messages: list
    route_destination: str = ""

class RouterAgent:
    """요청 분석 후 적절한 Agent 선택"""

    def __init__(self, user_id: str, llm_provider: LLMProvider):
        self.user_id = user_id
        self.llm = llm_provider.with_structured_output(RouteDecision)

    def route(self, message: str) -> str:
        """
        메시지 분석 후 destination 반환

        Returns:
            "source_management" 또는 "log_making"
        """
        system_message = SystemMessage(content=f"""
당신은 사용자 요청을 분석하는 Router입니다.
현재 사용자 ID: {self.user_id}

다음 중 하나를 선택하세요:

1. source_management - 학습 소스 추가/조회/삭제
   예: "Git 저장소 추가", "소스 목록"

2. log_making - 일지 작성/조회
   예: "2026-07-20 일지 작성", "오늘 한 일"

핵심 의도를 파악하여 선택하세요.
""")

        decision = self.llm.invoke([
            system_message,
            HumanMessage(content=message)
        ])

        print(f"[Router] 메시지: {message[:50]}...")
        print(f"[Router] 선택: {decision.destination} ({decision.reasoning})")

        return decision.destination
```

**2. Service 클래스 추가**

```python
# application/services/log_service.py (새 파일)
import uuid
from domain.models.log import LogRequest, LogResponse
from application.agents.log_agent import LogAgent

class LogService:
    """일지 생성 비즈니스 로직"""

    def __init__(self, log_agent: LogAgent):
        self.log_agent = log_agent

    async def create_log(self, request: LogRequest) -> LogResponse:
        """
        일지 생성 Use Case

        비즈니스 규칙:
        - thread_id가 없으면 UUID 생성
        - Agent 실행 후 결과 반환
        """
        thread_id = request.thread_id or str(uuid.uuid4())

        content = await self.log_agent.run(
            message=request.message,
            thread_id=thread_id
        )

        return LogResponse(
            content=content,
            thread_id=thread_id
        )


# application/services/source_service.py (새 파일)
import os
import subprocess
import shutil
from domain.models.source import SourceSyncRequest, SourceSyncResponse
from application.agents.source_agent import SourceAgent
from infrastructure.vectordb.repository import VectorDBRepository

class SourceService:
    """소스 관리 비즈니스 로직"""

    def __init__(
        self,
        source_agent: SourceAgent,
        vectordb_repo: VectorDBRepository
    ):
        self.source_agent = source_agent
        self.vectordb_repo = vectordb_repo

    async def sync_repository(
        self,
        request: SourceSyncRequest
    ) -> SourceSyncResponse:
        """
        Git 저장소 동기화 Use Case

        흐름:
        1. Git clone (기존 디렉토리 삭제 후)
        2. 임베딩 (VectorDB Repository 사용)
        3. 결과 반환
        """
        user_dir = f"./repos/{request.user_id}"

        # 기존 디렉토리 삭제
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)

        try:
            # Git clone
            print(f"[SourceService] Cloning {request.repo_url}...")
            subprocess.run(
                [
                    "git", "clone",
                    "--branch", request.branch,
                    "--depth", "1",
                    str(request.repo_url),
                    user_dir
                ],
                check=True,
                capture_output=True,
                text=True
            )

            # 임베딩 (Repository 패턴 사용)
            embedding_result = await self.vectordb_repo.embed_documents(
                user_id=request.user_id,
                path=user_dir
            )

            return SourceSyncResponse(
                success=True,
                message="동기화 및 임베딩 완료",
                user_id=request.user_id,
                repo_url=str(request.repo_url),
                embedding_result=embedding_result
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return SourceSyncResponse(
                success=False,
                message=f"Git clone 실패: {error_msg}",
                user_id=request.user_id,
                repo_url=str(request.repo_url)
            )
        except Exception as e:
            return SourceSyncResponse(
                success=False,
                message=f"동기화 실패: {str(e)}",
                user_id=request.user_id,
                repo_url=str(request.repo_url)
            )

    async def manage_source(
        self,
        user_id: str,
        message: str
    ) -> str:
        """
        소스 관리 대화형 Use Case

        Agent를 통해 소스 추가/조회/삭제 처리
        """
        return await self.source_agent.run(message)
```

**변경 요약:**

| 항목 | 변경 전 | 변경 후 | 이유 |
|------|---------|---------|------|
| **파일 수** | 1개 (controller.py) | 6개 (Agent 3 + Service 3) | 단일 책임 |
| **코드 길이** | 465줄 | 각 50-150줄 | 가독성 |
| **구조** | 함수 기반 | 클래스 기반 | 의존성 주입 |
| **Graph** | 전역 변수 | 인스턴스 변수 | 테스트 가능 |
| **재사용** | 불가능 | 가능 (다른 프로젝트) | 확장성 |

---

### 3.3 tools.py (672줄) → 5개 파일

#### 현재 구조 분석

```python
# tools.py의 현재 내용
# [줄 1-146] 임베딩 도구 (파일 → ChromaDB)
@tool
def embedding_file(path: str) -> str: ...

# [줄 148-212] 벡터 검색 도구
@tool
def retriever_vectordb(date: str, reference_len: str) -> str: ...

# [줄 214-230] 일지 저장 도구
@tool
def maker_logfile(date: str, content: str) -> str: ...

# [줄 234-449] 사용자별 임베딩 함수 (Git 연동)
def embedding_file_for_user(user_id: str, path: str) -> str: ...

# [줄 454-583] Source 관리 도구들
@tool
def add_source_to_db(...) -> str: ...

@tool
def get_user_sources(user_id: str) -> str: ...

@tool
def delete_source_from_db(...) -> str: ...
```

#### 이동 계획

**1. Agent 도구 분리**

```python
# application/agents/tools/log_tools.py (새 파일)
from langchain_core.tools import tool
from infrastructure.vectordb.repository import VectorDBRepository
from datetime import datetime
import os

# Repository 인스턴스 (의존성 주입 예정)
_vectordb_repo: VectorDBRepository = None

def set_vectordb_repo(repo: VectorDBRepository):
    """Repository 주입 (초기화 시 호출)"""
    global _vectordb_repo
    _vectordb_repo = repo

@tool
def retriever_vectordb(date: str, reference_len: str = "5") -> str:
    """
    날짜별 문서 검색 도구

    이 도구는 사용자가 요청한 날짜(2026-07-09, 05월 13일 등)와 관련된
    문서를 ChromaDB에서 검색합니다.

    Args:
        date: 날짜 (YYYY-MM-DD, YYYY_MM_DD, MM월 DD일 등)
        reference_len: 참조 문서 수 (기본값: 5)

    Returns:
        검색된 문서 내용 (텍스트)
    """
    if not _vectordb_repo:
        return "❌ VectorDB Repository가 초기화되지 않았습니다"

    try:
        k = int(reference_len) if reference_len else 5
        docs = _vectordb_repo.search_by_date(date, k=k)

        if not docs:
            return f"'{date}' 날짜와 관련된 기록을 찾을 수 없습니다."

        result_text = f"'{date}' 날짜 관련 검색 결과 ({len(docs)}개 문서):\n\n"
        for i, doc in enumerate(docs, 1):
            result_text += f"--- 문서 {i} ---\n"
            result_text += f"날짜: {doc.metadata.get('date', '정보 없음')}\n"
            result_text += f"출처: {doc.metadata.get('source', 'unknown')}\n"
            result_text += f"내용:\n{doc.page_content}\n\n"

        return result_text

    except Exception as e:
        return f"❌ 검색 실패: {str(e)}"

@tool
def maker_logfile(date: str, content: str) -> str:
    """
    일지를 마크다운 파일로 저장합니다.

    Args:
        date: 날짜 (YYYY-MM-DD 형식)
        content: 일지 내용 (마크다운)

    Returns:
        저장 완료 메시지
    """
    try:
        os.makedirs("logs", exist_ok=True)
        filename = f"logs/{date.replace('-', '.')}_log.md"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"✅ 일지 저장 완료: {filename}"

    except Exception as e:
        return f"❌ 저장 실패: {str(e)}"


# application/agents/tools/source_tools.py (새 파일)
from langchain_core.tools import tool
from infrastructure.storage.database import SessionLocal
from infrastructure.storage.models import Source, SourceType
from infrastructure.vectordb.repository import VectorDBRepository
from datetime import datetime
import subprocess
import shutil
import os

# Repository 인스턴스 (의존성 주입)
_vectordb_repo: VectorDBRepository = None

def set_vectordb_repo(repo: VectorDBRepository):
    global _vectordb_repo
    _vectordb_repo = repo

@tool
def add_source_to_db(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    학습 소스 추가 (Git 저장소 자동 클론 + 임베딩)

    Git URL을 받으면:
    1. 자동 git clone
    2. 파일 임베딩 (VectorDB 저장)
    3. DB에 소스 정보 저장

    Args:
        user_id: 사용자 ID
        name: 소스 이름
        source_type: "git" 또는 "local_til"
        location: Git URL 또는 로컬 경로
    """
    db = SessionLocal()

    try:
        # 소스 타입 변환
        type_mapping = {
            "git": SourceType.GIT,
            "local_til": SourceType.LOCAL_TIL,
        }

        if source_type.lower() not in type_mapping:
            return f"❌ 잘못된 소스 타입: {source_type}"

        # 중복 체크
        existing = db.query(Source).filter(
            Source.user_id == user_id,
            Source.type == type_mapping[source_type.lower()],
            Source.location == location
        ).first()

        if existing:
            return f"⚠️ 이미 등록된 소스: {existing.name}"

        # DB에 소스 저장
        new_source = Source(
            user_id=user_id,
            name=name,
            type=type_mapping[source_type.lower()],
            location=location,
            last_synced_at=datetime.now(),
            is_active=True
        )

        db.add(new_source)
        db.commit()
        db.refresh(new_source)

        # Git인 경우 클론 + 임베딩
        if source_type.lower() == "git":
            try:
                user_dir = f"./repos/{user_id}"
                repo_name = location.rstrip('/').split('/')[-1].replace('.git', '')
                local_path = f"{user_dir}/{repo_name}"

                if os.path.exists(local_path):
                    shutil.rmtree(local_path)

                os.makedirs(user_dir, exist_ok=True)

                # Git clone
                subprocess.run(
                    ["git", "clone", "--depth", "1", location, local_path],
                    check=True,
                    capture_output=True
                )

                # 임베딩 (Repository 사용)
                if _vectordb_repo:
                    result = await _vectordb_repo.embed_documents(
                        user_id=user_id,
                        path=local_path
                    )
                    return f"✅ Git 저장소 추가 및 임베딩 완료!\n{result}"
                else:
                    return "⚠️ 저장소는 추가되었지만 임베딩 실패 (Repository 미초기화)"

            except Exception as e:
                return f"⚠️ 저장소 추가됨 (임베딩 실패: {str(e)})"

        return f"✅ 소스 추가 완료: {name}"

    except Exception as e:
        db.rollback()
        return f"❌ 실패: {str(e)}"
    finally:
        db.close()

@tool
def get_user_sources(user_id: str) -> str:
    """사용자의 등록된 소스 목록 조회"""
    db = SessionLocal()
    try:
        sources = db.query(Source).filter(
            Source.user_id == user_id,
            Source.is_active == True
        ).all()

        if not sources:
            return f"📭 '{user_id}' 사용자의 소스가 없습니다"

        result = f"📚 '{user_id}' 등록 소스 ({len(sources)}개):\n\n"
        for idx, source in enumerate(sources, 1):
            result += f"{idx}. {source.name}\n"
            result += f"   - 타입: {source.type.value}\n"
            result += f"   - 위치: {source.location}\n"
            result += f"   - ID: {source.id}\n\n"

        return result

    except Exception as e:
        return f"❌ 조회 실패: {str(e)}"
    finally:
        db.close()

@tool
def delete_source_from_db(source_id: int, user_id: str) -> str:
    """등록된 소스 삭제"""
    db = SessionLocal()
    try:
        source = db.query(Source).filter(
            Source.id == source_id,
            Source.user_id == user_id
        ).first()

        if not source:
            return f"❌ 소스를 찾을 수 없음 (ID: {source_id})"

        source_name = source.name
        db.delete(source)
        db.commit()

        return f"✅ 소스 삭제 완료: {source_name}"

    except Exception as e:
        db.rollback()
        return f"❌ 삭제 실패: {str(e)}"
    finally:
        db.close()
```

**2. Repository 패턴 적용**

```python
# infrastructure/vectordb/repository.py (새 파일)
from typing import List, Optional
from langchain_core.documents import Document
from langchain_chroma import Chroma
from infrastructure.vectordb.chroma_client import get_chroma_client
from infrastructure.vectordb.embedder import get_embedding_function
from infrastructure.llm.factory import LLMFactory
import hashlib
import re

class VectorDBRepository:
    """
    VectorDB 접근 추상화 (Repository Pattern)

    ChromaDB 구현 세부사항을 숨기고,
    비즈니스 로직에 필요한 메서드만 노출
    """

    def __init__(self):
        self.client = get_chroma_client()
        self.embedding_function = get_embedding_function()

    async def embed_documents(
        self,
        user_id: str,
        path: str
    ) -> str:
        """
        파일을 임베딩하여 사용자별 컬렉션에 저장

        Args:
            user_id: 사용자 ID
            path: 임베딩할 디렉토리 경로

        Returns:
            임베딩 결과 메시지
        """
        from langchain_community.document_loaders import DirectoryLoader, TextLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        all_docs = []

        # 텍스트 파일 로드
        for pattern in ["**/*.md", "**/*.txt"]:
            loader = DirectoryLoader(
                path=path,
                glob=pattern,
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"}
            )
            docs = loader.load()

            # 파일명에서 날짜 추출
            for doc in docs:
                source = doc.metadata.get("source", "")
                date_patterns = [
                    r'(\d{4})[_-](\d{1,2})[_-](\d{1,2})',
                    r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
                ]

                for pattern_regex in date_patterns:
                    match = re.search(pattern_regex, source)
                    if match:
                        year, month, day = match.groups()
                        date_str = f"{year}년 {int(month)}월 {int(day)}일"
                        doc.metadata["date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        doc.page_content = f"작성 날짜: {date_str}\n\n{doc.page_content}"
                        break

            all_docs.extend(docs)

        # 빈 문서 필터링
        non_empty_docs = [doc for doc in all_docs if doc.page_content.strip()]

        if not non_empty_docs:
            return f"❌ {user_id}: 임베딩할 문서 없음"

        # 청킹 (토큰 제한 대응)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )

        chunked_docs = []
        for doc in non_empty_docs:
            if len(doc.page_content) > 1500:
                chunks = text_splitter.split_documents([doc])
                # 메타데이터 복사
                for chunk in chunks:
                    chunk.metadata.update({
                        "source": doc.metadata.get("source"),
                        "date": doc.metadata.get("date"),
                    })
                chunked_docs.extend(chunks)
            else:
                chunked_docs.append(doc)

        # 컬렉션 가져오기
        collection_name = f"user_{user_id}"
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding_function,
            client=self.client
        )

        # 중복 방지: 변경된 파일만 임베딩
        try:
            existing_data = vectorstore.get(include=["metadatas"])
            existing_hashes = {
                meta.get("source"): meta.get("content_hash")
                for meta in existing_data.get("metadatas", [])
                if meta.get("content_hash")
            }
        except:
            existing_hashes = {}

        new_chunks = []
        skipped_count = 0

        for doc in chunked_docs:
            source = doc.metadata.get("source", "")
            content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
            doc.metadata["content_hash"] = content_hash

            if source in existing_hashes and existing_hashes[source] == content_hash:
                skipped_count += 1
                continue

            new_chunks.append(doc)

        if not new_chunks:
            return f"✅ {user_id}: 변경 없음 (임베딩 스킵)"

        # ID 생성
        ids = []
        for doc in new_chunks:
            unique_str = f"{user_id}_{doc.metadata.get('source')}_{doc.metadata.get('content_hash')}"
            ids.append(hashlib.md5(unique_str.encode()).hexdigest())

        # 배치 저장
        batch_size = 100
        for i in range(0, len(new_chunks), batch_size):
            batch_docs = new_chunks[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            vectorstore.add_documents(batch_docs, ids=batch_ids)

        return f"✅ {user_id}: {len(non_empty_docs)}개 문서 → {len(new_chunks)}개 신규 임베딩 (스킵: {skipped_count})"

    def search_by_date(
        self,
        date: str,
        k: int = 5,
        user_id: str = "hrun"  # TODO: 현재 하드코딩, 나중에 제거
    ) -> List[Document]:
        """
        날짜별 문서 검색

        Args:
            date: 날짜 문자열
            k: 반환 문서 수
            user_id: 사용자 ID

        Returns:
            검색된 Document 리스트
        """
        collection_name = f"user_{user_id}"

        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding_function,
            client=self.client
        )

        # 날짜 정규화
        date_normalized = re.sub(r'\D', '', date)
        if len(date_normalized) >= 8:
            date_filter = f"{date_normalized[:4]}-{date_normalized[4:6]}-{date_normalized[6:8]}"
        else:
            date_filter = date

        # 메타데이터 필터 검색
        try:
            result = vectorstore.get(where={"date": date_filter}, limit=k)
            if result and result.get('documents'):
                docs = [
                    Document(
                        page_content=content,
                        metadata=metadata
                    )
                    for content, metadata in zip(result['documents'], result['metadatas'])
                ]
                return docs
        except:
            pass

        # 유사도 검색 (폴백)
        return vectorstore.similarity_search(f"작성 날짜: {date}", k=k)


# infrastructure/vectordb/chroma_client.py (새 파일)
import os
import chromadb
from chromadb.config import Settings

def get_chroma_client():
    """ChromaDB 클라이언트 싱글톤"""
    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8001"))

    try:
        # 서버 모드
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False)
        )
        client.heartbeat()
        print(f"[ChromaDB] ✅ 서버 연결: {host}:{port}")
        return client
    except Exception as e:
        # 로컬 모드 폴백
        print(f"[ChromaDB] ⚠️ 서버 연결 실패, 로컬 모드 전환")
        return chromadb.PersistentClient(path="./chroma_db")


# infrastructure/vectordb/embedder.py (새 파일)
import os
from dotenv import load_dotenv

load_dotenv()

def get_embedding_function():
    """임베딩 함수 싱글톤"""
    mode = os.getenv("EMBEDDING_MODE", "google")

    if mode == "local":
        from langchain_huggingface import HuggingFaceEmbeddings
        print("[Embedding] 🖥️ 로컬 모델 (메모리: ~6GB)")
        return HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    else:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        print("[Embedding] ☁️ Google Gemini API (메모리: 0MB)")
        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
```

**변경 요약:**

| 항목 | 변경 전 | 변경 후 | 이유 |
|------|---------|---------|------|
| **파일 수** | 1개 (tools.py) | 5개 (도구 2 + Repository 3) | 단일 책임 |
| **코드 길이** | 672줄 | 각 50-200줄 | 가독성 |
| **테스트** | 불가능 (ChromaDB 직접 의존) | 가능 (Repository Mock) | 테스트 가능성 |
| **확장성** | 낮음 (Chroma 교체 어려움) | 높음 (Repository만 교체) | 확장성 |

---

### 3.4 llm_router.py (80줄) → Factory Pattern

#### 현재 문제

```python
# llm_router.py - 전역 변수 의존
google_embedding = GoogleGenerativeAIEmbeddings(...)
google_llm = ChatGoogleGenerativeAI(...)
codex_llm = ChatCodexOAuth(...)
anthropic_llm = ChatAnthropic(...)

# 모든 파일에서 import
from src.llm_router import anthropic_llm, google_llm, embedding_function
```

**문제점:**
- 전역 변수 → 테스트 어려움 (Mock 불가능)
- 초기화 시점 제어 불가
- 환경별 설정 변경 어려움

#### Factory Pattern 적용

```python
# infrastructure/llm/base.py (새 파일)
from abc import ABC, abstractmethod
from typing import List, Any

class LLMProvider(ABC):
    """LLM 추상 인터페이스"""

    @abstractmethod
    def invoke(self, messages: List[Any]) -> Any:
        """메시지 전송"""
        pass

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> 'LLMProvider':
        """도구 바인딩"""
        pass

    @abstractmethod
    def with_structured_output(self, schema: Any) -> 'LLMProvider':
        """구조화된 출력"""
        pass


# infrastructure/llm/providers/claude_provider.py (새 파일)
from langchain_anthropic import ChatAnthropic
from infrastructure.llm.base import LLMProvider

class ClaudeProvider(LLMProvider):
    """Claude API 구현"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        self._client = ChatAnthropic(
            model=model,
            anthropic_api_key=api_key
        )

    def invoke(self, messages):
        return self._client.invoke(messages)

    def bind_tools(self, tools):
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema):
        self._client = self._client.with_structured_output(schema)
        return self


# infrastructure/llm/providers/gemini_provider.py (새 파일)
from langchain_google_genai import ChatGoogleGenerativeAI
from infrastructure.llm.base import LLMProvider

class GeminiProvider(LLMProvider):
    """Google Gemini API 구현"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        self._client = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key
        )

    def invoke(self, messages):
        return self._client.invoke(messages)

    def bind_tools(self, tools):
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema):
        self._client = self._client.with_structured_output(schema)
        return self


# infrastructure/llm/providers/codex_provider.py (새 파일)
from langchain_codex_oauth import ChatCodexOAuth
from infrastructure.llm.base import LLMProvider

class CodexProvider(LLMProvider):
    """Codex OAuth 구현"""

    def __init__(self, model: str = "gpt-5.4-mini"):
        self._client = ChatCodexOAuth(model=model)

    def invoke(self, messages):
        return self._client.invoke(messages)

    def bind_tools(self, tools):
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema):
        raise NotImplementedError("Codex does not support structured output")


# infrastructure/llm/factory.py (새 파일)
import os
from typing import Dict
from dotenv import load_dotenv
from infrastructure.llm.base import LLMProvider
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.providers.codex_provider import CodexProvider

load_dotenv()

class LLMFactory:
    """
    LLM Provider Factory (Singleton)

    환경변수에서 API 키를 읽어 LLM 인스턴스 생성
    """
    _instance = None
    _providers: Dict[str, LLMProvider] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_llm(self, provider_name: str) -> LLMProvider:
        """
        LLM Provider 가져오기 (캐싱)

        Args:
            provider_name: "claude", "gemini", "codex"

        Returns:
            LLMProvider 인스턴스
        """
        if provider_name in self._providers:
            return self._providers[provider_name]

        if provider_name == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found")
            self._providers["claude"] = ClaudeProvider(api_key)

        elif provider_name == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found")
            self._providers["gemini"] = GeminiProvider(api_key)

        elif provider_name == "codex":
            self._providers["codex"] = CodexProvider()

        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        return self._providers[provider_name]

    def set_provider(self, name: str, provider: LLMProvider):
        """테스트용: Provider 주입"""
        self._providers[name] = provider
```

**사용 예시:**

```python
# Before (전역 변수)
from src.llm_router import anthropic_llm

llm_with_tools = anthropic_llm.bind_tools(tools)

# After (Factory Pattern)
from infrastructure.llm.factory import LLMFactory

llm_factory = LLMFactory()
claude = llm_factory.get_llm("claude")
llm_with_tools = claude.bind_tools(tools)
```

**변경 요약:**

| 항목 | 변경 전 | 변경 후 | 이유 |
|------|---------|---------|------|
| **구조** | 전역 변수 | Factory Pattern | 의존성 주입 |
| **테스트** | Mock 불가능 | Mock 가능 | 테스트 가능 |
| **확장** | LLM 추가 시 모든 파일 수정 | Factory만 수정 | 확장성 |
| **초기화** | import 시점 (제어 불가) | 필요 시점 (지연 로딩) | 성능 |

---

## 4. 적용할 디자인 패턴

### 4.1 Factory Pattern (LLM 생성)

**적용 위치**: `infrastructure/llm/factory.py`

**목적:**
- LLM 인스턴스 생성 로직 캡슐화
- Provider 교체 시 수정 범위 최소화

**예시:**
```python
# 단일 진입점
llm_factory = LLMFactory()

# Claude로 일지 Agent
log_agent = LogAgent(llm_factory.get_llm("claude"))

# Gemini로 소스 Agent
source_agent = SourceAgent(user_id, llm_factory.get_llm("gemini"))
```

### 4.2 Repository Pattern (VectorDB 접근)

**적용 위치**: `infrastructure/vectordb/repository.py`

**목적:**
- DB 접근 로직 추상화
- ChromaDB → Pinecone 등 교체 시 Application 계층 수정 불필요

**인터페이스:**
```python
class VectorDBRepository:
    async def embed_documents(user_id: str, path: str) -> str
    def search_by_date(date: str, k: int, user_id: str) -> List[Document]
```

### 4.3 Dependency Injection (의존성 주입)

**적용 위치**: 모든 계층

**목적:**
- 클래스 간 결합도 감소
- 테스트 시 Mock 객체 주입 가능

**예시:**
```python
# Service는 Agent를 주입받음
class LogService:
    def __init__(self, log_agent: LogAgent):
        self.log_agent = log_agent

# Agent는 LLM Provider를 주입받음
class LogAgent:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

# FastAPI에서 의존성 주입
def get_log_service() -> LogService:
    llm_factory = LLMFactory()
    log_agent = LogAgent(llm_factory.get_llm("claude"))
    return LogService(log_agent)

@router.post("/logs")
async def create_log(
    request: LogRequest,
    service: LogService = Depends(get_log_service)  # 주입!
):
    return await service.create_log(request)
```

### 4.4 Strategy Pattern (임베딩 모드)

**적용 위치**: `infrastructure/vectordb/embedder.py`

**목적:**
- 로컬/API 임베딩 전략 런타임 교체

**예시:**
```python
# 환경변수로 전략 선택
EMBEDDING_MODE=google  # 또는 local

def get_embedding_function():
    mode = os.getenv("EMBEDDING_MODE", "google")

    if mode == "local":
        return HuggingFaceEmbeddings(...)  # Strategy A
    else:
        return GoogleGenerativeAIEmbeddings(...)  # Strategy B
```

---

## 5. 타입 안정성 강화

### 5.1 Pydantic 모델 확장

**현재:**
```python
class QueryReq(BaseModel):
    req: str
    thread_id: str
```

**개선:**
```python
from pydantic import BaseModel, Field, validator
from typing import Optional

class LogRequest(BaseModel):
    """일지 생성 요청 (도메인 모델)"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="사용자 메시지"
    )
    thread_id: Optional[str] = Field(
        None,
        description="대화 스레드 ID (UUID 형식)"
    )

    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError("메시지는 공백일 수 없습니다")
        return v

    @validator('thread_id')
    def validate_thread_id(cls, v):
        if v is not None:
            import uuid
            try:
                uuid.UUID(v)
            except ValueError:
                raise ValueError("thread_id는 UUID 형식이어야 합니다")
        return v
```

### 5.2 Type Hints 추가

**현재:**
```python
def main(req):
    input_dict = {"messages": [HumanMessage(content=req.req)]}
    res = graph.invoke(input_dict)
    return res["messages"][-1].content
```

**개선:**
```python
from typing import Dict, Any, Optional

async def create_log(
    request: LogRequest
) -> LogResponse:
    """
    일지 생성 Use Case

    Args:
        request: 일지 생성 요청 (Pydantic 모델)

    Returns:
        LogResponse: 일지 내용 및 thread_id

    Raises:
        ValueError: 요청 데이터가 유효하지 않을 때
    """
    thread_id: str = request.thread_id or str(uuid.uuid4())

    content: str = await self.log_agent.run(
        message=request.message,
        thread_id=thread_id
    )

    return LogResponse(
        content=content,
        thread_id=thread_id
    )
```

### 5.3 mypy 적용

**설정 파일:**
```ini
# mypy.ini (새 파일)
[mypy]
python_version = 3.12
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_any_generics = True

[mypy-langchain.*]
ignore_missing_imports = True

[mypy-chromadb.*]
ignore_missing_imports = True
```

**실행:**
```bash
# 타입 체크
mypy src/

# CI/CD에 추가
pytest && mypy src/
```

---

## 6. 테스트 전략

### 6.1 테스트 디렉토리 구조

```
tests/
├── unit/                      # 단위 테스트
│   ├── domain/
│   │   └── test_models.py     # Pydantic 모델 validation
│   ├── application/
│   │   ├── test_log_service.py
│   │   └── test_source_service.py
│   └── infrastructure/
│       ├── test_llm_factory.py
│       └── test_vectordb_repo.py
│
├── integration/               # 통합 테스트
│   ├── test_log_api.py        # API 엔드포인트
│   └── test_source_api.py
│
└── conftest.py                # pytest fixtures
```

### 6.2 Unit Test 예시

```python
# tests/unit/domain/test_models.py
import pytest
from domain.models.log import LogRequest, LogResponse

def test_log_request_validation():
    """LogRequest Pydantic validation 테스트"""
    # 정상 케이스
    request = LogRequest(
        message="2026-07-20 일지 작성해줘",
        thread_id=None
    )
    assert request.message == "2026-07-20 일지 작성해줘"

    # 빈 메시지 거부
    with pytest.raises(ValueError, match="비어있을 수 없습니다"):
        LogRequest(message="   ", thread_id=None)


# tests/unit/application/test_log_service.py
from unittest.mock import AsyncMock, Mock
from application.services.log_service import LogService
from application.agents.log_agent import LogAgent
from domain.models.log import LogRequest, LogResponse

@pytest.mark.asyncio
async def test_create_log_generates_thread_id():
    """thread_id가 없으면 자동 생성"""
    # Mock Agent
    mock_agent = AsyncMock(spec=LogAgent)
    mock_agent.run.return_value = "일지 내용"

    # Service 생성 (의존성 주입)
    service = LogService(log_agent=mock_agent)

    # 실행
    request = LogRequest(message="테스트", thread_id=None)
    response = await service.create_log(request)

    # 검증
    assert response.content == "일지 내용"
    assert response.thread_id is not None  # UUID 생성됨
    mock_agent.run.assert_called_once()


# tests/unit/infrastructure/test_llm_factory.py
from infrastructure.llm.factory import LLMFactory
from infrastructure.llm.providers.claude_provider import ClaudeProvider

def test_factory_caches_providers():
    """Factory가 Provider를 캐싱하는지 확인"""
    factory = LLMFactory()

    claude1 = factory.get_llm("claude")
    claude2 = factory.get_llm("claude")

    # 동일한 인스턴스 반환 (캐싱됨)
    assert claude1 is claude2


def test_factory_raises_on_unknown_provider():
    """존재하지 않는 Provider 요청 시 에러"""
    factory = LLMFactory()

    with pytest.raises(ValueError, match="Unknown provider"):
        factory.get_llm("unknown")
```

### 6.3 Integration Test 예시

```python
# tests/integration/test_log_api.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_log_endpoint():
    """일지 생성 API 통합 테스트"""
    response = client.post(
        "/logs",
        json={
            "message": "2026-07-20 일지 작성해줘",
            "thread_id": None
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "thread_id" in data
```

### 6.4 pytest Fixtures

```python
# tests/conftest.py
import pytest
from infrastructure.llm.factory import LLMFactory
from infrastructure.llm.base import LLMProvider
from unittest.mock import Mock

@pytest.fixture
def mock_llm_provider():
    """Mock LLM Provider"""
    mock = Mock(spec=LLMProvider)
    mock.invoke.return_value = Mock(content="테스트 응답")
    return mock

@pytest.fixture
def llm_factory_with_mock(mock_llm_provider):
    """Mock Provider가 주입된 Factory"""
    factory = LLMFactory()
    factory.set_provider("test", mock_llm_provider)
    return factory
```

---

## 7. 마이그레이션 계획

### 7.1 단계별 리팩토링 (5단계)

**원칙:** 기존 코드를 유지하면서 점진적으로 리팩토링

#### Phase 1: 인프라 계층 (1주)

**목표:** 외부 의존성 분리

**작업:**
1. `infrastructure/llm/` 생성
   - Factory Pattern 구현
   - Provider 클래스들 생성
2. `infrastructure/vectordb/` 생성
   - Repository Pattern 구현
   - ChromaDB 클라이언트 분리
3. `storage/` → `infrastructure/storage/` 이동

**테스트:**
- LLM Factory 단위 테스트
- VectorDB Repository Mock 테스트

**커밋:**
```bash
git commit -m "feat: Add LLM Factory and VectorDB Repository

- Implement Factory Pattern for LLM providers
- Add Repository Pattern for VectorDB access
- Move storage to infrastructure layer"
```

#### Phase 2: 도메인 계층 (3일)

**목표:** 비즈니스 규칙 분리

**작업:**
1. `domain/models/` 생성
   - `router.py`의 Pydantic 모델 이동
   - Validation 로직 추가
2. Type Hints 강화

**테스트:**
- 도메인 모델 Validation 테스트

**커밋:**
```bash
git commit -m "feat: Extract domain models from router

- Move Pydantic models to domain/models/
- Add field validation and constraints
- Improve type hints"
```

#### Phase 3: 응용 계층 (1주)

**목표:** Agent 및 Service 클래스화

**작업:**
1. `application/agents/` 생성
   - `controller.py`의 Agent 함수 → 클래스로 변환
2. `application/services/` 생성
   - Service 클래스 생성 (의존성 주입)
3. `application/agents/tools/` 생성
   - `tools.py` → log_tools.py, source_tools.py 분리

**테스트:**
- Agent Mock 테스트
- Service 단위 테스트

**커밋:**
```bash
git commit -m "refactor: Convert Agents and Services to classes

- Transform agent functions to LogAgent, SourceAgent classes
- Create Service layer with dependency injection
- Split tools.py into domain-specific tool modules"
```

#### Phase 4: 표현 계층 (3일)

**목표:** API 라우트 분리

**작업:**
1. `presentation/api/routes/` 생성
   - `router.py` → auth_routes.py, log_routes.py, source_routes.py 분리
2. 의존성 주입 설정
3. `main.py` 수정 (새 라우터 import)

**테스트:**
- API 통합 테스트
- E2E 테스트

**커밋:**
```bash
git commit -m "refactor: Split router into domain-specific routes

- Create auth_routes, log_routes, source_routes
- Implement FastAPI dependency injection
- Update main.py with new router structure"
```

#### Phase 5: 레거시 제거 (2일)

**목표:** 기존 파일 삭제 및 정리

**작업:**
1. `router.py` 삭제
2. `controller.py` 삭제
3. `tools.py` 삭제
4. `llm_router.py` 삭제
5. 문서 업데이트 (README, ARCHITECTURE.md)

**테스트:**
- 전체 테스트 스위트 실행
- 수동 QA

**커밋:**
```bash
git commit -m "chore: Remove legacy files after refactoring

- Delete router.py, controller.py, tools.py, llm_router.py
- Update documentation to reflect new architecture
- All tests passing ✅"
```

### 7.2 타임라인

```
Week 1: Phase 1 (Infrastructure)
Week 2: Phase 2 (Domain) + Phase 3 (Application)
Week 3: Phase 4 (Presentation) + Phase 5 (Cleanup)
```

### 7.3 롤백 전략

**각 Phase마다:**
1. Git branch 생성 (`refactor/phase-1` 등)
2. Phase 완료 후 main에 merge
3. 문제 발생 시 `git revert` 로 이전 상태 복구

**안전장치:**
- 각 Phase 끝에 전체 테스트 실행
- Phase 1-2는 기존 코드 유지하면서 새 코드 추가
- Phase 3부터 기존 코드를 새 코드로 교체
- Phase 5에서만 기존 코드 삭제

---

## 8. 기대 효과

### 8.1 코드 품질

| 지표 | 현재 | 리팩토링 후 |
|------|------|-------------|
| **파일당 평균 줄 수** | 340줄 (router: 286, controller: 465, tools: 672) | 80줄 |
| **순환 복잡도** | 높음 (함수 내 많은 분기) | 낮음 (클래스/메서드로 분산) |
| **테스트 커버리지** | 0% | 80%+ (목표) |
| **타입 안정성** | mypy 미사용 | mypy strict 모드 통과 |

### 8.2 개발 생산성

**Before:**
```
새 LLM (GPT-5) 추가 시:
1. llm_router.py 수정 (전역 변수 추가)
2. controller.py 수정 (각 Agent에서 import)
3. 모든 Agent 테스트 (의존성 변경)
→ 30-40분 소요, 버그 위험 높음
```

**After:**
```
새 LLM (GPT-5) 추가 시:
1. infrastructure/llm/providers/gpt5_provider.py 생성
2. factory.py에 케이스 추가 (5줄)
→ 5-10분 소요, 기존 코드 영향 없음
```

### 8.3 학습 가치

**습득 가능한 개념:**
- Clean Architecture
- SOLID 원칙 (특히 S, D)
- Design Patterns (Factory, Repository, Dependency Injection)
- Type Safety (Pydantic, mypy)
- Test-Driven Development

---

## 9. 참고 자료

**Clean Architecture:**
- [The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Python Clean Architecture Example](https://github.com/cosmic-python/code)

**Design Patterns:**
- [Refactoring Guru - Factory Pattern](https://refactoring.guru/design-patterns/factory-method)
- [Martin Fowler - Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)

**FastAPI Best Practices:**
- [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)

---

## 10. 체크리스트

리팩토링 완료 조건:

- [ ] Phase 1: Infrastructure 계층 완료
  - [ ] LLM Factory 구현
  - [ ] VectorDB Repository 구현
  - [ ] 단위 테스트 통과
- [ ] Phase 2: Domain 계층 완료
  - [ ] Pydantic 모델 분리
  - [ ] Validation 추가
  - [ ] 도메인 테스트 통과
- [ ] Phase 3: Application 계층 완료
  - [ ] Agent 클래스 변환
  - [ ] Service 클래스 생성
  - [ ] 의존성 주입 구현
- [ ] Phase 4: Presentation 계층 완료
  - [ ] 라우터 분리
  - [ ] API 통합 테스트 통과
- [ ] Phase 5: 레거시 제거
  - [ ] 기존 파일 삭제
  - [ ] 문서 업데이트
  - [ ] 전체 테스트 스위트 통과
- [ ] mypy strict 모드 통과
- [ ] 테스트 커버리지 80% 이상
- [ ] README 및 ARCHITECTURE.md 업데이트

---

**End of Document**
