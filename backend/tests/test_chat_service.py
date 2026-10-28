"""Disconnects, driven on the service directly: TestClient buffers the whole response, so it
can't hang up halfway through a stream."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import chromadb
import pytest
from chat_helpers import MIN_SCORE, QUESTION, BlockingChat, seed_documents
from chromadb.config import Settings as ChromaSettings
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Conversation, Message, MessageRole, Workspace
from app.db.session import create_db_engine, create_session_factory
from app.services.chat import ChatEvent, stream_reply
from app.services.embeddings import FakeEmbedder
from app.services.llm import ChatModel, FakeChat
from app.services.rag import DeltaEvent, RagService, SourcesEvent
from app.services.vectorstore import ChromaVectorStore

pytestmark = pytest.mark.anyio

WS = "a" * 32
PARTIAL_REPLY = "Five days [1]. Keep your receipt."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    return create_session_factory(create_db_engine(tmp_path / "data"))


@pytest.fixture
def conversation_id(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as db:
        conversation = Conversation(workspace_id=WS)
        db.add_all([Workspace(id=WS, name="Acme"), conversation])
        db.commit()
        return conversation.id


@pytest.fixture
def store(tmp_path: Path) -> ChromaVectorStore:
    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
    )
    store = ChromaVectorStore(client, FakeEmbedder(dimension=256))
    seed_documents(store, WS)
    return store


def start_reply(
    store: ChromaVectorStore,
    chat: ChatModel,
    session_factory: sessionmaker[Session],
    conversation_id: str,
) -> AsyncGenerator[ChatEvent, None]:
    rag = RagService(
        store,
        chat,
        count_tokens=lambda text: len(text.split()),
        top_k=6,
        min_score=MIN_SCORE,
        token_budget=5500,
        history_tokens=1000,
        max_output_tokens=1024,
    )
    return stream_reply(
        rag,
        session_factory,
        workspace_id=WS,
        conversation_id=conversation_id,
        question=QUESTION,
        history=[],
        asked_at=datetime.now(UTC),
    )


def saved(session_factory: sessionmaker[Session], conversation_id: str) -> list[Message]:
    with session_factory() as db:
        return list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
        )


def usage_log(caplog: pytest.LogCaptureFixture) -> dict[str, Any]:
    [record] = [r for r in caplog.records if r.getMessage() == "chat usage"]
    return vars(record)


async def test_closing_mid_answer_saves_the_partial_answer_as_incomplete(
    store: ChromaVectorStore,
    session_factory: sessionmaker[Session],
    conversation_id: str,
    caplog: pytest.LogCaptureFixture,
):
    reply = start_reply(store, FakeChat(PARTIAL_REPLY), session_factory, conversation_id)

    with caplog.at_level(logging.INFO, logger="app.services.chat"):
        assert isinstance(await anext(reply), SourcesEvent)
        deltas = [await anext(reply) for _ in range(3)]
        assert all(isinstance(delta, DeltaEvent) for delta in deltas)
        await reply.aclose()  # what a client disconnect does

    user, assistant = saved(session_factory, conversation_id)
    assert (user.role, user.content, user.incomplete) == (MessageRole.USER, QUESTION, False)
    assert (assistant.role, assistant.content) == (MessageRole.ASSISTANT, "Five days [1]. ")
    assert assistant.incomplete is True
    assert [citation["number"] for citation in assistant.citations] == [1]
    # The flags describe finished answers only
    assert (assistant.refused, assistant.uncited) == (False, False)

    usage = usage_log(caplog)
    assert (usage["outcome"], usage["message_id"]) == ("incomplete", assistant.id)
    assert usage["llm_calls"] == 1


async def test_cancelling_mid_answer_saves_the_partial_answer_as_incomplete(
    store: ChromaVectorStore, session_factory: sessionmaker[Session], conversation_id: str
):
    chat = BlockingChat(PARTIAL_REPLY)
    reply = start_reply(store, chat, session_factory, conversation_id)

    async def consume() -> list[ChatEvent]:
        return [event async for event in reply]

    task = asyncio.create_task(consume())
    with anyio.fail_after(5):
        await chat.streaming.wait()
    task.cancel()  # what the SSE server does when the client hangs up
    with pytest.raises(asyncio.CancelledError):
        await task

    _user, assistant = saved(session_factory, conversation_id)
    assert (assistant.content, assistant.incomplete) == ("Five ", True)
    assert assistant.citations == []


async def test_closing_before_any_answer_text_saves_nothing(
    store: ChromaVectorStore,
    session_factory: sessionmaker[Session],
    conversation_id: str,
    caplog: pytest.LogCaptureFixture,
):
    reply = start_reply(store, FakeChat(PARTIAL_REPLY), session_factory, conversation_id)

    with caplog.at_level(logging.INFO, logger="app.services.chat"):
        assert isinstance(await anext(reply), SourcesEvent)
        await reply.aclose()

    assert saved(session_factory, conversation_id) == []
    usage = usage_log(caplog)
    assert (usage["outcome"], usage["message_id"]) == ("abandoned", None)


async def test_a_partial_answer_is_saved_with_normalized_citations(
    store: ChromaVectorStore, session_factory: sessionmaker[Session], conversation_id: str
):
    reply_text = (
        "Five days \N{LEFT BLACK LENTICULAR BRACKET}1\N{DAGGER}faq.txt"
        "\N{RIGHT BLACK LENTICULAR BRACKET}. Keep your receipt."
    )
    reply = start_reply(store, FakeChat(reply_text), session_factory, conversation_id)

    assert isinstance(await anext(reply), SourcesEvent)
    for _ in range(3):  # "Five ", "days ", "【1†faq.txt】. "
        await anext(reply)
    await reply.aclose()

    _user, assistant = saved(session_factory, conversation_id)
    assert assistant.content == "Five days [1]. "
    assert assistant.incomplete is True
    assert [citation["number"] for citation in assistant.citations] == [1]
