import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from src.router import router
from storage.database import init_db

load_dotenv() #env
init_db() #데이터베이스 초기화

app = FastAPI(title="log_maker")

app.include_router(router)
