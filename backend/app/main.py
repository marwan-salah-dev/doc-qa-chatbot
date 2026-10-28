import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import conversations, documents, health, workspaces
from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.logging_config import configure_logging
from app.services.chat import ReplyGuard
from app.services.embeddings import create_embedder, ensure_chunk_fits
from app.services.ingestion import fail_interrupted_documents
from app.services.llm import create_chat_model
from app.services.vectorstore import create_vector_store

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        embedder = create_embedder(settings)
        # Bad chunking config fails here, at startup, not halfway through someone's upload
        ensure_chunk_fits(embedder, settings.chunk_size_tokens)
        app.state.embedder = embedder
        app.state.vector_store = create_vector_store(settings, embedder)
        # A missing key for the chosen LLM provider fails here too, not on the first question
        app.state.chat_model = create_chat_model(settings)
        if interrupted := fail_interrupted_documents(app.state.session_factory):
            logger.warning("marked interrupted documents as failed", extra={"count": interrupted})
        yield
        await app.state.chat_model.aclose()

    app = FastAPI(title="DocQA Support Agent", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.data_dir)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.reply_guard = ReplyGuard()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    return app
