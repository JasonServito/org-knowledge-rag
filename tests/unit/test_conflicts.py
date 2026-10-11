"""S10-T2: the rule-found conflicts (ADR-010 D1; the S10-R1 contract's "T2 rules (pinned)").

Every expected value is typed by hand from those rules, ADR-003 D2 and the real corpus lines;
none is computed by the code under test. No database, no network: the hits, the KEP versions,
the observations and the release dates are hand-built. Release dates are the manifest's.
"""

from datetime import date
from typing import Any

import pytest

from orgknow.db.models import Authority, Confidence, Hit, NewestVersion, Observation
from orgknow.generation.conflicts import Conflict, claim_mismatches, history_dates

GATE = "StrictIPCIDRValidation"  # KEP-4858's one gate, as its kep.yaml names it


def _hit(chunk_id: int, canonical_id: str = "kep:4858", **changes: Any) -> Hit:
    hit = Hit(
        chunk_id=chunk_id,
        content_hash="a" * 64,
        distance=0.3,
        text="Source: kep\nDocument: kep:4858\n\nbody",
        canonical_id=canonical_id,
        source_type="kep",
        heading_path=["Summary"],
        release_windows=[(37, None)],
        current=True,
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="enhancements",
        snapshot_sha="0" * 40,
        source_path="keps/sig-network/4858-ip-cidr-validation/README.md",
        metadata={},
        authority=Authority(target_release=37, tier=3, effective_stage=None, stage_confidence=None),
    )
    return hit.model_copy(update=changes)


def _version(
    claimed_stage: str | None,
    gates: list[str],
    milestone: str | None = None,
    canonical_id: str = "kep:4858",
) -> NewestVersion:
    metadata: dict[str, Any] = {"feature-gates": [{"name": gate} for gate in gates]}
    if milestone is not None:
        metadata["latest-milestone"] = milestone
    return NewestVersion(
        canonical_id=canonical_id,
        source_type="kep",
        claimed_status="implementable",
        claimed_stage=claimed_stage,
        metadata=metadata,
    )


def _row(
    gate: str, release: int, stage: str | None, confidence: Confidence = "high"
) -> Observation:
    return Observation(gate=gate, release=release, stage=stage, status_confidence=confidence)


# --- claim_mismatch -------------------------------------------------------------------------------


def test_a_claim_ahead_of_the_observed_stage_is_one_conflict() -> None:
    # KEP-4858 at 1.37: its version valid there claims stable for v1.38; the reference says beta.
    versions = {"kep:4858": _version("stable", [GATE], "v1.38")}

    conflicts = claim_mismatches([_hit(101)], versions, [_row(GATE, 37, "beta")], 37)

    assert conflicts == [
        Conflict(
            kind="claim_mismatch",
            found_by="rule",
            chunk_ids=[101],
            documents=["kep:4858"],
            summary=(
                "kep:4858 claims stable (latest milestone v1.38); the feature-gate reference at "
                "1.37 says beta."
            ),
            resolution="observed_beats_claimed",
            prevails=None,
        )
    ]


def test_with_no_latest_milestone_the_summary_leaves_it_out() -> None:
    versions = {"kep:4858": _version("stable", [GATE])}

    [conflict] = claim_mismatches([_hit(101)], versions, [_row(GATE, 37, "beta")], 37)

    assert conflict.summary == (
        "kep:4858 claims stable; the feature-gate reference at 1.37 says beta."
    )


def test_a_claim_equal_to_the_observed_stage_is_no_conflict() -> None:
    versions = {"kep:4858": _version("beta", [GATE], "v1.36")}

    assert claim_mismatches([_hit(101)], versions, [_row(GATE, 37, "beta")], 37) == []


