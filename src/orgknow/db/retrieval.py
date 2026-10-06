"""Dense retrieval's read: the chunk texts nearest a question vector (S04-T5).

One fixed, hand-written query (ADR-005). It searches distinct texts, because `embeddings` holds
one vector per text (migration 0003), then expands each text to the chunks and versions holding
it (S04-R2 decision 4).
"""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import Hit


def search(
    conn: psycopg.Connection[TupleRow], question_vector: Sequence[float], model: str, k: int
) -> list[Hit]:
    """Return the `k` chunk texts whose `model` vectors are nearest `question_vector` by cosine
    distance, nearest first, ties by content hash. No vectors: an empty list.

    One hit per text: it cites the chunk in the newest version holding the text and lists the
    release window of every version holding it. `k` is at most 40 (RETRIEVAL_TOP_K, settings).
    """
    # This builds a parameter value, not SQL: the query below stays a fixed string.
    vector_text = "[" + ",".join(str(x) for x in question_vector) + "]"
    with conn.cursor(row_factory=class_row(Hit)) as cur:
        cur.execute(
            """
            -- The k nearest texts. ORDER BY the distance expression alone, so the planner can
            -- walk the HNSW index (migration 0004) instead of sorting every vector. The filters
            -- sit before the LIMIT, so another model's vector, or an orphan no chunk holds,
            -- can't take one of the k places.
            WITH nearest AS (
                SELECT e.content_hash, e.embedding <=> %(query)s::vector AS distance
                FROM embeddings e
                WHERE e.model = %(model)s
                  AND EXISTS (SELECT 1 FROM chunks c WHERE c.content_hash = e.content_hash)
                ORDER BY e.embedding <=> %(query)s::vector
                LIMIT %(k)s
            )
            SELECT n.content_hash, n.distance, cited.*, windows.release_windows
            FROM nearest n
            -- Per text, the chunk to cite: the one in the newest version (latest date window)
            -- holding the text, and the lowest id if that version holds it twice. The order is
            -- total: a text names its document in its header, and one document's date windows
            -- never overlap (R8).
            CROSS JOIN LATERAL (
                SELECT c.id AS chunk_id, c.text, c.heading_path, d.canonical_id, d.source_type,
                       v.claimed_status, v.claimed_stage, v.snapshot_repo, v.snapshot_sha,
                       v.source_path, v.metadata
                FROM chunks c
                JOIN document_versions v ON v.id = c.document_version_id
                JOIN documents d ON d.id = v.document_id
                WHERE c.content_hash = n.content_hash
                ORDER BY v.valid_from_date DESC, c.id
                LIMIT 1
            ) cited
            -- Per text, one (from, until) release window per version holding it (IN lists a
            -- version once, however many of its chunks hold the text), oldest first. Never
            -- merged: a text absent from one release must show that gap.
            CROSS JOIN LATERAL (
                SELECT array_agg(ARRAY[v.valid_from_release, v.valid_until_release]
                                 ORDER BY v.valid_from_release, v.valid_from_date)
                       AS release_windows
                FROM document_versions v
                WHERE v.id IN (
                    SELECT c.document_version_id FROM chunks c
                    WHERE c.content_hash = n.content_hash
                )
            ) windows
            -- The content hash makes equal distances come back in a fixed order.
            ORDER BY n.distance, n.content_hash
            """,
            {"query": vector_text, "model": model, "k": k},
        )
        return cur.fetchall()
