"""The prompt for the answer step: a fixed system prompt, then one evidence block per hit, then
the conflicts code found in the hits, if any (S10-T4).

Each block's first line gives the chunk id and every release window of the text (S04-R2
decision 4), its second the hit's authority tier (S09-T6); a KEP block adds the status and stage
the KEP claimed, then its effective stage at the target release. Pure functions.
"""

from collections.abc import Sequence

from orgknow.db.models import Authority, Hit
from orgknow.generation.conflicts import Conflict, Resolution

# Short and plain on purpose: Opus 5.5 does worse with over-prescriptive prompts. It is not asked
# to write out its reasoning (it reasons anyway). The output schema is set by the API call.
SYSTEM_PROMPT = """\
You answer questions about Kubernetes from evidence: chunks of the Kubernetes docs and of KEPs \
(Kubernetes Enhancement Proposals). Each chunk starts with a line giving its id and the releases \
it was valid in ("now": still valid in the latest release), then its authority tier (1 = docs \
and feature-gate pages, 2 = release notes, 3 = shipped KEPs, 4 = governance docs, 5 = unshipped \
KEPs, 6 = blog posts). A KEP chunk adds the status and stage the KEP claimed, and its stage at \
the asked-about release.

- Answer only from the evidence, and cite the ids of the chunks that support the answer.
- If the evidence doesn't support an answer, return `insufficient_evidence` with a short reason \
saying what is missing.
- Never state a rationale, motive or history that the evidence doesn't contain.
"""


def _window(start: int, until: int | None) -> str:
    """One release window: from and until joined by an en dash ("now" when still open), or one
    release alone when from and until are the same."""
    if until is None:
        return f"1.{start}\N{EN DASH}now"
    if until == start:
        return f"1.{start}"
    return f"1.{start}\N{EN DASH}1.{until}"


def _tier(authority: Authority) -> str:
    """The authority line: "authority: tier 3", or "authority: superseded proposal"."""
    if authority.tier is None:
        return "authority: superseded proposal"
    return f"authority: tier {authority.tier}"


def _stage(authority: Authority) -> str:
    """A KEP's stage line at the target release: observed (high), claimed (low) or unknown."""
    at = f"stage at 1.{authority.target_release}"
    if authority.effective_stage is None:
        return f"{at}: unknown"
    seen = "observed" if authority.stage_confidence == "high" else "claimed, not observed"
    return f"{at}: {authority.effective_stage} ({seen})"


def evidence_block(hit: Hit) -> str:
    """The hit as the model sees it: the id and windows line, the authority line, a KEP's claim
    line and stage line, the text.

    Windows are printed as the hit lists them, never merged. A hit with no `authority` (never
    one from `retrieve`) has no authority or stage line.
    """
    windows = ", ".join(_window(start, until) for start, until in hit.release_windows)
    lines = [f"[chunk {hit.chunk_id}] valid in releases: {windows}"]
    if hit.authority is not None:
        lines.append(_tier(hit.authority))
    if hit.source_type == "kep":
        status = "none" if hit.claimed_status is None else hit.claimed_status
        stage = "none" if hit.claimed_stage is None else hit.claimed_stage
        lines.append(f"claimed: {status}/{stage}")
        if hit.authority is not None:
            lines.append(_stage(hit.authority))
    lines.append(hit.text)  # starts with its Source/Title/Document/Section header
    return "\n".join(lines)


# How a rule-found conflict's resolution reads (S10-R1, pinned). The rules resolve only this way
# (ADR-010 D2), and only rule-found conflicts are shown to the model.
_RESOLVED: dict[Resolution, str] = {"observed_beats_claimed": "Resolved: observed beats claimed."}


def conflicts_block(conflicts: Sequence[Conflict]) -> str:
    """The rule-found conflicts as the model sees them (S10-R1, pinned): a heading line, then one
    line per conflict with its chunk ids ("chunk 205", or "chunks 101, 102"), its summary and its
    resolution."""
    lines = ["Conflicts found by code:"]
    for conflict in conflicts:
        noun = "chunk" if len(conflict.chunk_ids) == 1 else "chunks"
        ids = ", ".join(str(chunk_id) for chunk_id in conflict.chunk_ids)
        lines.append(f"- {noun} {ids}: {conflict.summary} {_RESOLVED[conflict.resolution]}")
    return "\n".join(lines)


def user_prompt(question: str, hits: Sequence[Hit], conflicts: Sequence[Conflict] = ()) -> str:
    """The user message: every evidence block, nearest first, then the rule-found `conflicts`'
    block when there is at least one, then the question."""
    blocks = "\n\n".join(evidence_block(hit) for hit in hits)
    found = f"\n\n{conflicts_block(conflicts)}" if conflicts else ""
    return f"Evidence:\n\n{blocks}{found}\n\nQuestion: {question}"
