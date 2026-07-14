from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import src.controller as controller
from src.tools import embedding_file
import uuid
import subprocess
import shutil
import os

router = APIRouter()

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

#router
@router.post("/call_agent")
async def call_agent(req: QueryReq):
    thread_id = req.thread_id or str(uuid.uuid4())
    res = controller.main(req)
    return res

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
