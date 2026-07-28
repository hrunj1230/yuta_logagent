# Unified Agent 설계 문서

**작성일:** 2026-07-28
**목적:** Source 관리 도구(source.py + embedding.py)를 호출하는 통합 Agent 구현

---

## 개요

work.md 기반으로 생성된 Source 관리 도구들을 효율적으로 활용하기 위한 두 가지 Agent 구조를 설계합니다:

1. **Router 방식** (`unified_controller_router.py`) - 요청을 분석하여 적절한 Sub-Agent로 라우팅
2. **단일 Agent 방식** (`unified_controller_single.py`) - 하나의 Agent가 모든 도구 처리

---

## 사용 도구 (6개 + 1개 통합 도구)

### Source 관리 도구 (tools/source.py)
1. `add_source_to_db` - 소스 DB 등록
2. `get_user_sources` - 소스 목록 조회
3. `delete_source_from_db` - 소스 삭제
4. `request_source_type_clarification` - 타입 확인 요청

### Embedding 관리 도구 (tools/embedding.py)
5. `embed_source` - 임베딩 실행
6. `get_embedding_status` - 임베딩 상태 조회

### 통합 도구 (Router 방식용)
7. `add_source_and_embed` - 소스 추가 + 임베딩 자동 시작

---

## 설계 1: Router 방식

### 아키텍처

```
사용자 요청
    ↓
Router Agent (요청 분석)
    ↓
┌───────────────────────┐
│ Conditional Edge      │
│ (route_to_agent)      │
└───────────────────────┘
    ↓              ↓
Source Agent   Embedding Agent
(CRUD 작업)    (실행/조회)
    ↓              ↓
  END            END
```

### 컴포넌트

#### 1. UnifiedState (TypedDict)
```python
class UnifiedState(TypedDict):
    messages: Annotated[list, add_messages]
    route_destination: str  # "source_management" | "embedding_execution"
```

#### 2. RouteDecision (Pydantic)
```python
class RouteDecision(BaseModel):
    destination: Literal["source_management", "embedding_execution"]
    reasoning: str
```

#### 3. Router Agent
- **LLM:** Gemini Flash + structured output
- **역할:** 사용자 요청 분석 → RouteDecision 생성
- **시스템 메시지:** user_id 포함, 명확한 라우팅 기준 제시

#### 4. Source Agent
- **LLM:** Gemini Flash
- **도구:**
  - `add_source_and_embed` (통합 도구)
  - `get_user_sources`
  - `delete_source_from_db`
  - `request_source_type_clarification`
- **역할:** Source CRUD + 자동 임베딩 시작

#### 5. Embedding Agent
- **LLM:** Anthropic Sonnet
- **도구:**
  - `embed_source` (수동 임베딩 시작)
  - `get_embedding_status`
- **역할:** 임베딩 상태 조회, 수동 재시작

#### 6. Checkpointer (대화 기록 유지)
- **타입:** InMemorySaver (langgraph.checkpoint.memory)
- **역할:** 사용자별 대화 히스토리 저장
- **thread_id:** user_id 사용 (사용자별 독립된 대화 세션)

### 데이터 플로우

```
1. 사용자 요청
   └─ unified_agent(user_id, message)

2. Config 설정 (대화 세션 유지)
   └─ config = {"configurable": {"thread_id": user_id}}

3. UnifiedState 초기화
   └─ {"messages": [...], "route_destination": ""}

4. Router Agent
   └─ Gemini Flash 호출
   └─ RouteDecision 생성
   └─ State 업데이트

5. Conditional Edge
   └─ route_destination 확인
   ├─ "source_management" → Source Agent
   └─ "embedding_execution" → Embedding Agent

6. Sub-Agent 실행
   └─ 도구 선택 및 실행
   └─ Tool Node → Agent 재실행
   └─ END

7. Checkpoint 저장
   └─ 대화 기록이 thread_id별로 자동 저장

8. 최종 응답
   └─ messages[-1].content
```

### 라우팅 예시

| 사용자 요청 | Router 판단 | 선택 Agent | 호출 도구 |
|------------|------------|-----------|----------|
| "소스 목록 보여줘" | source_management | Source | get_user_sources |
| "https://github.com/user/repo.git 추가" | source_management | Source | add_source_and_embed |
| "1번 소스 임베딩 다시 시작" | embedding_execution | Embedding | embed_source |
| "임베딩 상태 확인" | embedding_execution | Embedding | get_embedding_status |
| "2번 소스 삭제" | source_management | Source | delete_source_from_db |

