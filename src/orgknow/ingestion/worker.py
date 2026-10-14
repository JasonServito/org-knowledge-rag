"""The ingestion worker: `make worker` (S14-T5; ADR-013 D1, D2, D3, D5).

Every WORKER_POLL_S seconds it tries the corpus-writer lock (`db/writer_lock.py`). With it, it
runs the active job (`db/jobs.py`: the one queued or running), then releases the lock; with no
job, it releases the lock at once and sleeps. So a hand-run writer (`make ingest`, ...) can run
while the worker is idle, and exits 1 while a job runs.

A job is a fixed recipe (ADR-013 D2): ingest -> lifecycle -> embed -> chains, each step calling
the function its `make` target calls. Each step's status, times and counts are saved in the job's
row before and after it runs, so the job's row shows its progress.

- An error fails the step and the job at once, and the later steps stay pending, never run (D5).
  So embed never runs after a failed ingest: after `make reset-corpus`, a partly stored corpus
  would make embed's orphan deletion drop the vectors of the texts not stored yet (D2's guard).
- A crash (the worker killed, or stopped with Ctrl-C) leaves the job running. The next worker to
  hold the lock resumes it at its first step that hasn't succeeded; a step left running starts
  again from its beginning (each step is safe to re-run). Attempts are counted at each start; a
  job found at WORKER_MAX_ATTEMPTS is failed without running.
"""

import json
import logging
import logging.config
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.jobs import active_job, save_job
from orgknow.db.models import IngestionJob
from orgknow.db.report import stored_aliases, stored_chunks, stored_documents, stored_versions
from orgknow.db.writer_lock import release_writer_lock, try_writer_lock
from orgknow.embeddings.embed import RunTooLarge, embed_missing
from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.ingestion.github import GithubSnapshotError
from orgknow.ingestion.ingest import ReleasesMismatch, ingest
from orgknow.ingestion.lifecycle import rebuild_lifecycle
from orgknow.ingestion.manifest import load_normalization, load_releases, load_scope
from orgknow.ingestion.report import fingerprint
from orgknow.logs import request_id
from orgknow.provenance.build import chain_seeds, store_chain
from orgknow.settings import Settings

# Named, not `__name__`: run with `python -m`, this module's `__name__` is `__main__`, outside
# the `orgknow` logger that config/logging.json sets to INFO, so its INFO lines would be dropped.
log = logging.getLogger("orgknow.ingestion.worker")

Conn = psycopg.Connection[TupleRow]
# What a step reports (call d), saved in its `counts`, e.g. {"new_versions": 0, "fingerprint": ...}.
StepCounts = dict[str, int | str]
# A step's name (one of `db/jobs.py`'s STEP_NAMES) and its function, which runs on the worker's
# connection. Tests pass fakes.
Step = tuple[str, Callable[[Conn], StepCounts]]

# `make serve`'s log config (call g): JSON lines on stderr. Relative to the repo root, where the
# make targets run.
LOG_CONFIG = Path("config/logging.json")
# While another writer holds the lock, the worker says so at most once per this many seconds,
# not at every poll.
BUSY_LOG_INTERVAL_S = 60.0
_busy_logged_at: float | None = None  # time.monotonic() of the last such line


class IngestFailed(Exception):
    """Ingest reported failed documents or versions: any one fails the step (call d)."""


# The errors whose text is shown in the job (call h): each is one line written for the person
# running ingestion. Any other error's text could hold anything (a path, a server's reply), and
# the job is readable over the API, so it stays in the worker log.
KNOWN_ERRORS = (ReleasesMismatch, GithubSnapshotError, RunTooLarge, IngestFailed)


