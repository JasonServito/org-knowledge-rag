"""S14-T4: the `ingestion_jobs` table (migration 0009) and its reads and writes (`db/jobs.py`).

Every job is created inside `conn`'s rolled-back transaction. The one-active-job rule (ADR-013
D4) is the sitting's index check: a second queued job is refused, a finished one isn't counted.
"""

from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.errors import CheckViolation
from psycopg.rows import TupleRow

from orgknow.db.jobs import active_job, create_job, get_job, save_job
from orgknow.db.models import JobStep

Conn = psycopg.Connection[TupleRow]

STARTED = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
FINISHED = datetime(2026, 10, 14, 9, 1, 14, tzinfo=UTC)


def test_a_new_job_is_queued_with_the_4_steps_pending_in_order(conn: Conn) -> None:
    job = create_job(conn, "req-1")

    assert job is not None
    assert (job.status, job.attempts, job.error, job.request_id) == ("queued", 0, None, "req-1")
    assert (job.started_at, job.finished_at) == (None, None)
    assert job.created_at.tzinfo is not None
    # ADR-013 D2's recipe, in order, typed by hand.
    assert [step.name for step in job.steps] == ["ingest", "lifecycle", "embed", "chains"]
    assert {step.status for step in job.steps} == {"pending"}
    assert all(step.counts == {} and step.started_at is None for step in job.steps)
    assert get_job(conn, job.id) == job
    assert active_job(conn) == job


@pytest.mark.parametrize("status", ["queued", "running"])
def test_a_second_active_job_is_refused_and_a_finished_one_allows_a_new_one(
    conn: Conn, status: str
) -> None:
    first = create_job(conn, None)
    assert first is not None
    first.status = status  # type: ignore[assignment]
    save_job(conn, first)

    refused = create_job(conn, None)

    assert refused is None
    first.status = "succeeded"
    save_job(conn, first)
    second = create_job(conn, None)
    assert second is not None
    assert second.id != first.id
    assert active_job(conn) == second


def test_a_saved_job_reads_back_with_its_status_times_attempts_error_and_steps(conn: Conn) -> None:
    job = create_job(conn, "req-2")
    assert job is not None
    job.status = "failed"
    job.started_at, job.finished_at = STARTED, FINISHED
    job.attempts = 2
    job.error = "ingest: 1 failure"
    job.steps[0] = JobStep(
        name="ingest",
        status="failed",
        started_at=STARTED,
        finished_at=FINISHED,
        counts={"new_versions": 3, "fingerprint": "sha256:abc"},
        error="ingest: 1 failure",
    )

    save_job(conn, job)

    stored = get_job(conn, job.id)
    assert stored == job
    assert stored is not None
    assert stored.steps[0].counts == {"new_versions": 3, "fingerprint": "sha256:abc"}
    assert stored.steps[1].status == "pending"
    assert active_job(conn) is None  # failed is not active


def test_unknown_ids_and_no_active_job_read_as_none(conn: Conn) -> None:
    assert get_job(conn, 2**62) is None
    assert active_job(conn) is None


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("status", "paused", "ingestion_jobs_status_check"),
        ("attempts", -1, "ingestion_jobs_attempts_check"),
    ],
)
def test_the_table_refuses_an_unknown_status_and_negative_attempts(
    conn: Conn, column: str, value: object, constraint: str
) -> None:
    job = create_job(conn, None)
    assert job is not None

    with pytest.raises(CheckViolation, match=constraint), conn.transaction():
        conn.execute(
            f"UPDATE ingestion_jobs SET {column} = %s WHERE id = %s",  # type: ignore[arg-type]
            (value, job.id),
        )
