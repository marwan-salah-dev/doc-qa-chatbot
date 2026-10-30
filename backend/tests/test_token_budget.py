"""The public demo's daily LLM token cap: counted per UTC day, kept across restarts."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from chat_helpers import CITED_REPLY, MIN_SCORE, QUESTION, parse_sse, seed_documents
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import create_db_engine, create_session_factory
from app.services.llm import FakeChat, Usage
from app.services.token_budget import TokenBudget
from app.services.vectorstore import ChromaVectorStore

VISITOR = {"X-Visitor-Id": str(uuid.uuid4())}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    return create_session_factory(create_db_engine(tmp_path))


def test_usage_adds_up_and_survives_a_restart(session_factory: sessionmaker[Session]) -> None:
    clock = Clock(datetime(2026, 10, 30, 12, tzinfo=UTC))
    budget = TokenBudget(session_factory, cap=100, clock=clock)

    budget.record(Usage(input_tokens=40, output_tokens=20, complete=True))
    budget.record(Usage(input_tokens=30, output_tokens=None, complete=False))  # cut short

    assert budget.used_today() == 90
    assert not budget.exhausted()
    assert TokenBudget(session_factory, cap=100, clock=clock).used_today() == 90

    budget.record(Usage(input_tokens=10, output_tokens=0, complete=True))
    assert budget.exhausted()


def test_a_new_utc_day_starts_from_zero(session_factory: sessionmaker[Session]) -> None:
    clock = Clock(datetime(2026, 10, 30, 23, 59, tzinfo=UTC))
    budget = TokenBudget(session_factory, cap=50, clock=clock)
    budget.record(Usage(60, 0, complete=True))
    assert budget.exhausted()
    assert budget.seconds_until_reset() == pytest.approx(60)

    clock.now = datetime(2026, 10, 31, 0, 0, 1, tzinfo=UTC)

    assert budget.used_today() == 0
    assert not budget.exhausted()


def test_a_zero_cap_is_off(session_factory: sessionmaker[Session]) -> None:
    budget = TokenBudget(session_factory, cap=0)
    budget.record(Usage(10**9, 0, complete=True))

    assert not budget.exhausted()


# --- In the chat API -------------------------------------------------------------------------


@pytest.fixture
def capped(
    make_client: Callable[..., TestClient], api_store: ChromaVectorStore
) -> Callable[..., tuple[TestClient, FakeChat, str]]:
    def factory(**overrides: object) -> tuple[TestClient, FakeChat, str]:
        chat = FakeChat(CITED_REPLY, usage=Usage(input_tokens=10, output_tokens=5, complete=True))
        client = make_client(
            public_demo=True, rag_min_score=MIN_SCORE, chat_model=chat, **overrides
        )
        ws = client.post("/workspaces", json={"name": "Mine"}, headers=VISITOR).json()["id"]
        seed_documents(api_store, ws)
        conv = client.post(f"/workspaces/{ws}/conversations", headers=VISITOR).json()["id"]
        return client, chat, f"/workspaces/{ws}/conversations/{conv}/messages"

    return factory


def test_every_llm_call_counts_toward_the_cap(capped) -> None:
    client, chat, url = capped(daily_token_cap=1000)

    client.post(url, json={"question": QUESTION}, headers=VISITOR)

    budget = client.app.state.token_budget  # pyright: ignore[reportAttributeAccessIssue]
    assert budget.used_today() == 15 * len(chat.calls)


def test_once_the_cap_is_reached_questions_get_a_clear_429_without_an_llm_call(capped) -> None:
    client, chat, url = capped(daily_token_cap=1)
    first = client.post(url, json={"question": QUESTION}, headers=VISITOR)
    assert "done" in [name for name, _ in parse_sse(first.text)]
    calls = len(chat.calls)

    response = client.post(url, json={"question": QUESTION}, headers=VISITOR)

    assert response.status_code == 429
    assert "daily" in response.json()["detail"]
    assert "tomorrow" in response.json()["detail"]
    assert 0 < int(response.headers["Retry-After"]) <= 24 * 3600
    assert len(chat.calls) == calls


def test_private_deployments_have_no_cap(make_client: Callable[..., TestClient]) -> None:
    client = make_client(daily_token_cap=1)

    assert client.app.state.token_budget.cap == 0  # pyright: ignore[reportAttributeAccessIssue]