def test_the_claim_is_the_version_valid_at_the_target_not_the_hits_own() -> None:
    # KEP-2579 at 1.24: two versions are valid there, beta (1.22-1.24) and stable (1.24-1.25).
    # `kep_versions_at` gives the newest, the stable one (proved in the integration test); the hit
    # cites the beta one. PodSecurity is beta at 1.24, so the stable claim conflicts.
    hit = _hit(
        201,
        "kep:2579",
        claimed_stage="beta",
        metadata={"feature-gates": [{"name": "PodSecurity"}], "latest-milestone": "v1.23"},
    )
    versions = {"kep:2579": _version("stable", ["PodSecurity"], "v1.25", "kep:2579")}

    [conflict] = claim_mismatches([hit], versions, [_row("PodSecurity", 24, "beta")], 24)

    assert conflict.summary == (
        "kep:2579 claims stable (latest milestone v1.25); the feature-gate reference at 1.24 "
        "says beta."
    )


@pytest.mark.parametrize(
    ("versions", "rows"),
    [
        # KEP-4004: a claimed `disabled` is never compared (ADR-003 D2); 1.37 says deprecated.
        ({"kep:4858": _version("disabled", [GATE])}, [_row(GATE, 37, "deprecated")]),
        # No claim (ADR-003 D2: never a claim_mismatch).
        ({"kep:4858": _version(None, [GATE])}, [_row(GATE, 37, "beta")]),
        # No version valid at the target (the KEP was created later).
        ({}, [_row(GATE, 37, "beta")]),
        # No gates: nothing is observed.
        ({"kep:4858": _version("stable", [])}, []),
        # A gate with no row at the target (rows at 36 only).
        ({"kep:4858": _version("stable", [GATE])}, [_row(GATE, 36, "beta")]),
        # A low row.
        ({"kep:4858": _version("stable", [GATE])}, [_row(GATE, 37, None, "low")]),
        # 2 gates giving alpha and beta: no one observed stage.
        (
            {"kep:4858": _version("stable", ["A", "B"])},
            [_row("A", 37, "alpha"), _row("B", 37, "beta")],
        ),
        # 2 gates, one with no row.
        ({"kep:4858": _version("stable", ["A", "B"])}, [_row("A", 37, "beta")]),
    ],
    ids=[
        "disabled",
        "no-claim",
        "no-version",
        "no-gates",
        "gate-without-row",
        "low-row",
        "gates-disagree",
        "one-gate-unobserved",
    ],
)
def test_no_claim_mismatch_without_a_comparable_claim_and_observed_stage(
    versions: dict[str, NewestVersion], rows: list[Observation]
) -> None:
    assert claim_mismatches([_hit(101)], versions, rows, 37) == []


def test_three_hits_of_one_kep_are_one_conflict_holding_their_ids_by_rank() -> None:
    hits = [
        _hit(103),
        _hit(300, "web:/docs/reference/networking/", source_type="docs_page"),
        _hit(101),
        _hit(102),
    ]
    versions = {"kep:4858": _version("stable", [GATE], "v1.38")}

    [conflict] = claim_mismatches(hits, versions, [_row(GATE, 37, "beta")], 37)

    assert (conflict.chunk_ids, conflict.documents) == ([103, 101, 102], ["kep:4858"])


def test_a_non_kep_hit_is_ignored() -> None:
    # Even with a "version" whose claim would conflict: only KEP hits are compared.
    hit = _hit(300, "web:/docs/x/", source_type="docs_page")
    versions = {"web:/docs/x/": _version("stable", [GATE], canonical_id="web:/docs/x/")}

    assert claim_mismatches([hit], versions, [_row(GATE, 37, "beta")], 37) == []


def test_conflicts_follow_each_keps_first_hit() -> None:
    hits = [_hit(201, "kep:2579"), _hit(101), _hit(202, "kep:2579")]
    versions = {
        "kep:4858": _version("stable", [GATE], "v1.38"),
        "kep:2579": _version("stable", ["PodSecurity"], "v1.25", "kep:2579"),
    }
    rows = [_row(GATE, 37, "beta"), _row("PodSecurity", 37, "beta")]

    conflicts = claim_mismatches(hits, versions, rows, 37)

    assert [(c.documents, c.chunk_ids) for c in conflicts] == [
        (["kep:2579"], [201, 202]),
        (["kep:4858"], [101]),
    ]


