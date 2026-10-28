from app.config import Settings
from app.services.llm.anthropic import AnthropicChat
from app.services.llm.base import ChatMessage, ChatModel, Usage, UsageCallback
from app.services.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.llm.fake import FakeCall, FakeChat
from app.services.llm.openai import OpenAIChat


def _require(value: str, env_var: str, provider: str) -> None:
    if not value:
        raise LLMConfigError(f"LLM_PROVIDER={provider} needs {env_var} to be set")


def create_chat_model(settings: Settings) -> ChatModel:
    """Pick the chat model named by LLM_PROVIDER. Fails at startup if its key or model is unset."""
    if settings.llm_provider == "openai":
        api_key = settings.openai_api_key.get_secret_value()
        _require(api_key, "OPENAI_API_KEY", "openai")
        _require(settings.openai_model, "OPENAI_MODEL", "openai")
        return OpenAIChat(
            settings.openai_model,
            api_key=api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    api_key = settings.anthropic_api_key.get_secret_value()
    _require(api_key, "ANTHROPIC_API_KEY", "anthropic")
    _require(settings.anthropic_model, "ANTHROPIC_MODEL", "anthropic")
    return AnthropicChat(
        settings.anthropic_model,
        api_key=api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
        effort=settings.anthropic_effort,
    )


__all__ = [
    "AnthropicChat",
    "ChatMessage",
    "ChatModel",
    "FakeCall",
    "FakeChat",
    "LLMAuthError",
    "LLMBadRequestError",
    "LLMConfigError",
    "LLMError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "OpenAIChat",
    "Usage",
    "UsageCallback",
    "create_chat_model",
]
