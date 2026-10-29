"""Fusion: merge the dense and lexical rankings into one (S07).

Reciprocal Rank Fusion (RRF) combines rankings by position only. Dense search scores by
vector distance and lexical search by `ts_rank_cd`; the two are on different scales, so
their raw scores can't be added. Each list instead gives a text 1 / (k + rank), rank from 1,
and a text's fused score is the sum over the lists that hold it. A text high in both lists
beats a text high in one.

k damps the top ranks' advantage: with k = 60, rank 1 gives 1/61 and rank 2 gives 1/62, so
one list's first place can't outweigh agreement between lists. k = 60 is the value from the
RRF paper (Cormack et al., 2009), not tuned here.

`rrf` fuses ranked ids; `fuse` applies it to the two lists of `Hit`s that hybrid retrieval
gets (S07-T3). Both are pure: no database, no network; k is passed in.
"""

from collections.abc import Sequence

from orgknow.db.models import Hit


def rrf(rankings: Sequence[Sequence[str]], k: int) -> list[tuple[str, float]]:
    """Fuse ranked lists of ids, each best first, into one list of (id, score).

    An id's score is the sum of 1 / (k + rank) over the lists holding it, rank from 1. Sorted
    by score descending, then id ascending, so ties come out in a fixed order. An id twice in
    one list raises ValueError: a rank must be one position.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, start=1):
            if doc_id in seen:
                raise ValueError(f"id {doc_id!r} appears twice in one ranking")
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def fuse(dense: Sequence[Hit], lexical: Sequence[Hit], k: int, top_k: int) -> list[Hit]:
    """Fuse the dense and lexical hits, each list best first, with `rrf` over their content
    hashes; return the `top_k` best fused hits (all of them if fewer).

    Each text is one hit. A text in both lists keeps the dense hit's fields: both searches cite
    the same chunk for a text, and only the dense hit has a distance. Every fused hit gets its
    `rrf_score`, and its position in each list, from 1, as `dense_rank` and `lexical_rank` (None
    for a list that doesn't hold it): the ranks `rrf` scored.
    """
    dense_ranks = {hit.content_hash: rank for rank, hit in enumerate(dense, start=1)}
    lexical_ranks = {hit.content_hash: rank for rank, hit in enumerate(lexical, start=1)}
    # Dense first, so setdefault keeps the dense hit of a text in both lists.
    hits: dict[str, Hit] = {}
    for hit in [*dense, *lexical]:
        hits.setdefault(hit.content_hash, hit)

    # The lists themselves, not the rank dicts' keys: rrf refuses a text twice in one list.
    fused = rrf([[hit.content_hash for hit in dense], [hit.content_hash for hit in lexical]], k)
    return [
        hits[content_hash].model_copy(
            update={
                "rrf_score": score,
                "dense_rank": dense_ranks.get(content_hash),
                "lexical_rank": lexical_ranks.get(content_hash),
            }
        )
        for content_hash, score in fused[:top_k]
    ]
