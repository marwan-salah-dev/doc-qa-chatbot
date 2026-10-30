from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/.env, so the same file loads whether commands run from backend/ or the repo root
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Chat model. Keys are SecretStr so a repr, log line or traceback shows ********** instead.
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5-mini"
    # Empty = api.openai.com; set to use an OpenAI-compatible provider such as Groq
    openai_base_url: str = ""
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_output_tokens: int = Field(default=1024, gt=0)

    # Embeddings
    embedding_provider: Literal["local", "openai"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_embedding_model: str = "text-embedding-3-small"

    # Chunking (estimated tokens; keep chunk_size_tokens under the embedding model's input limit)
    chunk_size_tokens: int = Field(default=350, gt=0)
    chunk_overlap_tokens: int = Field(default=50, ge=0)

    # Answering (RAG)
    rag_top_k: int = Field(default=6, gt=0)
    # Errs low on purpose (eval/retrieval.py, bge-small, 2026-10-30): English answerable questions
    # score >= 0.559 and off-topic ones <= 0.461, so 0.51 would be the midpoint, but that margin
    # rests on only 4 off-topic questions, and 0.51 refuses 4 of 6 Arabic/French/Spanish
    # questions (2 of them had the right section retrieved) before the LLM sees them. At 0.45 an
    # off-topic question that slips through costs one LLM call, and the LLM still refuses it.
    rag_min_score: float = Field(default=0.45, ge=0, le=1)
    rag_token_budget: int = Field(default=5500, gt=0)
    rag_history_tokens: int = Field(default=1000, ge=0)

    # Uploads
    max_upload_mb: int = Field(default=20, gt=0)

    # Storage
    data_dir: Path = Path("./data")
    chroma_host: str = ""
    chroma_port: int = 8000

    # Web
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    admin_api_key: SecretStr = SecretStr("")

    # Public demo hardening. Nothing below applies unless public_demo is on; 0 turns a limit off.
    public_demo: bool = False
    rate_limit_chat_per_minute: int = Field(default=5, ge=0)
    rate_limit_chat_per_day: int = Field(default=100, ge=0)
    rate_limit_uploads_per_hour: int = Field(default=10, ge=0)
    rate_limit_conversations_per_hour: int = Field(default=30, ge=0)
    # New workspaces per client IP per 24 hours
    visitor_workspaces_per_ip: int = Field(default=3, ge=0)
    visitor_workspace_ttl_hours: float = Field(default=24, gt=0)
    max_documents_per_workspace: int = Field(default=10, ge=0)
    max_document_chunks: int = Field(default=300, ge=0)
    max_visitor_storage_mb: int = Field(default=500, ge=0)
    # Input + output tokens across every chat, per UTC day; below Groq's free 200K
    daily_token_cap: int = Field(default=150_000, ge=0)
    cleanup_interval_minutes: float = Field(default=10, gt=0)

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def check_chunk_overlap(self) -> Self:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        return self

    @model_validator(mode="after")
    def check_rag_token_budget(self) -> Self:
        if self.rag_token_budget <= self.llm_max_output_tokens:
            raise ValueError(
                "RAG_TOKEN_BUDGET must be larger than LLM_MAX_OUTPUT_TOKENS (it includes them)"
            )
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
