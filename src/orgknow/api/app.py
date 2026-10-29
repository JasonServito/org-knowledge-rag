"""FastAPI app factory: `/health`, `/ready`, `POST /query` (S12-T2), which answers through the
same pipeline as `orgknow ask` (`pipeline.answer_question`), and `GET /decisions/{canonical_id}`
(S13-T5), which reads a stored decision chain as `orgknow chain` does (`load_chain`), and the
ingestion job routes (S14-T6; ADR-013): `POST /ingestion-jobs` queues a rebuild that `make worker`
runs, and `GET /ingestion-jobs/{job_id}` shows its progress. `make serve` runs it with uvicorn.
Every response carries an `X-Request-ID`, and every error one envelope (S14-T2;
docs/interfaces.md)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anthropic
import psycopg
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from langfuse import Langfuse
from pydantic import BaseModel, Field, SecretStr
from starlette.exceptions import HTTPException

from orgknow.api.errors import ApiError, api_error, http_error, invalid_request
from orgknow.api.middleware import RequestIdMiddleware
from orgknow.db.connect import api_connection
from orgknow.db.health import is_reachable
from orgknow.db.jobs import active_job, create_job, get_job
from orgknow.db.models import IngestionJob
from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.generation.generator import AnthropicGenerator, Generator
from orgknow.generation.schema import Answer
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.logs import request_id
from orgknow.pipeline import ASK_ERRORS, answer_question, langfuse_client, load_reranker, one_line
from orgknow.provenance.chain import Chain, load_chain
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
            client = anthropic.Anthropic(
                api_key=anthropic_key.get_secret_value(),
                max_retries=app_settings.anthropic_max_retries,
            )
            if generator is None:
                generator = AnthropicGenerator(client, app_settings)
            if routed and router is None:
                router = ClaudeRouter(client, app_settings)
        if embedder is None:
            voyage_key = _key(app_settings.voyage_api_key, "VOYAGE_API_KEY")
            embedder = VoyageEmbedder(
                app_settings.voyage_api_url,
                voyage_key,
                app_settings.embedding_model,
                timeout_s=app_settings.voyage_timeout_s,
                max_retries=app_settings.voyage_max_retries,
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

    app = FastAPI(
        title="orgknow",
        lifespan=lifespan,
        # Each error as the one envelope (api/errors.py). An unexpected exception becomes the
        # `internal` 500 in the middleware instead.
        exception_handlers={
            ApiError: api_error,
            RequestValidationError: invalid_request,
            HTTPException: http_error,
        },
    )
    app.add_middleware(RequestIdMiddleware)

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
    def query(body: Query, request: Request) -> Answer:
        """The answer `orgknow ask` prints for the question, with its `trace_id` (null when
        tracing is off). An ask error is a 502 `upstream_failed` with its one-line message; a
        database that can't be reached, or a statement past its timeout, a 503
        `database_unavailable`. Any other error (e.g. a missing table) is the middleware's 500
        `internal`."""
        # A plain `def`, as `/ready`: it runs in a worker thread, so the blocking calls can't
        # stall the event loop.
        assert embedder is not None and generator is not None  # built at startup
        try:
            # One autocommit connection per request: no transaction stays open during the
            # answer call (db/connect.py).
            with api_connection(app_settings) as conn:
                result = answer_question(
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
            raise ApiError("upstream_failed", one_line(error)) from error
        except psycopg.OperationalError as error:
            # Includes a statement cancelled by its timeout (`QueryCanceled`). Never the error's
            # own message: it can name the database URL.
            raise ApiError("database_unavailable", "database unavailable") from error
        if result.trace_id is not None:
            # For the middleware's log line of this request (S14-R1 open call f).
            request.state.trace_id = result.trace_id
        return result

    @app.get("/decisions/{canonical_id}")
    def decision(canonical_id: str) -> Chain:
        """The stored decision chain of the seed KEP `canonical_id` (e.g. `kep:2572`): the model
        `orgknow chain` prints from (`load_chain`). Free, read-only, never builds (`make chains`
        does). No stored chain: a 404 `not_found`; a database that can't be reached, or a
        statement past its timeout: a 503, as `/query`."""
        repo_urls = load_repo_urls(app_settings.corpus_manifest_path)
        try:
            with api_connection(app_settings) as conn:
                chain = load_chain(conn, canonical_id, repo_urls)
        except psycopg.OperationalError as error:
            # Never the error's own message: it can name the database URL.
            raise ApiError("database_unavailable", "database unavailable") from error
        if chain is None:
            # The id isn't repeated: a message never carries the caller's input.
            raise ApiError(
                "not_found",
                "no stored decision chain for this canonical_id; chains are built by make chains",
            )
        return chain

    @app.post("/ingestion-jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_ingestion_job(response: Response) -> IngestionJob:
        """Queue a rebuild of the corpus (ingest, lifecycle, embed, chains; ADR-013 D2), which
        `make worker` runs: a 202 with the new job, its `request_id` this request's. When a job is
        already queued or running, a 200 with that job instead (D4), so a repeated POST is safe.
        Takes no input: a request body is ignored. Never takes the corpus-writer lock. A database
        that can't be reached, or a statement past its timeout: a 503, as `/query`."""
        try:
            with api_connection(app_settings) as conn:
                # One insert per try, refused while a job is active (the database's
                # one-active-job rule). A refused insert, then no active job: that job ended in
                # between, so the next insert succeeds. At most 2 tries (S14-R2 call i).
                for _ in range(2):
                    job = create_job(conn, request_id.get())
                    if job is not None:
                        return job
                    job = active_job(conn)
                    if job is not None:
                        response.status_code = status.HTTP_200_OK
                        return job
        except psycopg.OperationalError as error:
            # Never the error's own message: it can name the database URL.
            raise ApiError("database_unavailable", "database unavailable") from error
        # Practically unreachable: a job ended between each refused insert and the read after it.
        # The middleware logs this and answers the `internal` 500; the caller can POST again.
        raise RuntimeError("no ingestion job created or active after 2 tries")

    @app.get("/ingestion-jobs/{job_id}")
    def ingestion_job(job_id: int) -> IngestionJob:
        """The ingestion job `job_id`, with each step's status, times and counts. No such job: a
        404 `not_found`; a non-integer id: a 422; a database that can't be reached, or a
        statement past its timeout: a 503, as `/query`."""
        try:
            with api_connection(app_settings) as conn:
                # An id beyond bigint's range is sent as a numeric and matches no row: a 404.
                job = get_job(conn, job_id)
        except psycopg.OperationalError as error:
            raise ApiError("database_unavailable", "database unavailable") from error
        if job is None:
            # The id isn't repeated: a message never carries the caller's input.
            raise ApiError("not_found", "no ingestion job with this id")
        return job

    return app


def _key(value: SecretStr | None, name: str) -> SecretStr:
    """An API key from the settings, or a startup error that names its variable, never a value."""
    if not value:  # unset or empty
        raise RuntimeError(f"{name} is not set: add the key to .env (see .env.example).")
    return value
