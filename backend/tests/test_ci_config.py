"""Guards for the CI workflow: the guarantees the pipeline promises, checked from the file."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True
    return workflow.get("on") or workflow.get(True) or {}


def _runs(job: str) -> list[str]:
    steps = _workflow()["jobs"][job]["steps"]
    return [step["run"] for step in steps if "run" in step]


def _has_command(job: str, command: str) -> bool:
    return any(command in run for run in _runs(job))


def test_runs_on_push_and_pull_request_with_read_only_token():
    workflow = _workflow()
    assert {"push", "pull_request"} <= set(_triggers(workflow))
    assert workflow["permissions"] == {"contents": "read"}


def test_every_action_is_pinned_to_a_full_commit_sha():
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"), re.M)
    assert uses, "the workflow uses no actions?"
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"not pinned to a SHA: {ref}"


def test_needs_no_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "docker login" not in text


@pytest.mark.parametrize(
    "command",
    [
        "uv sync --frozen",
        "uv run pytest",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pyright",
    ],
)
def test_backend_job_runs(command: str):
    assert _has_command("backend", command)


@pytest.mark.parametrize(
    "command",
    [
        "npm ci",
        "npm run test",
        "npm run lint",
        "npm run typecheck",
        "npm run format:check",
        "npm run build",
    ],
)
def test_frontend_job_runs(command: str):
    assert _has_command("frontend", command)


def test_backend_tests_never_download_the_model():
    # Any test that quietly needs the real model should fail in CI, not download 130 MB
    job = _workflow()["jobs"]["backend"]
    env = {**_workflow().get("env", {}), **job.get("env", {})}
    assert str(env.get("HF_HUB_OFFLINE")) == "1"


def test_both_package_managers_are_cached():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "enable-cache: true" in text
    assert "cache: npm" in text


def test_docker_job_builds_without_pushing():
    assert _has_command("docker", "docker compose build")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "push" not in text.replace("push:", "").replace("on:", "")
    assert "docker/login-action" not in text
    # compose reads env_file for every command, so CI gives it the placeholder example
    assert _has_command("docker", "cp backend/.env.example backend/.env")
