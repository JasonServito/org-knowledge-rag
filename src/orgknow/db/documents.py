"""Writes and lookups for `documents` and `document_aliases`.

R3 (an id or alias resolves to exactly one document) spans both tables, which no constraint can
express, so both write functions check the other table first (ADR-005 D2).
"""

import psycopg
from psycopg.rows import TupleRow


def create_document(conn: psycopg.Connection[TupleRow], canonical_id: str, source_type: str) -> int:
    """Insert a document and return its id. Raises ValueError if `canonical_id` is an alias."""
    alias_row = conn.execute(
        "SELECT 1 FROM document_aliases WHERE alias = %s", (canonical_id,)
    ).fetchone()
    if alias_row is not None:
        raise ValueError(f"{canonical_id!r} is already an alias of another document")

    row = conn.execute(
        "INSERT INTO documents (canonical_id, source_type) VALUES (%s, %s) RETURNING id",
        (canonical_id, source_type),
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    return int(row[0])


def add_alias(conn: psycopg.Connection[TupleRow], document_id: int, alias: str) -> None:
    """Point `alias` (an old URL or gate name) at a document. Raises ValueError if `alias` is
    already some document's canonical_id."""
    document_row = conn.execute(
        "SELECT 1 FROM documents WHERE canonical_id = %s", (alias,)
    ).fetchone()
    if document_row is not None:
        raise ValueError(f"{alias!r} is already a canonical_id")

    conn.execute(
        "INSERT INTO document_aliases (alias, document_id) VALUES (%s, %s)", (alias, document_id)
    )


def resolve_document(conn: psycopg.Connection[TupleRow], id_or_alias: str) -> int | None:
    """Return the id of the document with this canonical_id or alias, or None."""
    # R3 means at most one of the two branches matches.
    row = conn.execute(
        """
        SELECT id FROM documents WHERE canonical_id = %(key)s
        UNION ALL
        SELECT document_id FROM document_aliases WHERE alias = %(key)s
        """,
        {"key": id_or_alias},
    ).fetchone()
    return None if row is None else int(row[0])
