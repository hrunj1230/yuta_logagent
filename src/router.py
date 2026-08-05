from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from . import unified_controller_single as controller
from .storage.database import get_db
from .storage.models import Source, EmbeddingStatus
from .tools.embedding import (
    _delete_source_embeddings,
    describe_progress,
    embedding_coverage,
    is_stale,
)
from .tools.log import (
    HIGHLIGHT_CSS,
    describe_journal_progress,
    journal_archive,
    journal_overview,
    journal_progress,
    reindex_journal,
    render_journal,
)
from fastapi.responses import Response
import json

router = APIRouter()

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory="templates")


# 로그인 관련 모델
class LoginRequest(BaseModel):
    user_id: str

class LoginResponse(BaseModel):
    user_id: str
    message: str

class UserInfoResponse(BaseModel):
    user_id: str
    sources_count: int

#user-router
@router.get("/")
async def login_page(request: Request):
    """로그인 페이지 (HTML Form)"""
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )

@router.get("/debugger")
async def architecture_debugger(request: Request, user_id: str = ""):
    """현재 구현을 작은 세계처럼 탐색하는 아키텍처 디버거 UI."""
    return templates.TemplateResponse(
        request=request,
        name="debugger.html",
        context={"user_id": user_id.strip()},
    )


@router.get("/api/debugger/snapshot")
async def debugger_snapshot(user_id: str = "", db: Session = Depends(get_db)):
    """디버거 UI에 SQLite/ChromaDB의 읽기 전용 현재 상태를 제공한다."""
    sources = []
    status_counts = {status.value: 0 for status in EmbeddingStatus}

    query = db.query(Source).filter(Source.is_active == True)
    if user_id.strip():
        query = query.filter(Source.user_id == user_id.strip())

    for source in query.order_by(Source.id.asc()).all():
        status = source.embedding_status.value
        status_counts[status] += 1
        sources.append({
            "id": source.id,
            "user_id": source.user_id,
            "name": source.name,
            "type": source.type.value,
            "location": source.location,
            "embedding_status": status,
            "last_synced_at": (
                source.last_synced_at.isoformat() if source.last_synced_at else None
            ),
            "error": source.embedding_error,
        })

    vector_count = None
    vector_state = "사용자 선택 필요"
    selected_user = user_id.strip()
    if selected_user:
        try:
            collection = controller.llm_router.chroma_client.get_collection(
                name=f"user_{selected_user}"
            )
            vector_count = collection.count()
            vector_state = "연결됨"
        except Exception:
            vector_count = 0
            vector_state = "컬렉션 없음"

    return {
        "ok": True,
        "user_id": selected_user or None,
        "source_count": len(sources),
        "vector_count": vector_count,
        "vector_state": vector_state,
        "status_counts": status_counts,
        "sources": sources,
        "runtime": {
            "api": "FastAPI",
            "agent": "LangGraph 단일 Agent",
            "llm": "Claude Sonnet 4.5",
            "embedding": "jhgan/ko-sroberta-multitask",
            "checkpointer": "메모리 (재시작 시 초기화)",
        },
    }

@router.post("/login-form")
async def login_form(user_id: str = Form(...), db: Session = Depends(get_db)):
    """
    Form 방식 로그인 (서버 리다이렉트)
    - 로그인 후 자동으로 개인 페이지로 이동
    """
    result = controller.handle_login(db, user_id)
    # 로그인 성공 후 개인 페이지로 리다이렉트
    return RedirectResponse(url=f"/user/{result['user_id']}", status_code=303)

@router.get("/user/{user_id}")
async def get_user_page(request: Request, user_id: str, db: Session = Depends(get_db)):
    """
    개인 페이지 (HTML)
    - 사용자 정보를 HTML로 표시
    """
    result = controller.get_user_info(db, user_id=user_id)

    return templates.TemplateResponse(
        request=request,
        name="user_page.html",
        context={
            "user_id": result['user_id'],
            "sources_count": result['sources_count']
        }
    )

