"""Reciprocal Rank Fusion on hand-built rankings (S07-T2).

k = 60. Every expected score is worked out by hand and typed as a literal:
1/61 = 0.0163934, 1/62 = 0.0161290, 1/63 = 0.0158730.
"""

import pytest

from orgknow.retrieval.fusion import rrf

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
