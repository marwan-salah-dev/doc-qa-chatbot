from collections.abc import AsyncGenerator, Sequence
from typing import Any

import httpx2  # the HTTP library the SDK is built on; a dropped stream surfaces as its errors
import openai

from app.services.llm.base import (
    CONNECT_TIMEOUT_SECONDS,
    ChatMessage,
    Usage,
    UsageCallback,
    report_usage,
)
from app.services.llm.errors import LLMError, provider_error

PROVIDER = "openai"


def _map_error(exc: openai.APIError | httpx2.TransportError) -> LLMError:
    if isinstance(exc, openai.APIStatusError):
        return provider_error(PROVIDER, exc, status=exc.status_code, request_id=exc.request_id)
    timed_out = isinstance(exc, openai.APITimeoutError | httpx2.TimeoutException)
    return provider_error(PROVIDER, exc, timed_out=timed_out)


class OpenAIChat:
    """A GPT model through Chat Completions. Retries work as in `AnthropicChat`."""

    def __init__(
        self,
        model_name: str,
        api_key: str = "",
        client: Any = None,
        *,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        max_output_tokens: int = 1024,
    ) -> None:
        if client is None:
            client = openai.AsyncOpenAI(
                api_key=api_key,
                timeout=openai.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
                max_retries=max_retries,
            )
        self.model_name = model_name
        self._client = client
        self._max_output_tokens = max_output_tokens

    def _request(
        self, messages: Sequence[ChatMessage], system: str, max_tokens: int | None
    ) -> dict[str, Any]:
        chat = [{"role": m.role, "content": m.content} for m in messages]
        if system:
            chat.insert(0, {"role": "system", "content": system})
        return {
            "model": self.model_name,
            "messages": chat,
            # gpt-5 models reject the older `max_tokens`
            "max_completion_tokens": max_tokens or self._max_output_tokens,
        }

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
            response = await self._client.chat.completions.create(
                **self._request(messages, system, max_tokens),
                stream=True,
                stream_options={"include_usage": True},
            )
            # As in AnthropicChat: closing this generator early closes the HTTP response.
            async with response as chunks:
                opened = True
                async for chunk in chunks:
                    if chunk.usage:  # only the last chunk, which has no choices
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens
                    for choice in chunk.choices:
                        if choice.delta.content:
                            yield choice.delta.content
            finished = True
        except (openai.APIError, httpx2.TransportError) as exc:
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
            response = await self._client.chat.completions.create(
                **self._request(messages, system, max_tokens)
            )
        except (openai.APIError, httpx2.TransportError) as exc:
            raise _map_error(exc) from exc
        usage = Usage(response.usage.prompt_tokens, response.usage.completion_tokens, complete=True)
        report_usage(PROVIDER, self.model_name, usage, on_usage)
        return response.choices[0].message.content or ""

    async def aclose(self) -> None:
        await self._client.close()
