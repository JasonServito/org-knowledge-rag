"""The ingestion report's reads (S05-T8): counts, the chunk id range, and every stored record
for the fingerprint. Read-only; `ingestion/report.py` formats them.

A version is valid at release R when its release window `[from, until]` contains R (inclusive;
a NULL `until` is open), as in `versions_at_release`.
"""

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import Counts, StoredAlias, StoredChunk, StoredDocument, StoredVersion


def counts_by_source_type(conn: psycopg.Connection[TupleRow]) -> list[Counts]:
    """Documents, versions, chunks and distinct chunk texts per source type, by source type, then
    a total row (`source_type` None). An empty database gives only the total row, all zeros."""
    with conn.cursor(row_factory=class_row(Counts)) as cur:
        cur.execute(
            """
            SELECT d.source_type,
                   count(DISTINCT d.id) AS documents,
                   count(DISTINCT v.id) AS versions,
                   count(c.id) AS chunks,
                   count(DISTINCT c.content_hash) AS texts
            FROM documents d
            LEFT JOIN document_versions v ON v.document_id = d.id
            LEFT JOIN chunks c ON c.document_version_id = v.id
            -- One row per source type, plus () for the total: documents.source_type is NOT
            -- NULL, so only the total row has a NULL source type.
            GROUP BY GROUPING SETS ((d.source_type), ())
            ORDER BY d.source_type NULLS LAST
            """
        )
        return cur.fetchall()


def counts_by_release(conn: psycopg.Connection[TupleRow]) -> list[Counts]:
    """For each row of `releases`, oldest first: the counts of the versions valid at that release
    and of their documents, chunks and distinct texts, per source type (only the types with a
    version valid there), then a total row (`source_type` None, all zeros if there's none)."""
    with conn.cursor(row_factory=class_row(Counts)) as cur:
        cur.execute(
            """
            SELECT r.minor AS release,
                   d.source_type,
                   count(DISTINCT d.id) AS documents,
                   count(DISTINCT v.id) AS versions,
                   count(c.id) AS chunks,
                   count(DISTINCT c.content_hash) AS texts
            FROM releases r
            LEFT JOIN document_versions v
                   ON v.valid_from_release <= r.minor
                  AND (v.valid_until_release IS NULL OR r.minor <= v.valid_until_release)
            LEFT JOIN documents d ON d.id = v.document_id
            LEFT JOIN chunks c ON c.document_version_id = v.id
            GROUP BY GROUPING SETS ((r.minor, d.source_type), (r.minor))
            -- A release with no valid version has a (release, NULL) row in both sets: keep only
            -- the total's (grouping() is 1 where source_type was rolled up).
            HAVING grouping(d.source_type) = 1 OR d.source_type IS NOT NULL
            ORDER BY r.minor, d.source_type NULLS LAST
            """
        )
        return cur.fetchall()


def chunk_id_range(conn: psycopg.Connection[TupleRow]) -> tuple[int, int] | None:
    """The lowest and highest chunk id, or None if there are no chunks."""
    row = conn.execute("SELECT min(id), max(id) FROM chunks").fetchone()
    assert row is not None  # an aggregate without GROUP BY always returns one row
    return None if row[0] is None else (int(row[0]), int(row[1]))


def stored_documents(conn: psycopg.Connection[TupleRow]) -> list[StoredDocument]:
    """Every document, by canonical_id."""
    with conn.cursor(row_factory=class_row(StoredDocument)) as cur:
        cur.execute("SELECT canonical_id, source_type FROM documents ORDER BY canonical_id")
        return cur.fetchall()


def stored_aliases(conn: psycopg.Connection[TupleRow]) -> list[StoredAlias]:
    """Every alias, with the canonical_id it points to, by alias."""
    with conn.cursor(row_factory=class_row(StoredAlias)) as cur:
        cur.execute(
            """
            SELECT d.canonical_id, a.alias
            FROM document_aliases a
            JOIN documents d ON d.id = a.document_id
            ORDER BY a.alias
            """
        )
        return cur.fetchall()


def stored_versions(conn: psycopg.Connection[TupleRow]) -> list[StoredVersion]:
    """Every version's columns except its ids, with its document's canonical_id, by document and
    date window."""
    with conn.cursor(row_factory=class_row(StoredVersion)) as cur:
        cur.execute(
            """
            SELECT d.canonical_id, v.content_hash, v.source_path, v.snapshot_repo,
                   v.snapshot_ref, v.snapshot_sha, v.valid_from_release, v.valid_until_release,
                   v.valid_from_date, v.valid_until_date, v.claimed_status, v.claimed_stage,
                   v.metadata
            FROM document_versions v
            JOIN documents d ON d.id = v.document_id
            ORDER BY d.canonical_id, v.valid_from_date
            """
        )
        return cur.fetchall()


def stored_chunks(conn: psycopg.Connection[TupleRow]) -> list[StoredChunk]:
    """Every chunk's columns except its ids and text (its content_hash covers the text, R13),
    named by its document and its version's valid_from_date, by document, version and ordinal."""
    with conn.cursor(row_factory=class_row(StoredChunk)) as cur:
        cur.execute(
            """
            SELECT d.canonical_id, v.valid_from_date, c.ordinal, c.heading_path, c.content_hash
            FROM chunks c
            JOIN document_versions v ON v.id = c.document_version_id
            JOIN documents d ON d.id = v.document_id
            ORDER BY d.canonical_id, v.valid_from_date, c.ordinal
            """
        )
        return cur.fetchall()
