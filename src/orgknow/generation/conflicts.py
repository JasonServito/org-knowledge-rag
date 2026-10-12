"""Conflicts between pieces of evidence (S10; ADR-010, ADR-003 D2 and D6): the model an answer's
`conflicts[]` holds, the pairs the answer model lists (`ModelConflict`, S10-T5), and the
conflicts code finds in stored facts before the answer (S10-T2, ADR-010 D1).

- `claim_mismatches`: a KEP's claimed stage, from its version valid at the target release, vs.
  the one stage its feature gates' rows give there.
- `history_dates`: a KEP history line "YYYY-MM-DD: ... v1.N ... released" vs. the `releases`
  table's date for 1.N.
- `rule_conflicts`: both, on one question's hits. The only function here that reads the
  database; the two rules are pure.
- `pair_conflict` (S10-T3, ADR-010 D2): the kind and resolution of two hits that disagree.
- `model_conflicts` (S10-T5, ADR-010 D1 and D3): the pairs the answer model listed, checked on
  their own, each resolved by `pair_conflict`.

Both rules resolve as `observed_beats_claimed` (ADR-003 D6 rule 1): the observed stage, or the
release date, wins over what the KEP says. A pair resolves by D6's rules 2-4: the hit valid at
the target release, else the lower tier number, else unresolved.
"""

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

import psycopg
from psycopg.rows import TupleRow
from pydantic import BaseModel, Field

from orgknow.db.lifecycle import kep_versions_at, observations
from orgknow.db.models import Hit, NewestVersion, Observation
from orgknow.db.releases import list_releases
from orgknow.retrieval.authority import kep_gates, kep_stage
from orgknow.settings import Settings

ConflictKind = Literal["claim_mismatch", "history_date", "supersession", "contradiction"]
Resolution = Literal["observed_beats_claimed", "valid_at_target", "lower_tier", "unresolved"]


class Conflict(BaseModel):
    """One conflict in an answer's `conflicts[]` (ADR-010 D3), found by a rule or by the model."""

    kind: ConflictKind
    found_by: Literal["rule", "model"]
    chunk_ids: list[int]  # rule: the hits it is about, by rank; model: [first, second] as given
    documents: list[str]  # the canonical ids of chunk_ids, first appearance first, no repeats
    summary: str  # rule: the pinned wording; model: its sentence
    resolution: Resolution
    prevails: int | None  # the winning chunk (valid_at_target, lower_tier); None otherwise


# A pair of chunks the answer model says disagree, in its structured output (`ModelAnswer`): the
# chunk ids it gives, before code checks them (S10-T5). Comments, not docstrings, on this class:
# pydantic would send a docstring to the model as the schema's description.
class ModelConflict(BaseModel):
    first: int = Field(description="The id of one chunk.")
    second: int = Field(description="The id of a chunk that disagrees with it.")
    summary: str = Field(description="One sentence: what the two chunks disagree about.")


# A KEP history line (S10-R1, pinned): group 1 is the date D, group 2 the minor N of v1.N.
HISTORY_LINE = re.compile(
    r"^\s*[-*]?\s*(\d{4}-\d{2}-\d{2}):?\s+.*?\bv?1\.(\d+)\b.*\breleased\b", re.IGNORECASE
)

# A KEP's latest milestone, as its kep.yaml writes it ("v1.22", or "1.17"): group 1 is the minor
# (S10-R1, pinned).
MILESTONE = re.compile(r"^v?1\.(\d+)")


def releases_before(milestone: object, release: int) -> int | None:
    """How many releases a KEP's latest milestone is before `release`: 15 for "v1.22" at 1.37
    (S10-T5c, ADR-010 D1). None when it is at or after `release` (a plan, not a release), or
    isn't a string like v1.N or 1.N."""
    match = MILESTONE.match(milestone) if isinstance(milestone, str) else None
    if match is None:
        return None
    before = release - int(match[1])
    return before if before > 0 else None


