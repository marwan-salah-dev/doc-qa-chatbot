from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.embeddings import Embedder
from app.services.llm import ChatModel
from app.services.rag import RagService
from app.services.vectorstore import VectorStore


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """For background tasks, which outlive the request's own session."""
    return cast(sessionmaker[Session], request.app.state.session_factory)


def get_embedder(request: Request) -> Embedder:
    """The app's embedder, built at startup; tests swap it with `dependency_overrides`."""
    return cast(Embedder, request.app.state.embedder)


def get_vector_store(request: Request) -> VectorStore:
    """The app's vector store, built at startup; tests swap it with `dependency_overrides`."""
    return cast(VectorStore, request.app.state.vector_store)


def get_chat_model(request: Request) -> ChatModel:
    """The app's chat model, built at startup; tests swap it with `dependency_overrides`."""
    return cast(ChatModel, request.app.state.chat_model)


AppSettings = Annotated[Settings, Depends(get_app_settings)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
ChatModelDep = Annotated[ChatModel, Depends(get_chat_model)]


def get_rag_service(
    settings: AppSettings, store: VectorStoreDep, chat: ChatModelDep, embedder: EmbedderDep
) -> RagService:
    """Built per request (it is only a bundle of settings and shared clients); tests swap it, or
    the chat model and store it is built from, with `dependency_overrides`."""
    return RagService(
        store,
        chat,
        # The embedder's real tokenizer locally: closer to the LLM's count than a 4-char estimate
        count_tokens=embedder.count_tokens,
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        token_budget=settings.rag_token_budget,
        history_tokens=settings.rag_history_tokens,
        max_output_tokens=settings.llm_max_output_tokens,
    )


RagServiceDep = Annotated[RagService, Depends(get_rag_service)]
