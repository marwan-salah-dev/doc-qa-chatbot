"""One JSON file per run in `eval/results/`, so later runs can be compared with earlier ones."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).with_name("results")


def save_results(
    results_dir: Path, kind: str, payload: dict[str, Any], now: datetime | None = None
) -> Path:
    """`{kind}-YYYYMMDD-HHMMSS.json` (no colons, so the name is valid on Windows)."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{kind}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_previous(results_dir: Path, kind: str, before: Path | None = None) -> Any:
    """The newest earlier run of this kind (older than `before`, if given), or `None`."""
    runs = sorted(results_dir.glob(f"{kind}-*.json"))
    if before is not None:
        runs = [run for run in runs if run.name < before.name]
    if not runs:
        return None
    return json.loads(runs[-1].read_text(encoding="utf-8"))


def git_commit() -> str | None:
    """The checked-out commit (with `+dirty` for local changes), so a run says what it measured."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}+dirty" if dirty else commit
