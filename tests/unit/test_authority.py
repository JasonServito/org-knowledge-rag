"""S09-T6: each hit's authority tier at the question's target release, and a KEP's effective stage
(ADR-003 D2-D3 as changed in the S09-R2 design review; the S09-R2 plan's T6 rules). S09-T7: the
authority weights per routed mode (ADR-003 D4 as changed there; the plan's T7 rules).

Every expected value is typed by hand from those rules; none is computed by the code under test.
No database, no network: the observations are hand-built rows. 1.37 is the latest release.
"""

from typing import Any

import pytest

from orgknow.db.models import Authority, Confidence, Hit, Observation
from orgknow.retrieval.authority import (
    authority,
    factor,
    kep_gates,
    kep_stage,
    target_release,
    tier,
    weigh,
)
from orgknow.retrieval.router import Mode
from orgknow.retrieval.temporal import Window

LATEST = 37


def _row(
    gate: str, release: int, stage: str | None, confidence: Confidence = "high"
) -> Observation:
    return Observation(gate=gate, release=release, stage=stage, status_confidence=confidence)


# --- The target release ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "window", "expected"),
    [
        # CURRENT: the latest release, even with a window.
        ("CURRENT", Window(until_release=27), 37),
        # HISTORY: the window's until, capped at the latest; no until → the latest.
        ("HISTORY", Window(until_release=27), 27),
        ("HISTORY", Window(from_release=30), 37),
        ("HISTORY", Window(until_release=40), 37),
        ("HISTORY", None, 37),
        # CHANGE and WHY: the latest, whatever the window.
        ("CHANGE", Window(from_release=22, until_release=25), 37),
        ("WHY", None, 37),
        # No route (dense, hybrid and rerank modes): the latest.
        (None, None, 37),
    ],
    ids=[
        "current",
        "history-until-27",
        "history-from-30",
        "history-until-40",
        "history-no-window",
        "change",
        "why",
        "no-route",
    ],
)
def test_the_target_release(mode: Mode | None, window: Window | None, expected: int) -> None:
    assert target_release(mode, window, LATEST) == expected


# --- A KEP's feature gates ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        # KEP-2579's list, as stored: the names, as written.
        (
            {"feature-gates": [{"name": "PodSecurity", "components": ["kube-apiserver"]}]},
            ["PodSecurity"],
        ),
        ({"feature-gates": [{"name": "A"}, {"name": "B"}]}, ["A", "B"]),
        # An empty list (5 current KEPs), a null value, and no key: no gate.
        ({"feature-gates": []}, []),
        ({"feature-gates": None}, []),
        ({"title": "No gates"}, []),
    ],
    ids=["one", "two", "empty", "null", "missing"],
)
def test_a_keps_gates_are_the_names_in_its_feature_gates_list(
    metadata: dict[str, Any], expected: list[str]
) -> None:
    assert kep_gates(metadata) == expected


# --- Tiers (ADR-003 D3, decision 8) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [
        ("docs_page", 1),
        ("feature_gate_reference", 1),
        ("release_record", 2),
        ("governance_doc", 4),
        ("blog_post", 6),
        ("discussion", 7),  # S13-T1: GitHub issues, PRs and discussions
    ],
)
def test_each_source_types_tier(source_type: str, expected: int) -> None:
    assert tier(source_type, None, [], [], LATEST) == expected


@pytest.mark.parametrize("status", ["withdrawn", "rejected", "replaced"])
def test_a_withdrawn_rejected_or_replaced_kep_is_a_superseded_proposal(status: str) -> None:
    # No tier, even though its gate shipped.
    assert tier("kep", status, ["G"], [_row("G", 25, "beta")], LATEST) is None


def test_an_implementable_kep_whose_gate_was_seen_at_25_only_has_shipped_by_37() -> None:
    # The gate was removed after 1.25 (as 42 of 65 gated KEPs' gates are by 1.37).
    assert tier("kep", "implementable", ["G"], [_row("G", 25, "stable")], 37) == 3


def test_an_implementable_kep_never_seen_is_tier_5() -> None:
    assert tier("kep", "implementable", ["G"], [], LATEST) == 5


def test_an_implemented_kep_never_seen_is_tier_3() -> None:
    assert tier("kep", "implemented", ["G"], [], LATEST) == 3


