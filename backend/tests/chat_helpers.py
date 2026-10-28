"""Shared helpers for the chat API and chat service tests."""

import asyncio
import json
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from app.services.chunking import Chunk
from app.services.llm import ChatMessage, UsageCallback
from app.services.parsers import Location
from app.services.vectorstore import VectorStore

FAQ_DOC = "f" * 32
HANDBOOK_DOC = "h" * 32

REFUNDS = "Refunds are processed within 5 business days of the return arriving."
SHIPPING = "Shipping is free on orders over 50 dollars."
HOURS = "Our office hours are 9 to 5 Monday to Friday."

# With the bag-of-words fake embedder, QUESTION scores ~0.49 on REFUNDS and everything else
# scores under 0.3; OFF_TOPIC's best score is ~0.23. So 0.3 keeps one source or refuses.
MIN_SCORE = 0.3
QUESTION = "How many business days until refunds are processed?"
OFF_TOPIC = "What colour is the company van?"
CITED_REPLY = "Refunds are processed within 5 business days [1]."


def seed_documents(store: VectorStore, workspace_id: str) -> None:
    store.add_chunks(
        workspace_id,
        FAQ_DOC,
        "faq.txt",
        [
            Chunk(REFUNDS, Location(kind="txt", start=1, end=2), 0),
            Chunk(SHIPPING, Location(kind="txt", start=3, end=4), 1),
        ],
    )
    store.add_chunks(
        workspace_id, HANDBOOK_DOC, "handbook.pdf", [Chunk(HOURS, Location(kind="pdf", page=2), 0)]
    )


def parse_sse(text: str) -> list[tuple[str, Any]]:
    """`(event, data)` pairs from an SSE body; keep-alive comments are skipped."""
    events: list[tuple[str, Any]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data.append(line.removeprefix("data: "))
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


def event_names(events: list[tuple[str, Any]]) -> list[str]:
    return [name for name, _ in events]


def answer_of(events: list[tuple[str, Any]]) -> str:
    return "".join(data["text"] for name, data in events if name == "delta")


class ScriptedChat:
    """A chat model that streams exactly these deltas, split the way a real provider splits."""

    def __init__(self, deltas: Sequence[str]) -> None:
        self.model_name = "scripted-chat"
        self._deltas = list(deltas)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        for delta in self._deltas:
            yield delta

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> str:
        return "".join(self._deltas)

    async def aclose(self) -> None:
        return None


class BlockingChat:
    """A chat model whose first stream sends one delta, then waits until `release` is set.

    `streaming` is set once that first delta is out. Later streams never wait.
    """

    def __init__(self, reply: str = "Five business days [1]. Keep your receipt.") -> None:
        self.model_name = "blocking-chat"
        self.streaming = asyncio.Event()
        self.release = asyncio.Event()
        self.stream_calls = 0
        self._deltas = [word + " " for word in reply.split(" ")]
        self._deltas[-1] = self._deltas[-1].rstrip()

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> AsyncGenerator[str, None]:
        self.stream_calls += 1
        first, *rest = self._deltas
        yield first
        if self.stream_calls == 1:
            self.streaming.set()
            await self.release.wait()
        for delta in rest:
            yield delta

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str = "",
        max_tokens: int | None = None,
        on_usage: UsageCallback | None = None,
    ) -> str:
        return messages[-1].content

    async def aclose(self) -> None:
        return None
