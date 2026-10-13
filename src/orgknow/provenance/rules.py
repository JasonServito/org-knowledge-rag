"""The decision chain's rules (S13-T3; ADR-012 D1; the S13-R1 contract's "Pinned: T3").

Pure functions over rows the data-access layer returns (`db/decisions.py`); `build.py` reads the
rows and stores the result. A chain has 6 steps, each citing 1 stored chunk with its date and how
it was found, or missing with its reason, never guessed:

1. The tracking issue is `gh:enhancements/issues/<N>` for `kep:<N>`.
2. Its opening post's template fields give the proposal PR and the discussion: the first URL on
   each field's line (`field_link`). Only a full URL counts: a bare `#N` is not a link.
3. problem: the discussion's opening post, else the KEP's Motivation.
4. discussion: the discussion's first comment.
5. proposal: the KEP's Summary, dated by the proposal PR's opening, else the KEP's creation-date.
6. decision: the proposal PR's last `/approve` before its merge, dated by the merge.
7. implementation: the earliest blog post or release record linking the KEP, on or after the
   decision (the proposal when the decision is missing).
8. current_docs: the nearest text to the KEP's Summary vector, valid at the latest release (the
   search itself is `db/decisions.nearest_current_texts`).

Every chunk is read as the chunker stores it: header lines, a blank line, then the body. The rules
read the body only: the header repeats the title and section in every chunk. A GitHub post's
time is its heading's day (T1's rendering stores no post's exact time), at 00:00 UTC; an item's
own times (`created_at`, `merged_at`) are exact, from its metadata.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel

from orgknow.db.models import (
    ChainDocument,
    DocumentChunk,
    LinkCandidate,
    MissingReason,
    NearText,
    NewEvidence,
    Step,
)

# Tracking issues live in kubernetes/enhancements, the manifest's `enhancements` repo (rule 1).
ENHANCEMENTS = "enhancements"
# The tracking-issue template's fields (rule 2).
KEP_FIELD = "Kubernetes Enhancement Proposal:"
UPDATE_PR_FIELD = "KEP (`k/enhancements`) update PR(s):"
DISCUSSION_FIELD = "Discussion Link:"
# Prow's approval command, at the start of a line (rule 6).
APPROVE = "/approve"

OPENING_POST = "Opening post · "
COMMENTS = "Comments"
# A post's heading (T1's rendering): `Opening post · @<author> · <day>` or, under `Comments`,
# `@<login> · <day>`, then ` · reply` or ` · review`.
POST_HEADING = re.compile(
    r"^(?:Opening post · )?@\S+ · (\d{4}-\d{2}-\d{2})(?: · (?:reply|review))?$"
)
# A URL ends at whitespace or Markdown's brackets; trailing punctuation isn't part of it.
URL = re.compile(r"https?://[^\s<>()\[\]]+")
# An issue, PR or discussion on GitHub: `<owner>/<repo>`, its kind and its number.
ITEM_URL = re.compile(
    r"^https?://github\.com/([^/]+/[^/]+)/(issues|pull|discussions)/(\d+)(?:[/?#]|$)"
)


class Link(BaseModel):
    """A template field, resolved (rule 2): the item its first URL names, or why it names none.

    `canonical_id` set: the URL names an item of a manifest repo (stored or not: the builder
    looks it up). `reason` set: `no_tracking_issue`, `no_link` (no field line, or no URL on it),
    `not_public` (not GitHub) or `not_ingested` (GitHub, but not an item of a manifest repo).
    """

    via: DocumentChunk | None  # the tracking issue's chunk holding the field's line
    canonical_id: str | None
    reason: MissingReason | None


# --- Reading chunks ------------------------------------------------------------------------------


def body(text: str) -> str:
    """A chunk's body: its text after the header's blank line."""
    return text.partition("\n\n")[2]


def is_opening_post(path: Sequence[str]) -> bool:
    """Whether a heading path is under an item's opening post (by prefix: the post can start with
    a heading of its own)."""
    return bool(path) and path[0].startswith(OPENING_POST)


def is_comment(path: Sequence[str]) -> bool:
    """Whether a heading path is under a post in `# Comments` (a comment, reply or review)."""
    return len(path) >= 2 and path[0] == COMMENTS


def post_day(path: Sequence[str]) -> date | None:
    """The day in the heading of the post a chunk is in; None for a chunk in no post."""
    if is_opening_post(path):
        heading = path[0]
    elif is_comment(path):
        heading = path[1]
    else:
        return None
    match = POST_HEADING.match(heading)
    return None if match is None else date.fromisoformat(match[1])


def first_chunk(
    chunks: Sequence[DocumentChunk], keep: Callable[[Sequence[str]], bool]
) -> DocumentChunk | None:
    """The chunk with the lowest ordinal whose heading path `keep` accepts, or None."""
    kept = [chunk for chunk in chunks if keep(chunk.heading_path)]
    return min(kept, key=lambda chunk: chunk.ordinal, default=None)


def kep_section(kep: ChainDocument, name: str) -> DocumentChunk:
    """The first chunk of the KEP's `name` section: the heading under its title is `name` (by
    prefix: the section can start with a subheading). Raises ValueError when there is none
    (every KEP has a Summary and a Motivation by template)."""
    chunk = first_chunk(kep.chunks, lambda path: path[1:2] == [name])
    if chunk is None:
        raise ValueError(f"{kep.canonical_id} has no {name} section")
    return chunk


def day_start(day: date) -> datetime:
    """00:00 UTC of `day`."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _time(value: Any) -> datetime:
    """An item's time from its metadata (a UTC ISO 8601 string)."""
    return datetime.fromisoformat(str(value))


