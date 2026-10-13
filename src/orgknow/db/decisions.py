"""The decision chain's reads and writes (S13-T3; ADR-012 D2): the rows its rules read
(`provenance/rules.py`), and `decisions` and `decision_evidence`.

One fixed, hand-written query per use (ADR-005). The rules themselves are pure Python; the SQL
here only finds their candidates, except two filters pinned in the S13-R1 contract: the source
types rule 7 reads (blog posts and release records) and rule 8's texts (valid at the latest
release, in docs pages, feature gates, release records other than CHANGELOGs, governance docs).
"""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row, dict_row

from orgknow.db.models import (
    ChainDocument,
    DocumentChunk,
    LinkCandidate,
    NearText,
    NewEvidence,
    StoredDecision,
    StoredEvidence,
)


def newest_document(conn: psycopg.Connection[TupleRow], canonical_id: str) -> ChainDocument | None:
    """The document's newest version (latest date window) and its chunks, by ordinal; None when
    no document has this canonical id (aliases aren't searched: a chain names items by id)."""
    with conn.cursor(row_factory=dict_row) as cur:
        version = cur.execute(
            """
            -- One document's date windows never overlap (R8), so the newest is one version.
            SELECT d.id AS document_id, d.canonical_id, d.source_type, v.id AS version_id,
                   v.source_path, v.metadata
            FROM documents d
            JOIN document_versions v ON v.document_id = d.id
            WHERE d.canonical_id = %(canonical_id)s
            ORDER BY v.valid_from_date DESC
            LIMIT 1
            """,
            {"canonical_id": canonical_id},
        ).fetchone()
    if version is None:
        return None
    with conn.cursor(row_factory=class_row(DocumentChunk)) as cur:
        chunks = cur.execute(
            """
            SELECT id, ordinal, heading_path, text, content_hash
            FROM chunks
            WHERE document_version_id = %(version_id)s
            ORDER BY ordinal
            """,
            {"version_id": version["version_id"]},
        ).fetchall()
    return ChainDocument.model_validate({**version, "chunks": chunks})


def linking_candidates(conn: psycopg.Connection[TupleRow], number: int) -> list[LinkCandidate]:
    """Every chunk of every blog post and release record version whose text holds `number` (a
    KEP's), oldest version first: rule 7's candidates. Each of rule 7's link forms (the KEP's
    folder `<N>-…`, `enhancements/issues/<N>`, `KEP-<N>`) holds the number, so none is left out;
    the rule itself checks which chunks link the KEP."""
    with conn.cursor(row_factory=class_row(LinkCandidate)) as cur:
        cur.execute(
            """
            SELECT c.id AS chunk_id, d.canonical_id, d.source_type, c.ordinal, c.heading_path,
                   c.text, v.valid_from_date
            FROM chunks c
            JOIN document_versions v ON v.id = c.document_version_id
            JOIN documents d ON d.id = v.document_id
            WHERE d.source_type IN ('blog_post', 'release_record')
              AND strpos(c.text, %(number)s) > 0
            ORDER BY v.valid_from_date, d.canonical_id, c.ordinal
            """,
            {"number": str(number)},
        )
        return cur.fetchall()


def nearest_current_texts(
    conn: psycopg.Connection[TupleRow],
    content_hash: str,
    model: str,
    latest: int,
    k: int,
    ef_search: int,
) -> list[NearText]:
    """The `k` chunk texts whose `model` vectors are nearest the stored vector of the text
    `content_hash` (a KEP's first Summary chunk), nearest first, ties by content hash, among the
    texts some version holds that is valid at release `latest` in a docs page, a feature gate, a
    release record other than a CHANGELOG, or a governance doc (rule 8). Each cites the chunk in
    the newest such version holding it (lowest ordinal). No stored vector for `content_hash`: an
    empty list.

    The search is `retrieval.search`'s: an HNSW index scan in `ef_search` width, iterative in
    strict order, so the filter can drop rows without returning fewer than `k`.
    """
    with conn.transaction(), conn.cursor(row_factory=class_row(NearText)) as cur:
        # SET LOCAL for this block, as in `retrieval.search`.
        conn.execute(
            "SELECT set_config('hnsw.ef_search', %s, true), "
            "set_config('hnsw.iterative_scan', 'strict_order', true)",
            [str(ef_search)],
        )
        cur.execute(
            """
            -- The query vector is a scalar subquery: the planner runs it once, and the HNSW
            -- index (migration 0004) still orders the scan by distance to it. A missing vector
            -- makes every distance NULL, which the final WHERE drops.
            WITH nearest AS (
                SELECT e.content_hash,
                       e.embedding <=> (SELECT q.embedding FROM embeddings q
                                        WHERE q.content_hash = %(query_hash)s
                                          AND q.model = %(model)s) AS distance
                FROM embeddings e
                WHERE e.model = %(model)s
                  AND EXISTS (
                      SELECT 1
                      FROM chunks c
                      JOIN document_versions v ON v.id = c.document_version_id
                      JOIN documents d ON d.id = v.document_id
                      WHERE c.content_hash = e.content_hash
                        AND d.source_type IN ('docs_page', 'feature_gate_reference',
                                              'release_record', 'governance_doc')
                        AND d.canonical_id NOT LIKE 'changelog:%%'
                        AND v.valid_from_release <= %(latest)s
                        AND (v.valid_until_release IS NULL OR v.valid_until_release >= %(latest)s)
                  )
                ORDER BY distance
                LIMIT %(k)s
            )
            SELECT n.content_hash, n.distance, cited.*
            FROM nearest n
            -- Per text, the chunk to cite: in the newest version that passes the same filter.
            CROSS JOIN LATERAL (
                SELECT c.id AS chunk_id, d.canonical_id, c.heading_path, v.valid_from_date
                FROM chunks c
                JOIN document_versions v ON v.id = c.document_version_id
                JOIN documents d ON d.id = v.document_id
                WHERE c.content_hash = n.content_hash
                  AND d.source_type IN ('docs_page', 'feature_gate_reference',
                                        'release_record', 'governance_doc')
                  AND d.canonical_id NOT LIKE 'changelog:%%'
                  AND v.valid_from_release <= %(latest)s
                  AND (v.valid_until_release IS NULL OR v.valid_until_release >= %(latest)s)
                ORDER BY v.valid_from_date DESC, c.ordinal
                LIMIT 1
            ) cited
            WHERE n.distance IS NOT NULL
            ORDER BY n.distance, n.content_hash
            """,
            {"query_hash": content_hash, "model": model, "latest": latest, "k": k},
        )
        return cur.fetchall()


