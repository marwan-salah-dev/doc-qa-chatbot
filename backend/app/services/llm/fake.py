import re
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from app.services.llm.base import ChatMessage, Usage, UsageCallback, report_usage
from app.services.llm.errors import LLMError

# Each word with its trailing space, so the deltas join back into the exact text.
_DELTA = re.compile(r"\S+\s*|\s+")


@dataclass(frozen=True)
class FakeCall:
    messages: list[ChatMessage]
    system: str
    max_tokens: int | None


class FakeChat:
    """Offline chat model for tests: replies with canned text and records every call.

    `responses` are used in order, one per call, and the last one repeats. With `error`, a
    stream raises it after `error_after` deltas (and `complete` raises it straight away).
    """

    def __init__(
        self,
        responses: str | Sequence[str] = "This is a fake answer.",
        *,
        error: LLMError | None = None,
        error_after: int = 0,
        usage: Usage = Usage(input_tokens=10, output_tokens=5, complete=True),  # noqa: B008
    ) -> None:
        self.model_name = "fake-chat"
        self.calls: list[FakeCall] = []
        self._responses = [responses] if isinstance(responses, str) else list(responses)
        self._error = error
        self._error_after = error_after
        self._usage = usage

    def _record(self, messages: Sequence[ChatMessage], system: str, max_tokens: int | None) -> str:
        self.calls.append(FakeCall(list(messages), system, max_tokens))
        return self._responses[min(len(self.calls), len(self._responses)) - 1]

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        text = self._record(messages, system, max_tokens)
        finished = False
        try:
            for index, delta in enumerate(_DELTA.findall(text)):
                if self._error and index == self._error_after:
                    raise self._error
                yield delta
            if self._error:
                raise self._error
            finished = True
        finally:
            usage = self._usage if finished else Usage(self._usage.input_tokens, None, False)
            report_usage("fake", self.model_name, usage, on_usage)

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> str:
        text = self._record(messages, system, max_tokens)
        if self._error:
            raise self._error
        report_usage("fake", self.model_name, self._usage, on_usage)
        return text

    async def aclose(self) -> None:
        return None
