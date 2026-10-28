from app.config import Settings
from app.services.embeddings.base import Embedder, ensure_chunk_fits, model_slug
from app.services.embeddings.fake import FakeEmbedder
from app.services.embeddings.local import BGE_QUERY_PREFIX, LOCAL_MODEL_MAX_TOKENS, LocalEmbedder
from app.services.embeddings.openai import OpenAIEmbedder


def create_embedder(settings: Settings) -> Embedder:
    """Pick the embedder named by EMBEDDING_PROVIDER."""
    if settings.embedding_provider == "openai":
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai needs OPENAI_API_KEY to be set")
        return OpenAIEmbedder(settings.openai_embedding_model, api_key=api_key)
    return LocalEmbedder(settings.local_embedding_model)


__all__ = [
    "BGE_QUERY_PREFIX",
    "LOCAL_MODEL_MAX_TOKENS",
    "Embedder",
    "FakeEmbedder",
    "LocalEmbedder",
    "OpenAIEmbedder",
    "create_embedder",
    "ensure_chunk_fits",
    "model_slug",
]
