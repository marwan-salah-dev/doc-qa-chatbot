import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings

from app.config import Settings
from app.services.embeddings import Embedder
from app.services.vectorstore.base import SearchHit, StoredChunk, VectorStore
from app.services.vectorstore.chroma import ChromaVectorStore


def create_chroma_client(settings: Settings) -> ClientAPI:
    """Chroma server when CHROMA_HOST is set (Docker), otherwise an embedded one in DATA_DIR."""
    chroma_settings = ChromaSettings(anonymized_telemetry=False)
    if settings.chroma_host:
        return chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port, settings=chroma_settings
        )
    return chromadb.PersistentClient(
        path=str(settings.data_dir / "chroma"), settings=chroma_settings
    )


def create_vector_store(settings: Settings, embedder: Embedder) -> VectorStore:
    return ChromaVectorStore(create_chroma_client(settings), embedder)


__all__ = [
    "ChromaVectorStore",
    "SearchHit",
    "StoredChunk",
    "VectorStore",
    "create_chroma_client",
    "create_vector_store",
]
