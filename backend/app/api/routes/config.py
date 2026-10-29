from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AppSettings

router = APIRouter(tags=["config"])


class ConfigOut(BaseModel):
    """The settings the UI needs to behave like the server (so it never keeps its own copy)."""

    max_upload_mb: int


@router.get("/config", response_model=ConfigOut)
def get_config(settings: AppSettings) -> ConfigOut:
    return ConfigOut(max_upload_mb=settings.max_upload_mb)
