from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.db.models import Workspace
from app.db.session import get_db

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DbSession = Annotated[Session, Depends(get_db)]


def get_workspace_or_404(db: Session, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, db: DbSession) -> Workspace:
    workspace = Workspace(name=body.name)
    db.add(workspace)
    db.commit()
    return workspace


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: DbSession) -> list[Workspace]:
    return list(db.scalars(select(Workspace).order_by(Workspace.created_at.desc())))


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(workspace_id: str, db: DbSession) -> Workspace:
    return get_workspace_or_404(db, workspace_id)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def rename_workspace(workspace_id: str, body: WorkspaceUpdate, db: DbSession) -> Workspace:
    workspace = get_workspace_or_404(db, workspace_id)
    workspace.name = body.name
    db.commit()
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: str, db: DbSession) -> Response:
    # Vectors and stored files are cleaned up here once they exist (steps 7-8)
    workspace = get_workspace_or_404(db, workspace_id)
    db.delete(workspace)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
