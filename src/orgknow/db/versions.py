"""Writes and reads for `document_versions`.

Release windows are inclusive `[from, until]`; date windows are half-open `[from, until)`; a
NULL `until` is open (docs/domain-model.md). The two read functions are the only place that
applies these conventions.
"""

from datetime import datetime

import psycopg
from psycopg.rows import TupleRow, class_row
from psycopg.types.json import Jsonb

from orgknow.db.models import NewVersion, Version


def insert_version(conn: psycopg.Connection[TupleRow], version: NewVersion) -> int:
    """Insert one version and return its id.

    To supersede the current version, close it first (`close_version`) in the same
    transaction. Inserting first would give the document two open date windows, which R8
    rejects.
    """
    row = conn.execute(
        """
        INSERT INTO document_versions (
            document_id, content_hash, source_path, snapshot_repo, snapshot_ref, snapshot_sha,
            valid_from_release, valid_until_release, valid_from_date, valid_until_date,
            claimed_status, claimed_stage, metadata
        )
        VALUES (
            %(document_id)s, %(content_hash)s, %(source_path)s, %(snapshot_repo)s,
            %(snapshot_ref)s, %(snapshot_sha)s, %(valid_from_release)s, %(valid_until_release)s,
            %(valid_from_date)s, %(valid_until_date)s, %(claimed_status)s, %(claimed_stage)s,
            %(metadata)s
        )
        RETURNING id
        """,
        # psycopg sends a dict as jsonb only when it's wrapped in Jsonb.
        version.model_dump() | {"metadata": Jsonb(version.metadata)},
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    return int(row[0])


def close_version(
    conn: psycopg.Connection[TupleRow],
    version_id: int,
    valid_until_release: int,
    valid_until_date: datetime,
) -> None:
    """Set the `until` bounds of a version whose date window is still open (R10).

    A window is closed once. Raises ValueError if the version doesn't exist or is already
    closed, so nothing can move or reopen a window that was closed before.
    """
    # A naive datetime would be read in the database session's time zone.
    if valid_until_date.tzinfo is None:
        raise ValueError("valid_until_date must be timezone-aware")
    row = conn.execute(
        """
        UPDATE document_versions
        SET valid_until_release = %(valid_until_release)s,
            valid_until_date = %(valid_until_date)s
        WHERE id = %(version_id)s AND valid_until_date IS NULL
        RETURNING id
        """,
        {
            "version_id": version_id,
            "valid_until_release": valid_until_release,
            "valid_until_date": valid_until_date,
        },
    ).fetchone()
    if row is None:
        raise ValueError(f"version {version_id} is not open: it doesn't exist or is already closed")


def versions_at_release(
    conn: psycopg.Connection[TupleRow], document_id: int, release: int
) -> list[Version]:
    """Return the versions whose release window contains `release` (24 for v1.24), oldest first.

    Several can match for a date-scoped source: two blog edits in one release cycle both speak
    for that release.
    """
    with conn.cursor(row_factory=class_row(Version)) as cur:
        cur.execute(
            """
            SELECT id, document_id, content_hash, source_path, snapshot_repo, snapshot_ref,
                   snapshot_sha, valid_from_release, valid_until_release, valid_from_date,
                   valid_until_date, claimed_status, claimed_stage, metadata
            FROM document_versions
            WHERE document_id = %(document_id)s
              AND valid_from_release <= %(release)s
              AND (valid_until_release IS NULL OR %(release)s <= valid_until_release)
            ORDER BY valid_from_date
            """,
            {"document_id": document_id, "release": release},
        )
        return cur.fetchall()


def version_at_time(
    conn: psycopg.Connection[TupleRow], document_id: int, at: datetime
) -> Version | None:
    """Return the version whose date window contains `at`, or None if there was no text then.

    `until` is exclusive: at that instant the next version is the live one. R8 guarantees at
    most one match.
    """
    # A naive datetime would be read in the database session's time zone.
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    with conn.cursor(row_factory=class_row(Version)) as cur:
        cur.execute(
            """
            SELECT id, document_id, content_hash, source_path, snapshot_repo, snapshot_ref,
                   snapshot_sha, valid_from_release, valid_until_release, valid_from_date,
                   valid_until_date, claimed_status, claimed_stage, metadata
            FROM document_versions
            WHERE document_id = %(document_id)s
              AND valid_from_date <= %(at)s
              AND (valid_until_date IS NULL OR %(at)s < valid_until_date)
            """,
            {"document_id": document_id, "at": at},
        )
        return cur.fetchone()
