from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Enum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

class SourceType(str, enum.Enum):
    GIT = "git"
    LOCAL_TIL = "local_til"
    AGENT_CHATLOG = "agent_chatlog"
    MEMSEARCH = "memsearch"

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(primary_key=True) #id
    sources: Mapped[list["Source"]] = relationship()

"""디깅"""
class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))          # "내 TIL 레포"
    type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    location: Mapped[str] = mapped_column(Text)             # url 또는 로컬 경로

    last_synced_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (UniqueConstraint("user_id", "type", "location"),)