def replace_decision(
    conn: psycopg.Connection[TupleRow],
    document_id: int,
    title: str,
    evidence: Sequence[NewEvidence],
) -> int:
    """Delete the seed KEP's stored decision (its evidence cascades), then insert it again, built
    now, with `evidence`; return its id. The caller owns the transaction: one per chain."""
    conn.execute("DELETE FROM decisions WHERE document_id = %s", (document_id,))
    row = conn.execute(
        "INSERT INTO decisions (document_id, title, built_at) VALUES (%s, %s, now()) RETURNING id",
        (document_id, title),
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    decision_id = int(row[0])
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO decision_evidence
                (decision_id, step, chunk_id, occurred_at, found_by, via_chunk_id, missing_reason)
            VALUES (%(decision_id)s, %(step)s, %(chunk_id)s, %(occurred_at)s, %(found_by)s,
                    %(via_chunk_id)s, %(missing_reason)s)
            """,
            [{"decision_id": decision_id, **step.model_dump()} for step in evidence],
        )
    return decision_id


def stored_decision(conn: psycopg.Connection[TupleRow], canonical_id: str) -> StoredDecision | None:
    """The stored chain of the seed KEP `canonical_id`, its steps in step order, each with its
    cited chunk's and via chunk's fields; None when no chain is stored for it."""
    with conn.cursor(row_factory=dict_row) as cur:
        decision = cur.execute(
            """
            SELECT x.id, d.canonical_id AS seed, x.title, x.built_at
            FROM decisions x
            JOIN documents d ON d.id = x.document_id
            WHERE d.canonical_id = %(canonical_id)s
            """,
            {"canonical_id": canonical_id},
        ).fetchone()
    if decision is None:
        return None
    with conn.cursor(row_factory=class_row(StoredEvidence)) as cur:
        steps = cur.execute(
            """
            -- LEFT JOINs: a missing step cites no chunk, and a step found by `seed` or
            -- `similarity` has no via.
            SELECT e.step, e.occurred_at, e.found_by, e.missing_reason,
                   e.chunk_id, d.canonical_id, d.source_type, c.heading_path, v.claimed_status,
                   v.snapshot_repo, v.snapshot_sha, v.source_path, v.metadata,
                   e.via_chunk_id, vd.canonical_id AS via_canonical_id,
                   vc.heading_path AS via_heading_path
            FROM decision_evidence e
            LEFT JOIN chunks c ON c.id = e.chunk_id
            LEFT JOIN document_versions v ON v.id = c.document_version_id
            LEFT JOIN documents d ON d.id = v.document_id
            LEFT JOIN chunks vc ON vc.id = e.via_chunk_id
            LEFT JOIN document_versions vv ON vv.id = vc.document_version_id
            LEFT JOIN documents vd ON vd.id = vv.document_id
            WHERE e.decision_id = %(decision_id)s
            ORDER BY array_position(ARRAY['problem', 'discussion', 'proposal', 'decision',
                                          'implementation', 'current_docs'], e.step)
            """,
            {"decision_id": decision["id"]},
        ).fetchall()
    return StoredDecision(
        seed=decision["seed"], title=decision["title"], built_at=decision["built_at"], steps=steps
    )
