from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
from src.router import router
from src.storage.database import init_db
load_dotenv()


# 데이터베이스 초기화 (테이블이 없으면 자동 생성)
init_db()

app = FastAPI(title="나의 사관일지")

# 라우터 등록 (/, /login-form, /user, /unified_agent 등)
app.include_router(router)
