import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Document, DocumentStatus, Workspace
from app.services.chunking import chunk_segments
from app.services.embeddings import Embedder
from app.services.parsers import ParseError, file_kind, parse_document
from app.services.storage import document_path
from app.services.vectorstore import VectorStore

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Indexing was interrupted, please reindex."
GENERIC_FAILURE_MESSAGE = "Could not process this file. Please try again."

BUSY_STATUSES = (DocumentStatus.PENDING, DocumentStatus.PROCESSING)


def ingest_document(
    session_factory: sessionmaker[Session],
    embedder: Embedder,
    store: VectorStore,
    settings: Settings,
    document_id: str,
) -> None:
    """Parse, chunk and index one stored upload, recording the outcome on the document.

    Runs as a background task after the upload response has gone out, so it opens its own
    database sessions and never raises: every failure ends up in the document's status.
    """
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:  # deleted before indexing started
            return
        document.status = DocumentStatus.PROCESSING
        document.error = None
        db.commit()
        workspace_id, filename = document.workspace_id, document.filename
        workspace = db.get(Workspace, workspace_id)
        # The public demo caps visitor documents (not the seeded demo's) by chunk count
        max_chunks = (
            settings.max_document_chunks
            if settings.public_demo and workspace is not None and not workspace.is_demo
            else 0
        )

    try:
        path = document_path(settings.data_dir, workspace_id, document_id, file_kind(filename))
        segments = parse_document(filename, path.read_bytes())
        chunks = chunk_segments(
            segments,
            max_tokens=settings.chunk_size_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            count_tokens=embedder.count_tokens,
        )
        if max_chunks and len(chunks) > max_chunks:
            # Checked before embedding, which is the expensive part (CPU or a paid API)
            raise ParseError(
                f"This document is too long for the demo (over {max_chunks} sections). "
                "Try a shorter file."
            )
        count = store.add_chunks(workspace_id, document_id, filename, chunks)
    except ParseError as exc:
        # Parser messages are written for users ("No text found in this PDF...")
        _finish(session_factory, store, workspace_id, document_id, DocumentStatus.FAILED, str(exc))
        return
    except Exception:
        logger.exception("ingestion failed", extra={"document_id": document_id})
        _finish(
            session_factory,
            store,
            workspace_id,
            document_id,
            DocumentStatus.FAILED,
            GENERIC_FAILURE_MESSAGE,
        )
        return

    logger.info("document indexed", extra={"document_id": document_id, "chunks": count})
    _finish(session_factory, store, workspace_id, document_id, DocumentStatus.READY, None)


def _finish(
    session_factory: sessionmaker[Session],
    store: VectorStore,
    workspace_id: str,
    document_id: str,
    status: DocumentStatus,
    error: str | None,
) -> None:
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            # Deleted while it was being indexed: don't leave its vectors behind
            store.delete_document(workspace_id, document_id)
            return
        document.status = status
        document.error = error
        db.commit()


def fail_interrupted_documents(session_factory: sessionmaker[Session]) -> int:
    """Mark documents left pending or processing by a previous run as failed.

    Background tasks live only in the server process, so after a restart nothing will ever
    finish them. Call this once at startup. It assumes a single backend process (the Stage 1
    deployment): with several workers, one worker's startup would fail documents another
    worker is still indexing.
    """
    with session_factory() as db:
        stuck = list(db.scalars(select(Document).where(Document.status.in_(BUSY_STATUSES))))
        for document in stuck:
            document.status = DocumentStatus.FAILED
            document.error = INTERRUPTED_MESSAGE
        db.commit()
        return len(stuck)
