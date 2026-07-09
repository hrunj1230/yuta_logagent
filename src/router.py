from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import src.controller as controller
import uuid

router = APIRouter()

#class
class QueryReq(BaseModel):
    req: str
    thread_id: str
class QueryRes(BaseModel):
    res: str
    thread_id: str

#router
@router.post("/call_agent")
async def call_agent(req: QueryReq):
    thread_id = req.thread_id or str(uuid.uuid4())
    res = controller.main(req)
    return res