@pytest.mark.parametrize(
    ("gates", "rows", "target", "expected"),
    [
        # Seen only after the target release: not shipped by it.
        (["G"], [_row("G", 30, "alpha")], 25, 5),
        # A blank, low row counts: any stage, blank included.
        (["G"], [_row("G", 25, None, "low")], 37, 3),
        # Exact names only: an unmatched gate name has no row.
        (["MixedProtocolLBSVC"], [_row("MixedProtocolLBService", 25, "beta")], 37, 5),
        # No gate: the tier is by status alone.
        ([], [_row("G", 25, "beta")], 37, 5),
    ],
    ids=["seen-after-target", "blank-low-row", "unmatched-name", "no-gate"],
)
def test_shipped_by_the_target_release(
    gates: list[str], rows: list[Observation], target: int, expected: int
) -> None:
    assert tier("kep", "implementable", gates, rows, target) == expected


# --- A KEP's effective stage (ADR-003 D2) ---------------------------------------------------------


def test_one_high_stage_at_the_target_release_is_observed() -> None:
    # Both gates' rows at 37 are high and say beta; A's 36 row isn't at the target.
    rows = [_row("A", 36, "alpha"), _row("A", 37, "beta"), _row("B", 37, "beta")]
    assert kep_stage("stable", ["A", "B"], rows, 37) == ("beta", "high")


def test_two_gates_that_disagree_give_the_claim_low() -> None:
    rows = [_row("A", 37, "beta"), _row("B", 37, "alpha")]
    assert kep_stage("stable", ["A", "B"], rows, 37) == ("stable", "low")


def test_nothing_at_the_target_release_gives_the_claim_low() -> None:
    # A's only row is at 25: removed after GA.
    assert kep_stage("stable", ["A"], [_row("A", 25, "stable")], 37) == ("stable", "low")


def test_a_low_row_at_the_target_release_gives_the_claim_low() -> None:
    assert kep_stage("beta", ["A"], [_row("A", 37, None, "low")], 37) == ("beta", "low")


def test_another_gates_row_isnt_read() -> None:
    assert kep_stage("alpha", ["A"], [_row("B", 37, "beta")], 37) == ("alpha", "low")


def test_a_gate_with_no_row_at_the_target_release_gives_the_claim_low() -> None:
    # Resume decision R3d: every gate the KEP names needs a row at 37. A's high beta row alone
    # doesn't make the stage observed while B has none there.
    assert kep_stage("stable", ["A", "B"], [_row("A", 37, "beta")], 37) == ("stable", "low")


def test_no_claim_and_no_observation_is_unknown() -> None:
    assert kep_stage(None, ["A"], [], 37) == (None, None)


def test_an_observation_needs_no_claim() -> None:
    assert kep_stage(None, ["A"], [_row("A", 37, "beta")], 37) == ("beta", "high")


# --- A hit's authority ----------------------------------------------------------------------------


def _hit(source_type: str, **changes: Any) -> Hit:
    hit = Hit(
        chunk_id=1,
        content_hash="a" * 64,
        distance=0.3,
        text="text",
        canonical_id="kep:2579",
        source_type=source_type,
        heading_path=["Summary"],
        release_windows=[(25, None)],
        current=True,
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="enhancements",
        snapshot_sha="0" * 40,
        source_path="keps/sig-auth/2579-psp-replacement/README.md",
        metadata={},
    )
    return hit.model_copy(update=changes)


# KEP-2579's claim and gate, and PodSecurity's rows at 22 and 25 (the T5 plan's spot rows).
KEP_2579 = _hit(
    "kep",
    claimed_status="implemented",
    claimed_stage="stable",
    metadata={"feature-gates": [{"name": "PodSecurity", "components": ["kube-apiserver"]}]},
)
PODSECURITY = [_row("PodSecurity", 22, "alpha"), _row("PodSecurity", 25, "stable")]


def test_a_docs_hit_gets_its_tier_and_no_stage() -> None:
    assert authority(_hit("docs_page"), PODSECURITY, 37) == Authority(
        target_release=37, tier=1, effective_stage=None, stage_confidence=None
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (
            22,
            Authority(target_release=22, tier=3, effective_stage="alpha", stage_confidence="high"),
        ),
        # No row at 37 (the gate was removed after GA): the claim, low; shipped at 22.
        (
            37,
            Authority(target_release=37, tier=3, effective_stage="stable", stage_confidence="low"),
        ),
    ],
    ids=["at-22", "at-37"],
)
def test_a_kep_hit_gets_its_tier_and_stage_from_its_own_gates(
    target: int, expected: Authority
) -> None:
    assert authority(KEP_2579, PODSECURITY, target) == expected


