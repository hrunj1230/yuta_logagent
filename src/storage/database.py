from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = "sqlite:///users.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=True
)

SessionLocal = sessionmaker(bind=engine)

# 기존 DB에 나중에 추가된 컬럼. create_all은 이미 존재하는 테이블을 변경하지 않으므로
# 여기에 적어 두고 시작할 때 채워 넣는다. (테이블명, 컬럼명, DDL 타입)
_ADDED_COLUMNS = [
    ("sources", "embedding_started_at", "DATETIME"),
]


def _apply_column_migrations():
    """모델에 추가된 컬럼을 기존 테이블에 반영한다 (이미 있으면 건너뜀)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl_type in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue  # create_all이 새로 만들었으므로 컬럼이 이미 포함되어 있다
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            print(f"마이그레이션: {table}.{column} 컬럼 추가")


def init_db():
    """base를 상속한 모델의 테이블 생성"""
    Base.metadata.create_all(engine)
    _apply_column_migrations()
    print("db준비완료")
def get_db():
    """요청마다 session을 하나 만들어주고 끝나면 닫기"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