def claim_mismatches(
    hits: Sequence[Hit],
    versions: Mapping[str, NewestVersion],
    rows: Sequence[Observation],
    release: int,
) -> list[Conflict]:
    """One `claim_mismatch` per KEP among `hits` whose claim differs from its observed stage at
    `release` (ADR-003 D2, ADR-010 D1), in the order of each KEP's first hit. Per KEP:

    1. its version is `versions[canonical_id]` (`kep_versions_at` at `release`); none → no conflict
    2. that version's claimed stage is None or `disabled` → no conflict
    3. its gates (`kep_gates`) are empty → no conflict
    4. observed: every gate has a row at `release`, all high, giving one stage (`kep_stage` with
       no claim); otherwise → no conflict
    5. the claim ≠ the observed stage → a conflict holding all the KEP's hits, by rank

    The hits give only the KEPs and the chunk ids: their own claims can come from a version
    older than `release`, so they are never read. `rows` may hold any gates and releases.
    """
    conflicts = []
    keps = dict.fromkeys(hit.canonical_id for hit in hits if hit.source_type == "kep")
    for canonical_id in keps:  # in the order of each KEP's first hit
        version = versions.get(canonical_id)
        if version is None or version.claimed_stage in (None, "disabled"):
            continue
        gates = kep_gates(version.metadata)
        observed, _ = kep_stage(None, gates, rows, release)  # None unless observed
        if not gates or observed is None or observed == version.claimed_stage:
            continue
        milestone = version.metadata.get("latest-milestone")
        claim = version.claimed_stage
        if releases_before(milestone, release) is not None:  # only one older than `release`
            claim = f"{claim} (latest milestone {milestone})"
        conflicts.append(
            Conflict(
                kind="claim_mismatch",
                found_by="rule",
                chunk_ids=[hit.chunk_id for hit in hits if hit.canonical_id == canonical_id],
                documents=[canonical_id],
                summary=(
                    f"{canonical_id} claims {claim}; the feature-gate reference at 1.{release} "
                    f"says {observed}."
                ),
                resolution="observed_beats_claimed",
                prevails=None,
            )
        )
    return conflicts


def history_dates(
    hits: Sequence[Hit], release_dates: Mapping[int, date], tolerance_days: int
) -> list[Conflict]:
    """One `history_date` per (KEP, minor, date) whose date is more than `tolerance_days` from
    the release date of that minor in `release_dates` (by minor: 23 for 1.23), in the order of
    their first hit. Only KEP hits are read, line by line (`HISTORY_LINE`). A minor not in
    `release_dates`, or a date the calendar doesn't have, is skipped. The same line in 2 hits is
    one conflict holding both, by rank."""
    found: dict[tuple[str, int, date], list[int]] = {}  # (KEP, minor, date) → its chunk ids
    for hit in hits:
        if hit.source_type != "kep":
            continue
        for line in hit.text.splitlines():
            match = HISTORY_LINE.match(line)
            if match is None:
                continue
            minor = int(match[2])
            try:
                said = date.fromisoformat(match[1])
            except ValueError:  # e.g. 2021-13-45: the pattern doesn't check the calendar
                continue
            if minor not in release_dates:
                continue
            if abs((said - release_dates[minor]).days) <= tolerance_days:
                continue
            chunk_ids = found.setdefault((hit.canonical_id, minor, said), [])
            if hit.chunk_id not in chunk_ids:
                chunk_ids.append(hit.chunk_id)
    return [
        Conflict(
            kind="history_date",
            found_by="rule",
            chunk_ids=chunk_ids,
            documents=[canonical_id],
            summary=(
                f"{canonical_id} says v1.{minor} was released {said}; the releases table says "
                f"{release_dates[minor]}."
            ),
            resolution="observed_beats_claimed",
            prevails=None,
        )
        for (canonical_id, minor, said), chunk_ids in found.items()
    ]


def pair_conflict(
    a: Hit, b: Hit, target: int, latest: int
) -> tuple[ConflictKind, Resolution, int | None]:
    """The kind, resolution and prevailing chunk id of two hits that disagree, at the `target`
    release (ADR-010 D2, ADR-003 D6). The order of `a` and `b` doesn't change the result.

    - Kind: the same document and heading path → `supersession`; otherwise `contradiction`.
    - Exactly one hit valid at `target` (`_valid_at`) → it prevails: `valid_at_target`.
    - Otherwise their tiers decide, where no tier (a superseded proposal, or no `authority`) is
      worse than any tier: the lower number prevails (`lower_tier`); equal tiers, both None
      included, → `unresolved`, and nothing prevails.
    """
    same_section = a.canonical_id == b.canonical_id and a.heading_path == b.heading_path
    kind: ConflictKind = "supersession" if same_section else "contradiction"
    a_valid, b_valid = _valid_at(a, target, latest), _valid_at(b, target, latest)
    if a_valid != b_valid:
        return kind, "valid_at_target", a.chunk_id if a_valid else b.chunk_id
    a_rank, b_rank = _tier_rank(a), _tier_rank(b)
    if a_rank == b_rank:
        return kind, "unresolved", None
    return kind, "lower_tier", a.chunk_id if a_rank < b_rank else b.chunk_id


