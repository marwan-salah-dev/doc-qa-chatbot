import re
from pathlib import Path

import chromadb
import pytest
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings

from app.services.chunking import Chunk
from app.services.embeddings import FakeEmbedder
from app.services.parsers import Location
from app.services.vectorstore import ChromaVectorStore, SearchHit

WS = "a" * 32
WS2 = "b" * 32
DOC = "d" * 32
DOC2 = "e" * 32

# Chroma collection names: 3-63 chars, start and end alphanumeric, [a-zA-Z0-9._-] in between
_VALID_COLLECTION_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,61}[a-zA-Z0-9]")


class RecordingEmbedder(FakeEmbedder):
    """FakeEmbedder that remembers what it was asked to embed."""

    def __init__(self, model_name: str = "fake-embedder") -> None:
        super().__init__(dimension=256)  # fewer hash collisions, so rankings are stable
        self.model_name = model_name
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        return super().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return super().embed_query(text)


class OppositeEmbedder(FakeEmbedder):
    """Queries point the exact opposite way to documents: cosine distance 2."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dimension - 1) for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [-1.0] + [0.0] * (self.dimension - 1)


class SixtyDegreeEmbedder(FakeEmbedder):
    """Queries sit at 60 degrees to documents: cosine similarity exactly 0.5."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] + [0.0] * (self.dimension - 2) for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.5, 0.75**0.5] + [0.0] * (self.dimension - 2)


def txt_chunk(text: str, index: int = 0) -> Chunk:
    return Chunk(text, Location(kind="txt", start=index + 1, end=index + 1), index)


@pytest.fixture
def chroma_client(tmp_path: Path) -> ClientAPI:
    return chromadb.PersistentClient(
        path=str(tmp_path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
    )


@pytest.fixture
def embedder() -> RecordingEmbedder:
    return RecordingEmbedder()


@pytest.fixture
def store(chroma_client: ClientAPI, embedder: RecordingEmbedder) -> ChromaVectorStore:
    return ChromaVectorStore(chroma_client, embedder)


def texts(hits: list[SearchHit]) -> list[str]:
    return [hit.chunk.text for hit in hits]


# --- collection naming ---


def test_collection_name_is_workspace_plus_model_slug(store: ChromaVectorStore):
    assert store.collection_name(WS) == f"ws_{WS}__fake-embedder"


def test_different_embedding_models_use_separate_collections(chroma_client: ClientAPI):
    store_a = ChromaVectorStore(chroma_client, RecordingEmbedder("model-a"))
    store_b = ChromaVectorStore(chroma_client, RecordingEmbedder("model-b"))
    assert store_a.collection_name(WS) != store_b.collection_name(WS)

    store_a.add_chunks(WS, DOC, "faq.txt", [txt_chunk("refund policy")])
    assert store_b.query(WS, "refund policy") == []


def test_long_model_slug_is_hashed_to_a_valid_stable_name(chroma_client: ClientAPI):
    long_a = ChromaVectorStore(chroma_client, RecordingEmbedder("org/" + "a" * 80))
    long_b = ChromaVectorStore(chroma_client, RecordingEmbedder("org/" + "b" * 80))
    name = long_a.collection_name(WS)

    assert len(name) <= 63
    assert _VALID_COLLECTION_NAME.fullmatch(name)
    assert name.startswith(f"ws_{WS}__")
    # Stable across calls and instances, and distinct per model
    again = ChromaVectorStore(chroma_client, RecordingEmbedder("org/" + "a" * 80))
    assert again.collection_name(WS) == name
    assert long_b.collection_name(WS) != name

    long_a.add_chunks(WS, DOC, "faq.txt", [txt_chunk("refund policy")])
    assert texts(long_a.query(WS, "refund policy")) == ["refund policy"]
    long_a.delete_workspace(WS)
    assert long_a.query(WS, "refund policy") == []


# --- add and query ---


def test_query_ranks_the_most_relevant_chunk_first(store: ChromaVectorStore):
    store.add_chunks(
        WS,
        DOC,
        "faq.txt",
        [
            txt_chunk("Office hours are nine to five, Monday to Friday", 0),
            txt_chunk("Our refund policy allows returns within thirty days", 1),
            txt_chunk("Shipping takes three business days", 2),
        ],
    )

    hits = store.query(WS, "what is the refund policy for returns", k=3)

    assert hits[0].chunk.text == "Our refund policy allows returns within thirty days"
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)


def test_identical_text_scores_close_to_one_but_never_above(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk("refund policy")])
    [hit] = store.query(WS, "refund policy")
    assert hit.score == pytest.approx(1.0, abs=1e-4)
    assert hit.score <= 1.0


def test_score_is_cosine_similarity(chroma_client: ClientAPI):
    # With L2 distance instead of cosine this would come out as 0, not 0.5
    store = ChromaVectorStore(chroma_client, SixtyDegreeEmbedder())
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk("anything")])
    [hit] = store.query(WS, "anything")
    assert hit.score == pytest.approx(0.5, abs=1e-4)


