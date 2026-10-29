"""S14-T4: the corpus-writer lock (ADR-013 D3; S14-R2 call a).

The writers are the design review's list: make ingest, lifecycle, seed, embed and chains here; the
worker's own test is T5's. Each test holds the lock on its own connection, so a writer's `main`,
which opens its own, is the second session. The holder-dies test is the design review's probe: a
subprocess holds the lock and is SIGKILLed.
"""

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import psycopg
import pytest
from psycopg.rows import TupleRow
from pydantic import SecretStr

from orgknow.db.writer_lock import WriterBusy, try_writer_lock, writer_lock
from orgknow.embeddings import embed
from orgknow.ingestion import ingest, lifecycle, seed
from orgknow.provenance import build
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

ROOT = Path(__file__).parents[2]
# Call a's message, typed by hand from the S14-R2 plan.
BUSY = (
    "Another corpus writer is running (make ingest, lifecycle, embed, chains, seed or make "
    "worker); try again when it finishes."
)


@pytest.fixture
def holder(settings: Settings) -> Iterator[Conn]:
    """A connection holding the writer lock; closing it at the end frees the lock."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        assert try_writer_lock(conn)
        yield conn


@pytest.mark.parametrize("module", [ingest, lifecycle, seed, embed, build])
def test_each_cli_writer_exits_1_with_the_message_while_the_lock_is_held(
    holder: Conn,
    settings: Settings,
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The writer reads these settings instead of the environment's: the test database, the
    # committed manifest and lock, a fake Voyage key so embed gets as far as connecting, and an
    # empty corpus cache, so a writer that ran anyway (the lock broken) would read no corpus.
    writer_settings = settings.model_copy(
        update={
            "corpus_manifest_path": ROOT / "config" / "corpus_manifest.yaml",
            "corpus_lock_path": ROOT / "config" / "corpus_manifest.lock.yaml",
            "corpus_cache_dir": tmp_path,
            "voyage_api_key": SecretStr("pa-fake-key"),
        }
    )
    monkeypatch.setattr(module, "Settings", lambda: writer_settings)

    with pytest.raises(SystemExit) as exit_info:
        module.main()

    # sys.exit with a message: the message on stderr, exit status 1.
    assert exit_info.value.code == BUSY


def test_the_context_manager_refuses_a_second_session_and_releases_at_the_end(
    settings: Settings,
) -> None:
    with (
        psycopg.connect(settings.database_url, autocommit=True) as first,
        psycopg.connect(settings.database_url, autocommit=True) as second,
    ):
        # `second`'s block never starts: entering it raises.
        with (
            writer_lock(first),
            pytest.raises(WriterBusy, match="Another corpus writer"),
            writer_lock(second),
        ):
            pass
        assert try_writer_lock(second)  # released when `first`'s block ended


# Holds the lock on its own session, says so, then waits to be killed.
HOLD = """
import sys, time
import psycopg
from orgknow.db.writer_lock import try_writer_lock
conn = psycopg.connect(sys.argv[1], autocommit=True)
print(try_writer_lock(conn), flush=True)
time.sleep(60)
"""


def test_the_lock_is_freed_when_its_holder_is_killed(settings: Settings) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", HOLD, settings.database_url], stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline() == "True\n"
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            while_held = try_writer_lock(conn)
            process.kill()  # SIGKILL: no cleanup runs in the holder
            process.wait()
            # The server frees a dead session's locks as soon as it sees the connection close
            # (0.000 s in the review's probe); poll up to 5 s rather than assume it's instant.
            deadline = time.monotonic() + 5
            after_kill = try_writer_lock(conn)
            while not after_kill and time.monotonic() < deadline:
                time.sleep(0.05)
                after_kill = try_writer_lock(conn)
    finally:
        process.kill()
        process.wait()

    assert (while_held, after_kill) == (False, True)