def ingest_step(conn: Conn, settings: Settings) -> StepCounts:
    """`make ingest`'s store and chunk, without its lifecycle rebuild (the next step), then the
    stored corpus's fingerprint (`make ingest-report`'s)."""
    manifest = settings.corpus_manifest_path
    summary = ingest(
        conn,
        load_scope(manifest, settings.corpus_lock_path, settings.ingest_scope),
        settings.corpus_cache_dir.expanduser(),
        load_releases(manifest),
        load_normalization(manifest),
        settings.claim_synonyms,
        settings.chunk_max_tokens,
    )
    if summary.failures:
        failures = sorted(summary.failures)  # the report's order
        raise IngestFailed(f"{len(failures)} ingest failures; the first: {failures[0]}")
    # Read on the worker's connection: it holds the lock, so no writer commits meanwhile.
    digest = fingerprint(
        stored_documents(conn), stored_aliases(conn), stored_versions(conn), stored_chunks(conn)
    )
    return {
        "documents_stored": sum(summary.documents.values()),
        "new_documents": summary.new_documents,
        "new_versions": summary.new_versions,
        "closed_versions": summary.closed_versions,
        "new_chunks": summary.new_chunks,
        "failures": len(summary.failures),  # 0: any failure raised above
        "fingerprint": f"sha256:{digest}",
    }


def lifecycle_step(conn: Conn, settings: Settings) -> StepCounts:
    """`make lifecycle`: rebuild the observed lifecycle."""
    rows = rebuild_lifecycle(conn, settings.corpus_cache_dir.expanduser(), settings.claim_synonyms)
    return {"rows": len(rows)}


def embed_step(conn: Conn, settings: Settings, embedder: Embedder) -> StepCounts:
    """`make embed`: embed every text with no vector, capped by EMBED_MAX_TOKENS_PER_RUN."""
    summary = embed_missing(
        conn,
        embedder,
        settings.embed_batch_max_texts,
        settings.embed_batch_max_tokens,
        settings.embed_max_tokens_per_run,
    )
    return {
        "texts": summary.texts,
        "requests": summary.requests,
        "embedded": summary.embedded,
        "tokens": summary.total_tokens,  # Voyage's count: what was billed
        "orphans_deleted": summary.orphans_deleted,
    }


def chains_step(conn: Conn, settings: Settings) -> StepCounts:
    """`make chains`: rebuild every manifest chain; per seed, its steps found and missing, e.g.
    {"kep:2572_found": 6, "kep:2572_missing": 0}."""
    counts: StepCounts = {}
    for seed in chain_seeds(settings.corpus_manifest_path):
        evidence = store_chain(conn, seed, settings)
        missing = sum(step.missing_reason is not None for step in evidence)
        counts[f"{seed}_found"] = len(evidence) - missing
        counts[f"{seed}_missing"] = missing
    return counts


def job_steps(settings: Settings, embedder: Embedder) -> list[Step]:
    """The real steps, in ADR-013 D2's order."""
    return [
        ("ingest", lambda conn: ingest_step(conn, settings)),
        ("lifecycle", lambda conn: lifecycle_step(conn, settings)),
        ("embed", lambda conn: embed_step(conn, settings, embedder)),
        ("chains", lambda conn: chains_step(conn, settings)),
    ]


def _now() -> datetime:
    return datetime.now(UTC)


def _log_busy() -> None:
    """Log that another writer holds the lock, unless that was logged under a minute ago."""
    global _busy_logged_at
    now = time.monotonic()
    if _busy_logged_at is None or now - _busy_logged_at >= BUSY_LOG_INTERVAL_S:
        log.info("Another corpus writer holds the lock; waiting for it")
        _busy_logged_at = now


