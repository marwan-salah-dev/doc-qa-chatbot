import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.chunking import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def test_chunk_defaults_are_350_and_50():
    settings = make_settings()
    assert settings.chunk_size_tokens == 350
    assert settings.chunk_overlap_tokens == 50


def test_chunker_defaults_match_settings_defaults():
    settings = make_settings()
    assert settings.chunk_size_tokens == DEFAULT_MAX_TOKENS
    assert settings.chunk_overlap_tokens == DEFAULT_OVERLAP_TOKENS


def test_chunk_sizes_come_from_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHUNK_SIZE_TOKENS", "200")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "20")
    settings = make_settings()
    assert (settings.chunk_size_tokens, settings.chunk_overlap_tokens) == (200, 20)


@pytest.mark.parametrize(("size", "overlap"), [(100, 100), (100, 150), (0, 0), (100, -1)])
def test_bad_chunk_settings_are_rejected(size: int, overlap: int):
    with pytest.raises(ValidationError):
        make_settings(chunk_size_tokens=size, chunk_overlap_tokens=overlap)


def test_default_local_embedding_model_is_bge_small():
    assert make_settings().local_embedding_model == "BAAI/bge-small-en-v1.5"
