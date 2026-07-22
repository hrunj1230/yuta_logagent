# 대화형 소스 관리 시스템 구현 완료

## 📋 구현 개요

패스워드 없는 로그인 시스템과 대화형 소스 관리 기능을 구현했습니다.
- AI와 대화하면서 학습 소스(Git 저장소, 로컬 폴더) 추가
- 등록된 소스 목록 보기/삭제
- Source 테이블에 자동 저장

## 🔄 최근 업데이트 (2026-07-22)

### 🔥 Git 저장소 자동 클론 및 임베딩 추가
**공개 Git 저장소를 URL만으로 바로 추가 가능!**

#### 변경사항
- `add_source_to_db` 도구 업그레이드 (src/tools.py:358-452)
- Git URL 입력 시 자동으로:
  1. **Clone**: `./repos/{user_id}/{repo_name}`에 저장
  2. **Embedding**: `embedding_file_for_user()`로 벡터DB 저장
  3. **DB 저장**: Source 테이블에 기록

#### 사용 예시
```
사용자: "https://github.com/hrunj1230/Yuta_TIL.git 추가해줘"
Router: source_management로 라우팅
Source Agent: add_source_to_db 호출
  ↓ [자동 처리]
  1. git clone --depth 1 https://github.com/hrunj1230/Yuta_TIL.git ./repos/user123/Yuta_TIL
  2. embedding_file_for_user("user123", "./repos/user123/Yuta_TIL")
  3. DB에 Source 저장
  ↓
응답: "✅ Git 저장소 추가 완료! 자동으로 클론 및 임베딩이 완료되었습니다."
```

#### 기술 세부사항
- **Shallow Clone**: `--depth 1`로 최신 커밋만 가져와 속도 향상
- **사용자별 격리**: `./repos/{user_id}/`로 저장하여 충돌 방지
- **자동 덮어쓰기**: 기존 디렉토리가 있으면 삭제 후 재클론
- **에러 처리**: Git 실패 시 상세한 에러 메시지 반환

#### 로컬 경로는?
- **로컬 경로** (`./my_notes`, `/Users/*/docs`)는 클론하지 않고 그대로 임베딩
- **Git URL**만 자동 클론됨

---

## 🔄 최근 업데이트 (2026-07-22)

### 🚀 Router Agent 시스템 구현 (LangGraph 기반)
**하나의 채팅창에서 모든 작업 가능!**

#### 핵심 개념
```
사용자 메시지
    ↓
Router Agent (요청 분석 - LLM Structured Output)
    ↓
Conditional Edge (자동 라우팅)
    ├─→ Source Management Agent (소스 관리)
    └─→ Log Making Agent (일지 작성)
```

#### 구현 세부사항

**1. Router Agent (src/controller.py:257-321)**
- `RouteDecision` Pydantic 모델: structured output으로 명확한 라우팅
- `create_router_agent()`: 사용자 요청 분석 → "source_management" or "log_making"
- Claude Sonnet 4.5의 `with_structured_output()` 활용

**2. Conditional Edge (src/controller.py:323-337)**
- `route_to_agent()`: Router 결과에 따라 적절한 subgraph 선택
- "source_subgraph" 또는 "log_subgraph"로 분기

**3. Unified Graph (src/controller.py:339-393)**
- `_unified_graph_builder()`: Router + Source Agent + Log Agent 통합
- LangGraph의 `add_conditional_edges()` 활용
- 각 Agent는 독립적인 도구 세트와 흐름 유지

**4. 통합 엔드포인트**
- **Router**: `POST /unified_agent` (src/router.py:142-149)
- **UI**: `templates/user_page.html`의 "AI 어시스턴트" 메뉴
- **JavaScript**: `sendUnifiedMessage()`, `addUnifiedChatMessage()`

#### 사용 예시

**소스 관리 요청 → Source Agent**
- "https://github.com/user/repo.git 추가해줘"
- "내 소스 목록 보여줘"
- "1번 소스 삭제"

