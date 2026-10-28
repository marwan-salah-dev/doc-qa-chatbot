from dataclasses import dataclass
from typing import Protocol

from app.services.chunking import Chunk
from app.services.parsers import Location


@dataclass(frozen=True, slots=True)
class StoredChunk:
    """A chunk as it comes back from the store, with everything a citation needs."""

    document_id: str
    filename: str
    index: int
    text: str
    location: Location


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A retrieved chunk and how well it matches the question.

    `score` is cosine similarity (1 - cosine distance) clamped to 0..1, higher is better.
    Raw cosine similarity can go down to -1 for vectors pointing opposite ways; anything at or
    below 0 is unrelated for retrieval purposes, so it is reported as 0.
    """

    chunk: StoredChunk
    score: float


class VectorStore(Protocol):
    """Stores chunk vectors per workspace and finds the closest ones to a question.

    Callers pass text and ids only; the store embeds through its `Embedder`.
    """

    def add_chunks(
        self, workspace_id: str, document_id: str, filename: str, chunks: list[Chunk]
    ) -> int:
        """Replace all of a document's chunks with `chunks`; returns how many were stored."""
        ...

    def query(self, workspace_id: str, question: str, k: int = 5) -> list[SearchHit]:
        """Up to `k` closest chunks, best first. Empty when the workspace has none."""
        ...

    def delete_document(self, workspace_id: str, document_id: str) -> None: ...

    def delete_workspace(self, workspace_id: str) -> None: ...
