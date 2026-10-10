"""Reciprocal Rank Fusion on hand-built rankings (S07-T2), and `fuse` on hand-built hit lists
(S07-T3).

k = 60. Every expected score is worked out by hand and typed as a literal:
1/61 = 0.0163934, 1/62 = 0.0161290, 1/63 = 0.0158730.
"""

import pytest

from orgknow.db.models import Hit
from orgknow.retrieval.fusion import fuse, rrf

K = 60


def test_scores_and_order() -> None:
    # a: rank 1 + rank 2 = 1/61 + 1/62 = 0.0325225
    # c: rank 3 + rank 1 = 1/63 + 1/61 = 0.0322665
    # b: rank 2 only     = 1/62        = 0.0161290
    fused = rrf([["a", "b", "c"], ["c", "a"]], K)
    assert [doc_id for doc_id, _ in fused] == ["a", "c", "b"]
    assert [score for _, score in fused] == pytest.approx([0.032522, 0.032266, 0.016129], abs=1e-6)


def test_ties_break_by_id_ascending() -> None:
    # Both are rank 1 in one list: 1/61 = 0.0163934 each.
    fused = rrf([["y"], ["x"]], K)
    assert [doc_id for doc_id, _ in fused] == ["x", "y"]
    assert [score for _, score in fused] == pytest.approx([0.016393, 0.016393], abs=1e-6)


def test_one_list_empty() -> None:
    fused = rrf([[], ["a"]], K)
    assert [doc_id for doc_id, _ in fused] == ["a"]
    assert [score for _, score in fused] == pytest.approx([0.016393], abs=1e-6)


def test_both_lists_empty() -> None:
    assert rrf([[], []], K) == []


def test_id_twice_in_one_list_raises() -> None:
    with pytest.raises(ValueError, match="id 'a' appears twice"):
        rrf([["a", "a"]], K)


# `fuse` (S07-T3). Content hashes are single letters. A text's dense and lexical hits get
# different chunk ids here (in the database they cite the same chunk), so a test can tell which
# list's fields a fused hit kept.


def _hit(content_hash: str, chunk_id: int, distance: float | None) -> Hit:
    """A hit for `content_hash`; `fuse` reads only the hash and sets the score and ranks."""
    return Hit(
        chunk_id=chunk_id,
        content_hash=content_hash,
        distance=distance,
        text=f"text {content_hash}",
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
    )


def _dense(*hashes: str) -> list[Hit]:
    """Dense hits, nearest first: chunk ids 1, 2, 3 … and distances 0.1, 0.2, 0.3 …"""
    return [_hit(h, rank, rank / 10) for rank, h in enumerate(hashes, start=1)]


def _lexical(*hashes: str) -> list[Hit]:
    """Lexical hits, best first: chunk ids 101, 102 … and no distance (no vector compared)."""
    return [_hit(h, 100 + rank, None) for rank, h in enumerate(hashes, start=1)]


def _fields(hits: list[Hit]) -> list[tuple[str, int, float | None, int | None, int | None]]:
    return [(h.content_hash, h.chunk_id, h.distance, h.dense_rank, h.lexical_rank) for h in hits]


def test_fuse_orders_by_rrf_and_keeps_the_dense_hit_with_both_ranks() -> None:
    # c: dense 3 + lexical 1 = 1/63 + 1/61 = 0.0322665
    # a: dense 1             = 1/61        = 0.0163934
    # b: dense 2             = 1/62        = 0.0161290
    # d: lexical 2           = 1/62        = 0.0161290, tied with b: "b" sorts first
    fused = fuse(_dense("a", "b", "c"), _lexical("c", "d"), K, top_k=10)

    # c is in both lists: one hit, the dense hit's fields (chunk 3, distance 0.3), both ranks.
    # d is lexical only: no distance, no dense rank.
    assert _fields(fused) == [
        ("c", 3, 0.3, 3, 1),
        ("a", 1, 0.1, 1, None),
        ("b", 2, 0.2, 2, None),
        ("d", 102, None, None, 2),
    ]
    assert [h.rrf_score for h in fused] == pytest.approx(
        [0.032266, 0.016393, 0.016129, 0.016129], abs=1e-6
    )


def test_fuse_keeps_the_top_k() -> None:
    fused = fuse(_dense("a", "b", "c"), _lexical("c", "d"), K, top_k=2)

    assert [h.content_hash for h in fused] == ["c", "a"]


def test_fuse_with_no_lexical_hits_is_the_dense_order_with_rrf_scores() -> None:
    # A question of only stop words: lexical search finds nothing.
    fused = fuse(_dense("a", "b", "c"), [], K, top_k=10)

    assert _fields(fused) == [
        ("a", 1, 0.1, 1, None),
        ("b", 2, 0.2, 2, None),
        ("c", 3, 0.3, 3, None),
    ]
    assert [h.rrf_score for h in fused] == pytest.approx([0.016393, 0.016129, 0.015873], abs=1e-6)


def test_fuse_with_no_hits_is_empty() -> None:
    assert fuse([], [], K, top_k=10) == []
