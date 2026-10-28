from collections.abc import Callable
from pathlib import Path

import chromadb
import pytest
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings
from fastapi.testclient import TestClient

from app.api.deps import get_embedder, get_vector_store
from app.config import Settings
from app.main import create_app
from app.services.embeddings import Embedder, FakeEmbedder
from app.services.vectorstore import ChromaVectorStore, VectorStore


@pytest.fixture
def api_chroma(tmp_path: Path) -> ClientAPI:
    return chromadb.PersistentClient(
        path=str(tmp_path / "test-chroma"), settings=ChromaSettings(anonymized_telemetry=False)
    )


@pytest.fixture
def api_embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=256)  # fewer hash collisions, so rankings are stable


@pytest.fixture
def api_store(api_chroma: ClientAPI, api_embedder: FakeEmbedder) -> ChromaVectorStore:
    """The vector store every test client uses unless a test passes its own."""
    return ChromaVectorStore(api_chroma, api_embedder)


@pytest.fixture
def make_client(
    tmp_path: Path, api_chroma: ClientAPI, api_embedder: FakeEmbedder, api_store: ChromaVectorStore
) -> Callable[..., TestClient]:
    """Build a client on a throwaway data dir with a fake embedder; never reads .env.

    Pass `embedder=` to swap the embedder (the store is rebuilt around it) or `store=` to swap
    the store. Use the client as a context manager to also run the app's startup.
    """

    def factory(
        *, embedder: Embedder | None = None, store: VectorStore | None = None, **overrides: object
    ) -> TestClient:
        overrides.setdefault("data_dir", tmp_path)
        # _env_file is a runtime-only pydantic-settings argument that pyright can't see
        settings = Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]
        app = create_app(settings)
        if embedder is None:
            embedder, store = api_embedder, store or api_store
        else:
            store = store or ChromaVectorStore(api_chroma, embedder)
        resolved_embedder, resolved_store = embedder, store  # narrowed, for the lambdas
        app.dependency_overrides[get_embedder] = lambda: resolved_embedder
        app.dependency_overrides[get_vector_store] = lambda: resolved_store
        return TestClient(app)

    return factory


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
