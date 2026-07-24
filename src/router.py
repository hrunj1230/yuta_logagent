from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
import src.controller as controller
from src.tools import embedding_file
from storage.database import get_db
import uuid
import subprocess
import shutil
import os

router = APIRouter()

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory="templates")

#class
class QueryReq(BaseModel):
    req: str
    thread_id: str
class QueryRes(BaseModel):
    res: str
    thread_id: str
class EmbeddingReq(BaseModel):
    path: str
class GitSyncReq(BaseModel):
    user_id: str
    repo_url: str
    branch: str = "main"

# 로그인 관련 모델
class LoginRequest(BaseModel):
    user_id: str

class LoginResponse(BaseModel):
    user_id: str
    message: str

class UserInfoResponse(BaseModel):
    user_id: str
    sources_count: int


@router.get("/")
async def login_page(request: Request):
    """로그인 페이지 (HTML Form)"""
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )

@router.get("/log-maker")
async def log_maker_page(request: Request):
    """Git 동기화 & 일지 생성 UI"""
    return templates.TemplateResponse(
        request=request,
        name="log_maker.html"
    )

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
    from storage.models import Source

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
            "sources": sources
        }
    )

@router.post("/user/{user_id}/delete_source/{source_id}")
async def delete_source(user_id: str, source_id: int, db: Session = Depends(get_db)):
    """소스 삭제 API"""
    from storage.models import Source

    source = db.query(Source).filter(
        Source.id == source_id,
        Source.user_id == user_id
    ).first()

    if not source:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")

    db.delete(source)
    db.commit()

    return {"success": True, "message": "소스가 삭제되었습니다"}

@router.get("/user/{user_id}/embeddings")
async def get_embeddings_info(user_id: str):
    """
    사용자의 임베딩 정보 조회 (관리용)
    """
    from langchain_chroma import Chroma
    import src.llm_router as llm_router

    collection_name = f"user_{user_id}"

    try:
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=llm_router.embedding_function,
            client=llm_router.chroma_client
        )

        # 데이터 가져오기
        data = vectorstore.get(include=["metadatas", "documents"])

        total_count = len(data.get("ids", []))

        if total_count == 0:
            return {
                "user_id": user_id,
                "collection_name": collection_name,
                "total_chunks": 0,
                "files": [],
                "message": "임베딩 없음. 첫 동기화를 해주세요."
            }

        # 파일별 그룹화
        file_stats = {}
        for metadata, document in zip(data["metadatas"], data["documents"]):
            source = metadata.get("source", "unknown")
            content_hash = metadata.get("content_hash", "")

            if source not in file_stats:
                file_stats[source] = {
                    "source": source,
                    "chunk_count": 0,
                    "content_hash": content_hash,
                    "total_length": 0
                }

            file_stats[source]["chunk_count"] += 1
            file_stats[source]["total_length"] += len(document)

        return {
            "user_id": user_id,
            "collection_name": collection_name,
            "total_chunks": total_count,
            "total_files": len(file_stats),
            "files": list(file_stats.values()),
            "message": f"{len(file_stats)}개 파일, {total_count}개 청크 임베딩됨"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 조회 실패: {str(e)}")

@router.post("/call_agent")
async def call_agent(req: QueryReq):
    thread_id = req.thread_id or str(uuid.uuid4())
    res = controller.main(req)
    return res

@router.post("/unified_agent")
async def unified_agent_endpoint(user_id: str = Form(...), message: str = Form(...)):
    """
    통합 Agent (Router 기반)
    - Router가 요청을 분석하여 적절한 Agent로 자동 라우팅
    - 소스 관리 + 일지 작성 모두 처리 가능
    """
    res = controller.unified_agent(user_id, message)
    return {"response": res}

@router.post("/source_manager")
async def source_manager(user_id: str = Form(...), message: str = Form(...)):
    """
    소스 관리 대화형 Agent (레거시)
    - 사용자와 대화하면서 소스 추가/조회/삭제
    """
    res = controller.source_manager(user_id, message)
    return {"response": res}

@router.post("/embed")
async def embed_documents(req: EmbeddingReq):
    """파일이나 디렉토리를 임베딩"""
    result = embedding_file.invoke({"path": req.path})
    return {"message": "Embedding complete", "vectorstore": str(result)}

# 새로운 엔드포인트: Git 저장소 동기화
@router.post("/sync_git_repo")
async def sync_git_repo(req: GitSyncReq):
    """
    Git 저장소에서 TIL 가져오기 및 임베딩

    Args:
        user_id: 사용자 식별자
        repo_url: Git 저장소 URL (예: https://github.com/username/Yuta_TIL.git)
        branch: 브랜치 이름 (기본값: main)

    Returns:
        동기화 결과 및 임베딩 정보
    """
    user_dir = f"./repos/{req.user_id}"

    # 기존 디렉토리 삭제
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)

    try:
        # Git clone (shallow clone으로 빠르게)
        print(f"[Git Sync] Cloning {req.repo_url}...")
        result = subprocess.run(
            ["git", "clone", "--branch", req.branch, "--depth", "1", req.repo_url, user_dir],
            check=True,
            capture_output=True,
            text=True
        )

        print(f"[Git Sync] Clone 완료!")

        # 임베딩 (사용자별 컬렉션)
        from src.tools import embedding_file_for_user
        embedding_result = embedding_file_for_user(req.user_id, user_dir)

        return {
            "success": True,
            "message": "Git 동기화 및 임베딩 완료",
            "user_id": req.user_id,
            "repo_url": req.repo_url,
            "branch": req.branch,
            "local_path": user_dir,
            "embedding_result": embedding_result
        }

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        print(f"[Git Sync] 에러: {error_msg}")
        return {
            "success": False,
            "error": "Git clone 실패",
            "details": error_msg,
            "repo_url": req.repo_url
        }
    except Exception as e:
        print(f"[Git Sync] 예상치 못한 에러: {str(e)}")
        return {
            "success": False,
            "error": "동기화 실패",
            "details": str(e)
        }
