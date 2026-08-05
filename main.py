from fastapi import FastAPI
from dotenv import load_dotenv
from src.router import router
from src.storage.database import init_db

load_dotenv()
init_db()
app = FastAPI(title="나의 사관일지")
app.include_router(router)