def creation_date(kep: ChainDocument) -> datetime | None:
    """The KEP's `creation-date` (kep.yaml), at 00:00 UTC; None when it has none."""
    value = kep.metadata.get("creation-date")
    return None if value is None else day_start(date.fromisoformat(str(value)))


# --- Rules 1-2: the tracking issue and its fields ------------------------------------------------


def kep_number(seed: str) -> int:
    """`kep:2572` → 2572. Raises ValueError for a seed that isn't a numbered KEP."""
    number = seed.removeprefix("kep:")
    if not seed.startswith("kep:") or not number.isdigit():
        raise ValueError(f"{seed} is not a numbered KEP (kep:<N>)")
    return int(number)


def tracking_issue_id(number: int) -> str:
    """Rule 1: a KEP's number is its tracking issue's number."""
    return f"gh:{ENHANCEMENTS}/issues/{number}"


def repo_keys(repo_urls: Mapping[str, str]) -> dict[str, str]:
    """`<owner>/<repo>` → the manifest's repo key, from `load_repo_urls`."""
    return {urlsplit(url).path.strip("/"): key for key, url in repo_urls.items()}


def resolve(url: str | None, via: DocumentChunk, keys: Mapping[str, str]) -> Link:
    """Rule 2 for a field's first URL: an item of a manifest repo → its `gh:` id; another GitHub
    page → `not_ingested`; any other site → `not_public`; no URL → `no_link`."""
    if url is None:
        return Link(via=via, canonical_id=None, reason="no_link")
    item = ITEM_URL.match(url)
    if item is not None and item[1] in keys:
        return Link(via=via, canonical_id=f"gh:{keys[item[1]]}/{item[2]}/{item[3]}", reason=None)
    reason: MissingReason = (
        "not_ingested" if urlsplit(url).hostname == "github.com" else "not_public"
    )
    return Link(via=via, canonical_id=None, reason=reason)


def field_link(issue: ChainDocument | None, label: str, keys: Mapping[str, str]) -> Link:
    """Rule 2: the first line of the tracking issue's opening post holding `label`, resolved by
    its first URL. No tracking issue → `no_tracking_issue`; no such line → `no_link`."""
    if issue is None:
        return Link(via=None, canonical_id=None, reason="no_tracking_issue")
    opening = sorted(
        (chunk for chunk in issue.chunks if is_opening_post(chunk.heading_path)),
        key=lambda chunk: chunk.ordinal,
    )
    for chunk in opening:
        for line in body(chunk.text).split("\n"):
            if label in line:
                url = URL.search(line)
                return resolve(None if url is None else url[0].rstrip(".,;:"), chunk, keys)
    return Link(via=None, canonical_id=None, reason="no_link")


