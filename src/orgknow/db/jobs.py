"""The ingestion jobs' reads and writes (S14-T4; ADR-013 D1, D4, D6): the only SQL for
`ingestion_jobs`.

A job is one row, and its 4 steps are a JSON list in the row. The table is the worker's queue: at
most one job is queued or running, which the unique index `ingestion_jobs_one_active` (migration
0009) enforces, so `create_job` can't make a second one, even from 2 POSTs at the same instant.
"""

import psycopg
from psycopg.rows import TupleRow, class_row
from psycopg.types.json import Jsonb

from orgknow.db.models import IngestionJob, JobStep

# A job's fixed recipe (ADR-013 D2), in order.
STEP_NAMES = ("ingest", "lifecycle", "embed", "chains")


def _steps(steps: list[JobStep]) -> Jsonb:
    # psycopg sends a list as jsonb only when it's wrapped in Jsonb; dates go as ISO strings.
    return Jsonb([step.model_dump(mode="json") for step in steps])


def create_job(conn: psycopg.Connection[TupleRow], request_id: str | None) -> IngestionJob | None:
    """Insert a queued job with the 4 steps pending, and return it; None when the one-active-job
    rule refuses it (another job is queued or running). `request_id` is the creating request's."""
    with conn.cursor(row_factory=class_row(IngestionJob)) as cur:
        return cur.execute(
            """
            INSERT INTO ingestion_jobs (request_id, steps)
            VALUES (%(request_id)s, %(steps)s)
            -- A second queued or running job would break `ingestion_jobs_one_active`: no row is
            -- inserted, and none returned.
            ON CONFLICT DO NOTHING
            RETURNING id, status, created_at, started_at, finished_at, attempts, error,
                      request_id, steps
            """,
            {
                "request_id": request_id,
                "steps": _steps([JobStep(name=name) for name in STEP_NAMES]),
            },
        ).fetchone()


def get_job(conn: psycopg.Connection[TupleRow], job_id: int) -> IngestionJob | None:
    """The job with this id, or None."""
    with conn.cursor(row_factory=class_row(IngestionJob)) as cur:
        return cur.execute(
            """
            SELECT id, status, created_at, started_at, finished_at, attempts, error, request_id,
                   steps
            FROM ingestion_jobs
            WHERE id = %(id)s
            """,
            {"id": job_id},
        ).fetchone()


def active_job(conn: psycopg.Connection[TupleRow]) -> IngestionJob | None:
    """The job that is queued or running (at most one: the index), or None."""
    with conn.cursor(row_factory=class_row(IngestionJob)) as cur:
        return cur.execute(
            """
            SELECT id, status, created_at, started_at, finished_at, attempts, error, request_id,
                   steps
            FROM ingestion_jobs
            WHERE status IN ('queued', 'running')
            """
        ).fetchone()


def save_job(conn: psycopg.Connection[TupleRow], job: IngestionJob) -> None:
    """Store the job's status, times, attempts, error and steps (its id, creation time and
    request id never change)."""
    conn.execute(
        """
        UPDATE ingestion_jobs
        SET status = %(status)s, started_at = %(started_at)s, finished_at = %(finished_at)s,
            attempts = %(attempts)s, error = %(error)s, steps = %(steps)s
        WHERE id = %(id)s
        """,
        {
            "id": job.id,
            "status": job.status,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "attempts": job.attempts,
            "error": job.error,
            "steps": _steps(job.steps),
        },
    )