def model_conflicts(
    pairs: Sequence[ModelConflict], hits: Sequence[Hit], rule_found: Sequence[Conflict]
) -> tuple[list[Conflict], list[ModelConflict]]:
    """The model's `pairs`, checked on their own (S10-T5, ADR-010 D3): the kept ones as
    conflicts, in the model's order, and the dropped ones, for the trace.

    A pair is dropped when it names one chunk twice, a chunk not in `hits`, or the chunks of a
    conflict already kept: an earlier pair, in either order, or a rule-found conflict's chunk ids
    (`rule_found`) as a set. A kept pair gets its kind, resolution and prevailing chunk from
    `pair_conflict` at the hits' target release (their `authority.target_release`); with no
    target (no hit has `authority`, never one from `retrieve`), nothing can resolve a pair, so
    every pair is dropped.
    """
    target = next((h.authority.target_release for h in hits if h.authority is not None), None)
    by_id = {hit.chunk_id: hit for hit in hits}
    seen = [set(conflict.chunk_ids) for conflict in rule_found]  # the kept conflicts' chunks
    kept: list[Conflict] = []
    dropped: list[ModelConflict] = []
    for pair in pairs:
        ids = {pair.first, pair.second}
        retrieved = pair.first in by_id and pair.second in by_id
        if target is None or len(ids) < 2 or not retrieved or ids in seen:
            dropped.append(pair)
            continue
        seen.append(ids)
        first, second = by_id[pair.first], by_id[pair.second]
        # The target is never past the latest release (`target_release` caps it), so an open
        # window holds the target exactly when it opens by then: the target stands in for the
        # latest release, and no database read is needed.
        kind, resolution, prevails = pair_conflict(first, second, target, latest=target)
        kept.append(
            Conflict(
                kind=kind,
                found_by="model",
                chunk_ids=[pair.first, pair.second],
                documents=list(dict.fromkeys([first.canonical_id, second.canonical_id])),
                summary=pair.summary,
                resolution=resolution,
                prevails=prevails,
            )
        )
    return kept, dropped


def _valid_at(hit: Hit, target: int, latest: int) -> bool:
    """Whether some release window of `hit` holds `target`: from ≤ target ≤ until, where an
    open window (until None) runs to `latest`."""
    return any(
        start <= target <= (latest if until is None else until)
        for start, until in hit.release_windows
    )


def _tier_rank(hit: Hit) -> float:
    """The hit's tier at the target release, for comparing: no tier (a superseded proposal, or
    no `authority`) is infinity, worse than any tier."""
    if hit.authority is None or hit.authority.tier is None:
        return math.inf
    return hit.authority.tier


def rule_conflicts(
    conn: psycopg.Connection[TupleRow], hits: Sequence[Hit], settings: Settings
) -> list[Conflict]:
    """The rule-found conflicts of one question's `hits` (S10-T2), by their first chunk's rank,
    a `claim_mismatch` before a `history_date` on a tie. The target release is the hits'
    `authority.target_release` (one per question); no hit with `authority`, or no KEP hit, gives
    none. Reads the KEP versions valid at the target, their gates' observations, and the release
    dates; the tolerance is HISTORY_DATE_TOLERANCE_DAYS."""
    target = next((h.authority.target_release for h in hits if h.authority is not None), None)
    keps = sorted({hit.canonical_id for hit in hits if hit.source_type == "kep"})
    if target is None or not keps:
        return []
    versions = kep_versions_at(conn, keps, target)
    gates = {gate for version in versions.values() for gate in kep_gates(version.metadata)}
    rows = observations(conn, sorted(gates), target)
    release_dates = {release.minor: release.release_date for release in list_releases(conn)}
    claims = claim_mismatches(hits, versions, rows, target)
    dates = history_dates(hits, release_dates, settings.history_date_tolerance_days)
    rank = {hit.chunk_id: position for position, hit in enumerate(hits)}
    # A stable sort: on a tie, the claim mismatches stay before the history dates.
    return sorted([*claims, *dates], key=lambda conflict: rank[conflict.chunk_ids[0]])
