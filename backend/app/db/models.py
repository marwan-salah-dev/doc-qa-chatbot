import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite drops tzinfo; store UTC and hand back aware datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    # The seeded demo: read-only for visitors and the only one with starter questions
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # SHA-256 of the creating visitor's id (public demo only; the id itself is never stored)
    owner_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    # Visitor workspaces are deleted after this; None = kept
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )


class Document(Base):
    __tablename__ = "documents"
    # The same file can't be indexed twice in one workspace
    __table_args__ = (UniqueConstraint("workspace_id", "sha256"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=DocumentStatus.PENDING,
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    workspace: Mapped["Workspace"] = relationship(back_populates="documents")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)
    # As Workspace.owner_hash: whose chat this is on the public demo
    owner_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    workspace: Mapped["Workspace"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    content: Mapped[str] = mapped_column(Text)
    # The sources an assistant answer cites, as `services.chat.citation_dict` shapes them
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # The "not found in your documents" reply
    refused: Mapped[bool] = mapped_column(Boolean, default=False)
    # A finished answer that cites no source, so it may not be grounded
    uncited: Mapped[bool] = mapped_column(Boolean, default=False)
    # The client left mid-answer (usually the Stop button); this is what had streamed
    incomplete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class LlmUsageDay(Base):
    """LLM tokens used by all chats on one UTC day, for the public demo's daily cap."""

    __tablename__ = "llm_usage_days"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    tokens: Mapped[int] = mapped_column(Integer, default=0)