def test_a_superseded_kep_hit_has_no_tier_but_keeps_its_stage() -> None:
    hit = KEP_2579.model_copy(update={"claimed_status": "withdrawn"})
    assert authority(hit, PODSECURITY, 22) == Authority(
        target_release=22, tier=None, effective_stage="alpha", stage_confidence="high"
    )


# --- The weights (S09-T7; ADR-003 D4 as changed in the S09-R2 design review, decision 3) ---
#
# Boost 1.25 and demote 0.8, passed explicitly so no expected value rests on the defaults. The
# probabilities are typed by hand: sigmoid(x) = 1 / (1 + e^-x), so sigmoid(2) = 0.88080,
# sigmoid(1) = 0.73106, sigmoid(-1) = 0.26894, sigmoid(11) = 0.99998 and sigmoid(12) = 0.99999 (both
# 1.0000 at 4 decimals).

BOOST, DEMOTE = 1.25, 0.8


def _weighed_hit(
    source_type: str,
    tier: int | None,
    windows: list[tuple[int, int | None]] | None = None,
    headings: list[str] | None = None,
    score: float | None = None,
    chunk_id: int = 1,
) -> Hit:
    """A hit with its tier at 1.37 attached, as `retrieve` attaches it before the weights.
    Default: valid from 1.30 on (so at 1.37), no heading."""
    return _hit(
        source_type,
        chunk_id=chunk_id,
        release_windows=[(30, None)] if windows is None else windows,
        heading_path=[] if headings is None else headings,
        rerank_score=score,
        authority=Authority(
            target_release=37, tier=tier, effective_stage=None, stage_confidence=None
        ),
    )


@pytest.mark.parametrize(
    ("mode", "hit", "expected"),
    [
        # CURRENT: tier 1 or 2 valid at the latest release → boost; a blog → demote.
        ("CURRENT", _weighed_hit("docs_page", 1), BOOST),
        ("CURRENT", _weighed_hit("feature_gate_reference", 1, [(29, 37)]), BOOST),
        ("CURRENT", _weighed_hit("release_record", 2, [(37, 37)]), BOOST),
        # A current CHANGELOG section of an older release: tier 2, but valid at 1.25 only.
        ("CURRENT", _weighed_hit("release_record", 2, [(25, 25)]), 1.0),
        # A docs page whose text ended at 1.36: tier 1, not valid at 1.37.
        ("CURRENT", _weighed_hit("docs_page", 1, [(20, 36)]), 1.0),
        ("CURRENT", _weighed_hit("blog_post", 6), DEMOTE),
        ("CURRENT", _weighed_hit("kep", 3), 1.0),
        ("CURRENT", _weighed_hit("governance_doc", 4), 1.0),
        # A superseded proposal: no tier, never boosted.
        ("CURRENT", _weighed_hit("kep", None), 1.0),
        # CHANGE: a release record → boost, valid at the latest release or not.
        ("CHANGE", _weighed_hit("release_record", 2, [(25, 25)]), BOOST),
        ("CHANGE", _weighed_hit("docs_page", 1), 1.0),
        ("CHANGE", _weighed_hit("blog_post", 6), 1.0),
        # WHY: a KEP's Motivation or Alternatives section (any case, any heading level), blogs
        # and governance docs → boost; the feature-gate reference → demote.
        ("WHY", _weighed_hit("kep", 3, headings=["KEP-2579: PSP", "Motivation", "Goals"]), BOOST),
        ("WHY", _weighed_hit("kep", 5, headings=["KEP-1: X", "Alternatives Considered"]), BOOST),
        ("WHY", _weighed_hit("kep", 3, headings=["KEP-2579: PSP", "Design Details"]), 1.0),
        # A superseded proposal's Motivation: no tier, never boosted (resume decision R3a).
        ("WHY", _weighed_hit("kep", None, headings=["KEP-1: X", "Motivation"]), 1.0),
        ("WHY", _weighed_hit("blog_post", 6, headings=["Motivation"]), BOOST),
        ("WHY", _weighed_hit("governance_doc", 4), BOOST),
        ("WHY", _weighed_hit("feature_gate_reference", 1), DEMOTE),
        ("WHY", _weighed_hit("docs_page", 1, headings=["Motivation"]), 1.0),
        ("WHY", _weighed_hit("release_record", 2), 1.0),
        # HISTORY: no weights (validity matters more than tier).
        ("HISTORY", _weighed_hit("docs_page", 1), 1.0),
        ("HISTORY", _weighed_hit("blog_post", 6), 1.0),
        ("HISTORY", _weighed_hit("release_record", 2), 1.0),
        ("HISTORY", _weighed_hit("feature_gate_reference", 1), 1.0),
    ],
    ids=[
        "current-docs",
        "current-gate",
        "current-release-record-at-37",
        "current-release-record-at-25-only",
        "current-docs-ended-at-36",
        "current-blog",
        "current-kep",
        "current-governance",
        "current-superseded",
        "change-release-record",
        "change-docs",
        "change-blog",
        "why-kep-motivation",
        "why-kep-alternatives",
        "why-kep-other-section",
        "why-superseded-kep-motivation",
        "why-blog",
        "why-governance",
        "why-gate",
        "why-docs-motivation",
        "why-release-record",
        "history-docs",
        "history-blog",
        "history-release-record",
        "history-gate",
    ],
)
def test_each_modes_factor(mode: Mode, hit: Hit, expected: float) -> None:
    assert factor(hit, mode, LATEST, BOOST, DEMOTE) == expected


