"""S14-T5: the worker's `run_once` (ADR-013 D1, D3, D5, D6; the S14-R2 contract's "Pinned: T5").

The steps are fakes that record their calls, except in the pinned "embed never runs after a failed
ingest" test, which runs the real ingest step with `ingest` faked to report failures. Most tests
run the worker on `conn`, rolled back at the end. The resume test can't: a subprocess worker must
see its job, and the test sees the subprocess's writes, so that job is committed and deleted at the
end. Expected texts are typed by hand from the contract (calls c and h).
"""

import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.jobs import STEP_NAMES, active_job, create_job, get_job, save_job
from orgknow.db.models import IngestionJob
from orgknow.db.writer_lock import try_writer_lock
from orgknow.embeddings.embed import RunTooLarge
from orgknow.ingestion import worker
from orgknow.ingestion.ingest import Summary
from orgknow.ingestion.worker import Step, StepCounts, run_once
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]
# Each call of a fake step: its name, and every step's status as stored when it ran.
Calls = list[tuple[str, list[str]]]

ROOT = Path(__file__).parents[2]
STARTED = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def recording(name: str, calls: Calls, counts: StepCounts) -> Step:
    """A fake step that records its call, with the stored statuses it sees, and returns
    `counts`."""

    def run(conn: Conn) -> StepCounts:
        job = active_job(conn)
        calls.append((name, [] if job is None else [step.status for step in job.steps]))
        return counts

    return name, run


def raising(name: str, calls: Calls, error: Exception) -> Step:
    """A fake step that records its call, then raises `error`."""

    def run(conn: Conn) -> StepCounts:
        calls.append((name, []))
        raise error

    return name, run


def all_recording(calls: Calls) -> list[Step]:
    return [recording(name, calls, {}) for name in STEP_NAMES]


def new_job(conn: Conn, request_id: str | None = None) -> IngestionJob:
    job = create_job(conn, request_id)
    assert job is not None, "another job is queued or running in the test database"
    return job


def stored(conn: Conn, job_id: int) -> IngestionJob:
    job = get_job(conn, job_id)
    assert job is not None
    return job


def test_a_job_runs_its_4_steps_in_order_and_saves_each_ones_progress(conn: Conn) -> None:
    job = new_job(conn, "req-1")
    calls: Calls = []
    steps = [
        recording("ingest", calls, {"new_versions": 3, "fingerprint": "sha256:abc"}),
        recording("lifecycle", calls, {"rows": 3295}),
        recording("embed", calls, {"requests": 0}),
        recording("chains", calls, {"kep:2572_found": 6, "kep:2572_missing": 0}),
    ]
    before = datetime.now(UTC)

    assert run_once(conn, steps, 3) == job.id

    done = stored(conn, job.id)
    assert (done.status, done.attempts, done.error) == ("succeeded", 1, None)
    # Each step ran once, in ADR-013 D2's order, and saw itself stored as running, the steps
    # before it succeeded and the ones after it pending (Decision 6's per-step progress).
    assert calls == [
        ("ingest", ["running", "pending", "pending", "pending"]),
        ("lifecycle", ["succeeded", "running", "pending", "pending"]),
        ("embed", ["succeeded", "succeeded", "running", "pending"]),
        ("chains", ["succeeded", "succeeded", "succeeded", "running"]),
    ]
    assert [(step.name, step.status, step.counts, step.error) for step in done.steps] == [
        ("ingest", "succeeded", {"new_versions": 3, "fingerprint": "sha256:abc"}, None),
        ("lifecycle", "succeeded", {"rows": 3295}, None),
        ("embed", "succeeded", {"requests": 0}, None),
        ("chains", "succeeded", {"kep:2572_found": 6, "kep:2572_missing": 0}, None),
    ]
    # The job's and every step's start and finish, in order.
    times = [done.started_at]
    times += [at for step in done.steps for at in (step.started_at, step.finished_at)]
    times.append(done.finished_at)
    assert None not in times
    assert times == sorted(times)  # type: ignore[type-var]
    assert before <= times[0]  # type: ignore[operator]


