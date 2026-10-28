from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RagServiceDep, SessionFactory
from app.api.routes.workspaces import get_workspace_or_404
from app.api.schemas import ConversationOut, MessageCreate, MessageOut
from app.db.models import Conversation, Message
from app.db.session import get_db
from app.services.chat import (
    ChatEvent,
    ReplyFailed,
    ReplyGuard,
    ReplySaved,
    citation_dict,
    load_history,
    stream_reply,
)
from app.services.llm import ChatMessage
from app.services.rag import SourcesEvent

router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])

DbSession = Annotated[Session, Depends(get_db)]

REPLY_BUSY = "A reply is already being written in this conversation."


def get_conversation_or_404(db: Session, workspace_id: str, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(workspace_id: str, db: DbSession) -> Conversation:
    """An empty conversation; its title becomes the first question."""
    get_workspace_or_404(db, workspace_id)
    conversation = Conversation(workspace_id=workspace_id)
    db.add(conversation)
    db.commit()
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(workspace_id: str, db: DbSession) -> list[Conversation]:
    get_workspace_or_404(db, workspace_id)
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(Conversation.created_at.desc())
        )
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(workspace_id: str, conversation_id: str, db: DbSession) -> Response:
    db.delete(get_conversation_or_404(db, workspace_id, conversation_id))  # messages cascade
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(workspace_id: str, conversation_id: str, db: DbSession) -> list[Message]:
    get_conversation_or_404(db, workspace_id, conversation_id)
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )


# --- asking a question ---
# Everything that can fail with a status code (404, 409, 422) runs in dependencies, because once
# the event stream starts the response is already a 200.


@dataclass
class ReplyTurn:
    """A conversation reserved for one reply, and what that reply needs."""

    conversation_id: str
    asked_at: datetime
    history: list[ChatMessage] = field(default_factory=list)
    stream: AsyncGenerator[ChatEvent, None] | None = None


def get_reply_conversation(workspace_id: str, conversation_id: str, db: DbSession) -> Conversation:
    return get_conversation_or_404(db, workspace_id, conversation_id)


async def reserve_reply(
    request: Request, conversation: Annotated[Conversation, Depends(get_reply_conversation)]
) -> AsyncIterator[ReplyTurn]:
    """Hold the conversation while its reply streams; a second question meanwhile gets a 409.

    Released in this dependency's teardown rather than in the stream: FastAPI always runs it
    once the response is over, even if the stream never started (a 422, or a client that left
    early), whereas a generator that never started never runs its own `finally`.
    """
    guard = cast(ReplyGuard, request.app.state.reply_guard)
    if not guard.try_acquire(conversation.id):
        raise HTTPException(status.HTTP_409_CONFLICT, REPLY_BUSY)
    turn = ReplyTurn(conversation.id, asked_at=datetime.now(UTC))
    try:
        yield turn
    finally:
        try:
            # After a disconnect the stream may still be open: closing it saves the partial
            # answer, which must happen before the next reply can read the history.
            if turn.stream is not None:
                await turn.stream.aclose()
        finally:
            guard.release(conversation.id)


def load_reply_turn(turn: Annotated[ReplyTurn, Depends(reserve_reply)], db: DbSession) -> ReplyTurn:
    # Read after reserving, so a reply that has just finished is in the history
    turn.history = load_history(db, turn.conversation_id)
    return turn


@router.post("/{conversation_id}/messages", response_class=EventSourceResponse)
async def ask_question(
    workspace_id: str,
    body: MessageCreate,
    turn: Annotated[ReplyTurn, Depends(load_reply_turn)],
    rag: RagServiceDep,
    session_factory: SessionFactory,
) -> AsyncIterator[ServerSentEvent]:
    """Answer from the workspace's documents as Server-Sent Events.

    `sources` (every source given to the model), then `delta`s of answer text, then `done`
    (both messages are saved; carries their ids and the cited sources) or `error` (a message
    safe to show; nothing is saved).
    """
    turn.stream = stream_reply(
        rag,
        session_factory,
        workspace_id=workspace_id,
        conversation_id=turn.conversation_id,
        question=body.question,
        history=turn.history,
        asked_at=turn.asked_at,
    )
    async for event in turn.stream:
        yield _to_sse(event)


def _to_sse(event: ChatEvent) -> ServerSentEvent:
    if isinstance(event, SourcesEvent):
        sources = [citation_dict(source) for source in event.sources]
        return ServerSentEvent(event="sources", data={"sources": sources})
    if isinstance(event, ReplySaved):
        done = event.done
        return ServerSentEvent(
            event="done",
            data={
                "user_message_id": event.user_message_id,
                "message_id": event.message_id,
                "citations": [citation_dict(source) for source in done.citations],
                "refused": done.refused,
                "uncited": done.uncited,
            },
        )
    if isinstance(event, ReplyFailed):
        return ServerSentEvent(event="error", data={"message": event.message})
    return ServerSentEvent(event="delta", data={"text": event.text})
