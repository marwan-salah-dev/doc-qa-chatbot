"""Deleting workspaces, and the public demo's sweep of expired visitor data.

The sweep runs as one asyncio task inside the app (see `main.py`), not as a cron job or a
separate container: the backend runs exactly one uvicorn worker, so there is exactly one
sweeper and no two deletes can race. Expired workspaces already answer 404 (see
`api.routes.workspaces`), so the sweep only frees disk; how often it runs never decides what a
visitor can see. With several workers this would have to become one external job holding a
database lock.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Conversation, Document, Workspace
from app.services.ingestion import BUSY_STATUSES
from app.services.storage import delete_workspace_files
from app.services.vectorstore import VectorStore

logger = logging.getLogger(__name__)


def delete_workspace_data(
    db: Session, store: VectorStore, data_dir: Path, workspace: Workspace
) -> None:
    """Vectors, then rows (documents and conversations cascade), then files: the same order as
    deleting a document, so a failing store leaves the workspace in place to retry."""
    workspace_id = workspace.id
    store.delete_workspace(workspace_id)
    db.delete(workspace)
    db.commit()
    delete_workspace_files(data_dir, workspace_id)


def sweep(
    session_factory: sessionmaker[Session],
    store: VectorStore,
    data_dir: Path,
    *,
    visitor_chat_ttl: timedelta,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Delete expired workspaces and visitors' old chats in demo workspaces.

    Returns (workspaces deleted, conversations deleted). A workspace with a document still
    indexing is left for the next sweep, so ingestion never writes into a deleted workspace.
    """
    now = now or datetime.now(UTC)
    busy = exists().where(Document.workspace_id == Workspace.id, Document.status.in_(BUSY_STATUSES))
    deleted = 0
    with session_factory() as db:
        expired = db.scalars(select(Workspace).where(Workspace.expires_at <= now, ~busy)).all()
        for workspace in expired:
            try:
                delete_workspace_data(db, store, data_dir, workspace)
                deleted += 1
            except Exception:
                db.rollback()
                logger.exception("could not delete an expired workspace")

        demo_ids = select(Workspace.id).where(Workspace.is_demo)
        chats = db.execute(
            delete(Conversation).where(
                Conversation.workspace_id.in_(demo_ids),
                Conversation.owner_hash.is_not(None),
                Conversation.created_at <= now - visitor_chat_ttl,
            )
        )
        db.commit()
    chats_deleted = getattr(chats, "rowcount", 0) or 0
    if deleted or chats_deleted:
        logger.info(
            "expired visitor data deleted",
            extra={"workspaces": deleted, "conversations": chats_deleted},
        )
    return deleted, chats_deleted
