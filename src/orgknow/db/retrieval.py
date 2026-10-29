"""Retrieval's reads: the chunk texts nearest a question vector (dense, S04-T5) and the chunk
texts matching a question's words (lexical, S07-T1).

One fixed, hand-written query each (ADR-005). Both rank distinct texts (`embeddings` holds one
vector per text, migration 0003; a text's chunks share one `search_vector`, migration 0005), then
expand each text to the chunks and versions holding it (S04-R2 decision 4), so both return the
same `Hit`s.

Both take an optional `TemporalFilter` (S09-T4, S09-R1 decisions 2-4): a text is kept only if some
version holding it passes. Its conditions are parameters, each a no-op when its value is off, so
the query stays one fixed string with or without a filter.
"""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import Hit, TemporalFilter


def _filter_params(temporal: TemporalFilter | None) -> dict[str, bool | int | None]:
    """The filter's 3 query parameters; no filter turns every condition off."""
    if temporal is None:
        return {"current_only": False, "from_release": None, "until_release": None}
    return {
        "current_only": temporal.current_only,
        "from_release": temporal.from_release,
        "until_release": temporal.until_release,
    }


def search(
    conn: psycopg.Connection[TupleRow],
    question_vector: Sequence[float],
    model: str,
    k: int,
    ef_search: int,
    temporal: TemporalFilter | None = None,
) -> list[Hit]:
    """Return the `k` chunk texts whose `model` vectors are nearest `question_vector` by cosine
    distance, nearest first, ties by content hash, among the texts `temporal` keeps (all of them
    when None). No vectors: an empty list.

    One hit per text: it cites the chunk in the newest version holding the text, lists the
    release window of every version holding it, and is `current` when one of those versions is
    (S09-T3). `dense_rank` is the hit's position, from 1. A kept text is still the whole text:
    its citation and windows ignore the filter.

    `ef_search` is the HNSW search width for this query (HNSW_EF_SEARCH, S07-R1 decision 3). An
    HNSW index scan returns at most that many rows, so it must be at least `k` (settings check).
    The scan is iterative (`hnsw.iterative_scan`, strict order; S09-T4): when the filters drop
    rows, it keeps walking the index for more, nearest first, instead of returning fewer than `k`
    (up to pgvector's `hnsw.max_scan_tuples`, 20,000 by default). Every mode searches this way.
    """
    # This builds a parameter value, not SQL: the query below stays a fixed string.
    vector_text = "[" + ",".join(str(x) for x in question_vector) + "]"
    # set_config(..., true) is SET LOCAL: both settings last until the transaction ends. The
    # block gives them a transaction to live in, so they apply to the query below even on an
    # autocommit connection (where they then end with the block). Inside a caller's transaction
    # the block is a savepoint, and they last until that transaction ends.
    with conn.transaction(), conn.cursor(row_factory=class_row(Hit)) as cur:
        conn.execute(
            "SELECT set_config('hnsw.ef_search', %s, true), "
            "set_config('hnsw.iterative_scan', 'strict_order', true)",
            [str(ef_search)],
        )
        cur.execute(
            """
            -- The k nearest texts. ORDER BY the distance expression alone, so the planner can
            -- walk the HNSW index (migration 0004) instead of sorting every vector. The filters
            -- sit before the LIMIT, so another model's vector, an orphan no chunk holds, or a
            -- text no version passing the temporal filter holds, can't take one of the k places.
            -- The temporal filter (S09-T4): some version holding the text is current, when
            -- current_only; and its release window overlaps [from_release, until_release], an
            -- open end (NULL) on either side open. Each condition is true when its parameter is
            -- off, so with no filter this is "some chunk holds the text".
            WITH nearest AS (
                SELECT e.content_hash, e.embedding <=> %(query)s::vector AS distance
                FROM embeddings e
                WHERE e.model = %(model)s
                  AND EXISTS (
                      SELECT 1
                      FROM chunks c
                      JOIN document_versions v ON v.id = c.document_version_id
                      WHERE c.content_hash = e.content_hash
                        AND (NOT %(current_only)s OR v.valid_until_date IS NULL)
                        AND (%(from_release)s::int IS NULL OR v.valid_until_release IS NULL
                             OR v.valid_until_release >= %(from_release)s::int)
                        AND (%(until_release)s::int IS NULL
                             OR v.valid_from_release <= %(until_release)s::int)
                  )
                ORDER BY e.embedding <=> %(query)s::vector
                LIMIT %(k)s
            )
            -- The rank is the position in the final order below, from 1.
            SELECT n.content_hash, n.distance,
                   row_number() OVER (ORDER BY n.distance, n.content_hash) AS dense_rank,
                   cited.*, windows.release_windows, windows.current
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
            -- merged: a text absent from one release must show that gap. And whether any of
            -- those versions is current, i.e. has an open date window (S09-T3): false when
            -- later edits replaced the text in every version.
            CROSS JOIN LATERAL (
                SELECT array_agg(ARRAY[v.valid_from_release, v.valid_until_release]
                                 ORDER BY v.valid_from_release, v.valid_from_date)
                       AS release_windows,
                       bool_or(v.valid_until_date IS NULL) AS current
                FROM document_versions v
                WHERE v.id IN (
                    SELECT c.document_version_id FROM chunks c
                    WHERE c.content_hash = n.content_hash
                )
            ) windows
            -- The content hash makes equal distances come back in a fixed order.
            ORDER BY n.distance, n.content_hash
            """,
            {"query": vector_text, "model": model, "k": k, **_filter_params(temporal)},
        )
        return cur.fetchall()


