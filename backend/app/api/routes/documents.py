import hashlib
from pathlib import PureWindowsPath
from typing import Annotated, Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import Access, AccessDep
from app.api.deps import AppSettings, EmbedderDep, SessionFactory, VectorStoreDep
from app.api.limits import limit_uploads
from app.api.routes.workspaces import get_workspace_or_404
from app.api.schemas import DocumentOut
from app.config import Settings
from app.db.models import Document, DocumentStatus, Workspace
from app.db.session import get_db
from app.services.ingestion import BUSY_STATUSES, ingest_document
from app.services.parsers import FileKind, ParseError, file_kind
from app.services.storage import document_path, save_file

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_db)]

MAX_FILENAME_LENGTH = 255

# Set from the file type we accept, not the client's Content-Type header (which can say anything)
CONTENT_TYPES: dict[FileKind, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


def get_document_or_404(
    db: Session, workspace_id: str, document_id: str, access: Access, *, write: bool = False
) -> Document:
    get_workspace_or_404(db, workspace_id, access, write=write)
    document = db.get(Document, document_id)
    if document is None or document.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_uploads)],
)
def upload_document(
    workspace_id: str,
    file: UploadFile,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    session_factory: SessionFactory,
    embedder: EmbedderDep,
    store: VectorStoreDep,
    access: AccessDep,
) -> Document:
    """Store the file and queue it for indexing; poll the document until it is ready or failed."""
    get_workspace_or_404(db, workspace_id, access, write=True)
    filename = _display_name(file.filename)
    try:
        kind = file_kind(filename)
    except ParseError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    # By now the server has already received the whole body (spooled to disk past 1MB); the
    # reverse proxy enforces the hard cap. This check gives a clear message for the app's limit.
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file is larger than the {settings.max_upload_mb} MB upload limit.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")

    if access.restricted:
        _check_upload_caps(db, settings, workspace_id, len(data))

    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Document).where(Document.workspace_id == workspace_id, Document.sha256 == sha256)
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f'This file is already in the workspace as "{existing.filename}".',
        )

    document = Document(
        workspace_id=workspace_id,
        filename=filename,
        content_type=CONTENT_TYPES[kind],
        size_bytes=len(data),
        sha256=sha256,
        status=DocumentStatus.PENDING,
    )
    db.add(document)
    db.flush()  # assigns the id the stored file is named after
    path = document_path(settings.data_dir, workspace_id, document.id, kind)
    save_file(path, data)
    try:
        db.commit()
    except IntegrityError as exc:
        # The same file uploaded twice at the same moment: the unique constraint caught it
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This file is already in the workspace."
        ) from exc

    background.add_task(ingest_document, session_factory, embedder, store, settings, document.id)
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(workspace_id: str, db: DbSession, access: AccessDep) -> list[Document]:
    get_workspace_or_404(db, workspace_id, access)
    return list(
        db.scalars(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc())
        )
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(workspace_id: str, document_id: str, db: DbSession, access: AccessDep) -> Document:
    return get_document_or_404(db, workspace_id, document_id, access)


# HEAD lets the preview check the file still exists before offering "Open original"
@router.api_route("/{document_id}/file", methods=["GET", "HEAD"])
def download_document_file(
    workspace_id: str, document_id: str, db: DbSession, settings: AppSettings, access: AccessDep
) -> FileResponse:
    """The original upload, shown inline (the citation preview opens it in the browser)."""
    document = get_document_or_404(db, workspace_id, document_id, access)
    path = document_path(settings.data_dir, workspace_id, document_id, file_kind(document.filename))
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The original file is missing")
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.filename,
        content_disposition_type="inline",
    )


@router.post(
    "/{document_id}/reindex", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED
)
def reindex_document(
    workspace_id: str,
    document_id: str,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    session_factory: SessionFactory,
    embedder: EmbedderDep,
    store: VectorStoreDep,
    access: AccessDep,
) -> Document:
    """Index the stored file again, e.g. after a failure or a chunk size or model change."""
    document = get_document_or_404(db, workspace_id, document_id, access, write=True)
    # One conditional UPDATE, so two reindex requests at once can't both queue a run: two runs
    # would race on add_chunks' delete-then-add and could leave old and new chunks mixed.
    claimed = cast(
        CursorResult[Any],
        db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status.not_in(BUSY_STATUSES))
            .values(status=DocumentStatus.PENDING, error=None)
            .execution_options(synchronize_session=False)
        ),
    )
    db.commit()
    if claimed.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "This document is already being indexed.")
    db.refresh(document)

    background.add_task(ingest_document, session_factory, embedder, store, settings, document.id)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    workspace_id: str,
    document_id: str,
    db: DbSession,
    settings: AppSettings,
    store: VectorStoreDep,
    access: AccessDep,
) -> Response:
    document = get_document_or_404(db, workspace_id, document_id, access, write=True)
    path = document_path(settings.data_dir, workspace_id, document_id, file_kind(document.filename))
    # Vectors first: if the store is down the request fails and the document stays, so the
    # user can retry, rather than leaving vectors behind for a document that no longer exists.
    store.delete_document(workspace_id, document_id)
    db.delete(document)
    db.commit()
    path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _check_upload_caps(db: Session, settings: Settings, workspace_id: str, size: int) -> None:
    """The public demo's caps: documents per workspace and the disk all visitors share."""
    limit = settings.max_documents_per_workspace
    if limit:
        count = db.scalar(
            select(func.count()).select_from(Document).where(Document.workspace_id == workspace_id)
        )
        if (count or 0) >= limit:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This demo workspace already has {limit} documents, the most it can hold. "
                "Delete one to add another.",
            )
    if settings.max_visitor_storage_mb:
        used = db.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0))
            .join(Workspace)
            .where(Workspace.is_demo.is_(False))
        )
        if (used or 0) + size > settings.max_visitor_storage_mb * 1024 * 1024:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                "The demo's storage for uploads is full right now. Please try again later.",
            )


def _display_name(raw: str | None) -> str:
    """The client's filename without any directories (either slash style), max 255 chars.

    Only ever shown to users; files on disk are named by document id.
    """
    name = PureWindowsPath(raw or "").name.strip()
    if len(name) > MAX_FILENAME_LENGTH:
        suffix = PureWindowsPath(name).suffix[:16]
        name = name[: MAX_FILENAME_LENGTH - len(suffix)] + suffix
    return name
