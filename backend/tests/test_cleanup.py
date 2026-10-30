"""The sweep that deletes expired visitor workspaces and visitors' old chats in the demo."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from chat_helpers import seed_documents
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Conversation, Document, DocumentStatus, Workspace
from app.db.session import create_db_engine, create_session_factory
from app.services.cleanup import sweep
from app.services.storage import save_file, workspace_files_dir
from app.services.vectorstore import ChromaVectorStore

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
DAY = timedelta(hours=24)


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    return create_session_factory(create_db_engine(tmp_path))


def add(session_factory: sessionmaker[Session], *rows: object) -> None:
    with session_factory() as db:
        db.add_all(rows)
        db.commit()


def ids(session_factory: sessionmaker[Session], model: type) -> set[str]:
    with session_factory() as db:
        return {row.id for row in db.query(model).all()}


def test_expired_workspaces_lose_their_rows_vectors_and_files(
    session_factory: sessionmaker[Session], api_store: ChromaVectorStore, tmp_path: Path
) -> None:
    add(
        session_factory,
        Workspace(id="old", name="Old", expires_at=NOW - timedelta(minutes=1)),
        Workspace(id="new", name="New", expires_at=NOW + timedelta(hours=1)),
        Workspace(id="kept", name="Private deployment", expires_at=None),
    )
    seed_documents(api_store, "old")
    save_file(workspace_files_dir(tmp_path, "old") / "doc.txt", b"hello")

    deleted, _ = sweep(session_factory, api_store, tmp_path, visitor_chat_ttl=DAY, now=NOW)

    assert deleted == 1
    assert ids(session_factory, Workspace) == {"new", "kept"}
    assert api_store.query("old", "refunds", k=5) == []
    assert not workspace_files_dir(tmp_path, "old").exists()


def test_a_workspace_still_indexing_waits_for_the_next_sweep(
    session_factory: sessionmaker[Session], api_store: ChromaVectorStore, tmp_path: Path
) -> None:
    add(
        session_factory,
        Workspace(id="busy", name="Busy", expires_at=NOW - timedelta(minutes=1)),
        Document(
            workspace_id="busy",
            filename="a.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256="0" * 64,
            status=DocumentStatus.PROCESSING,
        ),
    )

    assert sweep(session_factory, api_store, tmp_path, visitor_chat_ttl=DAY, now=NOW) == (0, 0)
    assert ids(session_factory, Workspace) == {"busy"}


def test_visitors_old_chats_in_the_demo_workspace_are_deleted(
    session_factory: sessionmaker[Session], api_store: ChromaVectorStore, tmp_path: Path
) -> None:
    add(
        session_factory,
        Workspace(id="demo", name="Demo", is_demo=True),
        Conversation(id="stale", workspace_id="demo", owner_hash="a", created_at=NOW - 2 * DAY),
        Conversation(id="fresh", workspace_id="demo", owner_hash="a", created_at=NOW),
        # Not a visitor's (made before the public demo, or by the admin): kept
        Conversation(id="admin", workspace_id="demo", owner_hash=None, created_at=NOW - 2 * DAY),
    )

    _, chats = sweep(session_factory, api_store, tmp_path, visitor_chat_ttl=DAY, now=NOW)

    assert chats == 1
    assert ids(session_factory, Conversation) == {"fresh", "admin"}
    assert ids(session_factory, Workspace) == {"demo"}


def test_the_public_demo_sweeps_at_startup(make_client) -> None:
    client = make_client(public_demo=True)
    with client.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        db.add(Workspace(id="old", name="Old", expires_at=datetime.now(UTC) - DAY))
        db.commit()

    with client:  # runs the app's startup
        pass

    assert ids(client.app.state.session_factory, Workspace) == set()  # pyright: ignore[reportAttributeAccessIssue]


def test_a_private_deployment_never_sweeps(make_client) -> None:
    client = make_client()
    with client.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        db.add(Workspace(id="old", name="Old", expires_at=datetime.now(UTC) - DAY))
        db.commit()

    with client:
        pass

    assert ids(client.app.state.session_factory, Workspace) == {"old"}  # pyright: ignore[reportAttributeAccessIssue]