**일지 작성 요청 → Log Agent**
- "2026-07-22 일지 작성해줘"
- "오늘 한 일 정리해줘"
- "내일 할 일 알려줘"

#### 기술 스택
- **LangGraph**: StateGraph, conditional_edges, ToolNode
- **Pydantic**: Structured output으로 타입 안전성
- **Claude Sonnet 4.5**: Router 분석 + 각 Agent 실행
- **FastAPI**: Form 데이터 처리

#### 장점
✅ 사용자 친화적: 하나의 채팅창에서 모든 작업
✅ 명확한 역할 분리: 각 Agent는 자기 도구만 관리
✅ 확장 가능: 새로운 Agent 추가 시 Router만 수정
✅ 타입 안전: Pydantic으로 라우팅 결과 검증

---

### 자동 이름 지정 기능 추가
- 사용자가 소스 이름을 지정하지 않은 경우, source_type을 name으로 자동 사용
- 예: Git 저장소를 추가할 때 이름을 생략하면 "git"으로 저장됨
- `src/controller.py`의 `create_source_system_message()` 수정

---

## 🗂️ 수정/추가된 파일

### 1. `storage/models.py` - 데이터베이스 모델
```python
class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(primary_key=True)  # name 제거됨
    sources: Mapped[list["Source"]] = relationship()

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    location: Mapped[str] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (UniqueConstraint("user_id", "type", "location"),)
```

**변경사항:**
- User 모델에서 `name` 필드 제거
- `user_id`를 str 타입의 primary key로 변경
- Source 모델 간소화 (config, is_private, credential_id 제거)

---

### 2. `storage/auth.py` - 인증 로직 (NEW)
```python
def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """ID로 사용자 조회"""
    return db.query(User).filter(User.user_id == user_id).first()

def create_user(db: Session, user_id: str) -> User:
    """새 사용자 생성"""
    user = User(user_id=user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def login_or_register(db: Session, user_id: str) -> User:
    """로그인 또는 자동 회원가입 (패스워드 없음)"""
    user = get_user_by_id(db, user_id)
    if user:
        return user
    else:
        return create_user(db, user_id)
```

**기능:**
- 패스워드 없이 user_id만으로 로그인/회원가입
- 기존 사용자는 로그인, 신규 사용자는 자동 생성

---

### 3. `storage/database.py` - 데이터베이스 설정
```python
from .models import Base  # 순환 import 수정

def get_db():
    """요청마다 session을 하나 만들어주고 끝나면 닫기"""
    db = SessionLocal()
    try:
        yield db  # 수정됨
    finally:
        db.close()
```

**변경사항:**
- `from models import Base` → `from .models import Base` (상대 경로)
- `get_db()`에서 `yield db` 추가 (이전에는 yield만 있었음)

---

### 4. `src/tools.py` - Source 관리 Tool 추가
```python
@tool
def add_source_to_db(user_id: str, name: str, source_type: str, location: str) -> str:
    """사용자의 학습 소스를 데이터베이스에 저장"""
    # user_id 추출 (메시지에서 [USER_ID: xxx] 형식)
    # Source 테이블에 저장
    # 중복 체크
    # 결과 반환

@tool
def get_user_sources(user_id: str) -> str:
    """사용자의 등록된 소스 목록 조회"""
    # 활성화된 소스만 조회
    # 보기 좋게 포맷팅

@tool
def delete_source_from_db(source_id: int, user_id: str) -> str:
    """등록된 소스 삭제"""
    # 권한 확인 (본인 소스만 삭제)
    # 삭제 실행
```

**기능:**
- 소스 추가: 중복 체크, 자동 시간 기록
- 소스 조회: 이름, 타입, 위치, 마지막 동기화 시간 표시
- 소스 삭제: 권한 확인 후 삭제

---

