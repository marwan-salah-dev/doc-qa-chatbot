import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import config, conversations, documents, health, workspaces
from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.logging_config import configure_logging
from app.services.chat import ReplyGuard
from app.services.cleanup import sweep
from app.services.embeddings import create_embedder, ensure_chunk_fits
from app.services.ingestion import fail_interrupted_documents
from app.services.limits import SlidingWindowLimiter
from app.services.llm import create_chat_model
from app.services.token_budget import TokenBudget
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
        cleanup = None
        if settings.public_demo:
            if not settings.admin_api_key.get_secret_value():
                logger.warning("PUBLIC_DEMO is on but ADMIN_API_KEY is empty: seeding will fail")
            # Once now (catches workspaces that expired while the app was down), then on a timer
            await _sweep_once(app, settings)
            cleanup = asyncio.create_task(_sweep_forever(app, settings))
        yield
        if cleanup is not None:
            cleanup.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup
        await app.state.chat_model.aclose()

    app = FastAPI(title="DocQA Support Agent", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.data_dir)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.reply_guard = ReplyGuard()
    app.state.limiter = SlidingWindowLimiter()
    # The daily cap protects the shared demo key; a private deployment pays for its own use
    daily_cap = settings.daily_token_cap if settings.public_demo else 0
    app.state.token_budget = TokenBudget(app.state.session_factory, daily_cap)

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
    app.include_router(config.router)
    app.include_router(workspaces.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    return app


# --- the public demo's cleanup -------------------------------------------------------------
# One asyncio task in the app's only process (exactly one uvicorn worker), so there is exactly
# one sweeper: no cron container, no lock, no two sweeps racing. See services/cleanup.py.


async def _sweep_once(app: FastAPI, settings: Settings) -> None:
    try:
        await asyncio.to_thread(
            sweep,
            app.state.session_factory,
            app.state.vector_store,
            settings.data_dir,
            visitor_chat_ttl=timedelta(hours=settings.visitor_workspace_ttl_hours),
        )
    except Exception:
        logger.exception("cleanup sweep failed")
    app.state.limiter.prune()


async def _sweep_forever(app: FastAPI, settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)
        await _sweep_once(app, settings)
