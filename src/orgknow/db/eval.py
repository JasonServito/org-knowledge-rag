"""The golden-set label check's reads (S06-T1): which document a label names, and a document's
distinct chunk texts with their heading paths. Read-only.

The label rule itself (ADR-007 D2) is applied in Python (`eval/golden.py`), so the label check
and the metrics use one matching rule, not one in SQL and another in Python.
"""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import SectionText


def canonical_ids(conn: psycopg.Connection[TupleRow], names: Sequence[str]) -> dict[str, str]:
    """Map each of `names` that is a canonical_id or an alias to its document's canonical_id. A
    name that is neither is left out."""
    # R3 means a name is at most one of the two, so each name gets at most one row.
    rows = conn.execute(
        """
        SELECT canonical_id AS name, canonical_id
        FROM documents
        WHERE canonical_id = ANY(%(names)s)
        UNION ALL
        SELECT a.alias, d.canonical_id
        FROM document_aliases a
        JOIN documents d ON d.id = a.document_id
        WHERE a.alias = ANY(%(names)s)
        """,
        {"names": list(names)},
    ).fetchall()
    return {str(name): str(canonical_id) for name, canonical_id in rows}


def document_texts(conn: psycopg.Connection[TupleRow], canonical_id: str) -> list[SectionText]:
    """Every distinct (heading path, chunk text) of the document, in any of its versions, in order
    of first appearance: by version date, then chunk ordinal. A text is named by its content
    hash. No such document: an empty list."""
    with conn.cursor(row_factory=class_row(SectionText)) as cur:
        cur.execute(
            """
            SELECT heading_path, content_hash
            FROM (
                -- Each chunk's place in the document's history. The order is total: one
                -- document's versions have distinct dates (R8), and one version's chunks
                -- distinct ordinals.
                SELECT c.heading_path, c.content_hash,
                       row_number() OVER (ORDER BY v.valid_from_date, c.ordinal) AS place
                FROM chunks c
                JOIN document_versions v ON v.id = c.document_version_id
                JOIN documents d ON d.id = v.document_id
                WHERE d.canonical_id = %(canonical_id)s
            ) placed
            GROUP BY heading_path, content_hash
            ORDER BY min(place)
            """,
            {"canonical_id": canonical_id},
        )
        return cur.fetchall()