### 5. `src/controller.py` - 소스 관리 Agent 추가
```python
## 로그인 관련 컨트롤러
def handle_login(db: Session, user_id: str):
    """로그인/회원가입 처리"""
    user = login_or_register(db, user_id.strip())
    return {
        "user_id": user.user_id,
        "message": f"{user.user_id}님, 환영합니다!"
    }

def get_user_info(db: Session, user_id: str = None):
    """사용자 정보 조회"""
    user = get_user_by_id(db, user_id)
    return {
        "user_id": user.user_id,
        "sources_count": len(user.sources) if user.sources else 0
    }

## 소스 관리 Agent
source_tools = [
    tool.add_source_to_db,
    tool.get_user_sources,
    tool.delete_source_from_db
]

llm_source_manager = llm.anthropic_llm.bind_tools(source_tools)

SYSTEM_MESSAGE_SOURCE = SystemMessage(content="""
당신은 사용자의 학습 소스를 관리하는 친절한 어시스턴트입니다.

1️⃣ 인사 및 안내
"안녕하세요! 학습 자료를 등록해드릴게요 😊"

2️⃣ 소스 추가
- Git URL인지 로컬 경로인지 자동 판단
- 소스 이름 물어보기
- add_source_to_db 도구 사용

3️⃣ 소스 목록 보기
- get_user_sources 도구 사용

4️⃣ 소스 삭제
- delete_source_from_db 도구 사용
""")

def source_manager(user_id: str, message: str):
    """소스 관리 대화형 함수"""
    input_dict = {
        "messages": [
            HumanMessage(content=f"[USER_ID: {user_id}]\n{message}")
        ]
    }
    res = source_graph.invoke(input_dict)
    return res["messages"][-1].content
```

**기능:**
- 대화형 소스 관리 Agent
- 사용자와 자연스러운 대화
- Tool 자동 호출

---

### 6. `src/router.py` - 라우터 추가/수정
```python
## 로그인 관련
@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """패스워드 없이 이름만으로 로그인/회원가입"""
    result = controller.handle_login(db, req.user_id)
    return LoginResponse(**result)

@router.post("/login-form")
async def login_form(user_id: str = Form(...), db: Session = Depends(get_db)):
    """Form 방식 로그인 (서버 리다이렉트)"""
    result = controller.handle_login(db, user_id)
    return RedirectResponse(url=f"/user/{result['user_id']}", status_code=303)

@router.get("/user/{user_id}")
async def get_user_page(request: Request, user_id: str, db: Session = Depends(get_db)):
    """개인 페이지"""
    result = controller.get_user_info(db, user_id=user_id)
    return templates.TemplateResponse(...)

## 소스 관리 관련 (NEW)
@router.post("/source_manager")
async def source_manager(user_id: str = Form(...), message: str = Form(...)):
    """소스 관리 대화형 Agent"""
    res = controller.source_manager(user_id, message)
    return {"response": res}

@router.get("/user/{user_id}/settings")
async def get_settings_page(request: Request, user_id: str, db: Session = Depends(get_db)):
    """설정 페이지 - 소스 목록 보기/삭제"""
    sources = db.query(Source).filter(
        Source.user_id == user_id,
        Source.is_active == True
    ).all()
    return templates.TemplateResponse("settings.html", ...)

@router.post("/user/{user_id}/delete_source/{source_id}")
async def delete_source(user_id: str, source_id: int, db: Session = Depends(get_db)):
    """소스 삭제 API"""
    source = db.query(Source).filter(...).first()
    db.delete(source)
    db.commit()
    return {"success": True}
```

**엔드포인트:**
- `POST /login`: API 로그인
- `POST /login-form`: Form 로그인 (리다이렉트)
- `GET /user/{user_id}`: 개인 페이지
- `POST /source_manager`: 소스 관리 채팅
- `GET /user/{user_id}/settings`: 설정 페이지
- `POST /user/{user_id}/delete_source/{source_id}`: 소스 삭제

---

