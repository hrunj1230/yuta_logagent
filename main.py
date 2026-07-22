from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

load_dotenv()
from src.router import router
from storage.database import init_db

# 데이터베이스 초기화 (테이블이 없으면 자동 생성)
init_db()

app = FastAPI(title="log_maker")

# 라우터 등록 (/, /login-form, /user, /log-maker 등)
app.include_router(router)
