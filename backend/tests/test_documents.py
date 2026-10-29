from pathlib import Path

import pytest
from builders import make_docx, make_image_only_pdf, make_pdf
from sqlalchemy import select

from app.api.deps import get_vector_store
from app.db.models import Document, DocumentStatus
from app.services.chunking import Chunk
from app.services.embeddings import FakeEmbedder
from app.services.vectorstore import ChromaVectorStore, SearchHit

FAQ = b"Opening hours\nWe are open 9 to 5 on weekdays.\n\nParking is behind the building.\n"
INTERRUPTED = "Indexing was interrupted, please reindex."
GENERIC_FAILURE = "Could not process this file. Please try again."


def make_workspace(client, name="Acme Dental") -> str:
    response = client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, workspace_id, filename="faq.txt", data=FAQ, content_type="text/plain"):
    return client.post(
        f"/workspaces/{workspace_id}/documents", files={"file": (filename, data, content_type)}
    )


def upload_ok(client, workspace_id, filename="faq.txt", data=FAQ) -> dict:
    response = upload(client, workspace_id, filename, data)
    assert response.status_code == 202, response.text
    return response.json()


def get_document(client, workspace_id, document_id) -> dict:
    response = client.get(f"/workspaces/{workspace_id}/documents/{document_id}")
    assert response.status_code == 200
    return response.json()


def stored_file(tmp_path: Path, workspace_id: str, document_id: str, ext: str) -> Path:
    return tmp_path / "files" / workspace_id / f"{document_id}.{ext}"


def set_status(client, document_id: str, status: DocumentStatus) -> None:
    with client.app.state.session_factory() as db:
        db.get(Document, document_id).status = status
        db.commit()


class CountingEmbedder(FakeEmbedder):
    """FakeEmbedder that records every text it was asked to count tokens for."""

    def __init__(self) -> None:
        super().__init__(dimension=256)
        self.counted: list[str] = []

    def count_tokens(self, text: str) -> int:
        self.counted.append(text)
        return super().count_tokens(text)


class BrokenStore:
    """A vector store that is down: every write fails with an internal error."""

    def add_chunks(
        self, workspace_id: str, document_id: str, filename: str, chunks: list[Chunk]
    ) -> int:
        raise RuntimeError("connection refused to chroma:8000 (internal detail)")

    def query(self, workspace_id: str, question: str, k: int = 5) -> list[SearchHit]:
        return []

    def delete_document(self, workspace_id: str, document_id: str) -> None:
        pass

    def delete_workspace(self, workspace_id: str) -> None:
        pass


# --- upload and ingestion -------------------------------------------------------------------


def test_upload_txt_is_indexed_and_searchable(client, api_store, tmp_path):
    ws = make_workspace(client)
    created = upload_ok(client, ws, data=FAQ, filename="faq.txt")

    assert created["status"] == "pending"
    assert created["filename"] == "faq.txt"
    assert created["workspace_id"] == ws
    assert created["size_bytes"] == len(FAQ)
    assert created["content_type"] == "text/plain"

    document = get_document(client, ws, created["id"])
    assert document["status"] == "ready"
    assert document["error"] is None
    assert stored_file(tmp_path, ws, created["id"], "txt").read_bytes() == FAQ

    [hit, *_] = api_store.query(ws, "where is parking")
    assert hit.chunk.document_id == created["id"]
    assert hit.chunk.filename == "faq.txt"
    assert hit.chunk.location.kind == "txt"
    assert hit.chunk.location.start == 1


def test_upload_pdf_chunks_keep_their_page(client, api_store):
    ws = make_workspace(client)
    pdf = make_pdf(["Refund policy for damaged items", "Shipping takes three days"])
    created = upload_ok(client, ws, filename="policy.pdf", data=pdf)

    assert get_document(client, ws, created["id"])["status"] == "ready"
    assert created["content_type"] == "application/pdf"
    [hit, *_] = api_store.query(ws, "shipping three days")
    assert hit.chunk.location.kind == "pdf"
    assert hit.chunk.location.page == 1  # both short pages fit in one chunk starting on page 1
    assert hit.chunk.location.page_end == 2


def test_upload_docx_is_indexed(client, api_store):
    ws = make_workspace(client)
    created = upload_ok(client, ws, filename="Policies.DOCX", data=make_docx())

    assert get_document(client, ws, created["id"])["status"] == "ready"
    [hit, *_] = api_store.query(ws, "refunds take days")
    assert hit.chunk.location.kind == "docx"
    assert hit.chunk.filename == "Policies.DOCX"