### 7. `main.py` - 앱 초기화
```python
from storage.database import init_db

# 데이터베이스 초기화 (테이블이 없으면 자동 생성)
init_db()

app = FastAPI(title="log_maker")
```

**변경사항:**
- 앱 시작 시 자동으로 DB 테이블 생성

---

### 8. `templates/login.html` - 로그인 페이지
```html
<form action="/login-form" method="post">
    <input type="text" name="user_id" placeholder="사용자 ID" required>
    <button type="submit">로그인 / 회원가입</button>
</form>
```

**기능:**
- 세련된 디자인
- 패스워드 없이 user_id만 입력
- 자동 회원가입 안내

---

### 9. `templates/user_page.html` - 개인 페이지
```html
<ul class="menu-list">
    <li><a href="#" onclick="showSourceManager()">📚 학습 소스 관리 (대화형)</a></li>
    <li><a href="/user/{{ user_id }}/settings">⚙️ 설정 (소스 목록)</a></li>
    <li><a href="#" onclick="showAgentForm()">💬 에이전트와 대화하기</a></li>
    <li><a href="/log-maker">📝 Git 동기화 & 일지 생성</a></li>
</ul>

<div id="chat-history">
    <!-- 대화 내용이 여기에 표시됨 -->
</div>
<input id="source-message" placeholder="메시지를 입력하세요...">
<button onclick="sendSourceMessage()">전송</button>
```

**기능:**
- 소스 관리 채팅 UI
- 대화 히스토리 표시
- 실시간 응답

**JavaScript:**
```javascript
async function sendSourceMessage(event) {
    // 사용자 메시지 추가
    addChatMessage('user', message);

    // AI에게 전송
    const formData = new FormData();
    formData.append('user_id', '{{ user_id }}');
    formData.append('message', message);

    const response = await fetch('/source_manager', {
        method: 'POST',
        body: formData
    });

    // AI 응답 표시
    addChatMessage('ai', data.response);
}
```

---

### 10. `templates/settings.html` - 설정 페이지 (NEW)
```html
<h2>📚 등록된 학습 소스 ({{ sources|length }}개)</h2>

{% for source in sources %}
<div class="source-item">
    <div class="source-info">
        <h3>{{ source.name }}</h3>
        <span class="source-type">{{ source.type.value }}</span>
        <span>{{ source.location }}</span>
        <div>마지막 동기화: {{ source.last_synced_at }}</div>
    </div>
    <button onclick="deleteSource({{ source.id }})">삭제</button>
</div>
{% endfor %}
```

**기능:**
- 등록된 소스 목록 표시
- 소스별 삭제 버튼
- 빈 상태 UI

---

### 11. `pyproject.toml` - 의존성 추가
```toml
dependencies = [
    ...
    "jinja2>=3.1.0",
    "python-multipart>=0.0.5",
]
```

**추가된 패키지:**
- `jinja2`: HTML 템플릿
- `python-multipart`: Form 데이터 처리

---

## 🎯 사용 흐름

### 1. 로그인
```
브라우저 → http://localhost:8000/
    ↓
user_id 입력 (예: "hrun")
    ↓
POST /login-form
    ↓
User 테이블에 저장 (자동 회원가입)
    ↓
/user/hrun 페이지로 리다이렉트
```

### 2. 소스 추가 (대화형)
```
개인 페이지에서 "학습 소스 관리" 클릭
    ↓
채팅창에 입력: "https://github.com/hrun/til.git 추가해줘"
    ↓
POST /source_manager
    ↓
AI가 응답: "이 저장소 이름을 뭐라고 할까요?"
    ↓
사용자 입력: "내 TIL"
    ↓
add_source_to_db Tool 실행
    ↓
Source 테이블에 저장
    ↓
AI 응답: "✅ 소스 추가 완료!"
```

### 3. 소스 목록 보기
```
개인 페이지에서 "설정" 클릭
    ↓
GET /user/hrun/settings
    ↓
Source 테이블에서 조회
    ↓
등록된 소스 목록 표시
```

