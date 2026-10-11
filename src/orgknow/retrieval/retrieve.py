"""Retrieval (S07-T3, S08-T2, S09-T4, S09-T7): the chunk texts `ask` and the eval answer from, in
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
- `authority`: temporal's pool, reranked whole (no top-K cut), each hit's authority attached,
  then sorted by the reranker's probability times the hit's factor for the route's mode
  (AUTHORITY_BOOST, AUTHORITY_DEMOTE or 1), and cut to the RETRIEVAL_TOP_K best (S09-R2
  decisions 3 and 9). It needs a route too.

Every dense search uses the HNSW search width HNSW_EF_SEARCH, in every mode. In every mode, each
returned hit carries its authority at the question's target release (S09-T6): the route's in
temporal and authority modes, the latest release in the others.
"""

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.lifecycle import observations
from orgknow.db.models import Hit, TemporalFilter
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.embedder import Embedder
from orgknow.retrieval.authority import authority, kep_gates, target_release, weigh
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
    without one, before any call). A filter that keeps no text gives no hits. Authority mode:
    temporal's fields and needs, ordered by `weigh`, each hit with its `authority_score`.

    Every mode: each hit's `authority` (`attach_authority`) at the target release, which only
    temporal and authority modes take from the route (`target_release`); the other modes ignore
    a route.
    """
    mode = settings.retrieval_mode
    if mode in ("temporal", "authority") and route is None:
        raise ValueError(f"{mode} mode needs a route: none was given")
    routed = route if mode in ("temporal", "authority") else None
    window, temporal = (None, None) if routed is None else temporal_plan(conn, routed, settings)
    hits = _search(question, embedder, conn, settings, reranker, temporal)
    if not hits:
        return []
    latest = list_releases(conn)[-1].minor  # oldest first; a stored version implies a release
    target = target_release(None if routed is None else routed.mode, window, latest)
    hits = attach_authority(conn, hits, target)
    if mode != "authority":
        return hits
    assert routed is not None  # checked above: authority mode has a route
    boost, demote = settings.authority_boost, settings.authority_demote
    return weigh(hits, routed.mode, latest, boost, demote)[: settings.retrieval_top_k]


def attach_authority(conn: psycopg.Connection[TupleRow], hits: list[Hit], target: int) -> list[Hit]:
    """`hits`, in order, each with its authority at `target` (S09-T6): one read of the
    observations, up to `target`, of every feature gate the KEP hits name. It works on any list,
    a whole pool before a cut included."""
    gates = {gate for hit in hits if hit.source_type == "kep" for gate in kep_gates(hit.metadata)}
    rows = observations(conn, sorted(gates), target)
    return [hit.model_copy(update={"authority": authority(hit, rows, target)}) for hit in hits]


def _search(
    question: str,
    embedder: Embedder,
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    reranker: Reranker | None,
    temporal: TemporalFilter | None,
) -> list[Hit]:
    """The mode's hits, best first, among the texts `temporal` keeps (every text when None; dense
    mode never gets one). See `retrieve`. Authority mode: the whole reranked pool, which
    `retrieve` weighs before its top-K cut."""
    mode = settings.retrieval_mode
    vector = embedder.embed([question], "query").vectors[0]
    width = settings.hnsw_ef_search
    if mode == "dense":
        return search(conn, vector, embedder.model, settings.retrieval_top_k, width)
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
    keep = len(pool) if mode == "authority" else settings.retrieval_top_k
    return rerank(pool, scores, keep)
