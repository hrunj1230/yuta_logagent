from sqlalchemy.orm import Session
from storage.models import User
from typing import Optional

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """ID로 사용자 조회"""
    return db.query(User).filter(User.user_id == user_id).first()

def create_user(db: Session, user_id: str) -> User:
    """새 사용자 생성"""
    user = User(user_id=user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def login_or_register(db: Session, user_id: str) -> User:
    """로그인 또는 자동 회원가입 (패스워드 없음)"""
    user = get_user_by_id(db, user_id)

    if user:
        # 기존 사용자 로그인
        return user
    else:
        # 신규 사용자 자동 생성
        return create_user(db, user_id)
