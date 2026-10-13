"""FastAPI app factory: `/health`, `/ready`, and `POST /query` (S12-T2), which answers through the
same pipeline as `orgknow ask` (`pipeline.answer_question`). `make serve` runs it with uvicorn."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anthropic
import psycopg
from fastapi import FastAPI, HTTPException, Response, status
from langfuse import Langfuse
from pydantic import BaseModel, Field, SecretStr

from orgknow.db.health import is_reachable
from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.generation.generator import AnthropicGenerator, Generator
from orgknow.generation.schema import Answer
from orgknow.pipeline import ASK_ERRORS, answer_question, langfuse_client, load_reranker, one_line
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.router import ClaudeRouter, Router
from orgknow.settings import Settings


class Query(BaseModel):
    """`POST /query`'s body."""

    # Not empty and not only spaces, as `orgknow ask`.
    question: str = Field(min_length=1, pattern=r"\S")


def create_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    generator: Generator | None = None,
    router: Router | None = None,
    langfuse: Langfuse | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    """The app. Tests inject fakes; what isn't injected is built from the settings at startup."""
    # Settings are read when the app is built, not at import time, so tests can pass their own.
    app_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Built once per process, before the first request, never per request: the reranker's
        # model loads here (rerank, temporal and authority modes; None in dense and hybrid).
        # Known limit: concurrent requests share the one reranker.
        nonlocal embedder, generator, router, langfuse, reranker
        # The clients first (no network call), so a missing key stops startup before the
        # reranker's slow load.
        routed = app_settings.retrieval_mode in ("temporal", "authority")
        if generator is None or (routed and router is None):
            anthropic_key = _key(app_settings.anthropic_api_key, "ANTHROPIC_API_KEY")
            client = anthropic.Anthropic(api_key=anthropic_key.get_secret_value())
            if generator is None:
                generator = AnthropicGenerator(client, app_settings)
            if routed and router is None:
                router = ClaudeRouter(client, app_settings)
        if embedder is None:
            voyage_key = _key(app_settings.voyage_api_key, "VOYAGE_API_KEY")
            embedder = VoyageEmbedder(
                app_settings.voyage_api_url, voyage_key, app_settings.embedding_model
            )
        if reranker is None:
            reranker = load_reranker(app_settings)
        if langfuse is None:
            langfuse = langfuse_client(app_settings)  # None, after "tracing off", without keys
        try:
            yield
        finally:
            if langfuse is not None:
                langfuse.flush()  # the traces still queued (ADR-006 D3)

    app = FastAPI(title="orgknow", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        # Liveness: the process is up and answering HTTP. Deliberately ignores the database.
        return {"status": "ok"}

    @app.get("/ready")
    def ready(response: Response) -> dict[str, str]:
        # Readiness: can this process serve real traffic? A plain `def` (not `async def`)
        # makes FastAPI run it in a worker thread, so the blocking DB ping can't stall the
        # event loop.
        if is_reachable(app_settings.database_url, app_settings.db_connect_timeout_s):
            return {"status": "ready"}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}

    @app.post("/query")
    def query(body: Query) -> Answer:
        """The answer `orgknow ask` prints for the question, with its `trace_id` (null when
        tracing is off). An ask error is a 502 with its one-line message; a database that can't
        be reached, a 503."""
        # A plain `def`, as `/ready`: it runs in a worker thread, so the blocking calls can't
        # stall the event loop.
        assert embedder is not None and generator is not None  # built at startup
        try:
            # One connection per request.
            with psycopg.connect(
                app_settings.database_url, connect_timeout=app_settings.db_connect_timeout_s
            ) as conn:
                return answer_question(
                    body.question,
                    conn,
                    embedder,
                    generator,
                    app_settings,
                    langfuse,
                    reranker,
                    router,
                )
        except ASK_ERRORS as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, one_line(error)) from error
        except psycopg.OperationalError as error:
            # Never the error's own message: it can name the database URL.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "database unreachable"
            ) from error

    return app


def _key(value: SecretStr | None, name: str) -> SecretStr:
    """An API key from the settings, or a startup error that names its variable, never a value."""
    if not value:  # unset or empty
        raise RuntimeError(f"{name} is not set: add the key to .env (see .env.example).")
    return value
