"""Retrieval (S07-T3, S08-T2, S09-T4): the chunk texts `ask` and the eval answer from, in
RETRIEVAL_MODE.

- `dense`: the RETRIEVAL_TOP_K texts nearest the question's vector (S04-T5).
- `hybrid`: the RETRIEVAL_CANDIDATES nearest texts and the RETRIEVAL_CANDIDATES best full-text
  matches, fused with RRF (k = RRF_K, equal weights), then the RETRIEVAL_TOP_K best fused texts
  (S07-R1 decisions 1-3).
- `rerank`: hybrid's whole fused pool (no top-K cut: about 21 texts from 20 + 20 candidates),
  scored by the cross-encoder, then the RETRIEVAL_TOP_K best by that score (ADR-008 D3).
- `temporal`: rerank, with the question's route turned into a filter that both searches apply
  before their own top 20 (S09-R1 decisions 2-4): CURRENT keeps current text only; HISTORY with a
  release window keeps texts valid in it, widened by HISTORY_WINDOW_SLACK; every other route has
  no filter. The route comes from the caller (ADR-009: live in `ask`, stored in the eval).

Every dense search uses the HNSW search width HNSW_EF_SEARCH, in every mode.
"""

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.models import Hit, TemporalFilter
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.embedder import Embedder
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import Reranker, rerank
from orgknow.retrieval.router import Route
from orgknow.retrieval.temporal import Window, plan, resolve_window
from orgknow.settings import Settings


def temporal_plan(
    conn: psycopg.Connection[TupleRow], route: Route, settings: Settings
) -> tuple[Window | None, TemporalFilter | None]:
    """The route's release window, before slack, from the `releases` table, and the filter
    temporal mode applies for it (HISTORY_WINDOW_SLACK). `retrieve` uses this; `ask` and the eval
    call it too, to show and record what was searched."""
    window = resolve_window(route.time_scope, list_releases(conn))
    return window, plan(route.mode, window, settings.history_window_slack)


def retrieve(
    question: str,
    embedder: Embedder,
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    reranker: Reranker | None = None,
    route: Route | None = None,
) -> list[Hit]:
    """The `settings.retrieval_top_k` best chunk texts for `question`, best first.

    The question is embedded as a "query" (stored texts were embedded as "document"), and only
    vectors of the embedder's model are searched. Dense mode: each hit has its `distance` and
    `dense_rank`. Hybrid mode: each hit also has its `rrf_score` and `lexical_rank` (a rank is
    None when that list doesn't hold the text, and `distance` is None when only lexical search
    found it). Rerank mode: hybrid's fields, and the `rerank_score` it was ordered by; it needs
    `reranker` (ValueError without one), which isn't called when the pool is empty. Temporal
    mode: rerank's, on the texts `route`'s filter keeps; it needs `route` too (ValueError
    without one, before any call). A filter that keeps no text gives no hits.
    """
    mode = settings.retrieval_mode
    if mode == "temporal" and route is None:
        raise ValueError("temporal mode needs a route: none was given")
    vector = embedder.embed([question], "query").vectors[0]
    width = settings.hnsw_ef_search
    if mode == "dense":
        return search(conn, vector, embedder.model, settings.retrieval_top_k, width)
    temporal = None  # no filter outside temporal mode
    if mode == "temporal" and route is not None:  # checked above: a route is given
        _, temporal = temporal_plan(conn, route, settings)
    candidates = settings.retrieval_candidates
    dense = search(conn, vector, embedder.model, candidates, width, temporal)
    lexical = search_lexical(conn, question, candidates, temporal)
    if mode == "hybrid":
        return fuse(dense, lexical, settings.rrf_k, settings.retrieval_top_k)
    if reranker is None:
        raise ValueError(f"{mode} mode needs a reranker: none was given")
    # The whole pool: the fused list can't hold more texts than the two lists together.
    pool = fuse(dense, lexical, settings.rrf_k, len(dense) + len(lexical))
    if not pool:
        return []
    scores = reranker.score(question, [hit.text for hit in pool])
    return rerank(pool, scores, settings.retrieval_top_k)