def search_lexical(
    conn: psycopg.Connection[TupleRow],
    question: str,
    n: int,
    temporal: TemporalFilter | None = None,
) -> list[Hit]:
    """Return the `n` chunk texts holding every content word of `question`, best full-text rank
    first, ties by content hash, among the texts `temporal` keeps (all of them when None). No
    text holds them all, or the question has no content word (only stop words or punctuation):
    an empty list.

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
            -- one of the n places, not one per chunk. The temporal filter, as in `search`, reads
            -- each matching chunk's version before the LIMIT: a text is kept when one of its
            -- chunks is in a version that passes (every chunk has one version, so with no filter
            -- the join drops nothing).
            WITH matched AS (
                SELECT c.content_hash, max(ts_rank_cd(c.search_vector, q)) AS rank
                FROM chunks c
                JOIN document_versions v ON v.id = c.document_version_id
                CROSS JOIN plainto_tsquery('english', %(question)s) q
                WHERE c.search_vector @@ q
                  AND (NOT %(current_only)s OR v.valid_until_date IS NULL)
                  AND (%(from_release)s::int IS NULL OR v.valid_until_release IS NULL
                       OR v.valid_until_release >= %(from_release)s::int)
                  AND (%(until_release)s::int IS NULL
                       OR v.valid_from_release <= %(until_release)s::int)
                GROUP BY c.content_hash
                ORDER BY rank DESC, c.content_hash
                LIMIT %(n)s
            )
            -- No vector is compared, so no distance. The rank is the position in matched's own
            -- order, from 1.
            SELECT m.content_hash, NULL::double precision AS distance,
                   row_number() OVER (ORDER BY m.rank DESC, m.content_hash) AS lexical_rank,
                   cited.*, windows.release_windows, windows.current
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
            -- ... and one release window per version holding it, oldest first, never merged,
            -- and whether any of those versions is current.
            CROSS JOIN LATERAL (
                SELECT array_agg(ARRAY[v.valid_from_release, v.valid_until_release]
                                 ORDER BY v.valid_from_release, v.valid_from_date)
                       AS release_windows,
                       bool_or(v.valid_until_date IS NULL) AS current
                FROM document_versions v
                WHERE v.id IN (
                    SELECT c.document_version_id FROM chunks c
                    WHERE c.content_hash = m.content_hash
                )
            ) windows
            ORDER BY lexical_rank
            """,
            {"question": question, "n": n, **_filter_params(temporal)},
        )
        return cur.fetchall()
