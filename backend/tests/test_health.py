import json
import logging

from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_config import JsonFormatter
from app.main import create_app


def make_client(**overrides: object) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, **overrides)))


def test_health_returns_ok():
    response = make_client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_configured_origin_only():
    client = make_client(cors_origins="http://a.test, http://b.test")
    allowed = client.get("/health", headers={"Origin": "http://b.test"})
    denied = client.get("/health", headers={"Origin": "http://evil.test"})
    assert allowed.headers["access-control-allow-origin"] == "http://b.test"
    assert "access-control-allow-origin" not in denied.headers


def test_settings_defaults_and_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("CORS_ORIGINS", "http://x.test,http://y.test")
    settings = Settings(_env_file=None)
    assert settings.embedding_provider == "openai"
    assert settings.cors_origins == ["http://x.test", "http://y.test"]
    assert settings.llm_provider == "anthropic"


def test_json_formatter_includes_extra_fields():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", (), None)
    record.status = 200
    data = json.loads(JsonFormatter().format(record))
    assert data["message"] == "hello"
    assert data["level"] == "INFO"
    assert data["status"] == 200
