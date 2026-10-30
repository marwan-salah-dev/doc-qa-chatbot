from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.rust import RustBindingsAPI
from chromadb.config import Settings as ChromaSettings
from chromadb.config import System

from app.config import Settings
from app.services.embeddings import Embedder
from app.services.vectorstore.base import SearchHit, StoredChunk, VectorStore
from app.services.vectorstore.chroma import ChromaVectorStore

# Chroma's own default for the pool when it runs as a server
HNSW_INDEX_POOL_SIZE = 65536


def _keep_hnsw_indexes_resident() -> None:
    """Give every embedded Chroma client an HNSW index pool that never evicts in practice.

    Chroma 1.5.9 keeps an index under 1000 vectors only in memory, and evicting one does not
    write it to disk, so that collection then fails every query with "Nothing found on disk".
    The embedded client sizes the pool from the file-handle limit (102 slots on Windows, split
    across 64 shards), which two small workspaces can already overflow. There is no setting for
    it, and Chroma rejects a custom `chroma_api_impl`, so set the size after its constructor.
    """
    stock_init = RustBindingsAPI.__init__

    def init(self: RustBindingsAPI, system: System) -> None:
        stock_init(self, system)
        self.hnsw_cache_size = HNSW_INDEX_POOL_SIZE

    RustBindingsAPI.__init__ = init


_keep_hnsw_indexes_resident()


def create_persistent_chroma_client(path: Path) -> ClientAPI:
    """Embedded Chroma in `path`. Use this for every embedded client, so all share one pool size."""
    return chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def create_chroma_client(settings: Settings) -> ClientAPI:
    """Chroma server when CHROMA_HOST is set (Docker), otherwise an embedded one in DATA_DIR."""
    if settings.chroma_host:
        return chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return create_persistent_chroma_client(settings.data_dir / "chroma")


def create_vector_store(settings: Settings, embedder: Embedder) -> VectorStore:
    return ChromaVectorStore(create_chroma_client(settings), embedder)


__all__ = [
    "ChromaVectorStore",
    "SearchHit",
    "StoredChunk",
    "VectorStore",
    "create_chroma_client",
    "create_persistent_chroma_client",
    "create_vector_store",
]
