from fastapi import FastAPI
from dotenv import load_dotenv
from src.router import router
from src.storage.database import init_db
from src.mcp_server import mcp

load_dotenv()
init_db()

# MCP ASGI 앱을 먼저 생성해 lifespan을 FastAPI에 전달해야
# StreamableHTTPSessionManager 태스크 그룹이 초기화된다.
mcp_app = mcp.http_app(transport="streamable-http", path="/")
app = FastAPI(title="나의 사관일지", lifespan=mcp_app.lifespan)
app.include_router(router)

# MCP 서버 마운트
# Claude Desktop 연결: { "url": "http://3.106.155.36:8000/mcp" }
app.mount("/mcp", mcp_app)