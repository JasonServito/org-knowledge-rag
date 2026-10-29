"""S14-T4 (S14-R2 call j): `make ingest-report`'s reads and `stored_decision`'s 2 reads each run
in one read-only REPEATABLE READ transaction, so each sees one snapshot of the database.

A spy wraps the reads: before and after them it records the transaction's isolation level, its
read-only flag and its start time (`now()`, the same for every statement of one transaction).
"""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db import decisions
from orgknow.db.decisions import replace_decision, stored_decision
from orgknow.db.documents import create_document
from orgknow.ingestion import report
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

SEED = "kep:9301"  # made up; no test stores it


def _transaction(conn: Conn) -> tuple[str, str, datetime]:
    """The current transaction's isolation level, read-only flag and start time."""
    isolation = conn.execute("SHOW transaction_isolation").fetchone()
    read_only = conn.execute("SHOW transaction_read_only").fetchone()
    started = conn.execute("SELECT now()").fetchone()
    assert isolation is not None and read_only is not None and started is not None
    return isolation[0], read_only[0], started[0]


def _spy(read: Callable[..., Any], seen: list[tuple[str, str, datetime]]) -> Callable[..., Any]:
    """`read`, recording the transaction before and after it runs."""

    def spied(conn: Conn, *args: Any) -> Any:
        seen.append(_transaction(conn))
        result = read(conn, *args)
        seen.append(_transaction(conn))
        return result

    return spied


def test_make_ingest_report_reads_in_one_read_only_repeatable_read_transaction(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, str, datetime]] = []
    # The report's first read (the aliases) and its last (the chunk id range).
    monkeypatch.setattr(report, "stored_aliases", _spy(report.stored_aliases, seen))
    monkeypatch.setattr(report, "chunk_id_range", _spy(report.chunk_id_range, seen))
    monkeypatch.setattr(report, "Settings", lambda: settings)

    report.main()

    assert len(seen) == 4
    assert {(isolation, read_only) for isolation, read_only, _ in seen} == {
        ("repeatable read", "on")
    }
    assert len({started for _, _, started in seen}) == 1  # one transaction
    assert capsys.readouterr().out.splitlines()[-1].startswith("Fingerprint: sha256:")


@pytest.fixture
def committed_decision(settings: Settings) -> Iterator[str]:
    """A seed KEP and its decision (no steps), committed so that a new connection, like the
    API's, sees them; deleted at the end (the decision cascades)."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        document_id = create_document(conn, SEED, "kep")
        try:
            replace_decision(conn, document_id, "Made up", [])
            yield SEED
        finally:
            conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_stored_decision_reads_in_one_read_only_repeatable_read_transaction(
    settings: Settings, committed_decision: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str, datetime]] = []
    monkeypatch.setattr(decisions, "_read_decision", _spy(decisions._read_decision, seen))

    # Autocommit, as the API's connection: no transaction is open when the reads start.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        stored = stored_decision(conn, committed_decision)

    assert stored is not None
    assert (stored.seed, stored.title, stored.steps) == (SEED, "Made up", [])
    assert len(seen) == 2
    assert {(isolation, read_only) for isolation, read_only, _ in seen} == {
        ("repeatable read", "on")
    }
    assert len({started for _, _, started in seen}) == 1  # one transaction