@router.get("/user/{user_id}/settings")
async def get_settings_page(request: Request, user_id: str, db: Session = Depends(get_db)):
    """
    설정 페이지 (HTML)
    - 등록된 소스 목록 보기/삭제
    """
    # 사용자 존재 확인
    controller.get_user_info(db, user_id=user_id)

    # 소스 목록 조회
    sources = db.query(Source).filter(
        Source.user_id == user_id,
        Source.is_active == True
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "user_id": user_id,
            "sources": sources,
            # 중단된 작업을 화면에서 구분하기 위해 판정 함수를 그대로 넘긴다
            "is_stale": is_stale,
        }
    )

@router.post("/user/{user_id}/delete_source/{source_id}")
async def delete_source(user_id: str, source_id: int, db: Session = Depends(get_db)):
    """
    소스 삭제 API.

    SQLite 레코드만 지우면 해당 소스의 청크가 벡터DB에 남아 이후 검색에 계속
    섞이므로, Agent의 delete_source_from_db와 동일하게 임베딩까지 함께 지운다.
    """
    source = db.query(Source).filter(
        Source.id == source_id,
        Source.user_id == user_id
    ).first()

    if not source:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")

    deleted_chunks = _delete_source_embeddings(user_id, source_id)

    db.delete(source)
    db.commit()

    return {
        "success": True,
        "message": f"소스가 삭제되었습니다 (임베딩 {deleted_chunks}개 정리)",
        "deleted_chunks": deleted_chunks,
    }

#agent-router
@router.post("/unified_agent")
async def unified_agent_endpoint(user_id: str = Form(...), message: str = Form(...)):
    """
    통합 Agent — 소스 등록, 임베딩, 일지 작성을 하나의 대화창에서 처리한다.

    Git URL과 함께 소스 추가를 요청하면 Agent가 소스를 저장하고 임베딩을
    백그라운드로 시작한 뒤 곧바로 응답한다. 진행 상황은
    /user/{user_id}/sources/status 를 폴링해 확인한다.
    """
    res = controller.unified_agent(user_id, message)
    return {"response": res}


@router.get("/user/{user_id}/journals")
async def get_journals_page(request: Request, user_id: str, db: Session = Depends(get_db)):
    """
    일지 관리 화면.

    진실은 파일(logs/*.md)이고 벡터DB는 파생 색인이다. 그래서 목록은 파일에서
    만들고 색인 여부를 옆에 표시한다 — 파일은 있는데 색인이 없으면 일지를
    썼는데도 나중에 물어보면 "기록이 없습니다"가 나온다.

    머리말에는 등록된 소스를 URL 과 함께 싣는다. 일지의 재료가 어디서 왔는지
    화면 안에서 바로 확인할 수 있어야 하기 때문이다.
    """
    controller.get_user_info(db, user_id=user_id)

    sources = db.query(Source).filter(
        Source.user_id == user_id,
        Source.is_active == True
    ).order_by(Source.id).all()

    overview = journal_overview(user_id)
    coverage = embedding_coverage(user_id)

    # 일지가 있는 날짜를 표에 함께 표시한다 — '자료는 있는데 일지가 없는 날'이
    # 드러나야 다음에 무엇을 만들지 알 수 있다
    written = {journal["date"] for journal in overview["journals"]}
    for row in coverage["rows"]:
        row["has_journal"] = row["date"] in written

    return templates.TemplateResponse(
        request=request,
        name="journals.html",
        context={
            "user_id": user_id,
            "sources": sources,
            "journals": overview["journals"],
            "unindexed": overview["unindexed"],
            "coverage": coverage,
        },
    )


@router.get("/user/{user_id}/journals/summary")
async def get_journals_summary(user_id: str):
    """
    메인 화면의 일지 카드용 요약.

    색인이 빠진 일지 수를 함께 내보낸다 — 파일은 있는데 검색이 안 되는 상태는
    사용자가 알아챌 방법이 없으므로 첫 화면에서 눈에 띄어야 한다.
    """
    overview = journal_overview(user_id)
    journals = overview["journals"]

    return {
        "total": len(journals),
        "unindexed": overview["unindexed"],
        "latest": journals[0]["date"] if journals else "",
    }


@router.post("/user/{user_id}/journals/{date}/reindex")
async def reindex_journal_endpoint(user_id: str, date: str):
    """파일에 있는 일지를 벡터DB에 다시 등록한다 (색인이 어긋났을 때)."""
    message = reindex_journal(user_id, date)
    return {"success": not message.startswith("❌"), "message": message}


