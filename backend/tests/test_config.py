import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.chunking import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS

BACKEND_DIR = Path(__file__).resolve().parents[1]


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def test_env_file_is_backend_dotenv_whatever_the_working_directory():
    # A relative ".env" would load a different file (or none) when run from the repo root.
    env_file = Settings.model_config.get("env_file")
    assert isinstance(env_file, Path)
    assert env_file.is_absolute()
    assert env_file == BACKEND_DIR / ".env"


def test_env_example_sits_next_to_env_and_documents_every_setting():
    example = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", example, flags=re.MULTILINE))
    expected = {name.upper() for name in Settings.model_fields}
    assert expected - documented == set()


def test_openai_base_url_defaults_to_empty():
    assert make_settings().openai_base_url == ""


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


def test_rag_defaults_fit_the_free_groq_tier():
    settings = make_settings()
    assert settings.rag_top_k == 6
    assert settings.rag_min_score == 0.5
    assert settings.rag_token_budget == 5500
    assert settings.rag_history_tokens == 1000
    # Condense call (history + ~300 for prompt, question and output) plus the answer call
    assert settings.rag_history_tokens + 300 + settings.rag_token_budget < 8000


@pytest.mark.parametrize(
    "overrides",
    [
        {"rag_top_k": 0},
        {"rag_min_score": -0.1},
        {"rag_min_score": 1.1},
        {"rag_token_budget": 0},
        {"rag_history_tokens": -1},
        {"rag_token_budget": 1024, "llm_max_output_tokens": 1024},
    ],
)
def test_bad_rag_settings_are_rejected(overrides: dict[str, object]):
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_default_local_embedding_model_is_bge_small():
    assert make_settings().local_embedding_model == "BAAI/bge-small-en-v1.5"
