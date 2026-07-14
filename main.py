from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import os

load_dotenv()
from src.router import router

app = FastAPI(title="log_maker")
app.include_router(router)

# Static 파일 서빙 (웹 UI)
if os.path.exists("./static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    async def read_index():
        """메인 페이지 - Git 연동 UI"""
        return FileResponse("static/index.html")