### 통합 도구 (add_source_and_embed)

**목적:** Git URL 추가 시 Source 저장 → 임베딩 자동 시작 (한 번에 처리)

```python
@tool
def add_source_and_embed(
    user_id: str,
    name: str,
    source_type: str,
    location: str
) -> str:
    """
    소스를 추가하고 즉시 임베딩을 시작합니다.

    내부 동작:
    1. add_source_to_db 호출 → source_id 획득
    2. embed_source(user_id, source_id) 호출
    3. 통합 결과 반환
    """
```

**UX 개선:**
- 사용자가 한 번만 요청 → 소스 추가 + 임베딩 모두 완료
- Multi-turn 불필요

### 에러 핸들링

#### Router 판단 오류
- 애매한 요청 시 시스템 메시지의 명확한 기준 활용
- 잘못 라우팅되어도 Sub-Agent가 "처리 불가" 응답

#### 도구 실행 오류
- DB 연결 실패 → RuntimeError, 사용자에게 재시도 안내
- Git Clone 실패 → embedding_status=FAILED, 오류 메시지 저장
- 권한 오류 → user_id 필터로 보안 보장

#### LLM 도구 호출 실패
- 필수 파라미터 누락 → 도구에서 검증 및 에러 반환
- 잘못된 source_type → request_source_type_clarification 자동 호출

### 장점
- 책임 분리 (Source CRUD vs Embedding 실행)
- 확장성 좋음 (나중에 Log Agent 등 추가 가능)
- Agent별 다른 LLM 사용 가능

### 단점
- 구조 복잡 (Router + 2개 Agent)
- 코드 양 많음 (약 300줄)
- 현재 규모(도구 6개)에는 과도함

---

## 설계 2: 단일 Agent 방식

### 아키텍처

```
사용자 요청
    ↓
Unified Agent
    └─ tools: 6개 모두
    └─ Gemini Flash
    ↓
Tool Node
    ↓
Agent (결과 확인 및 연쇄 호출)
    ↓
END
```

### 컴포넌트

#### 1. MessagesState
```python
# LangGraph 기본 State 사용
MessagesState
```

#### 2. Unified Agent
- **LLM:** Gemini Flash
- **도구:** 6개 모두
  - `add_source_to_db`
  - `get_user_sources`
  - `delete_source_from_db`
  - `request_source_type_clarification`
  - `embed_source`
  - `get_embedding_status`
- **역할:** 모든 Source/Embedding 작업 처리

#### 3. Checkpointer (대화 기록 유지)
- **타입:** InMemorySaver (langgraph.checkpoint.memory)
- **역할:** 사용자별 대화 히스토리 저장
- **thread_id:** user_id 사용 (사용자별 독립된 대화 세션)

### 데이터 플로우

```
1. 사용자 요청
   └─ unified_agent(user_id, message)

2. Config 설정 (대화 세션 유지)
   └─ config = {"configurable": {"thread_id": user_id}}

3. MessagesState 초기화
   └─ {"messages": [HumanMessage(message)]}

4. Unified Agent 실행
   └─ 시스템 메시지 + 사용자 메시지
   └─ Gemini Flash 호출
   └─ 도구 선택 (자동)

5. Tool Node 실행
   └─ 선택된 도구 실행
   └─ ToolMessage 반환

6. Agent 재실행 (연쇄 호출 가능)
   └─ 이전 도구 결과 확인
   └─ 추가 도구 필요 시 호출
   └─ 예: add_source_to_db → source_id 획득 → embed_source 호출

7. Checkpoint 저장
   └─ 대화 기록이 thread_id별로 자동 저장

8. 최종 응답
   └─ messages[-1].content
```

### 연쇄 호출 예시

**사용자:** "https://github.com/user/repo.git 추가해줘"

```
Turn 1:
Agent → add_source_to_db 호출
Result: "✅ 소스 추가 완료 (ID: 5)"

Turn 2:
Agent → source_id=5 확인 → embed_source(5) 호출
Result: "✅ 임베딩 진행 중..."

Turn 3:
Agent → 최종 응답 생성
"소스 'repo'가 추가되었고 임베딩이 시작되었습니다."
```

### 시스템 메시지

