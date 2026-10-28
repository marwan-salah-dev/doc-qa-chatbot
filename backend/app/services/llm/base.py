import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

# Connecting should be quick; a slow connect means the provider is down, not thinking.
CONNECT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    """Tokens one call used. `None` means the provider never told us (the stream was cut short);
    `complete` is False when the answer did not finish."""

    input_tokens: int | None
    output_tokens: int | None
    complete: bool


UsageCallback = Callable[[Usage], None]


class ChatModel(Protocol):
    """A chat LLM. Usage goes to a per-call `on_usage` callback rather than onto the instance,
    because one instance serves every request at once."""

    model_name: str

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield the answer as text deltas. Closing the iterator early (a client disconnect)
        closes the provider stream, so the provider stops generating."""
        ...

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> str: ...

    async def aclose(self) -> None: ...


def report_usage(
    provider: str, model_name: str, usage: Usage, on_usage: UsageCallback | None
) -> None:
    """Log token usage (never content) and hand it to the caller's callback, if any."""
    logger.info(
        "llm usage",
        extra={
            "provider": provider,
            "model": model_name,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "complete": usage.complete,
        },
    )
    if on_usage is None:
        return
    try:
        on_usage(usage)
    except Exception:
        # Usage accounting must never cost the user their answer.
        logger.exception("usage callback failed", extra={"provider": provider})