# --- history_date ---------------------------------------------------------------------------------

# The `releases` table's dates (the manifest): 1.12 isn't in it.
RELEASE_DATES = {22: date(2021, 8, 4), 23: date(2021, 12, 7), 26: date(2022, 12, 8)}
TOLERANCE = 7  # HISTORY_DATE_TOLERANCE_DAYS' default

# KEP-2579's real lines (chunk 15293): 1.22 on its day; 1.23 34 days early (2021-11-03 to
# 2021-12-07: 27 days left in November, then 7).
KEP_2579_HISTORY = (
    "Source: kep\nDocument: kep:2579\nSection: Implementation History\n\n"
    "- 2021-08-04: v1.22 Alpha version released\n"
    "- 2021-11-03: v1.23 Beta version released\n"
)


def test_a_history_line_34_days_from_the_release_date_is_one_conflict() -> None:
    hit = _hit(15293, "kep:2579", text=KEP_2579_HISTORY)

    assert history_dates([hit], RELEASE_DATES, TOLERANCE) == [
        Conflict(
            kind="history_date",
            found_by="rule",
            chunk_ids=[15293],
            documents=["kep:2579"],
            summary=(
                "kep:2579 says v1.23 was released 2021-11-03; the releases table says 2021-12-07."
            ),
            resolution="observed_beats_claimed",
            prevails=None,
        )
    ]


@pytest.mark.parametrize(
    "line",
    [
        # KEP-3453's real line: on the release date.
        "- 2022-12-08: Kubernetes 1.26 released",
        # KEP-614's real line: 1.12 isn't in `releases`, so it is skipped.
        "- 2018-09-27 Kubernetes 1.12.0 released with Alpha SCTP support",
        # 7 days off (2021-11-30 to 2021-12-07): within the tolerance.
        "- 2021-11-30: v1.23 released",
        "- 2021-12-14: v1.23 released",
        # No "released" on the line.
        "- 2021-11-03: v1.23 Beta",
        # Not a date the calendar has.
        "- 2021-13-45: v1.23 released",
    ],
    ids=[
        "same-day",
        "minor-not-in-releases",
        "7-days-early",
        "7-days-late",
        "no-released",
        "bad-date",
    ],
)
def test_no_history_date_conflict(line: str) -> None:
    hit = _hit(1, "kep:2579", text=f"Source: kep\n\n{line}")

    assert history_dates([hit], RELEASE_DATES, TOLERANCE) == []


def test_a_history_line_8_days_off_is_a_conflict() -> None:
    hit = _hit(1, "kep:2579", text="Source: kep\n\n* 2021-11-29 v1.23 Released")

    [conflict] = history_dates([hit], RELEASE_DATES, TOLERANCE)

    assert conflict.summary == (
        "kep:2579 says v1.23 was released 2021-11-29; the releases table says 2021-12-07."
    )


def test_the_same_line_in_two_hits_is_one_conflict_holding_both() -> None:
    hits = [
        _hit(15293, "kep:2579", text=KEP_2579_HISTORY),
        _hit(300, "web:/docs/x/", source_type="docs_page"),
        _hit(9001, "kep:2579", text=KEP_2579_HISTORY),
    ]

    [conflict] = history_dates(hits, RELEASE_DATES, TOLERANCE)

    assert (conflict.chunk_ids, conflict.documents) == ([15293, 9001], ["kep:2579"])


def test_a_history_line_in_a_non_kep_hit_is_ignored() -> None:
    hit = _hit(300, "web:/blog/x/", source_type="blog_post", text=KEP_2579_HISTORY)

    assert history_dates([hit], RELEASE_DATES, TOLERANCE) == []
