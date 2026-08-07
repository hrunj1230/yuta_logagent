from fastapi import FastAPI
from dotenv import load_dotenv
from src.router import router
from src.storage.database import init_db
from src.mcp_server import mcp

load_dotenv()
init_db()
app = FastAPI(title="나의 사관일지")
app.include_router(router)

# MCP 서버 마운트
# Claude Desktop 연결: { "url": "http://3.106.155.36:8000/mcp" }
app.mount("/mcp", mcp.http_app(transport="streamable-http", path="/"))