```python
SYSTEM_MESSAGE = f"""당신은 소스 관리 어시스턴트입니다 (user_id: {user_id}).

주요 기능:
1. Source 관리
   - Git 저장소 추가 (자동 임베딩 시작)
   - 소스 목록 조회
   - 소스 삭제

2. Embedding 관리
   - 임베딩 상태 조회
   - 임베딩 재시작

워크플로우:
- Git URL 추가 시: add_source_to_db → embed_source (연쇄 호출)
- 단순 조회: 해당 도구만 호출
"""
```

### 에러 핸들링

Router 방식과 동일:
- DB 연결 실패 처리
- Git Clone 오류 처리
- 권한 검증
- 파라미터 검증

### 장점
- 구조 단순 (Agent 1개)
- 코드 짧음 (약 150줄)
- 연쇄 호출 자연스러움 (add → embed)
- Router 판단 오류 없음
- 유지보수 쉬움

### 단점
- 확장성 제한 (도구 20개+ 시 혼란 가능)
- Agent별 다른 LLM 사용 불가
- 복잡한 워크플로우 처리 어려움

---

## 비교 및 권장

| 항목 | Router 방식 | 단일 Agent 방식 |
|-----|-----------|---------------|
| 구조 복잡도 | 높음 (Router + 2개 Agent) | 낮음 (Agent 1개) |
| 코드 라인 수 | ~300줄 | ~150줄 |
| 확장성 | 매우 좋음 | 제한적 (도구 15개 이하) |
| 연쇄 호출 | 통합 도구 필요 | 자연스러움 |
| LLM 선택 | Agent별 다름 | 단일 LLM |
| 유지보수 | 어려움 | 쉬움 |
| 현재 프로젝트 적합성 | 과도함 | **적합 ⭐** |

### 권장: 단일 Agent 방식

**이유:**
1. 도구가 6개로 적음 (단일 Agent로 충분)
2. 단일 도메인 (Source/Embedding이 밀접)
3. 연쇄 호출이 자연스러움 (add → embed)
4. YAGNI 원칙 (불필요한 복잡성 회피)

### Router 방식이 필요한 경우
- 도구가 15개 이상으로 늘어날 때
- 완전히 다른 도메인 추가 시 (Log Agent, Analytics Agent)
- Agent별로 다른 LLM 필요 시

---

## 구현 계획

### Phase 1: 단일 Agent 방식 우선 구현
1. `unified_controller_single.py` 작성
2. InMemorySaver checkpointer 설정
3. 6개 도구 import 및 bind
4. 시스템 메시지 작성 (user_id 포함)
5. Graph 구성 (Agent ↔ Tools) + checkpointer compile
6. `unified_agent(user_id, message)` 함수 export (config with thread_id)

### Phase 2: Router 방식 구현
1. `add_source_and_embed` 통합 도구 작성 (tools/source.py에 추가)
2. `unified_controller_router.py` 작성
3. InMemorySaver checkpointer 설정
4. RouteDecision Pydantic 모델
5. Router Agent 구현
6. Source Agent, Embedding Agent 구현
7. Unified Graph 구성 (checkpointer compile)
8. `unified_agent(user_id, message)` 함수에 config 적용

### Phase 3: 테스트
1. 단일 Agent 방식 테스트
   - Source 추가 → 자동 임베딩 확인
   - 조회, 삭제 기능 확인
   - 대화 기록 유지 확인 (이전 대화 참조)
2. Router 방식 테스트
   - 라우팅 정확도 확인
   - 통합 도구 동작 확인
   - 대화 기록 유지 확인 (이전 대화 참조)
3. 비교 분석 및 최종 선택

---

## 파일 구조

```
src/
├─ tools/
│  ├─ source.py (기존)
│  │  └─ add_source_and_embed (추가)
│  └─ embedding.py (기존)
│
├─ unified_controller_single.py (새로 생성)
│  └─ unified_agent(user_id, message)
│
├─ unified_controller_router.py (새로 생성)
│  ├─ RouteDecision
│  ├─ create_router_agent(user_id)
│  ├─ create_source_agent(user_id)
│  ├─ create_embedding_agent(user_id)
│  └─ unified_agent(user_id, message)
│
├─ controller.py (기존 - 유지)
└─ _controller.py (참고용 - 유지)
```

---

## 결론

두 가지 방식 모두 구현하여 비교 학습할 수 있도록 합니다:

1. **단일 Agent 방식** - 현재 프로젝트에 적합, 간단하고 효율적
2. **Router 방식** - 확장 가능한 아키텍처, 학습 목적

사용자가 실제 동작을 확인하고 선택할 수 있도록 두 파일 모두 제공합니다.
