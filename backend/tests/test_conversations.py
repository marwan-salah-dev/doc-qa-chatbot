import logging
from collections.abc import Callable
from typing import Any

import pytest
from chat_helpers import (
    CITED_REPLY,
    FAQ_DOC,
    MIN_SCORE,
    OFF_TOPIC,
    QUESTION,
    answer_of,
    event_names,
    parse_sse,
    seed_documents,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Conversation, Message
from app.services.chat import GENERIC_ERROR
from app.services.chunking import Chunk
from app.services.llm import ChatModel, FakeChat, LLMRateLimitError
from app.services.rag import NOT_FOUND
from app.services.vectorstore import ChromaVectorStore, SearchHit

FOLLOW_UP = "How long does it take?"


@pytest.fixture
def chat_client(make_client: Callable[..., TestClient]) -> Callable[..., TestClient]:
    """A client whose relevance threshold suits the fake embedder (see chat_helpers)."""

    def factory(chat: ChatModel | None = None, **overrides: object) -> TestClient:
        overrides.setdefault("rag_min_score", MIN_SCORE)
        return make_client(chat_model=chat or FakeChat(CITED_REPLY), **overrides)

    return factory


def make_workspace(client: TestClient, name: str = "Acme Dental") -> str:
    response = client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def make_conversation(client: TestClient, workspace_id: str) -> str:
    response = client.post(f"/workspaces/{workspace_id}/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def seeded_conversation(client: TestClient, store: ChromaVectorStore) -> tuple[str, str]:
    workspace_id = make_workspace(client)
    seed_documents(store, workspace_id)
    return workspace_id, make_conversation(client, workspace_id)


def ask(client: TestClient, workspace_id: str, conversation_id: str, question: str = QUESTION):
    return client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        json={"question": question},
    )


def ask_ok(
    client: TestClient, workspace_id: str, conversation_id: str, question: str = QUESTION
) -> list[tuple[str, Any]]:
    response = ask(client, workspace_id, conversation_id, question)
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def messages_of(client: TestClient, workspace_id: str, conversation_id: str) -> list[dict]:
    response = client.get(f"/workspaces/{workspace_id}/conversations/{conversation_id}/messages")
    assert response.status_code == 200
    return response.json()


def session_factory_of(client: TestClient) -> sessionmaker[Session]:
    return client.app.state.session_factory  # pyright: ignore[reportAttributeAccessIssue]


def done_of(events: list[tuple[str, Any]]) -> dict:
    name, data = events[-1]
    assert name == "done"
    return data


def usage_logs(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    """The `extra=` fields of each "chat usage" record."""
    return [vars(r) for r in caplog.records if r.getMessage() == "chat usage"]


# --- conversations ---


def test_conversations_are_created_and_listed_newest_first(client: TestClient):
    workspace_id = make_workspace(client)
    other_id = make_workspace(client, "Other")

    first = make_conversation(client, workspace_id)
    second = make_conversation(client, workspace_id)

    listed = client.get(f"/workspaces/{workspace_id}/conversations").json()
    assert [c["id"] for c in listed] == [second, first]
    assert listed[0]["workspace_id"] == workspace_id
    assert listed[0]["title"] == "New conversation"
    assert client.get(f"/workspaces/{other_id}/conversations").json() == []


def test_conversations_of_an_unknown_workspace_are_404(client: TestClient):
    assert client.post("/workspaces/nope/conversations").status_code == 404
    assert client.get("/workspaces/nope/conversations").status_code == 404


def test_a_new_conversation_has_no_messages(client: TestClient):
    workspace_id = make_workspace(client)
    conversation_id = make_conversation(client, workspace_id)

    assert messages_of(client, workspace_id, conversation_id) == []


def test_a_conversation_from_another_workspace_is_404(client: TestClient):
    workspace_id = make_workspace(client)
    other_id = make_workspace(client, "Other")
    conversation_id = make_conversation(client, other_id)
    base = f"/workspaces/{workspace_id}/conversations/{conversation_id}"

    assert client.get(f"{base}/messages").status_code == 404
    assert client.delete(base).status_code == 404
    assert ask(client, workspace_id, conversation_id).status_code == 404


def test_deleting_a_conversation_deletes_its_messages(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)
    ask_ok(client, workspace_id, conversation_id)

    response = client.delete(f"/workspaces/{workspace_id}/conversations/{conversation_id}")

    assert response.status_code == 204
    assert client.get(f"/workspaces/{workspace_id}/conversations").json() == []
    with session_factory_of(client)() as db:
        count = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
    assert count == 0


def test_deleting_a_workspace_deletes_its_conversations_and_messages(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)
    ask_ok(client, workspace_id, conversation_id)

    assert client.delete(f"/workspaces/{workspace_id}").status_code == 204

    with session_factory_of(client)() as db:
        conversations = db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.workspace_id == workspace_id)
        )
        messages = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
    assert (conversations, messages) == (0, 0)