@router.get("/user/{user_id}/journals/status")
async def get_journals_status(user_id: str):
    """
    기간 일지 생성 진행 상황 (화면 폴링용).

    generate_daily_journals 는 날짜별로 하나씩 만드느라 몇 분씩 걸리므로
    백그라운드 스레드에서 돈다. 화면은 이 엔드포인트를 주기적으로 조회한다.
    """
    progress = journal_progress(user_id)

    return {
        "running": progress.get("phase") in ("starting", "writing"),
        "phase": progress.get("phase") or "",
        "progress_text": describe_journal_progress(progress),
        "done": progress.get("done") or 0,
        "total": progress.get("total") or 0,
        "current_date": progress.get("date") or "",
        "written": progress.get("written") or [],
        "skipped": progress.get("skipped") or [],
        "failed": progress.get("failed") or [],
    }


# ── 아래 세 경로는 반드시 /journals/summary·/journals/status 뒤에 둔다.
#    FastAPI 는 등록 순서대로 맞추므로, {date} 를 먼저 두면 'summary' 가
#    날짜로 잡혀 뷰어가 404 를 낸다.

@router.get("/user/{user_id}/journals/download-all")
async def download_all_journals(user_id: str):
    """모든 일지를 zip 으로 내려받는다 (원본 마크다운 그대로)."""
    data, count = journal_archive(user_id)

    if not count:
        raise HTTPException(status_code=404, detail="내려받을 일지가 없습니다")

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{user_id}-journals.zip"'},
    )


@router.get("/user/{user_id}/journals/{date}/download")
async def download_journal(user_id: str, date: str):
    """
    일지 한 편을 마크다운 원본으로 내려받는다.

    렌더된 HTML 이 아니라 원문을 준다 — 옵시디언이나 노션으로 그대로 옮길 수
    있어야 한다.
    """
    view = render_journal(user_id, date)
    if not view:
        raise HTTPException(status_code=404, detail="일지를 찾을 수 없습니다")

    filename = f"{view['date'].replace('-', '.')}_log.md"
    return Response(
        content=view["raw"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/user/{user_id}/journals/{date}")
async def get_journal_view(request: Request, user_id: str, date: str,
                           db: Session = Depends(get_db)):
    """일지 한 편을 읽는 화면 (마크다운 렌더)."""
    controller.get_user_info(db, user_id=user_id)

    view = render_journal(user_id, date)
    if not view:
        raise HTTPException(status_code=404, detail="일지를 찾을 수 없습니다")

    return templates.TemplateResponse(
        request=request,
        name="journal_view.html",
        context={"user_id": user_id, "view": view, "highlight_css": HIGHLIGHT_CSS},
    )


@router.get("/user/{user_id}/sources/status")
async def get_sources_status(user_id: str, db: Session = Depends(get_db)):
    """
    소스별 임베딩 진행 상황 (화면 폴링용).

    임베딩은 백그라운드 스레드에서 돌기 때문에, 화면은 이 엔드포인트를
    주기적으로 조회해 진행률을 갱신한다.
    """
    sources = db.query(Source).filter(
        Source.user_id == user_id,
        Source.is_active == True
    ).order_by(Source.id).all()

    items = []
    for source in sources:
        stats = json.loads(source.embedding_stats) if source.embedding_stats else {}
        running = source.embedding_status == EmbeddingStatus.IN_PROGRESS
        stalled = running and is_stale(source)

        items.append({
            "id": source.id,
            "name": source.name,
            "type": source.type.value,
            "status": "stalled" if stalled else source.embedding_status.value,
            "progress_text": describe_progress(stats) if running and not stalled else "",
            "done": stats.get("done") or 0,
            "total": stats.get("total") or 0,
            "chunks": stats.get("chunks_created") or 0,
            "error": source.embedding_error or "",
            "last_synced_at": (
                source.last_synced_at.strftime("%Y-%m-%d %H:%M")
                if source.last_synced_at else ""
            ),
        })

    # 하나라도 돌고 있으면 화면이 폴링을 계속한다
    return {
        "sources": items,
        "active": any(i["status"] == "in_progress" for i in items),
    }
