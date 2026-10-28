from typing import Any

from app.services.chunking import estimate_tokens
from app.services.embeddings.base import model_slug

# Input limit of the text-embedding-3 models.
OPENAI_MAX_TOKENS = 8191
_DEFAULT_BATCH_SIZE = 100


class OpenAIEmbedder:
    """Embeds through the OpenAI API (needs a key; keeps server memory low)."""

    def __init__(
        self,
        model_name: str,
        api_key: str = "",
        client: Any = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.max_tokens = OPENAI_MAX_TOKENS
        self._client = client
        self._batch_size = batch_size

    @property
    def slug(self) -> str:
        return model_slug(self.model_name)

    def count_tokens(self, text: str) -> int:
        # An estimate is enough: the 8191-token limit is far above any sensible chunk size.
        return estimate_tokens(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._client.embeddings.create(model=self.model_name, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend([float(x) for x in item.embedding] for item in ordered)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
