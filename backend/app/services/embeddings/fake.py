import hashlib
import math
import re

from app.services.chunking import estimate_tokens
from app.services.embeddings.base import model_slug

_WORD = re.compile(r"\w+")


class FakeEmbedder:
    """Offline embedder for tests: hashed bag of words, so texts sharing words score closer."""

    def __init__(self, dimension: int = 64, max_tokens: int = 512) -> None:
        self.dimension = dimension
        self.model_name = "fake-embedder"
        self.max_tokens = max_tokens

    @property
    def slug(self) -> str:
        return model_slug(self.model_name)

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in _WORD.findall(text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            vector[0] = 1.0  # empty text still gets a valid unit vector
            return vector
        return [x / norm for x in vector]
