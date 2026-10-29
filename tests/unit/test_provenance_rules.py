"""S13-T3: the decision chain's rules (ADR-012 D1; the S13-R1 plan's "Pinned: T3"), on
synthetic rows shaped like the data-access layer's: chunks with the chunker's header, GitHub posts
under T1's headings. No GitHub text: every body is made up. Expected values are typed by hand from
the plan's rules.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import pytest

from orgknow.db.models import ChainDocument, DocumentChunk, LinkCandidate, NearText, NewEvidence
from orgknow.provenance.rules import (
    DISCUSSION_FIELD,
    KEP_FIELD,
    UPDATE_PR_FIELD,
    ChainError,
    Link,
    current_docs_step,
    decision_step,
    discussion_step,
    field_link,
    implementation_step,
    kep_number,
    kep_section,
    links_kep,
    post_day,
    problem_step,
    proposal_link,
    proposal_step,
    repo_keys,
    tracking_issue_id,
)

REPO_URLS = {
    "enhancements": "https://github.com/kubernetes/enhancements",
    "sig-release": "https://github.com/kubernetes/sig-release",
    "kubernetes": "https://github.com/kubernetes/kubernetes",
}
KEYS = repo_keys(REPO_URLS)


def _chunk(id: int, ordinal: int, path: Sequence[str], body: str) -> DocumentChunk:
    """A chunk as the chunker stores it: header lines, a blank line, then the body."""
    section = " > ".join(path)
    text = f"Source: discussion\nTitle: Made up\nDocument: gh:x\nSection: {section}\n\n{body}"
    return DocumentChunk(
        id=id, ordinal=ordinal, heading_path=list(path), text=text, content_hash=f"{id:064x}"
    )


def _document(
    canonical_id: str,
    chunks: Sequence[DocumentChunk],
    metadata: dict[str, Any] | None = None,
    source_type: str = "discussion",
    source_path: str = "github/x.json",
) -> ChainDocument:
    return ChainDocument(
        document_id=1,
        canonical_id=canonical_id,
        source_type=source_type,
        source_path=source_path,
        metadata=metadata or {},
        chunks=list(chunks),
    )


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- Identity ------------------------------------------------------------------------------------


def test_a_kep_s_tracking_issue_is_the_enhancements_issue_with_its_number() -> None:
    assert kep_number("kep:2572") == 2572
    assert tracking_issue_id(2572) == "gh:enhancements/issues/2572"


def test_a_seed_without_a_number_is_refused() -> None:
    with pytest.raises(ChainError, match="kep:sig-auth/0014-dynamic-audit"):
        kep_number("kep:sig-auth/0014-dynamic-audit")


def test_a_kep_without_the_section_is_refused() -> None:
    kep = _document("kep:2572", [_chunk(1, 0, ["KEP-2572: Made up", "Motivation"], "Why.")])
    with pytest.raises(ChainError, match="kep:2572 has no Summary section"):
        kep_section(kep, "Summary")


def test_repo_keys_map_each_manifest_repo_s_github_path_to_its_key() -> None:
    assert KEYS == {
        "kubernetes/enhancements": "enhancements",
        "kubernetes/sig-release": "sig-release",
        "kubernetes/kubernetes": "kubernetes",
    }


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (["Opening post · @justaugustus · 2020-10-14"], date(2020, 10, 14)),
        (["Opening post · @a · 2021-03-15", "Enhancement Description"], date(2021, 3, 15)),
        (["Comments", "@dchen1107 · 2021-04-22"], date(2021, 4, 22)),
        (["Comments", "@spiffxp · 2021-04-23 · review"], date(2021, 4, 23)),
        (["Comments", "@erin · 2020-10-16 · reply", "A heading in the post"], date(2020, 10, 16)),
        (["KEP-1: Made up", "Summary"], None),
        (["Comments"], None),
    ],
)
def test_a_post_s_day_is_read_from_its_heading(path: list[str], expected: date | None) -> None:
    assert post_day(path) == expected


# --- Rule 2: the tracking issue's template fields ------------------------------------------------

OPENING = "Opening post · @owner · 2021-03-15"
FIELDS = "\n".join(
    [
        "- One-line enhancement description: Made up",
        "- Kubernetes Enhancement Proposal: https://github.com/kubernetes/enhancements/pull/7",
        "- Discussion Link: https://github.com/kubernetes/sig-release/discussions/12",
        "- [ ] Alpha",
        "  - [ ] KEP (`k/enhancements`) update PR(s): https://github.com/kubernetes/enhancements/pull/8",
        "- [ ] Beta",
        "  - [ ] KEP (`k/enhancements`) update PR(s): https://github.com/kubernetes/enhancements/pull/9",
    ]
)


def _issue(fields: str, comment: str = "Thanks.") -> ChainDocument:
    """A tracking issue whose opening post starts with a heading (so no chunk has the post's own
    heading path) and holds `fields` in its second chunk, then one comment."""
    return _document(
        "gh:enhancements/issues/1",
        [
            _chunk(10, 0, [OPENING, "Enhancement Description"], "Made-up text before the fields."),
            _chunk(11, 1, [OPENING, "Enhancement Description"], fields),
            _chunk(12, 2, ["Comments", "@someone · 2021-03-16"], comment),
        ],
    )


def test_each_field_names_the_item_of_its_first_url_and_the_chunk_holding_its_line() -> None:
    issue = _issue(FIELDS)

    kep = field_link(issue, KEP_FIELD, KEYS)
    discussion = field_link(issue, DISCUSSION_FIELD, KEYS)
    update = field_link(issue, UPDATE_PR_FIELD, KEYS)

    assert (kep.canonical_id, kep.reason) == ("gh:enhancements/pull/7", None)
    assert (discussion.canonical_id, discussion.reason) == ("gh:sig-release/discussions/12", None)
    # The first line holding the label: Alpha's, not Beta's.
    assert (update.canonical_id, update.reason) == ("gh:enhancements/pull/8", None)
    assert [link.via.id for link in (kep, discussion, update) if link.via] == [11, 11, 11]


@pytest.mark.parametrize(
    ("line", "canonical_id", "reason"),
    [
        # The first URL of several; the comma after it isn't part of it.
        (
            "- Discussion Link: https://github.com/kubernetes/enhancements/pull/3010, "
            "https://github.com/kubernetes/enhancements/pull/3016, #4931",
            "gh:enhancements/pull/3010",
            None,
        ),
        # A link to a comment still names the item.
        (
            "- Discussion Link: https://github.com/kubernetes/kubernetes/pull/5#issuecomment-1 "
            "has background",
            "gh:kubernetes/pull/5",
            None,
        ),
        # A gated document, in a Markdown link.
        (
            "- Discussion Link: [sig-auth](https://docs.google.com/document/d/x/edit#heading=h.1)",
            None,
            "not_public",
        ),
        # A bare #N is not a link (S13-R1, after the draw, option A).
        ("- Discussion Link: #4931", None, "no_link"),
        ("- Discussion Link:", None, "no_link"),
        # GitHub, but not an item in a manifest repo: public, never ingested.
        ("- Discussion Link: https://github.com/kubernetes/kubeadm/issues/5", None, "not_ingested"),
        (
            "- Discussion Link: https://github.com/kubernetes/enhancements/tree/master/keps/x/1-y",
            None,
            "not_ingested",
        ),
    ],
)
def test_a_field_s_first_url_resolves_to_an_item_or_a_missing_reason(
    line: str, canonical_id: str | None, reason: str | None
) -> None:
    link = field_link(_issue(line), DISCUSSION_FIELD, KEYS)

    assert (link.canonical_id, link.reason) == (canonical_id, reason)
    assert link.via is not None and link.via.id == 11


def test_a_field_missing_from_the_opening_post_is_no_link_even_if_a_comment_has_it() -> None:
    issue = _issue("- Kubernetes Enhancement Proposal: none yet", comment=FIELDS)

    link = field_link(issue, DISCUSSION_FIELD, KEYS)

    assert (link.via, link.canonical_id, link.reason) == (None, None, "no_link")


def test_with_no_tracking_issue_every_field_is_missing_no_tracking_issue() -> None:
    link = field_link(None, KEP_FIELD, KEYS)

    assert (link.via, link.canonical_id, link.reason) == (None, None, "no_tracking_issue")


VIA = _chunk(11, 1, [OPENING, "Enhancement Description"], FIELDS)


def _link(canonical_id: str | None = None, reason: str | None = None) -> Link:
    return Link.model_validate(
        {
            "via": VIA if reason != "no_tracking_issue" else None,
            "canonical_id": canonical_id,
            "reason": reason,
        }
    )


def test_the_proposal_pr_is_the_kep_field_when_it_names_an_enhancements_pr() -> None:
    kep_field = _link("gh:enhancements/pull/7")
    update = _link("gh:enhancements/pull/8")

    assert proposal_link(kep_field, update) == kep_field


@pytest.mark.parametrize(
    "kep_field",
    [
        _link(reason="not_ingested"),  # the KEP's folder on GitHub
        _link("gh:enhancements/issues/7"),  # an issue, not a PR
        _link("gh:sig-release/pull/7"),  # a PR, not in enhancements
        _link(reason="no_link"),
    ],
)
def test_otherwise_the_proposal_pr_is_the_first_update_pr_line(kep_field: Link) -> None:
    update = _link(reason="no_link")  # KEP-3015's "#5140"

    assert proposal_link(kep_field, update) == update


# --- Rules 3-5: problem, discussion, proposal ----------------------------------------------------

KEP = _document(
    "kep:1",
    [
        _chunk(20, 0, ["KEP-1: Made up"], "Intro."),
        _chunk(21, 1, ["KEP-1: Made up", "Summary"], "The summary."),
        _chunk(22, 2, ["KEP-1: Made up", "Summary"], "More summary."),
        # No text right under Motivation: its first chunk is under a subheading.
        _chunk(23, 3, ["KEP-1: Made up", "Motivation", "Goals"], "The goals."),
        _chunk(24, 4, ["KEP-1: Made up", "Proposal"], "The proposal."),
    ],
    metadata={"title": "Made up", "creation-date": "2021-01-21"},
    source_type="kep",
    source_path="keps/sig-release/1-made-up/README.md",
)
DISCUSSION_OPENING = "Opening post · @owner · 2020-10-14"
DISCUSSION = _document(
    "gh:sig-release/discussions/12",
    [
        _chunk(30, 0, [DISCUSSION_OPENING, "What would you like to be added:"], "Fewer releases."),
        _chunk(31, 1, [DISCUSSION_OPENING, "Why is this needed:"], "Because."),
        _chunk(32, 2, ["Comments", "@first · 2020-10-15"], "Agreed."),
        _chunk(33, 3, ["Comments", "@second · 2020-10-16"], "Disagree."),
    ],
    metadata={"created_at": "2020-10-14T20:36:05Z"},
)
FOUND = _link("gh:sig-release/discussions/12")


def test_problem_is_the_discussion_s_opening_post_dated_by_its_creation() -> None:
    assert problem_step(FOUND, DISCUSSION, KEP) == NewEvidence(
        step="problem",
        chunk_id=30,  # the opening post's first chunk: the lowest ordinal under its heading
        occurred_at=_at("2020-10-14T20:36:05Z"),
        found_by="template_field",
        via_chunk_id=11,
    )


@pytest.mark.parametrize(
    ("link", "item"),
    [
        (FOUND, None),  # names an item that isn't stored
        (_link(reason="not_public"), None),
        (_link(reason="no_tracking_issue"), None),
    ],
)
def test_without_a_stored_discussion_problem_is_the_kep_s_motivation(
    link: Link, item: ChainDocument | None
) -> None:
    assert problem_step(link, item, KEP) == NewEvidence(
        step="problem",
        chunk_id=23,
        occurred_at=_at("2021-01-21T00:00:00Z"),  # the KEP's creation-date
        found_by="seed",
    )


def test_discussion_is_the_discussion_s_first_comment_dated_by_it() -> None:
    assert discussion_step(FOUND, DISCUSSION) == NewEvidence(
        step="discussion",
        chunk_id=32,
        occurred_at=_at("2020-10-15T00:00:00Z"),  # the post heading's day
        found_by="template_field",
        via_chunk_id=11,
    )


@pytest.mark.parametrize(
    ("link", "item", "reason"),
    [
        (FOUND, None, "not_ingested"),
        (_link(reason="not_public"), None, "not_public"),
        (_link(reason="no_link"), None, "no_link"),
        (_link(reason="not_ingested"), None, "not_ingested"),
        (_link(reason="no_tracking_issue"), None, "no_tracking_issue"),
    ],
)
def test_without_a_stored_discussion_the_step_is_missing_with_the_field_s_reason(
    link: Link, item: ChainDocument | None, reason: str
) -> None:
    assert discussion_step(link, item) == NewEvidence.model_validate(
        {"step": "discussion", "missing_reason": reason}
    )


PR_OPENING = "Opening post · @owner · 2021-03-12"


def _pr(
    *comments: tuple[str, str], merged_at: str | None = "2021-04-23T15:38:03Z"
) -> ChainDocument:
    """A PR whose comments are (heading, body) pairs, in order."""
    chunks = [_chunk(40, 0, [PR_OPENING], "Adds the KEP.")]
    for ordinal, (heading, body) in enumerate(comments, start=1):
        chunks.append(_chunk(40 + ordinal, ordinal, ["Comments", heading], body))
    return _document(
        "gh:enhancements/pull/7",
        chunks,
        metadata={"created_at": "2021-03-12T14:32:43Z", "merged_at": merged_at},
    )


PROPOSAL = _link("gh:enhancements/pull/7")


def test_proposal_is_the_kep_s_summary_dated_by_the_proposal_pr_s_opening() -> None:
    assert proposal_step(PROPOSAL, _pr(), KEP) == NewEvidence(
        step="proposal",
        chunk_id=21,  # the Summary's first chunk
        occurred_at=_at("2021-03-12T14:32:43Z"),
        found_by="seed",
        via_chunk_id=11,
    )


@pytest.mark.parametrize(("link", "item"), [(PROPOSAL, None), (_link(reason="no_link"), None)])
def test_without_a_stored_proposal_pr_the_summary_is_dated_by_the_kep_s_creation_date(
    link: Link, item: ChainDocument | None
) -> None:
    assert proposal_step(link, item, KEP) == NewEvidence(
        step="proposal", chunk_id=21, occurred_at=_at("2021-01-21T00:00:00Z"), found_by="seed"
    )


# --- Rule 6: decision ----------------------------------------------------------------------------

# PR #2567's Prow order (prow_order.log), with made-up bodies: 4 /approves, the last on 04-22,
# then a /lgtm, and a /hold cancel just before the merge on 04-23.
PROW = (
    ("@dims · 2021-04-19", "/approve\n/hold for all approvers to cast their vote/support."),
    ("@derekwaynecarr · 2021-04-20", "/approve "),
    ("@jberkus · 2021-04-20", "/lgtm (non-binding)"),
    ("@johnbelamaric · 2021-04-20", "/approve"),
    ("@dchen1107 · 2021-04-22", "/approve "),
    ("@dims · 2021-04-22", "/lgtm"),
    ("@spiffxp · 2021-04-23 · review", "/lgtm"),
    ("@justaugustus · 2021-04-23", "Thanks everyone!\n\n/hold cancel"),
)


def test_decision_cites_the_last_approve_before_the_merge_dated_by_the_merge() -> None:
    assert decision_step(PROPOSAL, _pr(*PROW)) == NewEvidence(
        step="decision",
        chunk_id=45,  # dchen1107's, not the last Prow command (/hold cancel, 48)
        occurred_at=_at("2021-04-23T15:38:03Z"),
        found_by="merge_event",
        via_chunk_id=11,
    )


def test_an_approve_after_the_merge_day_or_not_at_a_line_start_does_not_count() -> None:
    pr = _pr(
        *PROW,
        ("@late · 2021-04-24", "/approve"),
        ("@quoted · 2021-04-23", "Please /approve when ready.\n> /approve"),
    )

    assert decision_step(PROPOSAL, pr).chunk_id == 45


def test_a_merged_pr_with_no_approve_cites_its_opening_post() -> None:
    pr = _pr(("@dims · 2021-04-22", "/lgtm"))

    assert decision_step(PROPOSAL, pr) == NewEvidence(
        step="decision",
        chunk_id=40,
        occurred_at=_at("2021-04-23T15:38:03Z"),
        found_by="merge_event",
        via_chunk_id=11,
    )


@pytest.mark.parametrize(
    ("link", "item", "reason"),
    [
        (PROPOSAL, _pr(*PROW, merged_at=None), "not_merged"),
        (PROPOSAL, None, "not_ingested"),
        (_link(reason="no_link"), None, "no_link"),
        (_link(reason="not_public"), None, "not_public"),
        (_link(reason="no_tracking_issue"), None, "no_tracking_issue"),
    ],
)
def test_an_unmerged_or_missing_pr_leaves_the_decision_missing(
    link: Link, item: ChainDocument | None, reason: str
) -> None:
    assert decision_step(link, item) == NewEvidence.model_validate(
        {"step": "decision", "missing_reason": reason}
    )


# --- Rule 7: implementation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Read [the KEP](https://github.com/kubernetes/enhancements/issues/1).", True),
        ("See KEP-1 for details.", True),
        ("See kep-1.", True),
        ("https://github.com/kubernetes/enhancements/tree/master/keps/sig-release/1-made-up", True),
        ("See https://github.com/kubernetes/enhancements/issues/10.", False),
        ("See KEP-10 and KEP-1a.", False),
        ("1 release a year.", False),
    ],
)
def test_a_link_to_the_kep_is_its_folder_its_tracking_issue_or_kep_n_as_a_word(
    body: str, expected: bool
) -> None:
    assert links_kep(_chunk(1, 0, ["S"], body).text, 1, "1-made-up") is expected


def test_the_header_is_not_a_link() -> None:
    # The chunker repeats the title and section in every chunk's header.
    text = "Source: blog_post\nTitle: KEP-1 explained\nDocument: web:/b/\nSection: KEP-1\n\nBody."

    assert links_kep(text, 1, "1-made-up") is False


def _candidate(
    chunk_id: int, canonical_id: str, valid_from: str, body: str, ordinal: int = 0
) -> LinkCandidate:
    source_type = "release_record" if canonical_id.startswith("changelog:") else "blog_post"
    return LinkCandidate(
        chunk_id=chunk_id,
        canonical_id=canonical_id,
        source_type=source_type,
        ordinal=ordinal,
        heading_path=["S"],
        text=_chunk(chunk_id, ordinal, ["S"], body).text,
        valid_from_date=_at(valid_from),
    )


LINK = "See https://github.com/kubernetes/enhancements/issues/1."
RELEASE_DATES = {22: date(2021, 8, 4), 23: date(2021, 12, 7)}
DECIDED = NewEvidence(
    step="decision",
    chunk_id=45,
    occurred_at=_at("2021-04-23T15:38:03Z"),
    found_by="merge_event",
    via_chunk_id=11,
)
PROPOSED = NewEvidence(
    step="proposal", chunk_id=21, occurred_at=_at("2021-03-12T14:32:43Z"), found_by="seed"
)


def test_implementation_is_the_earliest_linking_text_on_or_after_the_decision() -> None:
    candidates = [
        _candidate(50, "web:/blog/2021/03/01/early/", "2021-03-01T00:00:00Z", LINK),
        _candidate(51, "web:/blog/2021/05/01/no-link/", "2021-05-01T00:00:00Z", "KEP 1 is out."),
        _candidate(52, "web:/blog/2021/07/20/cadence/", "2021-07-20T00:00:00Z", "Intro.", 0),
        _candidate(53, "web:/blog/2021/07/20/cadence/", "2021-07-20T00:00:00Z", LINK, 7),
        _candidate(54, "web:/blog/2021/07/20/cadence/", "2021-07-22T17:37:52Z", LINK, 7),
    ]

    assert implementation_step(candidates, KEP, DECIDED, PROPOSED, RELEASE_DATES) == NewEvidence(
        step="implementation",
        chunk_id=53,  # the chunk holding the link, in the earliest version
        occurred_at=_at("2021-07-20T00:00:00Z"),
        found_by="linking_text",
        via_chunk_id=53,
    )


def test_a_changelog_is_dated_by_its_release_not_its_version() -> None:
    # CHANGELOG versions carry the lock refresh date (2026-09-30).
    candidates = [
        _candidate(60, "web:/blog/2021/09/01/later/", "2021-09-01T00:00:00Z", LINK),
        _candidate(61, "changelog:1.22", "2026-09-30T01:30:57Z", LINK),
    ]

    assert implementation_step(candidates, KEP, DECIDED, PROPOSED, RELEASE_DATES) == NewEvidence(
        step="implementation",
        chunk_id=61,
        occurred_at=_at("2021-08-04T00:00:00Z"),
        found_by="linking_text",
        via_chunk_id=61,
    )


def test_a_text_on_the_decision_s_day_counts() -> None:
    candidates = [_candidate(70, "web:/blog/2021/04/23/same-day/", "2021-04-23T00:00:00Z", LINK)]

    assert implementation_step(candidates, KEP, DECIDED, PROPOSED, RELEASE_DATES).chunk_id == 70


def test_with_the_decision_missing_the_proposal_s_date_is_the_bound() -> None:
    missing = NewEvidence(step="decision", missing_reason="no_link")
    candidates = [
        _candidate(80, "web:/blog/2021/03/01/before-the-proposal/", "2021-03-01T00:00:00Z", LINK),
        _candidate(81, "web:/blog/2021/03/20/after-the-proposal/", "2021-03-20T00:00:00Z", LINK),
    ]

    assert implementation_step(candidates, KEP, missing, PROPOSED, RELEASE_DATES).chunk_id == 81


def test_no_linking_text_on_or_after_the_decision_leaves_implementation_missing() -> None:
    candidates = [
        _candidate(90, "web:/blog/2021/03/01/early/", "2021-03-01T00:00:00Z", LINK),
        _candidate(91, "web:/blog/2021/05/01/no-link/", "2021-05-01T00:00:00Z", "KEP 1 is out."),
    ]

    assert implementation_step(
        candidates, KEP, DECIDED, PROPOSED, RELEASE_DATES
    ) == NewEvidence.model_validate({"step": "implementation", "missing_reason": "no_linking_text"})


# --- Rule 8: current docs ------------------------------------------------------------------------


def _near(chunk_id: int, content_hash: str, distance: float) -> NearText:
    return NearText(
        content_hash=content_hash * 64,
        distance=distance,
        chunk_id=chunk_id,
        canonical_id=f"web:/docs/{chunk_id}/",
        heading_path=["S"],
        valid_from_date=_at("2026-08-26T00:00:00Z"),
    )


def test_current_docs_is_the_nearest_text_ties_by_content_hash() -> None:
    nearest = [_near(100, "b", 0.201), _near(101, "c", 0.201), _near(102, "a", 0.219)]

    assert current_docs_step(nearest) == NewEvidence(
        step="current_docs",
        chunk_id=100,  # b before c at the same distance
        occurred_at=_at("2026-08-26T00:00:00Z"),
        found_by="similarity",
    )


def test_no_near_text_is_an_error_not_a_missing_step() -> None:
    with pytest.raises(ChainError, match="make embed"):
        current_docs_step([])


# --- Edge cases the plan leaves open (open calls) -----------------------------------------

COMMENTS_ONLY = _document(
    "gh:sig-release/discussions/12",
    [_chunk(35, 0, ["Comments", "@first · 2020-10-15"], "/lgtm")],
    metadata={"created_at": "2020-10-14T20:36:05Z", "merged_at": "2021-04-23T15:38:03Z"},
)


def test_a_stored_discussion_with_no_comment_is_missing_no_link() -> None:
    no_comment = _document("gh:sig-release/discussions/12", DISCUSSION.chunks[:2])

    assert discussion_step(FOUND, no_comment) == NewEvidence.model_validate(
        {"step": "discussion", "missing_reason": "no_link"}
    )


def test_a_discussion_whose_opening_post_has_no_text_falls_back_to_the_motivation() -> None:
    assert problem_step(FOUND, COMMENTS_ONLY, KEP).chunk_id == 23


def test_a_pr_with_no_approve_and_no_opening_post_text_cites_its_first_chunk() -> None:
    assert decision_step(PROPOSAL, COMMENTS_ONLY).chunk_id == 35