def test_current_weights_on_the_probability_put_the_boosted_docs_page_first() -> None:
    # Rerank order: the blog (logit 2.0), then 2 current docs pages (1.0 and -1.0). Products:
    # 0.88080 * 0.8 = 0.7046, 0.73106 * 1.25 = 0.9138, 0.26894 * 1.25 = 0.3362.
    blog = _weighed_hit("blog_post", 6, score=2.0, chunk_id=1)
    docs = _weighed_hit("docs_page", 1, score=1.0, chunk_id=2)
    low_docs = _weighed_hit("docs_page", 1, score=-1.0, chunk_id=3)

    weighed = weigh([blog, docs, low_docs], "CURRENT", LATEST, BOOST, DEMOTE)

    assert [hit.chunk_id for hit in weighed] == [2, 1, 3]
    assert [hit.authority_score for hit in weighed] == pytest.approx(
        [0.9138, 0.7046, 0.3362], abs=1e-4
    )
    # Every other field is kept, the raw score included.
    assert [hit.rerank_score for hit in weighed] == [1.0, 2.0, -1.0]


def test_equal_products_keep_rerank_order() -> None:
    # Two docs pages with one logit and one factor: equal products, so the input order stays.
    first = _weighed_hit("docs_page", 1, score=0.5, chunk_id=1)
    second = _weighed_hit("docs_page", 1, score=0.5, chunk_id=2)

    assert [h.chunk_id for h in weigh([first, second], "CURRENT", LATEST, BOOST, DEMOTE)] == [1, 2]
    assert [h.chunk_id for h in weigh([second, first], "CURRENT", LATEST, BOOST, DEMOTE)] == [2, 1]


def test_a_saturated_probability_ties_at_4_decimals_and_keeps_rerank_order() -> None:
    # sigmoid(11) = 0.99998 and sigmoid(12) = 0.99999: both 1.0000 at 4 decimals, so the logit-11
    # hit stays first although its unrounded product is lower.
    eleven = _weighed_hit("docs_page", 1, score=11.0, chunk_id=1)
    twelve = _weighed_hit("docs_page", 1, score=12.0, chunk_id=2)

    weighed = weigh([eleven, twelve], "HISTORY", LATEST, BOOST, DEMOTE)

    assert [hit.chunk_id for hit in weighed] == [1, 2]


def test_boost_1_and_demote_1_keep_the_input_order() -> None:
    # The CURRENT pool above, with every factor 1: the probabilities keep the logits' order.
    blog = _weighed_hit("blog_post", 6, score=2.0, chunk_id=1)
    docs = _weighed_hit("docs_page", 1, score=1.0, chunk_id=2)
    low_docs = _weighed_hit("docs_page", 1, score=-1.0, chunk_id=3)

    weighed = weigh([blog, docs, low_docs], "CURRENT", LATEST, 1.0, 1.0)

    assert [hit.chunk_id for hit in weighed] == [1, 2, 3]
    # The bare probabilities: sigmoid(2), sigmoid(1), sigmoid(-1).
    assert [hit.authority_score for hit in weighed] == pytest.approx(
        [0.88080, 0.73106, 0.26894], abs=1e-5
    )


def test_a_hit_without_a_rerank_score_is_refused() -> None:
    with pytest.raises(ValueError, match="rerank_score"):
        weigh([_weighed_hit("docs_page", 1)], "CURRENT", LATEST, BOOST, DEMOTE)
