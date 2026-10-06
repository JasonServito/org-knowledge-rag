"""Writes to `chunks` and `embeddings`, and the reads listing what is still to chunk or embed."""

import hashlib
from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import NewChunk, TextToEmbed, VersionToChunk


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


def texts_without_embedding(conn: psycopg.Connection[TupleRow], model: str) -> list[TextToEmbed]:
    """Return each distinct chunk text that has no vector for `model`, ordered by hash.

    The `embeddings` table is the embedding cache: a text already embedded under `model` is never
    listed again, so a re-run of `make embed` sends nothing. A hash identifies its text (R13), so
    DISTINCT over (hash, text) gives one row per hash.
    """
    with conn.cursor(row_factory=class_row(TextToEmbed)) as cur:
        cur.execute(
            """
            SELECT DISTINCT c.content_hash, c.text
            FROM chunks c
            WHERE NOT EXISTS (
                SELECT 1 FROM embeddings e
                WHERE e.content_hash = c.content_hash AND e.model = %s
            )
            ORDER BY c.content_hash
            """,
            (model,),
        )
        return cur.fetchall()


def add_embedding(
    conn: psycopg.Connection[TupleRow], content_hash: str, model: str, embedding: Sequence[float]
) -> None:
    """Store the vector of the chunk text with hash `content_hash` under `model`.

    The vector is sent in pgvector's text form, "[0.1,0.2,...]", and cast to `vector` in SQL,
    so the pgvector Python package isn't needed (ADR-005 D1). The column's `vector(1024)` type
    rejects any other length; a second vector for the same (hash, model) is a UniqueViolation.
    """
    # This builds a parameter value, not SQL: the query below stays a fixed string.
    vector_text = "[" + ",".join(str(x) for x in embedding) + "]"
    conn.execute(
        "INSERT INTO embeddings (content_hash, model, embedding) VALUES (%s, %s, %s::vector)",
        (content_hash, model, vector_text),
    )


def delete_orphan_embeddings(conn: psycopg.Connection[TupleRow]) -> int:
    """Delete every vector, of any model, whose hash no chunk has (only after the chunker
    changes), and return how many. Retrieval joins vectors to chunks, so an orphan could never be
    cited; deleting it keeps the table equal to the chunk texts."""
    cur = conn.execute(
        """
        DELETE FROM embeddings e
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.content_hash = e.content_hash)
        """
    )
    return cur.rowcount