def test_score_is_clamped_to_zero_for_opposite_vectors(chroma_client: ClientAPI):
    store = ChromaVectorStore(chroma_client, OppositeEmbedder())
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk("anything")])
    [hit] = store.query(WS, "anything")
    assert hit.score == 0.0


@pytest.mark.parametrize(
    "location",
    [
        Location(kind="pdf", page=3),
        Location(kind="pdf", page=3, page_end=4),
        Location(kind="docx", heading="Refunds", start=2, end=5),
        Location(kind="docx", start=1, end=1),
        Location(kind="txt", start=10, end=20),
    ],
    ids=["pdf-page", "pdf-range", "docx-heading", "docx-no-heading", "txt-lines"],
)
def test_citation_metadata_round_trips(store: ChromaVectorStore, location: Location):
    store.add_chunks(WS, DOC, "handbook.file", [Chunk("refund policy", location, 7)])

    [hit] = store.query(WS, "refund policy")

    assert hit.chunk.document_id == DOC
    assert hit.chunk.filename == "handbook.file"
    assert hit.chunk.index == 7
    assert hit.chunk.text == "refund policy"
    assert hit.chunk.location == location  # None fields come back as None


def test_query_respects_k(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk(f"refund rule {i}", i) for i in range(5)])
    assert len(store.query(WS, "refund rule", k=2)) == 2
    assert len(store.query(WS, "refund rule", k=10)) == 5


def test_query_on_unknown_workspace_returns_nothing(store: ChromaVectorStore):
    assert store.query(WS, "anything") == []


def test_workspaces_are_isolated(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund policy for acme")])
    store.add_chunks(WS2, DOC2, "b.txt", [txt_chunk("refund policy for globex")])

    assert texts(store.query(WS, "refund policy", k=10)) == ["refund policy for acme"]
    assert texts(store.query(WS2, "refund policy", k=10)) == ["refund policy for globex"]


def test_re_adding_a_document_replaces_its_old_chunks(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk(f"old refund text {i}", i) for i in range(5)])
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk(f"new refund text {i}", i) for i in range(3)])

    hits = store.query(WS, "refund text", k=10)

    assert sorted(hit.chunk.index for hit in hits) == [0, 1, 2]
    assert all(hit.chunk.text.startswith("new") for hit in hits)


def test_adding_no_chunks_clears_the_document(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "faq.txt", [txt_chunk("refund policy")])
    assert store.add_chunks(WS, DOC, "faq.txt", []) == 0
    assert store.query(WS, "refund policy") == []


def test_large_documents_are_embedded_and_stored_in_batches(
    chroma_client: ClientAPI, store: ChromaVectorStore, embedder: RecordingEmbedder
):
    chunks = [txt_chunk(f"refund clause {i}", i) for i in range(250)]

    assert store.add_chunks(WS, DOC, "big.txt", chunks) == 250

    assert sum(len(batch) for batch in embedder.document_calls) == 250
    assert max(len(batch) for batch in embedder.document_calls) <= 100
    # Count what was stored rather than query for all 250: HNSW search is approximate and these
    # fake vectors are mostly duplicates, so a k=250 query legitimately returns fewer
    assert chroma_client.get_collection(store.collection_name(WS)).count() == 250


# --- delete ---


def test_delete_document_removes_only_that_document(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund one", 0), txt_chunk("refund two", 1)])
    store.add_chunks(WS, DOC2, "b.txt", [txt_chunk("refund three")])

    store.delete_document(WS, DOC)

    assert texts(store.query(WS, "refund", k=10)) == ["refund three"]


def test_delete_unknown_document_or_workspace_is_a_no_op(store: ChromaVectorStore):
    store.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund policy")])
    store.delete_document(WS, DOC2)
    store.delete_document(WS2, DOC)
    store.delete_workspace(WS2)
    assert texts(store.query(WS, "refund policy")) == ["refund policy"]


def test_delete_workspace_removes_every_model_collection_and_nothing_else(
    chroma_client: ClientAPI,
):
    store_a = ChromaVectorStore(chroma_client, RecordingEmbedder("model-a"))
    store_b = ChromaVectorStore(chroma_client, RecordingEmbedder("model-b"))
    store_a.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund policy")])
    store_b.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund policy")])
    store_a.add_chunks(WS2, DOC2, "b.txt", [txt_chunk("refund policy")])

    store_a.delete_workspace(WS)

    assert store_a.query(WS, "refund policy") == []
    assert store_b.query(WS, "refund policy") == []
    assert texts(store_a.query(WS2, "refund policy")) == ["refund policy"]


# --- the store embeds through the Embedder interface ---


def test_store_embeds_through_the_embedder(store: ChromaVectorStore, embedder: RecordingEmbedder):
    store.add_chunks(WS, DOC, "a.txt", [txt_chunk("refund one", 0), txt_chunk("refund two", 1)])
    store.query(WS, "how do refunds work")

    assert embedder.document_calls == [["refund one", "refund two"]]
    assert embedder.query_calls == ["how do refunds work"]
