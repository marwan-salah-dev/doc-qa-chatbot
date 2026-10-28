"""Requests TestClient can't make: two at once (it runs one at a time), or one whose client
hangs up mid-stream (it reads every response to the end)."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import anyio
import httpx
import pytest
from chat_helpers import MIN_SCORE, QUESTION, BlockingChat, event_names, parse_sse, seed_documents
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.types import Message

from app.db import models
from app.services.vectorstore import ChromaVectorStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_only_one_reply_streams_at_a_time_per_conversation(
    make_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    chat = BlockingChat()
    app = make_client(chat_model=chat, rag_min_score=MIN_SCORE).app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        workspace_id = (await client.post("/workspaces", json={"name": "Acme"})).json()["id"]
        seed_documents(api_store, workspace_id)
        busy = (await client.post(f"/workspaces/{workspace_id}/conversations")).json()["id"]
        free = (await client.post(f"/workspaces/{workspace_id}/conversations")).json()["id"]

        async def ask(conversation_id: str) -> httpx.Response:
            return await client.post(
                f"/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
                json={"question": QUESTION},
            )

        first = asyncio.create_task(ask(busy))
        with anyio.fail_after(5):
            await chat.streaming.wait()

        second = await ask(busy)
        assert second.status_code == 409
        assert second.json() == {"detail": "A reply is already being written in this conversation."}

        other = await ask(free)  # a different conversation is not blocked
        assert other.status_code == 200
        assert event_names(parse_sse(other.text))[-1] == "done"

        chat.release.set()
        with anyio.fail_after(5):
            finished = await first
        assert event_names(parse_sse(finished.text))[-1] == "done"

        again = await ask(busy)
        assert again.status_code == 200


async def test_a_client_hanging_up_mid_answer_saves_the_partial_answer(
    make_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    """The whole real path: Starlette sees the disconnect, FastAPI cancels the SSE producer,
    and the reply is closed (its partial answer saved) before the guard is released."""
    chat = BlockingChat("Five days [1]. Keep your receipt.")
    app = make_client(chat_model=chat, rag_min_score=MIN_SCORE).app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        workspace_id = (await client.post("/workspaces", json={"name": "Acme"})).json()["id"]
        seed_documents(api_store, workspace_id)
        conversation_id = (await client.post(f"/workspaces/{workspace_id}/conversations")).json()[
            "id"
        ]
    path = f"/workspaces/{workspace_id}/conversations/{conversation_id}/messages"
    body = json.dumps({"question": QUESTION}).encode()

    # A bare ASGI call, so the "client" can hang up once the first delta exists
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    request_sent = False
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await chat.streaming.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    with anyio.fail_after(5):
        await app(scope, receive, send)

    assert sent[0]["status"] == 200
    with app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        user, assistant = db.scalars(
            select(models.Message)
            .where(models.Message.conversation_id == conversation_id)
            .order_by(models.Message.created_at)
        )
    assert (user.role, user.content) == (models.MessageRole.USER, QUESTION)
    assert (assistant.content, assistant.incomplete) == ("Five ", True)

    # The guard was released: the conversation takes a new question
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        again = await client.post(path, json={"question": QUESTION})
    assert again.status_code == 200
    assert event_names(parse_sse(again.text))[-1] == "done"
