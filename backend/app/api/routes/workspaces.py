from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app.api.access import Access, AccessDep
from app.api.deps import AppSettings, VectorStoreDep
from app.api.limits import limit_workspace_creation
from app.api.schemas import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.db.models import Workspace
from app.db.session import get_db
from app.services.cleanup import delete_workspace_data

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DbSession = Annotated[Session, Depends(get_db)]

READ_ONLY = "The demo workspace is read-only. Create your own workspace to upload files."


def _visible(workspace: Workspace, access: Access) -> bool:
    if not access.restricted or workspace.is_demo:
        return True
    if workspace.expires_at is not None and workspace.expires_at <= datetime.now(UTC):
        return False  # expired: gone for visitors even before the sweep deletes it
    return access.owner_hash is not None and workspace.owner_hash == access.owner_hash


def get_workspace_or_404(
    db: Session, workspace_id: str, access: Access, *, write: bool = False
) -> Workspace:
    """The workspace, if this request may see it. On the public demo another visitor's
    workspace is a 404, not a 403, so ids can't be probed; `write` (changing the workspace or
    its documents) is a 403 on the demo workspace, whose existence is no secret."""
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or not _visible(workspace, access):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    if write and access.restricted and workspace.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, READ_ONLY)
    return workspace


@router.post(
    "",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_workspace_creation)],
)
def create_workspace(
    body: WorkspaceCreate, db: DbSession, settings: AppSettings, access: AccessDep
) -> Workspace:
    if body.is_demo and access.restricted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the admin can create a demo workspace."
        )
    workspace = Workspace(name=body.name, is_demo=body.is_demo)
    if access.public:
        workspace.owner_hash = access.require_owner()
        if access.restricted:
            ttl = timedelta(hours=settings.visitor_workspace_ttl_hours)
            workspace.expires_at = datetime.now(UTC) + ttl
    db.add(workspace)
    db.commit()
    return workspace


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: DbSession, access: AccessDep) -> list[Workspace]:
    query = select(Workspace).order_by(Workspace.created_at.desc())
    if access.restricted:
        visible: list[ColumnElement[bool]] = [Workspace.is_demo.is_(True)]
        if access.owner_hash is not None:
            unexpired = or_(
                Workspace.expires_at.is_(None), Workspace.expires_at > datetime.now(UTC)
            )
            visible.append(and_(Workspace.owner_hash == access.owner_hash, unexpired))
        query = query.where(or_(*visible))
    return list(db.scalars(query))


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(workspace_id: str, db: DbSession, access: AccessDep) -> Workspace:
    return get_workspace_or_404(db, workspace_id, access)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def rename_workspace(
    workspace_id: str, body: WorkspaceUpdate, db: DbSession, access: AccessDep
) -> Workspace:
    workspace = get_workspace_or_404(db, workspace_id, access, write=True)
    workspace.name = body.name
    db.commit()
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    db: DbSession,
    settings: AppSettings,
    store: VectorStoreDep,
    access: AccessDep,
) -> Response:
    workspace = get_workspace_or_404(db, workspace_id, access, write=True)
    delete_workspace_data(db, store, settings.data_dir, workspace)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