# --- validation before the stream starts ---


@pytest.mark.parametrize(
    "body", [{"question": ""}, {"question": "   \n "}, {}, {"question": "x" * 4001}]
)
def test_an_empty_or_oversized_question_is_422(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore, body: dict
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    response = client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/messages", json=body
    )

    assert response.status_code == 422


def test_asking_in_an_unknown_conversation_is_404(chat_client: Callable[..., TestClient]):
    client = chat_client()
    workspace_id = make_workspace(client)

    response = ask(client, workspace_id, "nope")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


# --- streaming a grounded answer ---


def test_a_grounded_answer_streams_sources_then_deltas_then_done(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    response = ask(client, workspace_id, conversation_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = event_names(events)
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"delta"}
    assert len(names) > 3  # several deltas
    assert answer_of(events) == CITED_REPLY

    [source] = events[0][1]["sources"]
    assert source["number"] == 1
    assert (source["document_id"], source["filename"]) == (FAQ_DOC, "faq.txt")
    assert source["location"]["kind"] == "txt"
    assert (source["location"]["start"], source["location"]["end"]) == (1, 2)
    assert source["label"] == "lines 1-2"
    assert "Refunds are processed" in source["text"]

    done = done_of(events)
    assert done["citations"] == [source]
    assert (done["refused"], done["uncited"]) == (False, False)


def test_both_messages_are_saved_with_citations_and_flags(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    done = done_of(ask_ok(client, workspace_id, conversation_id))

    user, assistant = messages_of(client, workspace_id, conversation_id)
    assert (user["id"], user["role"], user["content"]) == (
        done["user_message_id"],
        "user",
        QUESTION,
    )
    assert user["citations"] == []
    assert (assistant["id"], assistant["role"], assistant["content"]) == (
        done["message_id"],
        "assistant",
        CITED_REPLY,
    )
    assert assistant["citations"] == done["citations"]
    assert (assistant["refused"], assistant["uncited"], assistant["incomplete"]) == (
        False,
        False,
        False,
    )
    assert user["created_at"] < assistant["created_at"]


def test_the_first_question_becomes_the_conversation_title(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)
    long_question = QUESTION + " " + "Please explain every step in detail. " * 4

    ask_ok(client, workspace_id, conversation_id, long_question)
    ask_ok(client, workspace_id, conversation_id, FOLLOW_UP)

    [conversation] = client.get(f"/workspaces/{workspace_id}/conversations").json()
    assert len(conversation["title"]) <= 80
    assert conversation["title"].startswith(QUESTION)
    assert conversation["title"].endswith("\N{HORIZONTAL ELLIPSIS}")


def test_a_follow_up_is_answered_with_the_saved_history(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    chat = FakeChat([CITED_REPLY, QUESTION, "Five business days [1]."])
    client = chat_client(chat)
    workspace_id, conversation_id = seeded_conversation(client, api_store)
    ask_ok(client, workspace_id, conversation_id)

    events = ask_ok(client, workspace_id, conversation_id, FOLLOW_UP)

    _first_answer, condense, answer = chat.calls
    assert QUESTION in condense.messages[0].content
    assert FOLLOW_UP in condense.messages[0].content
    # Old answers reach the model without their [n] markers
    assert [(m.role, m.content) for m in answer.messages[:-1]] == [
        ("user", QUESTION),
        ("assistant", "Refunds are processed within 5 business days."),
    ]
    assert done_of(events)["citations"][0]["document_id"] == FAQ_DOC
    assert len(messages_of(client, workspace_id, conversation_id)) == 4


def test_an_off_topic_question_is_refused_and_saved_as_refused(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    chat = FakeChat("should never be used")
    client = chat_client(chat)
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    events = ask_ok(client, workspace_id, conversation_id, OFF_TOPIC)

    assert chat.calls == []
    assert events[0] == ("sources", {"sources": []})
    assert answer_of(events) == NOT_FOUND
    done = done_of(events)
    assert (done["citations"], done["refused"], done["uncited"]) == ([], True, False)
    _user, assistant = messages_of(client, workspace_id, conversation_id)
    assert (assistant["content"], assistant["refused"]) == (NOT_FOUND, True)


def test_an_answer_without_citations_is_saved_as_uncited(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client(FakeChat("Refunds take five days."))
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    done = done_of(ask_ok(client, workspace_id, conversation_id))

    assert (done["refused"], done["uncited"]) == (False, True)
    _user, assistant = messages_of(client, workspace_id, conversation_id)
    assert (assistant["refused"], assistant["uncited"]) == (False, True)


def test_the_relevance_threshold_comes_from_settings(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    chat = FakeChat("should never be used")
    client = chat_client(chat, rag_min_score=0.99)
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    done = done_of(ask_ok(client, workspace_id, conversation_id))

    assert done["refused"] is True
    assert chat.calls == []


# --- errors become an SSE error event ---


def test_an_llm_error_mid_stream_becomes_an_error_event_and_nothing_is_saved(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    internal = "openai request failed: RateLimitError (HTTP 429)"
    chat = FakeChat(CITED_REPLY, error=LLMRateLimitError(internal), error_after=2)
    client = chat_client(chat)
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    response = ask(client, workspace_id, conversation_id)

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert event_names(events) == ["sources", "delta", "delta", "error"]
    assert events[-1][1] == {"message": LLMRateLimitError.user_message}
    assert "HTTP 429" not in response.text
    assert messages_of(client, workspace_id, conversation_id) == []


class QueryFailingStore:
    """A vector store that is down when searched."""

    def add_chunks(
        self, workspace_id: str, document_id: str, filename: str, chunks: list[Chunk]
    ) -> int:
        return len(chunks)

    def query(self, workspace_id: str, question: str, k: int = 5) -> list[SearchHit]:
        raise RuntimeError("connection refused to chroma:8000 (internal detail)")

    def delete_document(self, workspace_id: str, document_id: str) -> None:
        pass

    def delete_workspace(self, workspace_id: str) -> None:
        pass


def test_an_unexpected_error_becomes_a_generic_error_event(
    chat_client: Callable[..., TestClient],
):
    client = chat_client(store=QueryFailingStore())
    workspace_id = make_workspace(client)
    conversation_id = make_conversation(client, workspace_id)

    response = ask(client, workspace_id, conversation_id)

    assert response.status_code == 200
    assert parse_sse(response.text) == [("error", {"message": GENERIC_ERROR})]
    assert "internal detail" not in response.text
    assert messages_of(client, workspace_id, conversation_id) == []


# --- one reply at a time: the guard is always released ---


def test_the_reply_guard_is_released_after_every_kind_of_request(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    client = chat_client()
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    # after a 422
    assert ask(client, workspace_id, conversation_id, " ").status_code == 422
    # after a completed stream
    assert event_names(ask_ok(client, workspace_id, conversation_id))[-1] == "done"
    assert ask(client, workspace_id, conversation_id, FOLLOW_UP).status_code == 200


def test_the_reply_guard_is_released_after_an_error_stream(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    chat = FakeChat(CITED_REPLY, error=LLMRateLimitError("busy"), error_after=1)
    client = chat_client(chat)
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    assert event_names(ask_ok(client, workspace_id, conversation_id))[-1] == "error"
    assert event_names(ask_ok(client, workspace_id, conversation_id))[-1] == "error"


# --- token usage ---


def test_token_usage_is_logged_once_per_message(
    chat_client: Callable[..., TestClient],
    api_store: ChromaVectorStore,
    caplog: pytest.LogCaptureFixture,
):
    chat = FakeChat([CITED_REPLY, QUESTION, "Five business days [1]."])
    client = chat_client(chat)  # before attaching: create_app resets the root handlers
    logger = logging.getLogger("app.services.chat")
    logger.addHandler(caplog.handler)
    try:
        workspace_id, conversation_id = seeded_conversation(client, api_store)
        ask_ok(client, workspace_id, conversation_id)
        done = done_of(ask_ok(client, workspace_id, conversation_id, FOLLOW_UP))
    finally:
        logger.removeHandler(caplog.handler)

    tokens = ("llm_calls", "input_tokens", "output_tokens")
    first, follow_up = usage_logs(caplog)
    assert [first[key] for key in tokens] == [1, 10, 5]
    # The follow-up is condensed first: two calls, FakeChat reports 10 in / 5 out for each
    assert [follow_up[key] for key in tokens] == [2, 20, 10]
    assert follow_up["outcome"] == "done"
    assert follow_up["message_id"] == done["message_id"]
    assert follow_up["conversation_id"] == conversation_id
    logged = " ".join(str(fields) for fields in usage_logs(caplog))
    assert QUESTION not in logged  # never message content


def test_gpt_oss_style_citations_are_normalized_in_the_stream_and_the_saved_answer(
    chat_client: Callable[..., TestClient], api_store: ChromaVectorStore
):
    reply = (
        "Refunds are processed within 5\N{NARROW NO-BREAK SPACE}business days "
        "\N{LEFT BLACK LENTICULAR BRACKET}1\N{RIGHT BLACK LENTICULAR BRACKET}."
    )
    client = chat_client(FakeChat(reply))
    workspace_id, conversation_id = seeded_conversation(client, api_store)

    events = ask_ok(client, workspace_id, conversation_id)

    # The narrow no-break space becomes a no-break space, so "5 business" never wraps apart
    expected = CITED_REPLY.replace("5 business", "5\N{NO-BREAK SPACE}business")
    assert answer_of(events) == expected
    done = done_of(events)
    assert [citation["number"] for citation in done["citations"]] == [1]
    assert done["uncited"] is False
    _user, assistant = messages_of(client, workspace_id, conversation_id)
    assert assistant["content"] == expected
    assert assistant["uncited"] is False
