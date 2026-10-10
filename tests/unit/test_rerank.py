"""`rerank` on hand-built hits and fake scores (S08-T2): the hits in, in hybrid's fused order,
with one cross-encoder score per hit; the top K by score out.

Every expected order is worked out by hand from the scores typed below.
"""

import pytest

from orgknow.db.models import Hit
from orgknow.retrieval.rerank import rerank


def _hit(position: int, rrf_score: float = 0.01) -> Hit:
    """The hit at `position` (from 1) of hybrid's fused list: chunk id and hash name it."""
    return Hit(
        chunk_id=position,
        content_hash=f"h{position:02}",
        distance=0.5,
        text=f"text {position}",
        canonical_id="web:/docs/a/",
        source_type="docs_page",
        heading_path=[],
        release_windows=[(30, None)],
        current=True,
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="website",
        snapshot_sha="0" * 40,
        source_path="content/en/docs/a.md",
        metadata={},
        rrf_score=rrf_score,
        dense_rank=position,
        lexical_rank=None,
    )


# One score per position 1..20. Position 15 scores highest (6.40), deep in the pool.
SCORES = [
    0.10, 2.50, -1.00, 1.20, 0.30, -3.00, 4.00, 0.00, 3.10, -0.50,
    1.90, -2.20, 2.80, 0.70, 6.40, -4.10, 3.60, 1.50, -0.90, 0.90,
]  # fmt: skip


def test_the_best_score_is_promoted_from_15th_to_1st_and_the_top_10_follows_the_scores() -> None:
    hits = [_hit(position) for position in range(1, 21)]

    reranked = rerank(hits, SCORES, top_k=10)

    # By hand, the 10 highest scores: 6.40 (15), 4.00 (7), 3.60 (17), 3.10 (9), 2.80 (13),
    # 2.50 (2), 1.90 (11), 1.50 (18), 1.20 (4), 0.90 (20). Next would be 0.70 (14).
    assert [hit.chunk_id for hit in reranked] == [15, 7, 17, 9, 13, 2, 11, 18, 4, 20]
    assert [hit.rerank_score for hit in reranked] == [
        6.40, 4.00, 3.60, 3.10, 2.80, 2.50, 1.90, 1.50, 1.20, 0.90,
    ]  # fmt: skip


def test_scores_equal_at_4_decimals_keep_hybrid_order_and_store_the_raw_score() -> None:
    # 0.50001 and 0.50004 both round to 0.5000: a tie, so hybrid's order (1 before 2) stands,
    # though the raw scores would put 2 first.
    hits = [_hit(1), _hit(2)]

    reranked = rerank(hits, [0.50001, 0.50004], top_k=10)

    assert [(hit.chunk_id, hit.rerank_score) for hit in reranked] == [(1, 0.50001), (2, 0.50004)]


def test_fewer_hits_than_top_k_are_all_returned_reranked() -> None:
    # 0.9 (2), 0.2 (1), -0.4 (3).
    reranked = rerank([_hit(1), _hit(2), _hit(3)], [0.2, 0.9, -0.4], top_k=10)

    assert [hit.chunk_id for hit in reranked] == [2, 1, 3]


def test_no_hits_give_no_hits() -> None:
    assert rerank([], [], top_k=10) == []


def test_a_score_count_unlike_the_hit_count_raises() -> None:
    with pytest.raises(ValueError, match="2 scores for 3 hits"):
        rerank([_hit(1), _hit(2), _hit(3)], [0.1, 0.2], top_k=10)


def test_each_hit_keeps_hybrids_fields_and_gains_its_rerank_score() -> None:
    lexical_only = _hit(2, rrf_score=0.016129).model_copy(
        update={"distance": None, "dense_rank": None, "lexical_rank": 2}
    )
    both = _hit(1, rrf_score=0.032522).model_copy(update={"lexical_rank": 1})

    reranked = rerank([both, lexical_only], [-1.5, 3.25], top_k=10)

    # The text only lexical search found (no distance) is reranked like any other.
    assert [
        (h.chunk_id, h.distance, h.rrf_score, h.dense_rank, h.lexical_rank, h.rerank_score)
        for h in reranked
    ] == [
        (2, None, 0.016129, None, 2, 3.25),
        (1, 0.5, 0.032522, 1, 1, -1.5),
    ]
