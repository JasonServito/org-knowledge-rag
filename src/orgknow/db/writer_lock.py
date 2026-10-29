"""The corpus-writer lock (S14-T4; ADR-013 D3; S14-R2 call a).

Every corpus writer (make ingest, lifecycle, embed, chains, seed, and the worker) takes one
Postgres advisory lock, with one fixed key, before it reads or writes, and holds it to the end.
So at most one writes at a time: R3's check-then-insert can't race, and no 2 writers embed (and
pay for) the same texts at once. A writer killed between a Voyage request and its commit re-sends
that one batch when re-run or resumed.

A session lock (`pg_try_advisory_lock`), never a transaction lock: it is held across the
writer's many small transactions, until released or until its connection ends, however the
process dies (0.000 s after a SIGKILL in the design review's probe). It lives on the writer's only
connection, so a writer whose connection drops stops writing too. `make reset-corpus` (raw
`psql`) is outside it.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import TupleRow

# The lock's one fixed key: any bigint does, since nothing else here takes an advisory lock.
WRITER_LOCK_KEY = 1414
# What a CLI writer prints when it exits 1 because another writer holds the lock (call a).
BUSY_MESSAGE = (
    "Another corpus writer is running (make ingest, lifecycle, embed, chains, seed or make "
    "worker); try again when it finishes."
)


class WriterBusy(Exception):
    """Another session holds the corpus-writer lock."""


def try_writer_lock(conn: psycopg.Connection[TupleRow]) -> bool:
    """Take the lock for `conn`'s session and return True; return False at once, without
    waiting, when another session holds it."""
    row = conn.execute("SELECT pg_try_advisory_lock(%s)", (WRITER_LOCK_KEY,)).fetchone()
    assert row is not None  # a SELECT of one value always returns one row
    return bool(row[0])


def release_writer_lock(conn: psycopg.Connection[TupleRow]) -> None:
    """Release the lock `conn`'s session holds."""
    conn.execute("SELECT pg_advisory_unlock(%s)", (WRITER_LOCK_KEY,))


@contextmanager
def writer_lock(conn: psycopg.Connection[TupleRow]) -> Iterator[None]:
    """Hold the lock on `conn` for the block; raise WriterBusy, before the block starts, when
    another session holds it.

    Released when the block ends normally. After an error it is left to the connection's end:
    the connection may be unusable then (an aborted transaction, a lost server), and a failed
    release would hide the error. The CLI writers close their connection right after the block.
    """
    if not try_writer_lock(conn):
        raise WriterBusy(BUSY_MESSAGE)
    yield
    release_writer_lock(conn)