def test_chunks_are_sized_with_the_embedders_token_counter_and_settings(make_client, api_chroma):
    embedder = CountingEmbedder()
    client = make_client(embedder=embedder, chunk_size_tokens=20, chunk_overlap_tokens=5)
    ws = make_workspace(client)
    long_text = " ".join(f"word{i}" for i in range(200)).encode()

    created = upload_ok(client, ws, data=long_text)

    assert get_document(client, ws, created["id"])["status"] == "ready"
    assert embedder.counted, "ingestion must chunk with embedder.count_tokens"
    hits = ChromaVectorStore(api_chroma, embedder).query(ws, "word1", k=100)
    assert len(hits) > 1
    assert all(embedder.count_tokens(h.chunk.text) <= 20 for h in hits)


def test_client_filename_is_kept_for_display_only(client, tmp_path):
    ws = make_workspace(client)
    created = upload_ok(client, ws, filename="..\\..\\../evil.txt")

    assert created["filename"] == "evil.txt"
    assert stored_file(tmp_path, ws, created["id"], "txt").exists()
    assert not (tmp_path.parent / "evil.txt").exists()


# --- upload validation ----------------------------------------------------------------------


def test_unsupported_file_type_is_rejected(client):
    ws = make_workspace(client)
    response = upload(client, ws, filename="photo.png", data=b"\x89PNG...")

    assert response.status_code == 415
    assert "PDF, DOCX or TXT" in response.json()["detail"]
    assert client.get(f"/workspaces/{ws}/documents").json() == []


def test_oversized_file_is_rejected(make_client):
    client = make_client(max_upload_mb=1)
    ws = make_workspace(client)

    response = upload(client, ws, data=b"a" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]
    assert client.get(f"/workspaces/{ws}/documents").json() == []


def test_file_at_the_size_limit_is_accepted(make_client):
    client = make_client(max_upload_mb=1)
    ws = make_workspace(client)
    # Not a real PDF, so ingestion fails fast instead of embedding a megabyte of text
    response = upload(client, ws, filename="big.pdf", data=b"a" * (1024 * 1024))
    assert response.status_code == 202


def test_empty_file_is_rejected(client):
    ws = make_workspace(client)
    response = upload(client, ws, data=b"")
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_unknown_workspace_is_404(client):
    assert upload(client, "missing").status_code == 404
    assert client.get("/workspaces/missing/documents").status_code == 404


def test_duplicate_file_in_a_workspace_conflicts(client):
    ws = make_workspace(client)
    first = upload_ok(client, ws)

    response = upload(client, ws, filename="renamed-copy.txt")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert first["filename"] in detail
    assert first["id"] not in detail  # an internal id means nothing to the person uploading
    assert len(client.get(f"/workspaces/{ws}/documents").json()) == 1


def test_same_file_in_another_workspace_is_fine(client):
    upload_ok(client, make_workspace(client, "One"))
    upload_ok(client, make_workspace(client, "Two"))


# --- failures -------------------------------------------------------------------------------


def test_unreadable_pdf_fails_with_the_parsers_message(client):
    ws = make_workspace(client)
    created = upload_ok(client, ws, filename="scan.pdf", data=make_image_only_pdf())

    document = get_document(client, ws, created["id"])
    assert document["status"] == "failed"
    assert document["error"].startswith("No text found in this PDF")


def test_unexpected_error_fails_with_a_generic_message(make_client):
    client = make_client(store=BrokenStore())
    ws = make_workspace(client)
    created = upload_ok(client, ws)

    document = get_document(client, ws, created["id"])
    assert document["status"] == "failed"
    assert document["error"] == GENERIC_FAILURE  # no internal details leak to users


def test_document_deleted_during_indexing_leaves_no_vectors(
    make_client, api_chroma, api_embedder, api_store
):
    class DeletesDocumentMidway(ChromaVectorStore):
        """Simulates the user deleting the document while its chunks are being stored."""

        def add_chunks(self, workspace_id, document_id, filename, chunks):
            with client.app.state.session_factory() as db:
                db.delete(db.get(Document, document_id))
                db.commit()
            return super().add_chunks(workspace_id, document_id, filename, chunks)

    client = make_client(store=DeletesDocumentMidway(api_chroma, api_embedder))
    ws = make_workspace(client)
    upload_ok(client, ws)

    assert api_store.query(ws, "parking") == []


# --- list, get, file, delete ----------------------------------------------------------------


def test_list_shows_only_this_workspace_newest_first(client):
    ws = make_workspace(client, "One")
    other = make_workspace(client, "Two")
    first = upload_ok(client, ws, "a.txt", b"alpha")
    second = upload_ok(client, ws, "b.txt", b"beta")
    upload_ok(client, other, "c.txt", b"gamma")

    listed = client.get(f"/workspaces/{ws}/documents").json()
    assert [d["id"] for d in listed] == [second["id"], first["id"]]
    assert all(d["status"] == "ready" for d in listed)