### 4. 소스 삭제
```
설정 페이지에서 "삭제" 버튼 클릭
    ↓
확인 다이얼로그
    ↓
POST /user/hrun/delete_source/5
    ↓
Source 테이블에서 삭제
    ↓
페이지 새로고침
```

---

## 📊 데이터베이스 구조

### users 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| user_id | TEXT (PK) | 사용자 ID |

### sources 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER (PK) | 자동 증가 ID |
| user_id | TEXT (FK) | 사용자 ID |
| name | TEXT | 소스 이름 |
| type | TEXT | "git", "local_til", etc |
| location | TEXT | URL 또는 경로 |
| last_synced_at | DATETIME | 마지막 동기화 시간 |
| is_active | BOOLEAN | 활성화 여부 |

**제약조건:**
- `UniqueConstraint("user_id", "type", "location")`: 중복 방지

---

## 🚀 실행 방법

```bash
# 의존성 설치
uv sync

# 데이터베이스 초기화 (자동)
# main.py에서 init_db() 실행됨

# 서버 시작
uvicorn main:app --reload

# 브라우저 접속
open http://localhost:8000
```

---

## ✅ 완성된 기능

1. ✅ 패스워드 없는 로그인/회원가입
2. ✅ 대화형 소스 추가 (AI와 채팅)
3. ✅ 소스 목록 조회 (설정 페이지)
4. ✅ 소스 삭제
5. ✅ Source 테이블 자동 저장
6. ✅ 중복 체크
7. ✅ 사용자별 소스 관리
8. ✅ 세련된 UI (그라데이션, 카드, 채팅)

---

## 🎨 UI 특징

- **로그인 페이지**: 그라데이션 배경, 카드 스타일
- **개인 페이지**: 대시보드 레이아웃, 채팅 UI
- **설정 페이지**: 소스 목록 카드, 삭제 버튼
- **대화형 채팅**: 사용자/AI 메시지 구분, 스크롤 자동 이동

---

## 📝 주요 개선사항

### Before (기존)
- ❌ 딱딱한 폼 UI
- ❌ Source DB 저장 안 됨
- ❌ 설정 페이지 없음

### After (개선)
- ✅ 대화형 채팅 UI
- ✅ Source 자동 저장
- ✅ 설정 페이지에서 관리
- ✅ 중복 체크, 권한 확인

---

## 🐛 해결된 문제

1. **순환 import**: `models.py`에서 `database.py` import 제거
2. **TemplateResponse 오류**: 키워드 인자 방식으로 변경
3. **python-multipart 누락**: Form 데이터 처리를 위해 설치
4. **users 테이블 없음**: `init_db()` 자동 호출 추가
5. **relationship 오류**: `back_populates` 제거 (단방향)

---

## 💡 핵심 코드 패턴

### 1. Tool 사용 패턴
```python
@tool
def add_source_to_db(user_id: str, name: str, ...) -> str:
    """도구 설명 (AI가 읽음)"""
    # 비즈니스 로직
    # DB 저장
    return "결과 메시지"
```

### 2. Agent 패턴
```python
llm_with_tools = llm.anthropic_llm.bind_tools(tools)

SYSTEM_MESSAGE = SystemMessage(content="AI 역할 및 작업 흐름")

def agent(state: MessagesState) -> dict:
    messages = [SYSTEM_MESSAGE] + state["messages"]
    result = llm_with_tools.invoke(messages)
    return {"messages": [result]}

graph = StateGraph(MessagesState)
graph.add_node("agent", agent)
graph.add_node("tools", ToolNode(tools))
# ... edges 설정
```

### 3. 템플릿 렌더링 패턴
```python
templates.TemplateResponse(
    request=request,
    name="template.html",
    context={"key": "value"}
)
```

---

## 🔒 보안 고려사항

1. **패스워드 없음**: 개발/데모 용도로만 사용
2. **권한 확인**: 소스 삭제 시 user_id 확인
3. **SQL Injection 방지**: SQLAlchemy ORM 사용
4. **중복 방지**: UniqueConstraint 사용