def test_an_error_fails_the_step_and_the_job_at_once(conn: Conn, settings: Settings) -> None:
    job = new_job(conn)
    calls: Calls = []
    text = "3 texts to embed come to 9 estimated tokens, above EMBED_MAX_TOKENS_PER_RUN (1)."
    steps = [
        recording("ingest", calls, {"new_versions": 0}),
        raising("lifecycle", calls, RunTooLarge(text)),
        recording("embed", calls, {}),
        recording("chains", calls, {}),
    ]

    assert run_once(conn, steps, 3) == job.id

    failed = stored(conn, job.id)
    assert (failed.status, failed.attempts, failed.error) == ("failed", 1, text)
    assert failed.finished_at is not None
    assert [(step.status, step.error) for step in failed.steps] == [
        ("succeeded", None),
        ("failed", text),
        ("pending", None),
        ("pending", None),
    ]
    assert failed.steps[1].finished_at is not None
    assert [name for name, _ in calls] == ["ingest", "lifecycle"]  # 3 and 4 never called
    # Released after a failure too: another session takes the lock.
    with psycopg.connect(settings.database_url, autocommit=True) as other:
        assert try_writer_lock(other)


def test_embed_never_runs_after_a_failed_ingest(
    conn: Conn, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The real ingest step (it reads the committed manifest and lock), with `ingest` reporting 2
    # failures: any failure fails the step (call d), and the later steps never run (pinned).
    failures = ["kep:9999: no Summary section", "1.24 docs:a: bad front matter"]
    monkeypatch.setattr(worker, "ingest", lambda *args: Summary(failures=failures))
    step_settings = settings.model_copy(
        update={
            "corpus_manifest_path": ROOT / "config" / "corpus_manifest.yaml",
            "corpus_lock_path": ROOT / "config" / "corpus_manifest.lock.yaml",
            "corpus_cache_dir": tmp_path,
        }
    )
    job = new_job(conn)
    calls: Calls = []
    steps: list[Step] = [
        ("ingest", lambda c: worker.ingest_step(c, step_settings)),
        recording("lifecycle", calls, {}),
        recording("embed", calls, {}),
        recording("chains", calls, {}),
    ]

    run_once(conn, steps, 3)

    failed = stored(conn, job.id)
    # Call h: the count and the first failure, in the report's (sorted) order.
    text = "2 ingest failures; the first: 1.24 docs:a: bad front matter"
    assert (failed.status, failed.error) == ("failed", text)
    assert [step.status for step in failed.steps] == ["failed", "pending", "pending", "pending"]
    assert calls == []


def test_a_job_found_at_the_attempt_limit_fails_without_running(conn: Conn) -> None:
    # A job whose 3rd attempt's worker died in step 2.
    job = new_job(conn)
    job.status, job.attempts, job.started_at = "running", 3, STARTED
    job.steps[0].status, job.steps[1].status = "succeeded", "running"
    save_job(conn, job)
    calls: Calls = []

    assert run_once(conn, all_recording(calls), 3) == job.id

    failed = stored(conn, job.id)
    assert (failed.status, failed.attempts) == ("failed", 3)
    assert failed.error == "gave up after 3 attempts"
    assert failed.finished_at is not None
    assert failed.started_at == STARTED
    assert calls == []
    # The step its last worker died in no longer reads running.
    assert [step.status for step in failed.steps] == ["succeeded", "failed", "pending", "pending"]


def test_run_once_does_nothing_while_a_cli_writer_holds_the_lock(
    conn: Conn, settings: Settings
) -> None:
    job = new_job(conn)
    calls: Calls = []

    with psycopg.connect(settings.database_url, autocommit=True) as cli_writer:
        assert try_writer_lock(cli_writer)
        assert run_once(conn, all_recording(calls), 3) is None

    assert stored(conn, job.id) == job  # untouched
    assert calls == []


def test_a_cli_writer_is_refused_while_the_worker_runs_a_step(
    conn: Conn, settings: Settings
) -> None:
    new_job(conn)
    tries: list[bool] = []

    with psycopg.connect(settings.database_url, autocommit=True) as cli_writer:

        def try_lock(_: Conn) -> StepCounts:
            tries.append(try_writer_lock(cli_writer))
            return {}

        run_once(conn, [(name, try_lock) for name in STEP_NAMES], 3)
        tries.append(try_writer_lock(cli_writer))  # after the job: released

    assert tries == [False, False, False, False, True]


def test_an_unknown_errors_text_stays_in_the_worker_log(
    conn: Conn, caplog: pytest.LogCaptureFixture
) -> None:
    job = new_job(conn)
    calls: Calls = []
    steps = all_recording(calls)
    steps[0] = raising("ingest", calls, RuntimeError("secret-xyz"))

    run_once(conn, steps, 3)

    failed = stored(conn, job.id)
    text = f"internal error; see the worker log (job {job.id})"  # call h
    assert (failed.status, failed.error, failed.steps[0].error) == ("failed", text, text)
    assert "secret-xyz" not in failed.model_dump_json()
    # The traceback, with the error's text, is in the log instead.
    logged = [r for r in caplog.records if r.exc_info and "secret-xyz" in str(r.exc_info[1])]
    assert len(logged) == 1
    assert logged[0].job_id == job.id  # type: ignore[attr-defined]


# A worker whose step 1 succeeds and whose step 2 blocks until the test kills it.
KILLED_WORKER = """
import sys, time
import psycopg
from orgknow.ingestion.worker import run_once

def ingest(conn):
    return {"run_by": "the killed worker"}

def block(conn):
    time.sleep(60)
    return {}

conn = psycopg.connect(sys.argv[1], autocommit=True)
run_once(conn, [("ingest", ingest), ("lifecycle", block), ("embed", block), ("chains", block)], 3)
"""


@pytest.fixture
def committed(settings: Settings) -> Iterator[Conn]:
    """An autocommit connection; every job left in the table at the end is deleted."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        try:
            yield conn
        finally:
            conn.execute("DELETE FROM ingestion_jobs")


def test_a_killed_workers_job_is_resumed_at_its_first_unfinished_step(
    committed: Conn, settings: Settings
) -> None:
    job = new_job(committed, "req-resume")
    # The Python process itself, never a `uv run` wrapper: killing the wrapper leaves its child
    # running (the sitting's first kill probe).
    process = subprocess.Popen([sys.executable, "-c", KILLED_WORKER, settings.database_url])
    try:
        deadline = time.monotonic() + 30
        while stored(committed, job.id).steps[1].status != "running":
            assert process.poll() is None, "the subprocess worker exited"
            assert time.monotonic() < deadline, "step 2 never started"
            time.sleep(0.05)
    finally:
        process.kill()  # SIGKILL: no cleanup runs in the worker
        process.wait()
    killed = stored(committed, job.id)
    calls: Calls = []
    steps = [
        recording("ingest", calls, {"run_by": "the test"}),
        recording("lifecycle", calls, {"rows": 2}),
        recording("embed", calls, {}),
        recording("chains", calls, {}),
    ]

    # The server frees the dead session's lock at once (0.000 s in the sitting's probe); retry
    # up to 5 s rather than assume it's instant.
    deadline = time.monotonic() + 5
    resumed = run_once(committed, steps, 3)
    while resumed is None and time.monotonic() < deadline:
        time.sleep(0.05)
        resumed = run_once(committed, steps, 3)

    assert (killed.status, killed.attempts) == ("running", 1)
    assert [step.status for step in killed.steps] == ["succeeded", "running", "pending", "pending"]
    assert resumed == job.id
    done = stored(committed, job.id)
    assert (done.status, done.attempts, done.error) == ("succeeded", 2, None)
    assert [name for name, _ in calls] == ["lifecycle", "embed", "chains"]  # not ingest again
    assert done.steps[0].counts == {"run_by": "the killed worker"}
    assert done.steps[1].counts == {"rows": 2}  # rerun from its beginning
    assert done.started_at == killed.started_at  # the first attempt's start is kept
