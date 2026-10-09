"""Retrieval's reads: the chunk texts nearest a question vector (dense, S04-T5) and the chunk
texts matching a question's words (lexical, S07-T1).

One fixed, hand-written query each (ADR-005). Both rank distinct texts (`embeddings` holds one
vector per text, migration 0003; a text's chunks share one `search_vector`, migration 0005), then
expand each text to the chunks and versions holding it (S04-R2 decision 4), so both return the
same `Hit`s.
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


def search_lexical(conn: psycopg.Connection[TupleRow], question: str, n: int) -> list[Hit]:
    """Return the `n` chunk texts holding every content word of `question`, best full-text rank
    first, ties by content hash. No text holds them all, or the question has no content word
    (only stop words or punctuation): an empty list.

    One hit per text, expanded as in `search`. `distance` is None (no vector is compared) and
    `lexical_rank` is the hit's position, from 1. Needs no stored vector.
    """
    with conn.cursor(row_factory=class_row(Hit)) as cur:
        cur.execute(
            """
            -- The n best-ranked texts. plainto_tsquery parses the question the way migration
            -- 0005 built the column ('english': stop words dropped, words stemmed), then joins
            -- the words with AND (S07-R1 decision 1), so a text must hold every one. It accepts
            -- any text; a question of only stop words becomes an empty query, matching nothing.
            -- `@@` (matches) can use the GIN index. ts_rank_cd (cover density) ranks a text
            -- higher the closer together the question's words sit in it. Grouped by text: every
            -- chunk of a text has the same search_vector, so the same rank, and a text must take
            -- one of the n places, not one per chunk.
            WITH matched AS (
                SELECT c.content_hash, max(ts_rank_cd(c.search_vector, q)) AS rank
                FROM chunks c, plainto_tsquery('english', %(question)s) q
                WHERE c.search_vector @@ q
                GROUP BY c.content_hash
                ORDER BY rank DESC, c.content_hash
                LIMIT %(n)s
            )
            -- No vector is compared, so no distance. The rank is the position in matched's own
            -- order, from 1.
            SELECT m.content_hash, NULL::double precision AS distance,
                   row_number() OVER (ORDER BY m.rank DESC, m.content_hash) AS lexical_rank,
                   cited.*, windows.release_windows
            FROM matched m
            -- The same two expansions as `search` (see the comments there): the chunk to cite,
            -- in the newest version holding the text ...
            CROSS JOIN LATERAL (
                SELECT c.id AS chunk_id, c.text, c.heading_path, d.canonical_id, d.source_type,
                       v.claimed_status, v.claimed_stage, v.snapshot_repo, v.snapshot_sha,
                       v.source_path, v.metadata
                FROM chunks c
                JOIN document_versions v ON v.id = c.document_version_id
                JOIN documents d ON d.id = v.document_id
                WHERE c.content_hash = m.content_hash
                ORDER BY v.valid_from_date DESC, c.id
                LIMIT 1
            ) cited
            -- ... and one release window per version holding it, oldest first, never merged.
            CROSS JOIN LATERAL (
                SELECT array_agg(ARRAY[v.valid_from_release, v.valid_until_release]
                                 ORDER BY v.valid_from_release, v.valid_from_date)
                       AS release_windows
                FROM document_versions v
                WHERE v.id IN (
                    SELECT c.document_version_id FROM chunks c
                    WHERE c.content_hash = m.content_hash
                )
            ) windows
            ORDER BY lexical_rank
            """,
            {"question": question, "n": n},
        )
        return cur.fetchall()