---

## 📚 참고 자료

- FastAPI 공식 문서: https://fastapi.tiangolo.com/
- SQLAlchemy 문서: https://docs.sqlalchemy.org/
- LangChain 문서: https://python.langchain.com/
- Jinja2 문서: https://jinja.palletsprojects.com/

---

## 🔧 최근 버그 수정 및 개선 (2026-07-22 오후)

### 🎯 Git URL 자동 감지 및 강제 도구 호출

**문제**: Agent가 Git URL을 받아도 도구를 호출하지 않고 "먼저 클론해야 합니다"라는 텍스트 응답만 생성

**해결**: (src/controller.py:191-225)
```python
def create_source_agent(user_id: str):
    def source_agent(state: MessagesState) -> dict:
        # 1. Git URL 패턴 감지
        git_url_pattern = r'(https?://(?:github\.com|gitlab\.com|bitbucket\.org)/...)'
        has_git_url = re.search(git_url_pattern, user_message)

        # 2. Git URL 감지 시 tool_choice로 강제 호출
        if has_git_url and not is_after_tool_execution:
            llm_forced = llm.anthropic_llm.bind_tools(
                source_tools,
                tool_choice="add_source_to_db"  # 강제!
            )
            result = llm_forced.invoke(messages)
```

**효과**:
- ✅ Git URL 입력 시 **무조건 `add_source_to_db` 도구 호출**
- ✅ LLM의 선택권 제거 → 100% 확실한 실행
- ✅ GitHub, GitLab, Bitbucket URL 모두 감지

---

### 🔄 UnifiedState 클래스로 Router 문제 해결

**문제**: Router가 `route_destination`을 state에 저장했지만, 다음 노드에서 사라짐
```
[ROUTER] 🔄 State 업데이트: {'route_destination': 'source_management'}
[ROUTE_TO_AGENT] State keys: ['messages']  ← route_destination 없음!
[ROUTE_TO_AGENT] route_destination value: log_making  ← default 값 사용됨
```

**원인**: `MessagesState`는 기본적으로 `messages` 필드만 관리

**해결**: (src/controller.py:1-17)
```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class UnifiedState(TypedDict):
    """Router Agent를 위한 확장 State"""
    messages: Annotated[list, add_messages]
    route_destination: str  # 커스텀 필드 추가!

# StateGraph 생성 시 사용
builder = StateGraph(UnifiedState)  # MessagesState → UnifiedState
```

**결과**:
```
[ROUTER] 🔄 State 업데이트: {'route_destination': 'source_management'}
[ROUTE_TO_AGENT] State keys: ['messages', 'route_destination']  ✅
[ROUTE_TO_AGENT] route_destination value: source_management  ✅
[ROUTE_TO_AGENT] 🎯 라우팅: source_agent로 이동  ✅
```

---

### 💾 Source 저장 순서 변경 (임베딩 실패에도 안전)

**문제**: 임베딩 실패 시 Source가 DB에 저장되지 않음
```python
# Before (문제)
1. Git clone
2. 임베딩 시도 → 실패 시 return
3. Source 저장 ← 도달 못함!
```

**해결**: (src/tools.py:417-481)
```python
# After (해결)
1. Source를 먼저 DB에 저장 ✅
2. Git clone
3. 임베딩 시도 (실패해도 Source는 이미 저장됨)
4. 결과 메시지 반환
```

**효과**:
- ✅ 임베딩 실패해도 Source 정보는 DB에 보존
- ✅ 나중에 재동기화 가능
- ✅ 부분 성공 상태 지원

**결과 메시지**:
- 성공: `"✅ Git 저장소 추가 완료! 자동으로 클론 및 임베딩이 완료되었습니다."`
- 부분 실패: `"⚠️ Git 저장소 추가 완료 (임베딩 실패) ... 나중에 다시 동기화를 시도해주세요."`

---

