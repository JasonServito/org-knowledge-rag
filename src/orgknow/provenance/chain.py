"""A stored decision chain, as the CLI prints it and the API returns it (S13-T3; T5).

`load_chain` is the one shared function that reads a chain: `orgknow chain` and, from T5,
`GET /decisions/{canonical_id}` both call it. It never builds (`make chains` does). Each cited
step gets its source URL and its authority tier at the latest release (ADR-003 D3), computed as a
citation's are.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC

import psycopg
from psycopg.rows import TupleRow
from pydantic import AwareDatetime, BaseModel

from orgknow.db.decisions import stored_decision
from orgknow.db.lifecycle import observations
from orgknow.db.models import FoundBy, MissingReason, Observation, Step, StoredEvidence
from orgknow.db.releases import list_releases
from orgknow.retrieval.authority import kep_gates, tier


class ChainStep(BaseModel):
    """One step of a chain: the cited chunk (its document, section, source URL and tier), its
    date and how it was found, and the via chunk; or, for a missing step, only its reason."""

    step: Step
    occurred_at: AwareDatetime | None
    chunk_id: int | None
    canonical_id: str | None
    heading_path: list[str] | None
    source_type: str | None
    source_url: str | None  # the file on GitHub at the snapshot commit; a GitHub item's page
    tier: int | None  # at the latest release; None for a missing step or a superseded proposal
    found_by: FoundBy | None
    via_chunk_id: int | None  # the chunk holding the link that connects this step
    via_canonical_id: str | None
    via_heading_path: list[str] | None
    missing_reason: MissingReason | None


class Chain(BaseModel):
    """A seed KEP's stored decision chain: 6 steps in step order."""

    seed: str
    title: str
    built_at: AwareDatetime
    steps: list[ChainStep]


def source_url(evidence: StoredEvidence, repo_urls: Mapping[str, str]) -> str | None:
    """The cited chunk's source URL, as a citation's (`generation.validate.fill_in`): a GitHub
    item's own page (metadata `url`), else the file on GitHub at the snapshot commit."""
    if evidence.chunk_id is None:
        return None
    if evidence.source_type == "discussion" and evidence.metadata is not None:
        return str(evidence.metadata["url"])
    repo = repo_urls[str(evidence.snapshot_repo)]
    return f"{repo}/blob/{evidence.snapshot_sha}/{evidence.source_path}"


def step_tier(step: StoredEvidence, rows: Sequence[Observation], latest: int) -> int | None:
    """The cited chunk's tier at the latest release (ADR-003 D3): by source type, a KEP's by its
    gates' observations (`rows`) and claimed status. None for a missing step."""
    if step.source_type is None:
        return None
    gates = kep_gates(step.metadata or {}) if step.source_type == "kep" else []
    return tier(step.source_type, step.claimed_status, gates, rows, latest)


def load_chain(
    conn: psycopg.Connection[TupleRow], canonical_id: str, repo_urls: Mapping[str, str]
) -> Chain | None:
    """The stored chain of the seed KEP `canonical_id`, or None when none is stored. Read-only.
    `repo_urls` maps a manifest repo name to its GitHub URL (`load_repo_urls`)."""
    stored = stored_decision(conn, canonical_id)
    if stored is None:
        return None
    latest = list_releases(conn)[-1].minor  # oldest first; a stored chain implies a release
    gates = {
        gate
        for step in stored.steps
        if step.source_type == "kep"
        for gate in kep_gates(step.metadata or {})
    }
    rows = observations(conn, sorted(gates), latest)
    steps = [
        ChainStep(
            step=step.step,
            occurred_at=step.occurred_at,
            chunk_id=step.chunk_id,
            canonical_id=step.canonical_id,
            heading_path=step.heading_path,
            source_type=step.source_type,
            source_url=source_url(step, repo_urls),
            tier=step_tier(step, rows, latest),
            found_by=step.found_by,
            via_chunk_id=step.via_chunk_id,
            via_canonical_id=step.via_canonical_id,
            via_heading_path=step.via_heading_path,
            missing_reason=step.missing_reason,
        )
        for step in stored.steps
    ]
    return Chain(seed=stored.seed, title=stored.title, built_at=stored.built_at, steps=steps)


# Between a document and its section, as the S13-R1 plan writes a citation: U+203A, the
# single right-pointing angle quotation mark (" > " already joins the headings).
SECTION_MARK = "\u203a"


def _section(canonical_id: str | None, heading_path: Sequence[str] | None) -> str:
    """The canonical id, SECTION_MARK, then the heading path joined by " > "."""
    return f"{canonical_id} {SECTION_MARK} {' > '.join(heading_path or [])}"


def step_line(step: ChainStep) -> str:
    """One step: its UTC date (dashes when undated), the step, then the citation (source URL,
    canonical id and section, tier, how it was found and "via <the link's text>") or
    `missing: <reason>`."""
    day = "-" * 10 if step.occurred_at is None else f"{step.occurred_at.astimezone(UTC):%Y-%m-%d}"
    if step.missing_reason is not None:
        return f"{day}  {step.step:<14}  missing: {step.missing_reason}"
    tier_text = "no tier" if step.tier is None else f"tier {step.tier}"
    line = (
        f"{day}  {step.step:<14}  {step.source_url}  "
        f"{_section(step.canonical_id, step.heading_path)}  {tier_text}  {step.found_by}"
    )
    if step.via_chunk_id is not None:
        line += f" via {_section(step.via_canonical_id, step.via_heading_path)}"
    return line


def chain_lines(chain: Chain) -> list[str]:
    """The CLI's text: a header (seed, title, built time), then one line per step."""
    built = f"{chain.built_at.astimezone(UTC):%Y-%m-%d %H:%M:%S}"
    header = f"{chain.seed}: {chain.title} (built {built} UTC)"
    return [header, *(step_line(step) for step in chain.steps)]
