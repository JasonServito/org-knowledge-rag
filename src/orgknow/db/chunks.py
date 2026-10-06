"""Writes to `chunks` and `embeddings`, and the read listing versions still to chunk."""

import hashlib
from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import NewChunk, VersionToChunk


def versions_without_chunks(conn: psycopg.Connection[TupleRow]) -> list[VersionToChunk]:
    """Return every version that has no chunks yet, oldest id first, with its document's canonical
    id and source type. A version's chunks are written in one transaction: it has all or none."""
    with conn.cursor(row_factory=class_row(VersionToChunk)) as cur:
        cur.execute(
            """
            SELECT v.id, d.canonical_id, d.source_type, v.source_path, v.snapshot_repo,
                   v.snapshot_sha, v.metadata
            FROM document_versions v
            JOIN documents d ON d.id = v.document_id
            WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_version_id = v.id)
            ORDER BY v.id
            """
        )
        return cur.fetchall()


def add_chunks(
    conn: psycopg.Connection[TupleRow], version_id: int, chunks: Sequence[NewChunk]
) -> list[int]:
    """Insert a version's chunks and return their ids, in the order given.

    Computes each `content_hash` as the SHA-256 of the UTF-8 `text` (R13), so a stored hash
    always matches its text. Postgres can't generate it: `convert_to` isn't immutable.
    """
    ids = []
    for chunk in chunks:
        content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        row = conn.execute(
            """
            INSERT INTO chunks (document_version_id, ordinal, heading_path, text, content_hash)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (version_id, chunk.ordinal, chunk.heading_path, chunk.text, content_hash),
        ).fetchone()
        assert row is not None  # INSERT ... RETURNING always returns the new row
        ids.append(int(row[0]))
    return ids


def add_embedding(
    conn: psycopg.Connection[TupleRow], chunk_id: int, model: str, embedding: Sequence[float]
) -> None:
    """Store a chunk's vector under `model`.

    The vector is sent in pgvector's text form, "[0.1,0.2,...]", and cast to `vector` in SQL,
    so the pgvector Python package isn't needed (ADR-005 D1). The column's `vector(1024)` type
    rejects any other length.
    """
    # This builds a parameter value, not SQL: the query below stays a fixed string.
    vector_text = "[" + ",".join(str(x) for x in embedding) + "]"
    conn.execute(
        "INSERT INTO embeddings (chunk_id, model, embedding) VALUES (%s, %s, %s::vector)",
        (chunk_id, model, vector_text),
    )