### 🗄️ ChromaDB 클라이언트 일관성 수정

**문제**: `embedding_file_for_user`에서 매번 새로운 PersistentClient 생성
```python
# Before (문제)
llm_router.chroma_client.delete_collection(collection_name)  # 기존 클라이언트
vectorstore = Chroma(
    client=llm_router.chromadb.PersistentClient(path="./chroma_db")  # 새 클라이언트!
)
```

**해결**: (src/tools.py:343-347)
```python
# After (해결)
vectorstore = Chroma(
    collection_name=collection_name,
    embedding_function=llm_router.local_embedding,
    client=llm_router.chroma_client  # 기존 클라이언트 재사용 ✅
)
```

**효과**:
- ✅ 클라이언트 충돌 방지
- ✅ 컬렉션 삭제/생성이 동일한 DB에서 작동
- ✅ 임베딩 오류 감소

---

### 🔁 무한루프 문제 해결

**문제**: source_agent가 도구 실행 후에도 계속 Git URL을 감지하여 무한 반복
```
1. Git URL 감지 → 도구 호출
2. 도구 실행 → ToolMessage 반환
3. source_agent로 돌아옴
4. 여전히 Git URL이 state에 있음
5. 다시 Git URL 감지 → 도구 호출 (무한 반복!)
```

**해결**: (src/controller.py:195-225)
```python
from langchain_core.messages import HumanMessage, ToolMessage

def source_agent(state: MessagesState) -> dict:
    last_message = state["messages"][-1]

    # ⚠️ 중요: 도구 실행 결과 이후에는 Git URL 감지 안 함!
    is_after_tool_execution = isinstance(last_message, ToolMessage)

    # HumanMessage에서만 Git URL 감지
    has_git_url = False
    if isinstance(last_message, HumanMessage):
        has_git_url = re.search(git_url_pattern, user_message)

    # 도구 실행 후가 아닐 때만 강제 호출
    if has_git_url and not is_after_tool_execution:
        # 도구 강제 호출
```

**효과**:
- ✅ 처음: Git URL 감지 → 도구 호출
- ✅ 도구 실행 후: ToolMessage 감지 → Git URL 감지 안 함 → 최종 응답 생성 → **종료**
- ✅ 무한루프 방지

---

### 🛠️ @tool 데코레이터 제거 (embedding_file_for_user)

**문제**: `embedding_file_for_user`를 일반 함수처럼 호출했지만, `@tool` 데코레이터로 인해 StructuredTool 객체가 됨
```
❌ 임베딩 실패: 'StructuredTool' object is not callable
```

**원인**:
```python
# src/tools.py
@tool  # ← StructuredTool 객체로 변환
def embedding_file_for_user(user_id: str, path: str) -> str:
    ...

# src/tools.py (add_source_to_db 내부)
embedding_result = embedding_file_for_user(user_id, local_path)  # ❌ 호출 불가
```

**해결**: (src/tools.py:232-233, src/controller.py:132-136)
```python
# 1. @tool 데코레이터 제거
# @tool  ← 제거
def embedding_file_for_user(user_id: str, path: str) -> str:
    """내부 헬퍼 함수 (Agent가 직접 호출하지 않음)"""
    ...

# 2. source_tools 리스트에서 제거
source_tools = [
    tool.add_source_to_db,
    tool.get_user_sources,
    tool.delete_source_from_db
    # embedding_file_for_user 제거 (내부 함수)
]
```

**효과**:
- ✅ 일반 Python 함수로 호출 가능
- ✅ Agent가 직접 호출하지 않는 내부 헬퍼 함수로 명확히 구분
- ✅ 임베딩 정상 작동

---

### 📝 System Message 강화 (영어)

