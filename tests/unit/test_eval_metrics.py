"""Retrieval metrics on hand-built rankings (S06-T2, ADR-007 D3), and the S09 time metrics on
hand-built hits (S09-T3, S09-R1 decision 1).

Every expected value is worked out by hand from the ADR's formulas and typed as a literal:
1/log2(2) = 1, 1/log2(3) = 0.63093, 1/log2(6) = 0.38685, so IDCG for 2 labels = 1.63093. The
time metrics' counts are counted by hand from the hits each test lists.
"""

import pytest

from orgknow.db.models import Hit
from orgknow.eval.golden import Label, Question
from orgknow.eval.metrics import (
    RetrievalMetrics,
    gains,
    router_count,
    score_retrieval,
    stale_count,
    temporal_count,
)

K = 10
DOC_A = "web:/docs/a/"
DOC_B = "kep:1"
# Label A: a section of DOC_A. Label B: the whole of DOC_B.
LABEL_A = Label(canonical_id=DOC_A, section=["Install"])
LABEL_B = Label(canonical_id=DOC_B, section=None)


def _hit(
    canonical_id: str,
    *headings: str,
    current: bool = True,
    windows: list[tuple[int, int | None]] | None = None,
) -> Hit:
    """A hit in `canonical_id` under `headings`; the retrieval metrics read only those two
    fields, the time metrics only `current` and the release windows (default: one open window
    from 1.30)."""
    return Hit(
        chunk_id=1,
        content_hash="a" * 64,
        distance=0.3,
        text="text",
        canonical_id=canonical_id,
        source_type="docs_page",
        heading_path=list(headings),
        release_windows=[(30, None)] if windows is None else windows,
        current=current,
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


# --- The S09 time metrics (S09-T3) ----------------------------------------------------------

STALE = _hit("web:/docs/a/", current=False, windows=[(20, 27)])  # replaced by a later edit
FRESH = _hit("web:/docs/a/", current=True, windows=[(28, None)])


def test_3_stale_of_10_current_hits_is_3_of_10() -> None:
    # Pooled over 2 CURRENT questions: 2 stale of 6, then 1 stale of 4. The HISTORY and WHY
    # questions' stale hits don't count: the golden mode isn't CURRENT. 3 / 10 = 0.3.
    questions = [
        ("CURRENT", [STALE, FRESH, FRESH, STALE, FRESH, FRESH]),
        ("HISTORY", [STALE, STALE, STALE]),
        ("CURRENT", [FRESH, FRESH, STALE, FRESH]),
        ("WHY", [STALE, STALE]),
    ]

    assert stale_count(questions) == (3, 10)


def test_a_changelog_like_hit_is_not_stale() -> None:
    # A CHANGELOG section: valid only at its own release (1.24), but never edited, so its one
    # version is still current. Stale means replaced, not "not valid at the latest release".
    changelog = _hit("changelog:1.24", "v1.24.0", current=True, windows=[(24, 24)])

    assert stale_count([("CURRENT", [changelog])]) == (0, 1)


def test_a_text_current_in_a_later_version_is_not_stale() -> None:
    # In [20, 22], missing from 1.23, back from 1.25 unchanged: a current version holds it.
    back = _hit("web:/docs/a/", current=True, windows=[(20, 22), (25, None)])

    assert stale_count([("CURRENT", [back])]) == (0, 1)


def test_stale_is_none_when_no_current_question_has_a_hit() -> None:
    assert stale_count([]) is None
    assert stale_count([("HISTORY", [STALE]), (None, [STALE])]) is None
    assert stale_count([("CURRENT", [])]) is None


def test_a_hit_from_21_on_is_not_in_until_20_but_one_in_20_to_22_is() -> None:
    # Golden window "until 1.20": open start, end 20, inclusive.
    from_21 = _hit("web:/docs/a/", windows=[(21, None)])
    in_20_to_22 = _hit("web:/docs/a/", windows=[(20, 22)])
    # One of its 2 versions overlaps: any window counts.
    in_20_to_22_and_23_on = _hit("web:/docs/a/", windows=[(20, 22), (23, None)])

    hits = [from_21, in_20_to_22, in_20_to_22_and_23_on]

    assert temporal_count([((None, 20), hits)]) == (2, 3)


def test_a_closed_window_overlaps_an_open_hit_window_and_both_ends_count() -> None:
    # Golden window 1.28 to 1.28.
    hits = [
        _hit("web:/docs/a/", windows=[(25, 27)]),  # ends before 28: out
        _hit("web:/docs/a/", windows=[(27, 28)]),  # ends at 28: in
        _hit("web:/docs/a/", windows=[(28, 28)]),  # exactly 28: in
        _hit("web:/docs/a/", windows=[(29, None)]),  # starts after 28: out
        _hit("web:/docs/a/", windows=[(24, None)]),  # open, from 24: in
    ]

    assert temporal_count([((28, 28), hits)]) == (3, 5)


def test_a_window_open_at_its_end_keeps_every_later_hit() -> None:
    # Golden window "from 1.30": open end.
    hits = [
        _hit("web:/docs/a/", windows=[(20, 29)]),  # ends at 29: out
        _hit("web:/docs/a/", windows=[(20, 30)]),  # ends at 30: in
        _hit("web:/docs/a/", windows=[(35, None)]),  # in
    ]

    assert temporal_count([((30, None), hits)]) == (2, 3)


def test_temporal_pools_the_questions_with_a_golden_window_only() -> None:
    in_window = _hit("web:/docs/a/", windows=[(20, 22)])
    out_of_window = _hit("web:/docs/a/", windows=[(24, None)])
    questions = [
        ((None, 20), [in_window, out_of_window]),  # 1 of 2
        (None, [in_window, in_window, in_window]),  # no golden window: left out
        ((20, 20), [out_of_window, in_window, out_of_window]),  # 1 of 3
    ]

    assert temporal_count(questions) == (2, 5)


def test_temporal_is_none_when_no_question_with_a_window_has_a_hit() -> None:
    assert temporal_count([]) is None
    assert temporal_count([(None, [FRESH])]) is None
    assert temporal_count([((None, 20), [])]) is None


def test_router_accuracy_counts_routes_matching_the_golden_mode() -> None:
    # (golden, routed) for 5 answerable questions: the 2nd is routed CHANGE instead of HISTORY,
    # so 4 of 5 match (0.8).
    modes = [
        ("CURRENT", "CURRENT"),
        ("HISTORY", "CHANGE"),
        ("CHANGE", "CHANGE"),
        ("WHY", "WHY"),
        ("HISTORY", "HISTORY"),
    ]

    assert router_count(modes) == (4, 5)


def test_router_accuracy_is_none_with_no_routes() -> None:
    assert router_count([]) is None
