"""The public demo's upload caps: documents per workspace, total storage, document length."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

VISITOR = {"X-Visitor-Id": str(uuid.uuid4())}


def setup(make_client: Callable[..., TestClient], **overrides: object) -> tuple[TestClient, str]:
    client = make_client(public_demo=True, **overrides)
    ws = client.post("/workspaces", json={"name": "Mine"}, headers=VISITOR).json()["id"]
    return client, ws


def upload(client: TestClient, ws: str, content: bytes, name: str = "a.txt"):
    files = {"file": (name, content, "text/plain")}
    return client.post(f"/workspaces/{ws}/documents", files=files, headers=VISITOR)


def test_a_workspace_holds_a_limited_number_of_documents(make_client) -> None:
    client, ws = setup(make_client, max_documents_per_workspace=2)

    assert upload(client, ws, b"one").status_code == 202
    assert upload(client, ws, b"two").status_code == 202
    response = upload(client, ws, b"three")

    assert response.status_code == 409
    assert "2 documents" in response.json()["detail"]


def test_visitor_uploads_share_a_storage_cap(make_client) -> None:
    client, ws = setup(make_client, max_visitor_storage_mb=1)
    other = {"X-Visitor-Id": str(uuid.uuid4())}
    ws2 = client.post("/workspaces", json={"name": "Other"}, headers=other).json()["id"]

    assert upload(client, ws, b"x" * 700_000).status_code == 202
    files = {"file": ("b.txt", b"y" * 400_000, "text/plain")}
    response = client.post(f"/workspaces/{ws2}/documents", files=files, headers=other)

    assert response.status_code == 507
    assert "storage" in response.json()["detail"]


def test_a_too_long_document_fails_before_it_is_embedded(
    make_client, api_embedder, monkeypatch
) -> None:
    client, ws = setup(
        make_client, max_document_chunks=2, chunk_size_tokens=20, chunk_overlap_tokens=5
    )
    embedded: list[str] = []
    monkeypatch.setattr(api_embedder, "embed_documents", lambda texts: embedded.extend(texts))
    text = "\n\n".join(f"# Section {n}\n" + "word " * 15 for n in range(6)).encode()

    document = upload(client, ws, text).json()

    stored = client.get(f"/workspaces/{ws}/documents/{document['id']}", headers=VISITOR).json()
    assert stored["status"] == "failed"
    assert "too long" in stored["error"]
    assert embedded == []


def test_private_deployments_have_no_upload_caps(make_client) -> None:
    client = make_client(max_documents_per_workspace=1, max_document_chunks=1)
    ws = client.post("/workspaces", json={"name": "Mine"}).json()["id"]

    assert upload(client, ws, b"one").status_code == 202
    assert upload(client, ws, b"two").status_code == 202
