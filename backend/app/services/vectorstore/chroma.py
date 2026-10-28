import hashlib

from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Metadata, PyEmbedding
from chromadb.errors import NotFoundError

from app.services.chunking import Chunk
from app.services.embeddings import Embedder
from app.services.parsers import Location
from app.services.parsers.models import FileKind
from app.services.vectorstore.base import SearchHit, StoredChunk

MAX_COLLECTION_NAME = 63  # Chroma's limit (3-63 chars)
BATCH_SIZE = 100  # chunks per embedding call and per Chroma write

# Location fields copied flat into Chroma metadata (which can't hold None or nested values)
_LOCATION_FIELDS = ("page", "page_end", "heading", "start", "end")
_FILE_KINDS: tuple[FileKind, ...] = ("pdf", "docx", "txt")


class ChromaVectorStore:
    """`VectorStore` on ChromaDB: one cosine collection per workspace and embedding model."""

    def __init__(self, client: ClientAPI, embedder: Embedder) -> None:
        self._client = client
        self._embedder = embedder

    def collection_name(self, workspace_id: str) -> str:
        """`ws_{id}__{model-slug}`; a slug too long for Chroma is swapped for a short hash."""
        name = f"{_workspace_prefix(workspace_id)}{self._embedder.slug}"
        if len(name) <= MAX_COLLECTION_NAME:
            return name
        digest = hashlib.sha256(self._embedder.slug.encode()).hexdigest()[:12]
        return f"{_workspace_prefix(workspace_id)}{digest}"

    def add_chunks(
        self, workspace_id: str, document_id: str, filename: str, chunks: list[Chunk]
    ) -> int:
        # Embed before deleting, so a failed embedding call leaves the old chunks in place
        embeddings: list[PyEmbedding] = []
        for batch in _batches(chunks):
            embeddings.extend(self._embedder.embed_documents([chunk.text for chunk in batch]))

        collection = self._client.get_or_create_collection(
            self.collection_name(workspace_id),
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,
        )
        collection.delete(where={"document_id": document_id})
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            collection.add(
                ids=[f"{document_id}:{chunk.index}" for chunk in batch],
                embeddings=embeddings[start : start + BATCH_SIZE],
                documents=[chunk.text for chunk in batch],
                metadatas=[_to_metadata(document_id, filename, chunk) for chunk in batch],
            )
        return len(chunks)

    def query(self, workspace_id: str, question: str, k: int = 5) -> list[SearchHit]:
        collection = self._get_collection(workspace_id)
        if collection is None:
            return []
        n_results = min(max(k, 1), collection.count())
        if n_results == 0:
            return []

        result = collection.query(
            query_embeddings=[self._embedder.embed_query(question)],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result["documents"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        distances = (result["distances"] or [[]])[0]
        return [
            SearchHit(chunk=_from_metadata(text, metadata), score=_similarity(distance))
            for text, metadata, distance in zip(documents, metadatas, distances, strict=True)
        ]

    def delete_document(self, workspace_id: str, document_id: str) -> None:
        collection = self._get_collection(workspace_id)
        if collection is not None:
            collection.delete(where={"document_id": document_id})

    def delete_workspace(self, workspace_id: str) -> None:
        # Every embedding model's collection, so switching providers leaves no orphaned vectors
        prefix = _workspace_prefix(workspace_id)
        for collection in self._client.list_collections():
            if collection.name.startswith(prefix):
                self._client.delete_collection(collection.name)

    def _get_collection(self, workspace_id: str) -> Collection | None:
        try:
            return self._client.get_collection(
                self.collection_name(workspace_id), embedding_function=None
            )
        except NotFoundError:
            return None


def _workspace_prefix(workspace_id: str) -> str:
    return f"ws_{workspace_id}__"


def _batches(chunks: list[Chunk]) -> list[list[Chunk]]:
    return [chunks[start : start + BATCH_SIZE] for start in range(0, len(chunks), BATCH_SIZE)]


def _similarity(distance: float) -> float:
    """Cosine distance (0..2) to similarity, clamped to 0..1."""
    return min(1.0, max(0.0, 1.0 - distance))


def _to_metadata(document_id: str, filename: str, chunk: Chunk) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {
        "document_id": document_id,
        "filename": filename,
        "chunk_index": chunk.index,
        "kind": chunk.location.kind,
    }
    for field in _LOCATION_FIELDS:
        value = getattr(chunk.location, field)
        if value is not None:  # Chroma rejects None; a missing key reads back as None
            metadata[field] = value
    return metadata


def _from_metadata(text: str | None, metadata: Metadata) -> StoredChunk:
    index = _int_or_none(metadata.get("chunk_index"))
    if index is None:
        raise ValueError(f"stored chunk has no valid chunk_index: {metadata!r}")
    location = Location(
        kind=_file_kind(metadata.get("kind")),
        page=_int_or_none(metadata.get("page")),
        page_end=_int_or_none(metadata.get("page_end")),
        heading=_str_or_none(metadata.get("heading")),
        start=_int_or_none(metadata.get("start")),
        end=_int_or_none(metadata.get("end")),
    )
    return StoredChunk(
        document_id=str(metadata["document_id"]),
        filename=str(metadata["filename"]),
        index=index,
        text=text or "",
        location=location,
    )


def _file_kind(value: object) -> FileKind:
    for kind in _FILE_KINDS:
        if value == kind:
            return kind
    raise ValueError(f"stored chunk has an unknown file kind: {value!r}")


def _int_or_none(value: object) -> int | None:
    # bool is a subclass of int, but never a valid page or line number
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