def proposal_link(kep_field: Link, update_field: Link) -> Link:
    """The proposal PR's field (the contract's "Which items a chain gets"): the "Kubernetes
    Enhancement Proposal:" field when it names an `enhancements` PR, else the first "KEP
    (`k/enhancements`) update PR(s):" line."""
    names_pr = kep_field.canonical_id is not None and kep_field.canonical_id.startswith(
        f"gh:{ENHANCEMENTS}/pull/"
    )
    return kep_field if names_pr else update_field


def link_reason(link: Link, item: ChainDocument | None) -> MissingReason | None:
    """Why a field's item can't be cited: the field's own reason, or `not_ingested` when it
    names an item that isn't stored. None: `item` is that stored item."""
    if link.reason is not None:
        return link.reason
    return "not_ingested" if item is None else None


def missing(step: Step, reason: MissingReason) -> NewEvidence:
    return NewEvidence(step=step, missing_reason=reason)


# --- Rules 3-6: problem, discussion, proposal, decision ------------------------------------------


def problem_step(discussion: Link, item: ChainDocument | None, kep: ChainDocument) -> NewEvidence:
    """Rule 3: the discussion's opening post (its first chunk), dated by the discussion's
    creation. Else (no stored discussion, or an opening post with no text) the KEP's Motivation,
    dated by its creation-date."""
    if link_reason(discussion, item) is None:
        assert item is not None and discussion.via is not None  # a stored item, from a field
        post = first_chunk(item.chunks, is_opening_post)
        if post is not None:
            return NewEvidence(
                step="problem",
                chunk_id=post.id,
                occurred_at=_time(item.metadata["created_at"]),
                found_by="template_field",
                via_chunk_id=discussion.via.id,
            )
    motivation = kep_section(kep, "Motivation")
    return NewEvidence(
        step="problem", chunk_id=motivation.id, occurred_at=creation_date(kep), found_by="seed"
    )


def discussion_step(discussion: Link, item: ChainDocument | None) -> NewEvidence:
    """Rule 4: the discussion's first comment (its first chunk), dated by its heading's day; else
    the field's missing reason. A stored discussion with no comment is `no_link`: it holds no
    comment to cite (a call the contract leaves open)."""
    reason = link_reason(discussion, item)
    if reason is not None:
        return missing("discussion", reason)
    assert item is not None and discussion.via is not None  # a stored item, from a field
    comment = first_chunk(item.chunks, is_comment)
    day = None if comment is None else post_day(comment.heading_path)
    if comment is None or day is None:
        return missing("discussion", "no_link")
    return NewEvidence(
        step="discussion",
        chunk_id=comment.id,
        occurred_at=day_start(day),
        found_by="template_field",
        via_chunk_id=discussion.via.id,
    )


def proposal_step(proposal: Link, pr: ChainDocument | None, kep: ChainDocument) -> NewEvidence:
    """Rule 5: the KEP's Summary (its first chunk). With the proposal PR stored: dated by the PR's
    opening, via the field's text. Else dated by the KEP's creation-date."""
    summary = kep_section(kep, "Summary")
    if link_reason(proposal, pr) is None:
        assert pr is not None and proposal.via is not None  # a stored item, from a field
        return NewEvidence(
            step="proposal",
            chunk_id=summary.id,
            occurred_at=_time(pr.metadata["created_at"]),
            found_by="seed",
            via_chunk_id=proposal.via.id,
        )
    return NewEvidence(
        step="proposal", chunk_id=summary.id, occurred_at=creation_date(kep), found_by="seed"
    )


def holds_approve(chunk: DocumentChunk) -> bool:
    """Whether a line of the chunk's body starts with `/approve`."""
    return any(line.startswith(APPROVE) for line in body(chunk.text).split("\n"))


