from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def make_client(tmp_path: Path) -> Callable[..., TestClient]:
    """Build a client on a throwaway data dir; never reads .env."""

    def factory(**overrides: object) -> TestClient:
        overrides.setdefault("data_dir", tmp_path)
        return TestClient(create_app(Settings(_env_file=None, **overrides)))

    return factory


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
