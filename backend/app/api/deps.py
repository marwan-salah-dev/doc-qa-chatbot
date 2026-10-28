from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.embeddings import Embedder
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


AppSettings = Annotated[Settings, Depends(get_app_settings)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
