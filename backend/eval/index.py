"""Index the committed demo files in memory, the way ingestion does, with no server or database."""

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings
from app.services.chunking import TokenCounter, chunk_segments
from app.services.embeddings import Embedder, create_embedder, ensure_chunk_fits
from app.services.parsers import parse_document
from app.services.vectorstore import ChromaVectorStore
from scripts.seed_demo import DEMO_DATA_DIR, DEMO_FILES

DEMO_WORKSPACE_ID = "eval"


def index_demo_docs(
    store: ChromaVectorStore,
    *,
    count_tokens: TokenCounter,
    chunk_size: int = 350,
    chunk_overlap: int = 50,
) -> int:
    """Parse, chunk and store the demo files under `DEMO_WORKSPACE_ID`; returns the chunk count."""
    total = 0
    for filename in DEMO_FILES:
        segments = parse_document(filename, (DEMO_DATA_DIR / filename).read_bytes())
        chunks = chunk_segments(
            segments, max_tokens=chunk_size, overlap_tokens=chunk_overlap, count_tokens=count_tokens
        )
        # The file name doubles as the document id: one copy of each file
        total += store.add_chunks(DEMO_WORKSPACE_ID, filename, filename, chunks)
    return total


def build_demo_store(settings: Settings) -> tuple[Embedder, ChromaVectorStore, int]:
    """The configured embedder over an in-memory Chroma holding the demo files."""
    embedder = create_embedder(settings)
    ensure_chunk_fits(embedder, settings.chunk_size_tokens)
    client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
    store = ChromaVectorStore(client, embedder)
    store.delete_workspace(DEMO_WORKSPACE_ID)  # the in-memory client is shared per process
    chunks = index_demo_docs(
        store,
        count_tokens=embedder.count_tokens,
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
    )
    return embedder, store, chunks