def run_job(conn: Conn, job: IngestionJob, steps: Sequence[Step], max_attempts: int) -> None:
    """Run (or resume) `job` to its end, saving its row as it goes. The caller holds the lock."""
    extra = {"job_id": job.id}
    if job.attempts >= max_attempts:
        job.status, job.finished_at = "failed", _now()
        job.error = f"gave up after {job.attempts} attempts"
        for step in job.steps:
            if step.status == "running":  # the step the last attempt's worker died in
                step.status, step.finished_at, step.error = "failed", job.finished_at, job.error
        save_job(conn, job)
        log.error("Job %d: %s", job.id, job.error, extra=extra)
        return

    job.attempts += 1
    job.status = "running"
    job.started_at = job.started_at or _now()
    save_job(conn, job)
    log.info("Job %d: attempt %d started", job.id, job.attempts, extra=extra)
    functions = dict(steps)
    for step in job.steps:
        if step.status == "succeeded":  # by an earlier attempt: a resumed job
            continue
        step.status, step.started_at, step.finished_at = "running", _now(), None
        save_job(conn, job)
        log.info("Job %d: step %s started", job.id, step.name, extra=extra)
        try:
            step.counts = functions[step.name](conn)
        except Exception as error:
            if isinstance(error, KNOWN_ERRORS):
                text = str(error)
                log.error("Job %d: step %s failed: %s", job.id, step.name, text, extra=extra)
            else:
                text = f"internal error; see the worker log (job {job.id})"
                log.error("Job %d: step %s failed", job.id, step.name, exc_info=error, extra=extra)
            step.status, step.finished_at, step.error = "failed", _now(), text
            job.status, job.finished_at, job.error = "failed", step.finished_at, text
            save_job(conn, job)  # the later steps stay pending
            return
        step.status, step.finished_at = "succeeded", _now()
        save_job(conn, job)
        log.info(
            "Job %d: step %s succeeded",
            job.id,
            step.name,
            extra={**extra, "counts": step.counts},
        )
    job.status, job.finished_at = "succeeded", _now()
    save_job(conn, job)
    log.info("Job %d succeeded", job.id, extra=extra)


def run_once(conn: Conn, steps: Sequence[Step], max_attempts: int) -> int | None:
    """One poll: under the writer lock, run the active job (`run_job`) and return its id. None,
    having run nothing, when another session holds the lock or no job is queued or running.
    The lock is released before this returns or raises (on a lost connection, the server frees
    it)."""
    if not try_writer_lock(conn):
        _log_busy()
        return None
    try:
        job = active_job(conn)
        if job is None:
            return None
        # Every line logged during the job carries its creating request's ID (call g).
        token = request_id.set(job.request_id)
        try:
            run_job(conn, job, steps, max_attempts)
        finally:
            request_id.reset(token)
        return job.id
    finally:
        release_writer_lock(conn)


def main(settings: Settings | None = None) -> None:
    """`make worker`: poll for jobs until Ctrl-C."""
    settings = settings or Settings()
    # Checked before connecting (call f).
    if settings.ingest_scope != "full":
        scope = settings.ingest_scope
        sys.exit(f"The worker runs only with INGEST_SCOPE=full (ADR-013 D2), not {scope}.")
    api_key = settings.voyage_api_key
    if api_key is None or not api_key.get_secret_value():
        sys.exit(
            "VOYAGE_API_KEY is not set. The worker's embed step calls the Voyage API: add the key "
            "to .env (see .env.example)."
        )
    logging.config.dictConfig(json.loads(LOG_CONFIG.read_text(encoding="utf-8")))
    embedder = VoyageEmbedder(
        settings.voyage_api_url,
        api_key,
        settings.embedding_model,
        timeout_s=settings.voyage_timeout_s,
        max_retries=settings.voyage_max_retries,
    )
    steps = job_steps(settings, embedder)
    try:
        # One autocommit connection for the lock and every step (call e): each step's
        # `conn.transaction()` blocks commit on their own. No statement timeout: a step's
        # statements may run long.
        with psycopg.connect(
            settings.database_url,
            autocommit=True,
            connect_timeout=settings.db_connect_timeout_s,
        ) as conn:
            log.info("Worker started: polling every %d s", settings.worker_poll_s)
            while True:
                if run_once(conn, steps, settings.worker_max_attempts) is None:
                    time.sleep(settings.worker_poll_s)
    except KeyboardInterrupt:
        # A job stopped midway stays running: a crash, resumed by the next start (D5). The lock
        # was released, or freed when the connection closed.
        log.info("Worker stopped (Ctrl-C)")


if __name__ == "__main__":
    main()
