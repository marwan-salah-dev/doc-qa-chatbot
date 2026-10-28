import re
from typing import Protocol


class Embedder(Protocol):
    """Turns text into vectors. Documents and queries are embedded separately because some
    models (like bge) want a different treatment for a search query than for a passage."""

    model_name: str
    max_tokens: int
    """Longest input the model embeds in full; anything past this is silently cut off."""

    @property
    def slug(self) -> str:
        """Short, collection-name-safe id of the model (vectors from different models never mix)."""
        ...

    def count_tokens(self, text: str) -> int:
        """How many tokens this model sees for `text`, special tokens included."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def ensure_chunk_fits(embedder: Embedder, chunk_size_tokens: int) -> None:
    """Fail at startup, not by quietly truncating text, if chunks can outgrow the model."""
    if chunk_size_tokens > embedder.max_tokens:
        raise ValueError(
            f"CHUNK_SIZE_TOKENS={chunk_size_tokens} is over the {embedder.max_tokens}-token "
            f"input limit of {embedder.model_name}; lower it"
        )


def model_slug(model_name: str) -> str:
    """`BAAI/bge-small-en-v1.5` -> `bge-small-en-v1-5`: lowercase letters, digits and dashes."""
    name = model_name.rsplit("/", 1)[-1].lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")