def decision_step(proposal: Link, pr: ChainDocument | None) -> NewEvidence:
    """Rule 6: the proposal PR's last post holding a line starting `/approve` before the merge
    (its chunk holding the line), dated by `merged_at`. A post's time is its heading's day, so
    "before the merge" is "on or before the merge's UTC day". Merged with no `/approve` → its
    opening post. Not merged → `not_merged`; no stored PR → the field's reason."""
    reason = link_reason(proposal, pr)
    if reason is not None:
        return missing("decision", reason)
    assert pr is not None and proposal.via is not None  # a stored item, from a field
    if pr.metadata.get("merged_at") is None:
        return missing("decision", "not_merged")
    merged_at = _time(pr.metadata["merged_at"])
    merge_day = merged_at.astimezone(UTC).date()
    approvals = [
        chunk
        for chunk in pr.chunks
        if (day := post_day(chunk.heading_path)) is not None
        and day <= merge_day
        and holds_approve(chunk)
    ]
    if approvals:
        cited = max(approvals, key=lambda chunk: chunk.ordinal)
    else:
        opening = first_chunk(pr.chunks, is_opening_post)
        cited = opening if opening is not None else min(pr.chunks, key=lambda c: c.ordinal)
    return NewEvidence(
        step="decision",
        chunk_id=cited.id,
        occurred_at=merged_at,
        found_by="merge_event",
        via_chunk_id=proposal.via.id,
    )


# --- Rule 7: implementation ----------------------------------------------------------------------


def kep_folder(kep: ChainDocument) -> str:
    """The KEP's folder name, e.g. `2572-release-cadence`, from its README's path."""
    return PurePosixPath(kep.source_path).parent.name


def links_kep(text: str, number: int, folder: str) -> bool:
    """Whether a chunk's body links the KEP: its folder name, `enhancements/issues/<N>`, or
    `KEP-<N>` as a whole word (case-insensitive, as the S13-R1 sitting's probe matched)."""
    pattern = rf"{re.escape(folder)}|enhancements/issues/{number}(?!\d)|\bKEP-{number}\b"
    return re.search(pattern, body(text), re.IGNORECASE) is not None


def candidate_date(candidate: LinkCandidate, release_dates: Mapping[int, date]) -> datetime:
    """A linking text's date: a CHANGELOG's (`changelog:1.R`) is its release's date, at 00:00 UTC
    (its versions carry the lock refresh date); any other's is its version's date-window start."""
    if candidate.canonical_id.startswith("changelog:1."):
        return day_start(release_dates[int(candidate.canonical_id.removeprefix("changelog:1."))])
    return candidate.valid_from_date


def implementation_step(
    candidates: Sequence[LinkCandidate],
    kep: ChainDocument,
    decision: NewEvidence,
    proposal: NewEvidence,
    release_dates: Mapping[int, date],
) -> NewEvidence:
    """Rule 7: the earliest candidate whose body links the KEP, dated on or after the decision's
    UTC day (the proposal's when the decision is missing; no bound when that is undated). Ties:
    by canonical id, then version, then ordinal. It cites the chunk holding the link, via itself.
    None → `no_linking_text`. `release_dates` maps a minor to its release date."""
    number, folder = kep_number(kep.canonical_id), kep_folder(kep)
    bound = decision.occurred_at if decision.missing_reason is None else proposal.occurred_at
    dated = [
        (candidate_date(candidate, release_dates), candidate)
        for candidate in candidates
        if links_kep(candidate.text, number, folder)
    ]
    if bound is not None:
        since = bound.astimezone(UTC).date()
        dated = [(at, candidate) for at, candidate in dated if at.astimezone(UTC).date() >= since]
    if not dated:
        return missing("implementation", "no_linking_text")
    at, cited = min(
        dated,
        key=lambda pair: (pair[0], pair[1].canonical_id, pair[1].valid_from_date, pair[1].ordinal),
    )
    return NewEvidence(
        step="implementation",
        chunk_id=cited.chunk_id,
        occurred_at=at,
        found_by="linking_text",
        via_chunk_id=cited.chunk_id,
    )


# --- Rule 8: current docs ------------------------------------------------------------------------


def current_docs_step(nearest: Sequence[NearText]) -> NewEvidence:
    """Rule 8: the nearest text, ties by content hash, dated by its cited version's date-window
    start. No link connects it, so no via. Raises ValueError with no text (no vectors)."""
    if not nearest:
        raise ValueError("no text valid at the latest release has a vector: run `make embed`")
    cited = min(nearest, key=lambda text: (text.distance, text.content_hash))
    return NewEvidence(
        step="current_docs",
        chunk_id=cited.chunk_id,
        occurred_at=cited.valid_from_date,
        found_by="similarity",
    )
