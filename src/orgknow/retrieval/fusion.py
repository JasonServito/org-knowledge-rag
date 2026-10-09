"""Fusion: merge the dense and lexical rankings into one (S07).

Reciprocal Rank Fusion (RRF) combines rankings by position only. Dense search scores by
vector distance and lexical search by `ts_rank_cd`; the two are on different scales, so
their raw scores can't be added. Each list instead gives a text 1 / (k + rank), rank from 1,
and a text's fused score is the sum over the lists that hold it. A text high in both lists
beats a text high in one.

k damps the top ranks' advantage: with k = 60, rank 1 gives 1/61 and rank 2 gives 1/62, so
one list's first place can't outweigh agreement between lists. k = 60 is the value from the
RRF paper (Cormack et al., 2009), not tuned here.

Pure: ranked ids in, a fused ranking out. No database, no network; k is passed in.
"""

from collections.abc import Sequence


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
