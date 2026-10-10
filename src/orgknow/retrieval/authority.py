"""Authority tiers per hit (S09-T6; ADR-003 D2-D3 as changed in the S09-R2 sitting). Pure: the
caller passes in the latest release and the feature gates' observations (`observed_lifecycle`).

- `target_release`: the release a question asks about, from its route.
- `kep_gates`: the feature gates a KEP version names in its `kep.yaml`.
- `kep_stage`: a KEP's effective stage at the target release: observed, else claimed, else unknown.
- `tier`: 1 (docs) to 6 (blogs) by source type; a KEP 3 when shipped by the target release or
  implemented, else 5; None for a superseded proposal.
- `authority`: a hit's tier and, for a KEP, its effective stage, at the target release.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from orgknow.db.models import Authority, Confidence, Hit, Observation
from orgknow.retrieval.router import Mode
from orgknow.retrieval.temporal import Window

# ADR-003 D3 by source type (S09-R2 decision 8): a fixed rule, not a tuned weight. A KEP's tier
# depends on its status and its gates (`tier`).
SOURCE_TIERS = {
    "docs_page": 1,
    "feature_gate_reference": 1,
    "release_record": 2,
    "governance_doc": 4,
    "blog_post": 6,
}
# The claimed statuses of a superseded proposal: kept, but given no tier (ADR-003 D3).
SUPERSEDED = ("withdrawn", "rejected", "replaced")


def target_release(mode: Mode | None, window: Window | None, latest: int) -> int:
    """The release a question asks about, given its routed `mode` (None: no route) and the
    window its time scope resolved to: a HISTORY window's `until_release`, capped at `latest`;
    otherwise `latest` (CURRENT, CHANGE, WHY, HISTORY with no window or no `until`, and the
    modes with no route)."""
    if mode == "HISTORY" and window is not None and window.until_release is not None:
        return min(window.until_release, latest)
    return latest


def kep_gates(metadata: Mapping[str, Any]) -> list[str]:
    """The `name`s in a KEP version's `feature-gates` list (from its `kep.yaml`), as written. No
    gate when the key is missing, null or an empty list."""
    return [gate["name"] for gate in metadata.get("feature-gates") or []]


def kep_stage(
    claimed_stage: str | None, gates: Sequence[str], rows: Sequence[Observation], target: int
) -> tuple[str | None, Confidence | None]:
    """A KEP's effective stage at `target` and its confidence (ADR-003 D2): when its gates have
    rows at `target`, all high and giving one stage, that stage, high; otherwise its
    `claimed_stage`, low; with no claim either, (None, None). `rows` may hold other gates and
    releases: only `gates`' rows at `target` are read."""
    at_target = [row for row in rows if row.gate in gates and row.release == target]
    stages = {row.stage for row in at_target}
    if at_target and len(stages) == 1 and all(r.status_confidence == "high" for r in at_target):
        return stages.pop(), "high"
    if claimed_stage is None:
        return None, None
    return claimed_stage, "low"


def tier(
    source_type: str,
    claimed_status: str | None,
    gates: Sequence[str],
    rows: Sequence[Observation],
    target: int,
) -> int | None:
    """The authority tier at `target` (ADR-003 D3, S09-R2 decision 8). Every source type but a
    KEP: `SOURCE_TIERS`. A KEP claiming withdrawn, rejected or replaced: None (a superseded
    proposal). Any other KEP: 3 when it has shipped by `target` (one of its `gates` has a row,
    any stage, blank included, at a release up to `target`) or claims `implemented`; else 5."""
    if source_type != "kep":
        return SOURCE_TIERS[source_type]
    if claimed_status in SUPERSEDED:
        return None
    shipped = any(row.gate in gates and row.release <= target for row in rows)
    return 3 if shipped or claimed_status == "implemented" else 5


def authority(hit: Hit, rows: Sequence[Observation], target: int) -> Authority:
    """The hit's authority at `target`: its tier, and for a KEP its effective stage through the
    gates its cited version names. `rows` may hold any gates' observations (`retrieve` reads
    every hit's gates at once): each KEP reads only its own."""
    gates: list[str] = []
    stage: str | None = None  # only a KEP has an effective stage
    confidence: Confidence | None = None
    if hit.source_type == "kep":
        gates = kep_gates(hit.metadata)
        stage, confidence = kep_stage(hit.claimed_stage, gates, rows, target)
    return Authority(
        target_release=target,
        tier=tier(hit.source_type, hit.claimed_status, gates, rows, target),
        effective_stage=stage,
        stage_confidence=confidence,
    )
