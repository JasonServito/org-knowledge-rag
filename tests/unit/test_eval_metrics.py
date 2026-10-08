"""Retrieval metrics on hand-built rankings (S06-T2, ADR-007 D3).

Every expected value is worked out by hand from the ADR's formulas and typed as a literal:
1/log2(2) = 1, 1/log2(3) = 0.63093, 1/log2(6) = 0.38685, so IDCG for 2 labels = 1.63093.
"""

import pytest

from orgknow.db.models import Hit
from orgknow.eval.golden import Label, Question
from orgknow.eval.metrics import RetrievalMetrics, gains, score_retrieval

K = 10
DOC_A = "web:/docs/a/"
DOC_B = "kep:1"
# Label A: a section of DOC_A. Label B: the whole of DOC_B.
LABEL_A = Label(canonical_id=DOC_A, section=["Install"])
LABEL_B = Label(canonical_id=DOC_B, section=None)


def _hit(canonical_id: str, *headings: str) -> Hit:
    """A hit in `canonical_id` under `headings`; the metrics read only those two fields."""
    return Hit(
        chunk_id=1,
        content_hash="a" * 64,
        distance=0.3,
        text="text",
        canonical_id=canonical_id,
        source_type="docs_page",
        heading_path=list(headings),
        release_windows=[(30, None)],
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="website",
        snapshot_sha="0" * 40,
        source_path="content/en/docs/a.md",
        metadata={},
    )


def _question(*labels: Label) -> Question:
    return Question(
        id="q01",
        question="How do I install it?",
        mode="CURRENT" if labels else None,
        answerable=bool(labels),
        expected_answer="Like this.",
        smoke=False,
        labels=list(labels),
    )


# Hits matching neither label: 8 distinct (document, heading path) pairs.
MISSES = [
    _hit("web:/docs/b/", "Overview"),
    _hit("web:/docs/b/", "Usage"),
    _hit("kep:2", "KEP-2: Other", "Summary"),
    _hit("kep:2", "KEP-2: Other", "Motivation"),
    _hit("gate:Foo"),
    _hit("changelog:1.30", "v1.30.0"),
    _hit("blog:/x/"),
    _hit("blog:/x/", "Install"),  # label A's heading, but another document
]

# Seed #8's shape: label A matched at ranks 5 and 8, label B never.
SEED_8 = [
    *MISSES[0:4],
    _hit(DOC_A, "Install", "Linux"),  # rank 5: A (a subsection of it)
    *MISSES[4:6],
    _hit(DOC_A, "Install"),  # rank 8: A again
    *MISSES[6:8],
]


def _values(metrics: RetrievalMetrics | None) -> tuple[float, int, float, float, int]:
    assert metrics is not None
    return (metrics.recall, metrics.hit, metrics.mrr, metrics.ndcg, metrics.distinct_sections)


# --- Marking hits ---------------------------------------------------------------------------


def test_a_label_is_credited_once_at_its_first_matching_hit() -> None:
    assert gains([LABEL_A, LABEL_B], SEED_8) == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0]


def test_whole_headings_are_compared() -> None:
    assert gains([LABEL_A], [_hit(DOC_A, "Installation")]) == [0]
    assert gains([LABEL_A], [_hit(DOC_A, "Install", "Linux")]) == [1]


# --- The metrics ----------------------------------------------------------------------------


def test_seed_8_shaped_ranking() -> None:
    metrics = score_retrieval(_question(LABEL_A, LABEL_B), SEED_8, K)

    # Recall 1 of 2 labels; first match at rank 5; nDCG (1/log2 6) / (1 + 1/log2 3)
    # = 0.38685 / 1.63093; 10 distinct pairs (8 misses + A's 2 heading paths).
    assert _values(metrics) == (0.5, 1, 0.2, pytest.approx(0.23720, abs=1e-5), 10)


def test_no_hits_scores_0() -> None:
    metrics = score_retrieval(_question(LABEL_A, LABEL_B), [], K)

    assert _values(metrics) == (0.0, 0, 0.0, 0.0, 0)


def test_no_relevant_hit_scores_0() -> None:
    metrics = score_retrieval(_question(LABEL_A, LABEL_B), MISSES, K)

    assert _values(metrics) == (0.0, 0, 0.0, 0.0, 8)


def test_installation_does_not_match_install() -> None:
    metrics = score_retrieval(_question(LABEL_A), [_hit(DOC_A, "Installation")], K)

    assert _values(metrics) == (0.0, 0, 0.0, 0.0, 1)


def test_both_labels_at_ranks_1_and_2_score_1() -> None:
    hits = [_hit(DOC_B, "Summary"), _hit(DOC_A, "Install"), *MISSES]

    metrics = score_retrieval(_question(LABEL_A, LABEL_B), hits, K)

    assert _values(metrics) == (1.0, 1, 1.0, pytest.approx(1.0), 10)


def test_one_of_2_labels_at_rank_1() -> None:
    hits = [_hit(DOC_A, "Install"), *MISSES]

    metrics = score_retrieval(_question(LABEL_A, LABEL_B), hits, K)

    # nDCG 1 / 1.63093.
    assert _values(metrics) == (0.5, 1, 1.0, pytest.approx(0.61315, abs=1e-5), 9)


def test_fewer_than_k_hits_still_divide_by_the_ideal_for_every_label() -> None:
    # 1 hit, K = 10: IDCG still covers min(2 labels, 10) = 2 ranks, so nDCG is 1 / 1.63093.
    metrics = score_retrieval(_question(LABEL_A, LABEL_B), [_hit(DOC_A, "Install")], K)

    assert _values(metrics) == (0.5, 1, 1.0, pytest.approx(0.61315, abs=1e-5), 1)


def test_only_the_top_k_hits_count() -> None:
    label_c = Label(canonical_id="gate:Foo", section=[])
    hits = [_hit(DOC_A, "Install"), _hit(DOC_B), _hit("gate:Foo")]

    # K = 2: label C's match at rank 3 is outside the top K. IDCG covers min(3 labels, 2) = 2
    # ranks, so finding A and B at ranks 1 and 2 is ideal: nDCG 1.
    metrics = score_retrieval(_question(LABEL_A, LABEL_B, label_c), hits, 2)

    assert _values(metrics) == (pytest.approx(2 / 3), 1, 1.0, pytest.approx(1.0), 2)


def test_distinct_sections_counts_document_and_heading_path_pairs() -> None:
    hits = [
        _hit(DOC_A, "Install"),
        _hit(DOC_A, "Install"),
        _hit(DOC_A, "Install"),
        _hit(DOC_A, "Install", "Linux"),
        _hit(DOC_A, "Install", "Linux"),
        _hit(DOC_A),
        _hit("web:/docs/b/", "Install"),  # same heading path, another document
        _hit("web:/docs/b/", "Install"),
        _hit("web:/docs/b/"),
        _hit("gate:Foo"),
    ]

    metrics = score_retrieval(_question(LABEL_A), hits, K)

    assert metrics is not None
    assert metrics.distinct_sections == 6


def test_a_question_without_labels_is_not_scored() -> None:
    assert score_retrieval(_question(), SEED_8, K) is None
