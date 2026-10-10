"""S09-T6: each hit's authority tier at the question's target release, and a KEP's effective stage
(ADR-003 D2-D3 as changed in the S09-R2 sitting; the S09-R2 contract's T6 rules).

Every expected value is typed by hand from those rules; none is computed by the code under test.
No database, no network: the observations are hand-built rows. 1.37 is the latest release.
"""

from typing import Any

import pytest

from orgknow.db.models import Authority, Confidence, Hit, Observation
from orgknow.retrieval.authority import authority, kep_gates, kep_stage, target_release, tier
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


# KEP-2579's claim and gate, and PodSecurity's rows at 22 and 25 (the T5 contract's spot rows).
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
