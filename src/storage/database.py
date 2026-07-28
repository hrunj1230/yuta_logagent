from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = "sqlite:///users.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=True
)

SessionLocal = sessionmaker(bind=engine)

def init_db():
    """base를 상속한 모델의 테이블 생성"""
    Base.metadata.create_all(engine)
    print("db준비완료")
def get_db():
    """요청마다 session을 하나 만들어주고 끝나면 닫기"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



