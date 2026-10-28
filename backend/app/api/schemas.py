from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import DocumentStatus, MessageRole
from app.services.parsers import FileKind

# Long enough for any real question; stops one request filling the token budget
MAX_QUESTION_CHARS = 4000


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class WorkspaceUpdate(WorkspaceCreate):
    pass


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class LocationOut(BaseModel):
    """Which fields are set depends on `kind`; see `services.parsers.Location`."""

    kind: FileKind
    page: int | None = None
    page_end: int | None = None
    heading: str | None = None
    start: int | None = None
    end: int | None = None


class CitationOut(BaseModel):
    """A source shown to the model as `[number]`. `label` is the location in words."""

    number: int
    document_id: str
    filename: str
    location: LocationOut
    label: str
    text: str
    score: float


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: MessageRole
    content: str
    citations: list[CitationOut]
    refused: bool
    uncited: bool
    incomplete: bool
    created_at: datetime
