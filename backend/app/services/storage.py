import shutil
from pathlib import Path

from app.services.parsers import FileKind


def workspace_files_dir(data_dir: Path, workspace_id: str) -> Path:
    return data_dir / "files" / workspace_id


def document_path(data_dir: Path, workspace_id: str, document_id: str, kind: FileKind) -> Path:
    """Where an uploaded original lives. Named by document id, never by the client's filename."""
    return workspace_files_dir(data_dir, workspace_id) / f"{document_id}.{kind}"


def save_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_workspace_files(data_dir: Path, workspace_id: str) -> None:
    shutil.rmtree(workspace_files_dir(data_dir, workspace_id), ignore_errors=True)
