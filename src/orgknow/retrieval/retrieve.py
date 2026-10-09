"""Retrieval (S07-T3, S08-T2): the chunk texts `ask` and the eval answer from, in RETRIEVAL_MODE.

- `dense`: the RETRIEVAL_TOP_K texts nearest the question's vector (S04-T5).
- `hybrid`: the RETRIEVAL_CANDIDATES nearest texts and the RETRIEVAL_CANDIDATES best full-text
  matches, fused with RRF (k = RRF_K, equal weights), then the RETRIEVAL_TOP_K best fused texts
  (S07-R1 decisions 1-3).
- `rerank`: hybrid's whole fused pool (no top-K cut: about 21 texts from 20 + 20 candidates),
  scored by the cross-encoder, then the RETRIEVAL_TOP_K best by that score (ADR-008 D3).

Every dense search uses the HNSW search width HNSW_EF_SEARCH, in every mode.
"""

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.models import Hit
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.embedder import Embedder
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import Reranker, rerank
from orgknow.settings import Settings


def retrieve(
    question: str,
    embedder: Embedder,
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    reranker: Reranker | None = None,
) -> list[Hit]:
    """The `settings.retrieval_top_k` best chunk texts for `question`, best first.

    The question is embedded as a "query" (stored texts were embedded as "document"), and only
    vectors of the embedder's model are searched. Dense mode: each hit has its `distance` and
    `dense_rank`. Hybrid mode: each hit also has its `rrf_score` and `lexical_rank` (a rank is
    None when that list doesn't hold the text, and `distance` is None when only lexical search
    found it). Rerank mode: hybrid's fields, and the `rerank_score` it was ordered by; it needs
    `reranker` (ValueError without one), which isn't called when the pool is empty.
    """
    vector = embedder.embed([question], "query").vectors[0]
    width = settings.hnsw_ef_search
    if settings.retrieval_mode == "dense":
        return search(conn, vector, embedder.model, settings.retrieval_top_k, width)
    candidates = settings.retrieval_candidates
    dense = search(conn, vector, embedder.model, candidates, width)
    lexical = search_lexical(conn, question, candidates)
    if settings.retrieval_mode == "hybrid":
        return fuse(dense, lexical, settings.rrf_k, settings.retrieval_top_k)
    if reranker is None:
        raise ValueError("rerank mode needs a reranker: none was given")
    # The whole pool: the fused list can't hold more texts than the two lists together.
    pool = fuse(dense, lexical, settings.rrf_k, len(dense) + len(lexical))
    if not pool:
        return []
    scores = reranker.score(question, [hit.text for hit in pool])
    return rerank(pool, scores, settings.retrieval_top_k)