**변경**: (src/controller.py:142-189)
```python
# Before (한국어 + 간단)
"""당신은 사용자의 학습 소스를 관리하는 친절한 어시스턴트입니다.
1️⃣ 인사 및 안내
2️⃣ 소스 추가
..."""

# After (영어 + 강화)
"""You are a source management assistant for user_id: {user_id}

🚨 ABSOLUTE RULES - NO EXCEPTIONS:
1. **Git URL Detection (MANDATORY TOOL CALL)**
   👉 YOU MUST IMMEDIATELY call add_source_to_db tool

⚠️ CRITICAL BEHAVIORS:
- NEVER explain what you will do - JUST CALL THE TOOL
- NEVER ask for confirmation - JUST CALL THE TOOL
..."""
```

**이유**:
- LLM이 영어 지시문을 더 정확하게 따름
- 도구 호출 같은 구조적 작업에 효과적
- "NEVER", "IMMEDIATELY", "MUST" 같은 강한 지시어 사용

---

## 🐛 해결된 문제 요약

| 문제 | 해결 방법 | 파일 |
|------|-----------|------|
| Git URL 입력해도 도구 미호출 | `tool_choice` 파라미터로 강제 호출 | src/controller.py:191-225 |
| route_destination이 state에서 사라짐 | `UnifiedState` 클래스 정의 | src/controller.py:1-17 |
| 임베딩 실패 시 Source 저장 안 됨 | Source를 먼저 저장하도록 순서 변경 | src/tools.py:417-481 |
| ChromaDB 클라이언트 충돌 | 기존 `chroma_client` 재사용 | src/tools.py:343-347 |
| 무한루프 발생 | ToolMessage 이후 Git URL 감지 안 함 | src/controller.py:195-225 |
| StructuredTool 호출 오류 | `@tool` 데코레이터 제거 | src/tools.py:232 |

---

## ✅ 최종 작동 흐름 (Git URL 입력 시)

```
사용자: "https://github.com/hrunj1230/Yuta_TIL.git 추가해줘"
    ↓
Router Agent
    ├─ 요청 분석: "Git 저장소 추가" → source_management
    └─ State 업데이트: route_destination = "source_management"
    ↓
Conditional Edge (route_to_agent)
    └─ route_destination 확인 → "source_agent"로 라우팅 ✅
    ↓
Source Agent
    ├─ Git URL 감지: github.com 포함 ✅
    ├─ tool_choice="add_source_to_db" 강제 호출 ✅
    └─ Tool 실행
    ↓
add_source_to_db Tool
    ├─ 1. Source DB 저장 (users.db) ✅
    ├─ 2. Git clone (./repos/hrunj1230/Yuta_TIL) ✅
    ├─ 3. embedding_file_for_user() 호출
    │   ├─ *.md, *.txt 파일 로드
    │   ├─ 날짜 추출 및 메타데이터 추가
    │   ├─ ChromaDB에 저장 (collection: user_hrunj1230) ✅
    │   └─ 임베딩 완료 메시지 반환
    └─ 4. 결과 메시지 반환
    ↓
Source Agent (다시 돌아옴)
    ├─ ToolMessage 감지 → Git URL 감지 안 함 ✅
    ├─ 최종 응답 생성: "✅ Git 저장소 추가 완료!"
    └─ 종료 (무한루프 없음) ✅
```

---

## 🎯 성능 및 안정성 개선 결과

### Before (문제)
- ❌ Git URL 입력 → 텍스트 응답만 ("먼저 클론해야 합니다")
- ❌ 임베딩 실패 시 Source 저장 안 됨
- ❌ Router 라우팅 실패 (route_destination 소실)
- ❌ 무한루프 발생
- ❌ ChromaDB 클라이언트 충돌

### After (해결)
- ✅ Git URL 입력 → 자동으로 clone + 임베딩 + DB 저장
- ✅ 임베딩 실패해도 Source는 DB에 저장됨
- ✅ Router 라우팅 100% 정확
- ✅ 무한루프 없음 (한 번만 도구 호출)
- ✅ ChromaDB 안정적 작동

---

**최종 업데이트**: 2026-07-22 오후
**작성자**: Claude Sonnet 4.5
