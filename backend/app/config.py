from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Chat model
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_model: str = ""

    # Embeddings
    embedding_provider: Literal["local", "openai"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_embedding_model: str = "text-embedding-3-small"

    # Chunking (estimated tokens; keep chunk_size_tokens under the embedding model's input limit)
    chunk_size_tokens: int = Field(default=350, gt=0)
    chunk_overlap_tokens: int = Field(default=50, ge=0)

    # Storage
    data_dir: Path = Path("./data")
    chroma_host: str = ""
    chroma_port: int = 8000

    # Web
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    admin_api_key: str = ""

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def check_chunk_overlap(self) -> Self:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
