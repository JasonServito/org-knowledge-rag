"""Authority tiers per hit (S09-T6; ADR-003 D2-D3 as changed in the S09-R2 sitting), and the
weights of authority mode (S09-T7). Pure: the caller passes in the latest release, the feature
gates' observations (`observed_lifecycle`) and the weights (settings).

- `target_release`: the release a question asks about, from its route.
- `kep_gates`: the feature gates a KEP version names in its `kep.yaml`.
- `kep_stage`: a KEP's effective stage at the target release: observed, else claimed, else unknown.
- `tier`: 1 (docs) to 7 (GitHub discussions) by source type; a KEP 3 when shipped by the target
  release or implemented, else 5; None for a superseded proposal.
- `authority`: a hit's tier and, for a KEP, its effective stage, at the target release.

S09-T7 (ADR-003 D4 as changed in the S09-R2 sitting), authority mode's weights:

- `factor`: a hit's multiplier for its question's routed mode: AUTHORITY_BOOST, AUTHORITY_DEMOTE
  or 1.
- `weigh`: reranked hits sorted by the reranker's probability times their factor.
"""

import math
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
    "discussion": 7,  # GitHub issues, PRs and discussions (S13-T1)
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
    """A KEP's effective stage at `target` and its confidence (ADR-003 D2): when every gate in
    `gates` has a row at `target`, all high and giving one stage, that stage, high; otherwise
    (no gate, a gate with no row there, a low row, or 2+ stages) its `claimed_stage`, low; with
    no claim either, (None, None). `rows` may hold other gates and releases: only `gates`' rows
    at `target` are read."""
    at_target = [row for row in rows if row.gate in gates and row.release == target]
    every_gate = {row.gate for row in at_target} == set(gates)
    stages = {row.stage for row in at_target}
    if every_gate and len(stages) == 1 and all(r.status_confidence == "high" for r in at_target):
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


def factor(hit: Hit, mode: Mode, latest: int, boost: float, demote: float) -> float:
    """The multiplier for `hit` in a question routed to `mode` (ADR-003 D4 as changed in the
    S09-R2 sitting): `boost`, `demote` or 1, by the first rule that matches.

    - CURRENT: tier 1 or 2 and some release window containing `latest` → boost (so a CHANGELOG
      section of an older release, tier 2 but valid only at its release, isn't); a blog post →
      demote.
    - CHANGE: a release record → boost.
    - WHY: a KEP section with a heading containing "motivation" or "alternatives" (any case),
      unless the KEP is a superseded proposal → boost; a blog post or governance doc → boost; the
      feature-gate reference → demote.
    - HISTORY, and every other hit: 1.

    The tier is the hit's `authority`'s, None (like a superseded proposal's) when it has none. A
    hit with no tier is never boosted (resume decision R3a): CURRENT needs tier 1 or 2, WHY's KEP
    rule needs a tier, and the other boosted types always have one.
    """
    source = hit.source_type
    hit_tier = None if hit.authority is None else hit.authority.tier
    if mode == "CURRENT":
        valid_now = any(
            start <= latest and (until is None or latest <= until)
            for start, until in hit.release_windows
        )
        if hit_tier in (1, 2) and valid_now:
            return boost
        if source == "blog_post":
            return demote
    elif mode == "CHANGE":
        if source == "release_record":
            return boost
    elif mode == "WHY":
        headings = [heading.lower() for heading in hit.heading_path]
        if (
            source == "kep"
            and hit_tier is not None
            and any(
                word in heading for heading in headings for word in ("motivation", "alternatives")
            )
        ):
            return boost
        if source in ("blog_post", "governance_doc"):
            return boost
        if source == "feature_gate_reference":
            return demote
    return 1.0


def weigh(hits: Sequence[Hit], mode: Mode, latest: int, boost: float, demote: float) -> list[Hit]:
    """`hits` (reranked, in rerank order, each with its tier) sorted by the reranker's
    probability times its `factor` (S09-R2 decision 3), best first.

    The probability is sigmoid(rerank_score) = 1 / (1 + e^-score), from 0 to 1, so a multiplier
    above 1 always lifts a hit, which a raw score (negative for a poor match) can't promise.
    Products are compared rounded to 4 decimals, and a tie keeps the earlier hit first, as
    `rerank` compares its scores: a saturated probability (0.99998 and 0.99999) ties. Each hit
    gets the unrounded product as its `authority_score`. With boost 1 and demote 1, every factor
    is 1, and the order is the input's. A hit with no `rerank_score` raises ValueError.
    """
    products = []
    for hit in hits:
        if hit.rerank_score is None:
            raise ValueError(f"chunk {hit.chunk_id} has no rerank_score: weigh reranked hits only")
        probability = 1 / (1 + math.exp(-hit.rerank_score))
        products.append(probability * factor(hit, mode, latest, boost, demote))
    order = sorted(range(len(hits)), key=lambda i: (-round(products[i], 4), i))
    return [hits[i].model_copy(update={"authority_score": products[i]}) for i in order]
