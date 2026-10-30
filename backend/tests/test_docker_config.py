"""Guards for the Docker setup: the guarantees the deploy relies on, checked from the files."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
BACKEND_DOCKERFILE = REPO / "backend" / "Dockerfile"
NGINX_CONF = REPO / "frontend" / "nginx.conf"


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _ignore_patterns(context: str) -> set[str]:
    lines = (REPO / context / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return {line.strip().rstrip("/") for line in lines if line.strip() and not line.startswith("#")}


def _environment(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return {key: str(value) for key, value in env.items()}


def _api_location(conf: str) -> str:
    match = re.search(r"location /api/ \{(.*?)\n    \}", conf, re.DOTALL)
    assert match, "nginx.conf has no `location /api/` block"
    return match.group(1)


@pytest.mark.parametrize(
    ("context", "required"),
    [
        ("backend", {".env", "data", ".venv", ".git"}),
        ("frontend", {".env", "node_modules", ".git"}),
    ],
)
def test_dockerignore_keeps_secrets_and_local_state_out_of_the_build(context, required):
    assert required <= _ignore_patterns(context)


def test_backend_gets_secrets_only_from_env_file_at_runtime():
    backend = _compose()["services"]["backend"]

    assert backend["env_file"] in ("backend/.env", ["backend/.env"], "./backend/.env")
    for name in _environment(backend):
        assert not re.search(r"KEY|SECRET|TOKEN|PASSWORD", name), name


def test_every_service_has_a_memory_limit():
    for name, service in _compose()["services"].items():
        assert service["deploy"]["resources"]["limits"]["memory"], name


def test_data_lives_in_named_volumes_and_the_backend_is_not_published():
    compose = _compose()
    backend = compose["services"]["backend"]

    assert "ports" not in backend
    for mount in backend["volumes"]:
        source = mount.split(":", 1)[0]
        assert source in compose["volumes"], f"{mount} is not a named volume"
    assert any(mount.endswith(":/app/data") for mount in backend["volumes"])


def test_backend_runs_one_worker_as_non_root_with_the_model_offline():
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "--workers 1" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert re.search(r"^USER (?!root)\S+", dockerfile, re.MULTILINE)
    assert "HEALTHCHECK" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile


def test_forwarded_headers_are_trusted_only_from_the_compose_network():
    # Trusting "*" would let any client pick its own IP for the per-IP rate limit (step 18)
    compose = _compose()
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    allowed = _environment(compose["services"]["backend"])["FORWARDED_ALLOW_IPS"]
    subnet = compose["networks"]["default"]["ipam"]["config"][0]["subnet"]

    assert not re.search(r"forwarded-allow-ips[= ]['\"]?\*", dockerfile)
    assert "FORWARDED_ALLOW_IPS=*" not in dockerfile
    assert allowed == subnet


def test_nginx_streams_sse_unbuffered():
    assert re.search(r"proxy_buffering\s+off;", _api_location(NGINX_CONF.read_text("utf-8")))


def test_nginx_overwrites_the_client_ip_headers_instead_of_appending():
    conf = NGINX_CONF.read_text(encoding="utf-8")
    api = _api_location(conf)

    assert "$proxy_add_x_forwarded_for" not in conf
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;", api)
    assert re.search(r"proxy_set_header\s+X-Real-IP\s+\$remote_addr;", api)
