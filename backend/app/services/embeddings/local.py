import threading
from collections.abc import Callable
from typing import Any

from app.services.embeddings.base import model_slug

# Longest input BAAI/bge-small-en-v1.5 embeds; anything past this is silently dropped.
LOCAL_MODEL_MAX_TOKENS = 512

# BAAI recommends this prefix on search queries (never on passages) for retrieval.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _load_sentence_transformer(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _load_tokenizer(model_name: str) -> Any:
    # Fetches only tokenizer.json; the `tokenizers` library does not import torch.
    from tokenizers import Tokenizer

    return Tokenizer.from_pretrained(model_name)


class LocalEmbedder:
    """Runs a sentence-transformers model on this machine (free, no API key, CPU is fine)."""

    def __init__(
        self,
        model_name: str,
        model_loader: Callable[[str], Any] = _load_sentence_transformer,
        tokenizer_loader: Callable[[str], Any] = _load_tokenizer,
        max_tokens: int = LOCAL_MODEL_MAX_TOKENS,
    ) -> None:
        self.model_name = model_name
        self.max_tokens = max_tokens
        self._model_loader = model_loader
        self._tokenizer_loader = tokenizer_loader
        self._model: Any = None
        self._tokenizer: Any = None
        # Uploads are indexed on a threadpool; without these, two arriving together could both
        # load the model, doubling the memory spike. One lock each, so counting tokens never
        # waits for the much slower model load.
        self._model_lock = threading.Lock()
        self._tokenizer_lock = threading.Lock()
        self._query_prefix = BGE_QUERY_PREFIX if "bge-" in model_name.lower() else ""

    @property
    def slug(self) -> str:
        return model_slug(self.model_name)

    def count_tokens(self, text: str) -> int:
        """Real token count from the model's own tokenizer, [CLS] and [SEP] included."""
        if self._tokenizer is None:
            with self._tokenizer_lock:
                if self._tokenizer is None:  # another thread may have loaded it while we waited
                    tokenizer = self._tokenizer_loader(self.model_name)
                    # The saved config may cap or pad inputs at 512; we want the true length.
                    tokenizer.no_truncation()
                    tokenizer.no_padding()
                    self._tokenizer = tokenizer  # only published once fully configured
        return len(self._tokenizer.encode(text).ids)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:  # loading takes seconds, so only do it when first needed
            with self._model_lock:
                if self._model is None:  # another thread may have loaded it while we waited
                    self._model = self._model_loader(self.model_name)
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in vector] for vector in vectors]
