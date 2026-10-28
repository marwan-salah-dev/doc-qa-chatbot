from collections.abc import AsyncGenerator, Sequence
from typing import Any, Literal

import anthropic
import httpx2  # the HTTP library the SDK is built on; a dropped stream surfaces as its errors

from app.services.llm.base import (
    CONNECT_TIMEOUT_SECONDS,
    ChatMessage,
    Usage,
    UsageCallback,
    report_usage,
)
from app.services.llm.errors import LLMError, provider_error

PROVIDER = "anthropic"

Effort = Literal["low", "medium", "high", "xhigh", "max"]


def _map_error(exc: anthropic.APIError | httpx2.TransportError) -> LLMError:
    if isinstance(exc, anthropic.APIStatusError):
        return provider_error(PROVIDER, exc, status=exc.status_code, request_id=exc.request_id)
    timed_out = isinstance(exc, anthropic.APITimeoutError | httpx2.TimeoutException)
    return provider_error(PROVIDER, exc, timed_out=timed_out)


class AnthropicChat:
    """Claude through the Anthropic Messages API.

    The SDK retries 408/409/429/5xx/529 and connection errors with exponential backoff, but only
    until the response starts: a stream that breaks halfway is not retried, since the user would
    see the text twice.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str = "",
        client: Any = None,
        *,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        max_output_tokens: int = 1024,
        effort: Effort = "low",
    ) -> None:
        if client is None:
            client = anthropic.AsyncAnthropic(
                api_key=api_key,
                # For a stream, `read` is the longest gap between chunks, not the whole answer.
                timeout=anthropic.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
                max_retries=max_retries,
            )
        self.model_name = model_name
        self._client = client
        self._max_output_tokens = max_output_tokens
        self._effort = effort

    def _request(
        self, messages: Sequence[ChatMessage], system: str, max_tokens: int | None
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens or self._max_output_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # Low effort keeps a chat answer quick and cheap; thinking stays at the model default.
            "output_config": {"effort": self._effort},
        }
        if system:
            request["system"] = system
        return request

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        input_tokens: int | None = None
        output_tokens: int | None = None
        opened = finished = False
        try:
            # `async with` inside the generator: if the caller stops early, closing the generator
            # exits this block, which closes the HTTP response and stops generation.
            async with self._client.messages.stream(
                **self._request(messages, system, max_tokens)
            ) as events:
                opened = True
                async for event in events:
                    if event.type == "message_start":
                        input_tokens = event.message.usage.input_tokens
                    elif event.type == "message_delta":
                        output_tokens = event.usage.output_tokens
                    elif event.type == "text" and event.text:
                        yield event.text
            finished = True
        except (anthropic.APIError, httpx2.TransportError) as exc:
            raise _map_error(exc) from exc
        finally:
            if opened:
                usage = Usage(input_tokens, output_tokens, complete=finished)
                report_usage(PROVIDER, self.model_name, usage, on_usage)

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> str:
        try:
            response = await self._client.messages.create(
                **self._request(messages, system, max_tokens)
            )
        except (anthropic.APIError, httpx2.TransportError) as exc:
            raise _map_error(exc) from exc
        usage = Usage(response.usage.input_tokens, response.usage.output_tokens, complete=True)
        report_usage(PROVIDER, self.model_name, usage, on_usage)
        return "".join(block.text for block in response.content if block.type == "text")

    async def aclose(self) -> None:
        await self._client.close()
