from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import DocumentStatus


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
