"""One chat turn: stream a RAG answer, save the question and the answer, log token usage."""

import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Conversation, Message, MessageRole
from app.services.llm import ChatMessage, LLMError, Usage
from app.services.rag import (
    DeltaEvent,
    DoneEvent,
    RagService,
    Source,
    SourcesEvent,
    clean_citation_markers,
    parse_citations,
)

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong while answering. Please try again."

# RagService trims history to RAG_HISTORY_TOKENS; this only caps how much is read from the DB
HISTORY_MESSAGES = 20
TITLE_MAX_CHARS = 80

Outcome = Literal["done", "incomplete", "error", "abandoned"]


class ReplyGuard:
    """Conversations with a reply being written right now, so a second one can be refused.

    In-process only, which is correct for the single uvicorn worker this app runs. With several
    workers or servers it would need a shared lock (a database row or Redis). Only used from the
    event loop thread, so the set needs no lock of its own.
    """

    def __init__(self) -> None:
        self._busy: set[str] = set()

    def try_acquire(self, conversation_id: str) -> bool:
        if conversation_id in self._busy:
            return False
        self._busy.add(conversation_id)
        return True

    def release(self, conversation_id: str) -> None:
        self._busy.discard(conversation_id)


@dataclass(frozen=True, slots=True)
class ReplySaved:
    """Sent last when the answer finished: both messages are saved."""

    user_message_id: str
    message_id: str
    done: DoneEvent


@dataclass(frozen=True, slots=True)
class ReplyFailed:
    """Sent last when the answer failed; nothing is saved. `message` is safe to show users."""

    message: str


ChatEvent = SourcesEvent | DeltaEvent | ReplySaved | ReplyFailed


@dataclass
class _UsageTally:
    """Token usage of every LLM call in one turn (the condense call too)."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: Usage) -> None:
        self.llm_calls += 1
        # None means the provider never said (a stream cut short), so count what is known
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0


def citation_dict(source: Source) -> dict[str, Any]:
    """A source as JSON, both for the SSE events and for `Message.citations`."""
    return {
        "number": source.number,
        "document_id": source.document_id,
        "filename": source.filename,
        "location": asdict(source.location),
        "label": source.location.label(),
        "text": source.text,
        "score": source.score,
    }


def title_from(question: str) -> str:
    title = " ".join(question.split())
    if len(title) <= TITLE_MAX_CHARS:
        return title
    return title[: TITLE_MAX_CHARS - 1].rstrip() + "\N{HORIZONTAL ELLIPSIS}"


def load_history(
    db: Session, conversation_id: str, limit: int = HISTORY_MESSAGES
) -> list[ChatMessage]:
    """The conversation's latest `limit` messages, oldest first."""
    latest = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return [
        ChatMessage("user" if message.role == MessageRole.USER else "assistant", message.content)
        for message in reversed(list(latest))
    ]


def _save_turn(
    session_factory: sessionmaker[Session],
    conversation_id: str,
    question: str,
    asked_at: datetime,
    answer: str,
    citations: Sequence[Source],
    *,
    refused: bool = False,
    uncited: bool = False,
    incomplete: bool = False,
) -> tuple[str, str]:
    """Save the question and its answer in one transaction; return both message ids."""
    with session_factory() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise LookupError("the conversation was deleted while the answer streamed")
        has_messages = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        if not has_messages:
            conversation.title = title_from(question)
        user = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            created_at=asked_at,
        )
        assistant = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            citations=[citation_dict(source) for source in citations],
            refused=refused,
            uncited=uncited,
            incomplete=incomplete,
        )
        db.add_all([user, assistant])
        db.commit()
        return user.id, assistant.id


async def stream_reply(
    rag: RagService,
    session_factory: sessionmaker[Session],
    *,
    workspace_id: str,
    conversation_id: str,
    question: str,
    history: Sequence[ChatMessage],
    asked_at: datetime,
) -> AsyncGenerator[ChatEvent, None]:
    """Yield a `SourcesEvent`, `DeltaEvent`s, then `ReplySaved` or `ReplyFailed`.

    Both messages are saved together once the answer is done. After an error nothing is saved,
    so retrying doesn't repeat the question in the history. If the client leaves mid-answer
    (this generator is closed or cancelled), the text that had streamed is saved marked
    `incomplete`: the user saw it, usually because they pressed Stop. If no answer text had
    streamed yet, nothing is saved. One "chat usage" line is logged in every case.
    """
    usage = _UsageTally()
    sources: list[Source] = []
    parts: list[str] = []
    outcome: Outcome = "abandoned"
    message_id: str | None = None
    try:
        answer = rag.answer(workspace_id, question, history, on_usage=usage.add)
        async with aclosing(answer) as events:
            async for event in events:
                if isinstance(event, DoneEvent):
                    user_message_id, message_id = _save_turn(
                        session_factory,
                        conversation_id,
                        question,
                        asked_at,
                        event.answer,
                        event.citations,
                        refused=event.refused,
                        uncited=event.uncited,
                    )
                    outcome = "done"
                    yield ReplySaved(user_message_id, message_id, event)
                    continue
                if isinstance(event, SourcesEvent):
                    sources = event.sources
                else:
                    parts.append(event.text)
                yield event
    except LLMError as exc:
        outcome = "error"
        yield ReplyFailed(exc.user_message)
    except Exception:
        outcome = "error"
        logger.exception("chat reply failed", extra={"conversation_id": conversation_id})
        yield ReplyFailed(GENERIC_ERROR)
    finally:
        if outcome == "abandoned" and parts:
            # No `await` in here: while being cancelled, an await would be cancelled again
            # (the deltas are already normalized; only the [1†source] notes are left to drop)
            partial = clean_citation_markers("".join(parts))
            message_id = _save_partial(
                session_factory, conversation_id, question, asked_at, partial, sources
            )
            outcome = "incomplete"
        logger.info(
            "chat usage",
            extra={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "outcome": outcome,
                "llm_calls": usage.llm_calls,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        )


def _save_partial(
    session_factory: sessionmaker[Session],
    conversation_id: str,
    question: str,
    asked_at: datetime,
    answer: str,
    sources: Sequence[Source],
) -> str | None:
    """Save a cut-off answer. `refused`/`uncited` stay False: they describe finished answers."""
    citations = [sources[number - 1] for number in parse_citations(answer, len(sources))]
    try:
        _user_message_id, message_id = _save_turn(
            session_factory, conversation_id, question, asked_at, answer, citations, incomplete=True
        )
    except Exception:
        # Already unwinding a disconnect; losing the partial answer must not raise over it
        logger.exception(
            "could not save a partial answer", extra={"conversation_id": conversation_id}
        )
        return None
    return message_id
