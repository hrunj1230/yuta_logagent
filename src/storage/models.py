from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Enum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

class SourceType(str, enum.Enum):
    GIT = "git"
    GIT_LOG = "git_log"
    LOCAL = "local"
    AGENT_CHATLOG = "agent_chatlog"
    MEMSEARCH = "memsearch"

class EmbeddingStatus(str, enum.Enum):
    """임베딩 진행 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

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

    # 새로 추가되는 필드
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus),
        default=EmbeddingStatus.PENDING
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_stats: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 백그라운드 임베딩 시작 시각.
    # 서버가 작업 도중 죽으면 상태가 IN_PROGRESS로 남아 재시도가 막히므로,
    # 이 값으로 경과 시간을 재어 오래된 작업을 자동으로 해제한다.
    embedding_started_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "type", "location"),)