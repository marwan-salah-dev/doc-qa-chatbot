"""Create the "Demo: BrightSmile Dental" workspace and load the files in `backend/demo_data/`.

Start the backend first, then run from backend/:

    uv run python -m scripts.seed_demo [--api-url http://localhost:8000]

It goes through the running API, so the files are validated, deduplicated and indexed exactly
like a browser upload (and the server stays the only process writing to its Chroma store). It is
safe to run again: the workspace is found by name, files already in it are skipped, a file that
failed to index is reindexed, and a file whose committed copy has changed (a different SHA-256)
is deleted and uploaded again, so edits to demo_data/ reach the index. Other workspaces are never
touched.
"""

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.demo import DEMO_WORKSPACE_NAME

DEMO_DATA_DIR = Path(__file__).resolve().parents[1] / "demo_data"
DEMO_FILES = (
    "brightsmile-patient-handbook.pdf",
    "brightsmile-price-list.docx",
    "brightsmile-faq.txt",
)
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
BUSY_STATUSES = ("pending", "processing")


class ApiResponse(Protocol):
    @property
    def status_code(self) -> int: ...
    @property
    def text(self) -> str: ...
    def json(self) -> Any: ...


class ApiClient(Protocol):
    """What the seed needs from an HTTP client: an `httpx.Client` with a base URL, or the
    tests' Starlette `TestClient` (which is built on the separate httpx2 package)."""

    def get(self, url: str) -> ApiResponse: ...
    def post(self, url: str, *, json: Any = None, files: Any = None) -> ApiResponse: ...
    def delete(self, url: str) -> ApiResponse: ...


class SeedError(Exception):
    """Seeding could not finish. The message says why."""


@dataclass
class SeedResult:
    workspace_id: str
    created_workspace: bool
    uploaded: list[str] = field(default_factory=list)
    reindexed: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def seed(
    client: ApiClient,
    *,
    data_dir: Path = DEMO_DATA_DIR,
    timeout: float = 300,
    poll_interval: float = 2,
) -> SeedResult:
    """Make sure the demo workspace holds every demo file, then wait until all are ready."""
    workspace_id, created = _find_or_create_workspace(client)
    result = SeedResult(workspace_id, created)
    existing = {doc["filename"]: doc for doc in _documents(client, workspace_id)}

    for name in DEMO_FILES:
        path = data_dir / name
        doc = existing.get(name)
        if doc is None:
            if _upload(client, workspace_id, path):
                result.uploaded.append(name)
            else:
                result.skipped.append(name)
        elif doc["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            # The committed file changed: replace it (deleting also drops its chunks and file)
            url = f"/workspaces/{workspace_id}/documents/{doc['id']}"
            _check(client.delete(url), f"DELETE {url}")
            _upload(client, workspace_id, path)
            result.replaced.append(name)
        elif doc["status"] == "failed":
            url = f"/workspaces/{workspace_id}/documents/{doc['id']}/reindex"
            _check(client.post(url), f"POST {url}")
            result.reindexed.append(name)
        else:
            result.skipped.append(name)

    _wait_until_ready(client, workspace_id, timeout, poll_interval)
    return result


def _find_or_create_workspace(client: ApiClient) -> tuple[str, bool]:
    listed = _check(client.get("/workspaces"), "GET /workspaces").json()
    matches = [w for w in listed if w["name"] == DEMO_WORKSPACE_NAME]
    if matches:
        # Should there ever be several, keep using the oldest one
        return min(matches, key=lambda w: w["created_at"])["id"], False
    response = _check(
        client.post("/workspaces", json={"name": DEMO_WORKSPACE_NAME}), "POST /workspaces"
    )
    return response.json()["id"], True


def _documents(client: ApiClient, workspace_id: str) -> list[dict]:
    url = f"/workspaces/{workspace_id}/documents"
    return _check(client.get(url), f"GET {url}").json()


def _upload(client: ApiClient, workspace_id: str, path: Path) -> bool:
    """Upload one file; False when the workspace already has the same content under another
    name (the API's duplicate check answers 409)."""
    file = (path.name, path.read_bytes(), CONTENT_TYPES[path.suffix])
    url = f"/workspaces/{workspace_id}/documents"
    response = client.post(url, files={"file": file})
    if response.status_code == HTTPStatus.CONFLICT:
        return False
    _check(response, f"POST {url} ({path.name})")
    return True


def _wait_until_ready(
    client: ApiClient, workspace_id: str, timeout: float, poll_interval: float
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        docs = [d for d in _documents(client, workspace_id) if d["filename"] in DEMO_FILES]
        if failed := [d for d in docs if d["status"] == "failed"]:
            details = "; ".join(f"{d['filename']}: {d['error']}" for d in failed)
            raise SeedError(f"Indexing failed for {details}")
        if not any(d["status"] in BUSY_STATUSES for d in docs):
            return
        if time.monotonic() > deadline:
            raise SeedError(f"Documents were still indexing after {timeout:.0f} seconds.")
        time.sleep(poll_interval)


def _check(response: ApiResponse, what: str) -> ApiResponse:
    if response.status_code >= HTTPStatus.BAD_REQUEST:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise SeedError(f"{what} -> {response.status_code}: {detail}")
    return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--api-url", default="http://localhost:8000", help="the backend's URL")
    parser.add_argument("--ui-url", default="http://localhost:5173", help="the frontend's URL")
    parser.add_argument("--timeout", type=float, default=300, help="seconds to wait for indexing")
    args = parser.parse_args(argv)

    try:
        with httpx.Client(base_url=args.api_url, timeout=60) as client:
            result = seed(client, timeout=args.timeout)
    except httpx.TransportError:
        print(
            f"Could not reach the API at {args.api_url}. Start the backend first:\n"
            "  uv run uvicorn app.main:create_app --factory --port 8000",
            file=sys.stderr,
        )
        return 1
    except SeedError as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1

    action = "Created" if result.created_workspace else "Found"
    print(f'{action} workspace "{DEMO_WORKSPACE_NAME}" ({result.workspace_id})')
    for label, names in (
        ("Uploaded", result.uploaded),
        ("Reindexed", result.reindexed),
        ("Replaced (file changed)", result.replaced),
        ("Already present", result.skipped),
    ):
        if names:
            print(f"  {label}: {', '.join(names)}")
    print(f"All demo documents are ready. Open {args.ui_url}/w/{result.workspace_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
