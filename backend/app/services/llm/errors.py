import logging

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base for every chat model failure. `user_message` is safe to show in the UI."""

    user_message = "The assistant is unavailable right now. Please try again."


class LLMConfigError(LLMError):
    user_message = "The assistant is not configured correctly."


class LLMAuthError(LLMError):
    user_message = "The assistant is not configured correctly."


class LLMRateLimitError(LLMError):
    user_message = "The assistant is busy. Please try again in a moment."


class LLMTimeoutError(LLMError):
    user_message = "The assistant took too long to respond. Please try again."


class LLMBadRequestError(LLMError):
    user_message = "That question could not be processed."


class LLMUnavailableError(LLMError):
    pass


def _error_for_status(status: int) -> type[LLMError]:
    if status in (401, 403):
        return LLMAuthError
    if status == 429:
        return LLMRateLimitError
    if status == 408:
        return LLMTimeoutError
    if 400 <= status < 500:
        return LLMBadRequestError
    return LLMUnavailableError  # 5xx, Anthropic's 529 "overloaded", or an error mid-stream


def provider_error(
    provider: str,
    exc: Exception,
    *,
    timed_out: bool = False,
    status: int | None = None,
    request_id: str | None = None,
) -> LLMError:
    """Turn an SDK exception into ours. Only the class, status and request id are kept: the
    SDK's own message can quote the request, so it is neither logged nor passed on."""
    if timed_out:
        error_type: type[LLMError] = LLMTimeoutError
    elif status is not None:
        error_type = _error_for_status(status)
    else:
        error_type = LLMUnavailableError
    logger.warning(
        "llm request failed",
        extra={
            "provider": provider,
            "error": type(exc).__name__,
            "status": status,
            "request_id": request_id,
        },
    )
    detail = f" (HTTP {status})" if status is not None else ""
    return error_type(f"{provider} request failed: {type(exc).__name__}{detail}")