def test_document_in_another_workspace_is_404(client):
    ws = make_workspace(client, "One")
    other = make_workspace(client, "Two")
    created = upload_ok(client, ws)
    assert client.get(f"/workspaces/{other}/documents/{created['id']}").status_code == 404
    assert client.delete(f"/workspaces/{other}/documents/{created['id']}").status_code == 404


def test_original_file_can_be_downloaded(client):
    ws = make_workspace(client)
    created = upload_ok(client, ws, filename="policy.pdf", data=make_pdf(["Hello"]))

    response = client.get(f"/workspaces/{ws}/documents/{created['id']}/file")

    assert response.status_code == 200
    assert response.content == make_pdf(["Hello"])
    assert response.headers["content-type"] == "application/pdf"
    assert "policy.pdf" in response.headers["content-disposition"]


def test_delete_removes_vectors_file_and_record(client, api_store, tmp_path):
    ws = make_workspace(client)
    keep = upload_ok(client, ws, "keep.txt", b"Parking is free for patients.")
    gone = upload_ok(client, ws)

    response = client.delete(f"/workspaces/{ws}/documents/{gone['id']}")

    assert response.status_code == 204
    assert {h.chunk.document_id for h in api_store.query(ws, "parking", k=10)} == {keep["id"]}
    assert not stored_file(tmp_path, ws, gone["id"], "txt").exists()
    assert client.get(f"/workspaces/{ws}/documents/{gone['id']}").status_code == 404
    assert client.delete(f"/workspaces/{ws}/documents/{gone['id']}").status_code == 404
    # The same file can be uploaded again once it has been deleted
    upload_ok(client, ws)


def test_deleting_a_workspace_removes_its_vectors_and_files(client, api_store, tmp_path):
    ws = make_workspace(client)
    upload_ok(client, ws)

    assert client.delete(f"/workspaces/{ws}").status_code == 204

    assert api_store.query(ws, "parking") == []
    assert not (tmp_path / "files" / ws).exists()


# --- reindex --------------------------------------------------------------------------------


def test_reindex_recovers_a_failed_document(make_client, api_store):
    client = make_client(store=BrokenStore())
    ws = make_workspace(client)
    created = upload_ok(client, ws)
    assert get_document(client, ws, created["id"])["status"] == "failed"

    client.app.dependency_overrides[get_vector_store] = lambda: api_store  # the store is back
    response = client.post(f"/workspaces/{ws}/documents/{created['id']}/reindex")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["error"] is None
    assert get_document(client, ws, created["id"])["status"] == "ready"
    assert api_store.query(ws, "parking")[0].chunk.document_id == created["id"]


@pytest.mark.parametrize("busy", [DocumentStatus.PENDING, DocumentStatus.PROCESSING])
def test_reindex_while_indexing_conflicts(client, busy):
    ws = make_workspace(client)
    created = upload_ok(client, ws)
    set_status(client, created["id"], busy)

    response = client.post(f"/workspaces/{ws}/documents/{created['id']}/reindex")

    assert response.status_code == 409
    assert get_document(client, ws, created["id"])["status"] == busy.value


def test_reindex_unknown_document_is_404(client):
    ws = make_workspace(client)
    assert client.post(f"/workspaces/{ws}/documents/missing/reindex").status_code == 404


# --- startup --------------------------------------------------------------------------------


def test_startup_rejects_a_chunk_size_over_the_embedding_model_limit(make_client):
    client = make_client(chunk_size_tokens=600)  # the local bge model takes at most 512
    with pytest.raises(ValueError, match="CHUNK_SIZE_TOKENS"), client:
        pass


def test_startup_fails_documents_left_mid_indexing(make_client):
    client = make_client()
    ws = make_workspace(client)
    with client.app.state.session_factory() as db:
        for status in DocumentStatus:
            db.add(
                Document(
                    id=status.value.ljust(32, "0"),
                    workspace_id=ws,
                    filename=f"{status.value}.txt",
                    content_type="text/plain",
                    size_bytes=1,
                    sha256=status.value,
                    status=status,
                    error="Old parser error" if status is DocumentStatus.FAILED else None,
                )
            )
        db.commit()

    with client:  # runs the app's startup
        pass

    with client.app.state.session_factory() as db:
        found = {d.filename: (d.status, d.error) for d in db.scalars(select(Document))}
    assert found == {
        "pending.txt": (DocumentStatus.FAILED, INTERRUPTED),
        "processing.txt": (DocumentStatus.FAILED, INTERRUPTED),
        "ready.txt": (DocumentStatus.READY, None),
        "failed.txt": (DocumentStatus.FAILED, "Old parser error"),
    }
