"""PUBLIC_DEMO: a visitor only reaches their own workspaces and chats, plus the read-only demo."""

import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from chat_helpers import CITED_REPLY, MIN_SCORE, QUESTION, parse_sse, seed_documents
from fastapi.testclient import TestClient

from app.db.models import Conversation, Workspace
from app.services.llm import FakeChat
from app.services.vectorstore import ChromaVectorStore

ADMIN_KEY = "admin-key-for-tests-only"
ALICE = {"X-Visitor-Id": str(uuid.uuid4())}
BOB = {"X-Visitor-Id": str(uuid.uuid4())}
ADMIN = {"X-Admin-Key": ADMIN_KEY}
TXT = ("faq.txt", b"Refunds are processed within 5 business days.", "text/plain")


@pytest.fixture
def demo(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client(
        public_demo=True,
        admin_api_key=ADMIN_KEY,
        rag_min_score=MIN_SCORE,
        chat_model=FakeChat(CITED_REPLY),
    )


def create_workspace(client: TestClient, headers: dict[str, str], **body: object) -> str:
    response = client.post("/workspaces", json={"name": "Mine", **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def demo_workspace(client: TestClient) -> str:
    return create_workspace(client, ADMIN, name="Demo", is_demo=True)


def upload(client: TestClient, workspace_id: str, headers: dict[str, str], file=TXT):
    return client.post(
        f"/workspaces/{workspace_id}/documents", files={"file": file}, headers=headers
    )


# --- Visitor identity ------------------------------------------------------------------------


def test_creating_a_workspace_needs_a_visitor_id(demo: TestClient) -> None:
    for headers in ({}, {"X-Visitor-Id": "not-a-uuid"}):
        response = demo.post("/workspaces", json={"name": "Mine"}, headers=headers)
        assert response.status_code == 400
        assert "visitor" in response.json()["detail"].lower()


def test_a_visitor_workspace_expires_and_stores_only_a_hash_of_the_id(demo: TestClient) -> None:
    before = datetime.now(UTC)

    response = demo.post("/workspaces", json={"name": "Mine"}, headers=ALICE)

    body = response.json()
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=23.9) < expires - before < timedelta(hours=24.1)
    assert body["is_demo"] is False
    with demo.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        workspace = db.get(Workspace, body["id"])
        raw = ALICE["X-Visitor-Id"]
        assert workspace.owner_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in repr(vars(workspace))


# --- Ownership -------------------------------------------------------------------------------


def test_visitors_only_list_their_own_workspaces_and_the_demo(demo: TestClient) -> None:
    demo_id = demo_workspace(demo)
    alice_ws = create_workspace(demo, ALICE)
    bob_ws = create_workspace(demo, BOB)

    def listed(headers: dict[str, str]) -> set[str]:
        return {w["id"] for w in demo.get("/workspaces", headers=headers).json()}

    assert listed(ALICE) == {demo_id, alice_ws}
    assert listed(BOB) == {demo_id, bob_ws}
    assert listed({}) == {demo_id}
    assert listed(ADMIN) == {demo_id, alice_ws, bob_ws}


def test_another_visitors_workspace_is_404_on_every_route(demo: TestClient) -> None:
    ws = create_workspace(demo, ALICE)
    doc = upload(demo, ws, ALICE).json()["id"]
    conv = demo.post(f"/workspaces/{ws}/conversations", headers=ALICE).json()["id"]
    base = f"/workspaces/{ws}"

    requests = [
        ("GET", base, None),
        ("PATCH", base, {"name": "Taken"}),
        ("DELETE", base, None),
        ("GET", f"{base}/documents", None),
        ("GET", f"{base}/documents/{doc}", None),
        ("GET", f"{base}/documents/{doc}/file", None),
        ("HEAD", f"{base}/documents/{doc}/file", None),
        ("POST", f"{base}/documents/{doc}/reindex", None),
        ("DELETE", f"{base}/documents/{doc}", None),
        ("GET", f"{base}/conversations", None),
        ("POST", f"{base}/conversations", None),
        ("DELETE", f"{base}/conversations/{conv}", None),
        ("GET", f"{base}/conversations/{conv}/messages", None),
        ("POST", f"{base}/conversations/{conv}/messages", {"question": QUESTION}),
    ]
    for method, url, body in requests:
        for headers in (BOB, {}):
            response = demo.request(method, url, json=body, headers=headers)
            assert response.status_code == 404, (method, url, headers)
    assert upload(demo, ws, BOB).status_code == 404

    # Alice still has everything
    assert demo.get(f"{base}/documents/{doc}/file", headers=ALICE).status_code == 200
    assert demo.get(f"{base}/conversations/{conv}/messages", headers=ALICE).status_code == 200


def test_an_expired_workspace_is_gone_before_the_sweep_runs(demo: TestClient) -> None:
    ws = create_workspace(demo, ALICE)
    with demo.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        db.get(Workspace, ws).expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    assert demo.get(f"/workspaces/{ws}", headers=ALICE).status_code == 404
    assert ws not in {w["id"] for w in demo.get("/workspaces", headers=ALICE).json()}


# --- The read-only demo workspace ------------------------------------------------------------


def test_only_an_admin_can_create_the_demo_workspace(demo: TestClient) -> None:
    response = demo.post("/workspaces", json={"name": "Demo", "is_demo": True}, headers=ALICE)
    assert response.status_code == 403

    wrong_key = {"X-Admin-Key": "guess"}
    response = demo.post("/workspaces", json={"name": "Demo", "is_demo": True}, headers=wrong_key)
    assert response.status_code == 403

    response = demo.post("/workspaces", json={"name": "Demo", "is_demo": True}, headers=ADMIN)
    assert response.status_code == 201
    assert response.json()["is_demo"] is True
    assert response.json()["expires_at"] is None
    assert response.json()["starter_questions"]


def test_an_empty_admin_key_never_matches(make_client: Callable[..., TestClient]) -> None:
    client = make_client(public_demo=True, admin_api_key="")

    response = client.post(
        "/workspaces", json={"name": "Demo", "is_demo": True}, headers={"X-Admin-Key": ""}
    )

    assert response.status_code == 403


def test_the_demo_workspace_is_read_only_for_visitors(demo: TestClient) -> None:
    ws = demo_workspace(demo)
    doc = upload(demo, ws, ADMIN).json()["id"]
    base = f"/workspaces/{ws}"

    writes = [
        ("PATCH", base, {"name": "Hacked"}),
        ("DELETE", base, None),
        ("POST", f"{base}/documents/{doc}/reindex", None),
        ("DELETE", f"{base}/documents/{doc}", None),
    ]
    for method, url, body in writes:
        response = demo.request(method, url, json=body, headers=ALICE)
        assert response.status_code == 403, (method, url)
        assert "read-only" in response.json()["detail"]
    assert upload(demo, ws, ALICE, ("new.txt", b"Hello", "text/plain")).status_code == 403

    # Reading it is fine, for anyone
    assert demo.get(base, headers=BOB).status_code == 200
    assert demo.get(f"{base}/documents", headers={}).status_code == 200
    assert demo.get(f"{base}/documents/{doc}/file", headers=BOB).status_code == 200
    # And the admin can still change it (the seed replaces changed files)
    assert demo.delete(f"{base}/documents/{doc}", headers=ADMIN).status_code == 204


def test_visitors_chat_privately_in_the_demo_workspace(
    demo: TestClient, api_store: ChromaVectorStore
) -> None:
    ws = demo_workspace(demo)
    seed_documents(api_store, ws)
    conversations = f"/workspaces/{ws}/conversations"

    assert demo.post(conversations, headers={}).status_code == 400  # needs a visitor id
    conv = demo.post(conversations, headers=ALICE).json()["id"]
    reply = demo.post(
        f"{conversations}/{conv}/messages", json={"question": QUESTION}, headers=ALICE
    )

    assert "done" in [name for name, _ in parse_sse(reply.text)]
    assert [c["id"] for c in demo.get(conversations, headers=ALICE).json()] == [conv]
    assert demo.get(conversations, headers=BOB).json() == []
    assert demo.get(f"{conversations}/{conv}/messages", headers=BOB).status_code == 404
    assert demo.delete(f"{conversations}/{conv}", headers=BOB).status_code == 404
    with demo.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        assert db.get(Conversation, conv).owner_hash is not None


# --- Off by default --------------------------------------------------------------------------


def test_without_public_demo_everything_stays_open(client: TestClient) -> None:
    ws = create_workspace(client, {})
    other = create_workspace(client, ALICE)

    assert {w["id"] for w in client.get("/workspaces", headers=BOB).json()} == {ws, other}
    assert client.get(f"/workspaces/{other}", headers=BOB).json()["expires_at"] is None
    assert client.patch(f"/workspaces/{other}", json={"name": "X"}).status_code == 200
    demo_ws = create_workspace(client, {}, name="Demo", is_demo=True)
    assert upload(client, demo_ws, {}).status_code == 202
    assert client.delete(f"/workspaces/{demo_ws}").status_code == 204
