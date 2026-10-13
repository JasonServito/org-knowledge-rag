"""S13-T1: the chain label check's reading of the gold chains file (the S13-R1 contract, "Pinned:
T4", for the format). Only `texts` entries are labels to check; `not_public`, `not_stored` and
`none` steps cite no stored text. The database half is in tests/integration/test_ingest_github.py.

S13-T4: the gold file's loader and its rejections, the matching per step kind, the same-UTC-day
check, the control's lookup table, the verdict and one chain scored end to end, on hand-computed
fixtures (no database: aliases resolve through a plain mapping).
"""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from orgknow.db.models import FoundBy, Hit, MissingReason, Step
from orgknow.eval.chains import (
    ChainLabel,
    Form,
    GoldChain,
    GoldStep,
    Pick,
    built_cell,
    control_cell,
    control_picks,
    control_step,
    label_line,
    load_chains_file,
    resolve_chains,
    right_same_day,
    score_chain,
    step_right,
    summary_lines,
    text_labels,
    verdict,
)
from orgknow.eval.golden import GoldenSetError, Label
from orgknow.provenance.chain import Chain, ChainStep

GOLD = """\
version: chains-test
chains:
  - seed: kep:1
    role: built-on
    question: "Why?"
    steps:
      - step: problem
        date: 2020-10-14
        texts:
          - document: "gh:sig-release/discussions/12"
            section: "Opening post · @erin · 2020-10-14"
          - {document: "kep:1", section: "KEP-1: X > Motivation"}
      - step: discussion
        not_public: "https://docs.google.com/document/d/x"
      - step: implementation
        date: 2021-08-04
        texts:
          - {document: "web:/blog/2021/07/20/x/"}
          - {document: "web:/blog/2021/08/04/y/", section: ""}
  - seed: kep:2
    role: held-out
    question: "Why not?"
    steps:
      - step: decision
        not_stored: "https://github.com/kubernetes/enhancements/pull/5140"
"""


def test_every_texts_entry_is_a_label_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "chains.yaml"
    path.write_text(GOLD, encoding="utf-8")

    assert text_labels(path) == [
        ChainLabel(
            seed="kep:1",
            step="problem",
            document="gh:sig-release/discussions/12",
            section="Opening post · @erin · 2020-10-14",
        ),
        ChainLabel(seed="kep:1", step="problem", document="kep:1", section="KEP-1: X > Motivation"),
        ChainLabel(seed="kep:1", step="implementation", document="web:/blog/2021/07/20/x/"),
        ChainLabel(
            seed="kep:1", step="implementation", document="web:/blog/2021/08/04/y/", section=""
        ),
    ]


def test_a_label_line_names_the_chain_step_document_and_section() -> None:
    label = ChainLabel(
        seed="kep:2572",
        step="decision",
        document="gh:enhancements/pull/2567",
        section="Comments > @dims · 2021-04-19",
    )

    assert label_line(label, 2) == (
        'kep:2572 decision  gh:enhancements/pull/2567  "Comments > @dims · 2021-04-19"  2 texts'
    )
    whole = ChainLabel(seed="kep:1", step="implementation", document="web:/blog/x/")
    assert label_line(whole, 0) == "kep:1 implementation  web:/blog/x/  (whole document)  0 texts"


# S13-T4: decision-chain completeness (the S13-R1 contract, "Pinned: T4"; ADR-012 D4). Every
# expected value below is hand-computed from the fixture beside it, never by the code under test.

STEPS_FILE = """\
version: chains-test
chains:
  - seed: kep:1
    role: held-out
    question: "Why?"
    steps:
{steps}
"""


def _write(tmp_path: Path, steps: str) -> Path:
    """A gold file with one chain, kep:1, whose steps are `steps` (YAML, indented 6 spaces)."""
    path = tmp_path / "chains.yaml"
    body = "\n".join("      " + line if line else line for line in steps.splitlines())
    path.write_text(STEPS_FILE.format(steps=body), encoding="utf-8")
    return path


def _errors(path: Path, ids: dict[str, str] | None = None) -> list[str]:
    """The loader's error lines for the file at `path`; with `ids`, resolution's too."""
    with pytest.raises(GoldenSetError) as caught:
        chains_file = load_chains_file(path)
        resolve_chains(chains_file, ids or {})
    return caught.value.errors


IDS = {name: name for name in ["gh:s/discussions/12", "gh:e/pull/7", "kep:1", "web:/docs/x/"]}


def test_a_valid_file_loads_and_resolves_each_form(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """\
- step: problem
  date: 2020-10-14
  texts:
    - {document: "gh:s/discussions/12", section: "Opening post · @erin · 2020-10-14"}
- step: discussion
  date: 2020-10-14
  texts:
    - {document: "gh:s/discussions/12", section: "Comments"}
- step: proposal
  not_public: "https://docs.google.com/document/d/x"
- step: decision
  none: "decided in a meeting with no record"
- step: implementation
  not_stored: "https://github.com/kubernetes/enhancements/pull/5140"
- step: current_docs
  texts:
    - {document: "kep-old:1", section: ""}
    - {document: "web:/docs/x/"}""",
    )

    chains = resolve_chains(load_chains_file(path), {**IDS, "kep-old:1": "kep:1"})

    assert chains == [
        GoldChain(
            seed="kep:1",
            role="held-out",
            question="Why?",
            steps=[
                GoldStep(
                    step="problem",
                    form="texts",
                    date=date(2020, 10, 14),
                    labels=[
                        Label(
                            canonical_id="gh:s/discussions/12",
                            section=["Opening post · @erin · 2020-10-14"],
                        )
                    ],
                ),
                GoldStep(
                    step="discussion",
                    form="texts",
                    date=date(2020, 10, 14),
                    labels=[Label(canonical_id="gh:s/discussions/12", section=["Comments"])],
                ),
                GoldStep(step="proposal", form="not_public", date=None, labels=[]),
                GoldStep(step="decision", form="none", date=None, labels=[]),
                GoldStep(step="implementation", form="not_stored", date=None, labels=[]),
                GoldStep(
                    step="current_docs",
                    form="texts",
                    date=None,  # current docs is undated
                    labels=[
                        Label(canonical_id="kep:1", section=[]),  # by its alias
                        Label(canonical_id="web:/docs/x/", section=None),
                    ],
                ),
            ],
        )
    ]


def test_the_loader_rejects_an_unknown_step(tmp_path: Path) -> None:
    path = _write(tmp_path, '- step: approval\n  none: "x"')

    [line] = _errors(path)
    assert line.startswith("chains.0.steps.0.step: Input should be 'problem'")


def test_the_loader_rejects_a_repeated_step(tmp_path: Path) -> None:
    path = _write(tmp_path, '- step: decision\n  none: "x"\n- step: decision\n  none: "y"')

    assert _errors(path) == ["chains.0: Value error, step decision is repeated"]


@pytest.mark.parametrize(
    ("step", "found"),
    [
        ("- step: decision\n  date: 2021-04-23", "found 0"),
        (
            '- step: decision\n  not_public: "u"\n  none: "x"',
            "found 2: not_public, none",
        ),
        (
            '- step: problem\n  date: 2020-10-14\n  texts: [{document: "kep:1"}]\n'
            '  not_stored: "u"',
            "found 2: texts, not_stored",
        ),
    ],
)
def test_the_loader_rejects_a_step_with_0_or_2_forms(tmp_path: Path, step: str, found: str) -> None:
    path = _write(tmp_path, step)

    assert _errors(path) == [
        "chains.0.steps.0: Value error, needs exactly one of texts, not_public, not_stored, none "
        f"({found})"
    ]


def test_the_loader_rejects_an_event_step_with_texts_and_no_date(tmp_path: Path) -> None:
    path = _write(tmp_path, '- step: proposal\n  texts: [{document: "kep:1"}]')

    assert _errors(path) == ["chains.0.steps.0: Value error, an event step with texts needs a date"]


def test_current_docs_needs_no_date(tmp_path: Path) -> None:
    path = _write(tmp_path, '- step: current_docs\n  texts: [{document: "web:/docs/x/"}]')

    [chain] = resolve_chains(load_chains_file(path), IDS)
    assert chain.steps[0].date is None


def test_the_loader_rejects_a_document_that_does_not_resolve(tmp_path: Path) -> None:
    path = _write(tmp_path, '- step: current_docs\n  texts: [{document: "web:/nope/"}]')

    assert _errors(path, IDS) == [
        "kep:1 current_docs: 'web:/nope/' is neither a stored canonical id nor an alias"
    ]


def _two_steps(first: str, second: str, document: str = "gh:s/discussions/12") -> str:
    """problem and discussion, each with one text of `document`; a section "-" is omitted (the
    whole document)."""

    def text(section: str) -> str:
        if section == "-":
            return f'{{document: "{document}"}}'
        return f'{{document: "{document}", section: "{section}"}}'

    return (
        f"- step: problem\n  date: 2020-10-14\n  texts: [{text(first)}]\n"
        f"- step: discussion\n  date: 2020-10-14\n  texts: [{text(second)}]"
    )


@pytest.mark.parametrize(
    ("first", "second", "shown"),
    [
        # A whole-document label next to any other label of the same document.
        ("-", "Comments", '(whole document) and "Comments"'),
        (
            "Opening post · @erin · 2020-10-14",
            "-",
            '"Opening post · @erin · 2020-10-14" and (whole document)',
        ),
        # One section a prefix of the other's, heading by heading; the same section twice.
        (
            "Comments",
            "Comments > @kim · 2020-10-15",
            '"Comments" and "Comments > @kim · 2020-10-15"',
        ),
        (
            "Comments > @kim · 2020-10-15",
            "Comments",
            '"Comments > @kim · 2020-10-15" and "Comments"',
        ),
        ("Comments", "Comments", '"Comments" and "Comments"'),
        # The intro twice.
        ("", "", '"" and ""'),
    ],
)
def test_the_loader_rejects_steps_sharing_a_document_by_nested_labels(
    tmp_path: Path, first: str, second: str, shown: str
) -> None:
    path = _write(tmp_path, _two_steps(first, second))

    assert _errors(path, IDS) == [
        f"kep:1: problem and discussion share gh:s/discussions/12 with nested labels: {shown}"
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Opening post · @erin · 2020-10-14", "Comments"),
        # The intro is nested in no section, and no section in it (ADR-007 D2).
        ("", "Comments"),
        # Compared heading by heading: "Traffic distribution" is no prefix of "... control".
        ("A > Traffic distribution", "A > Traffic distribution control"),
    ],
)
def test_steps_may_share_a_document_with_separate_sections(
    tmp_path: Path, first: str, second: str
) -> None:
    path = _write(tmp_path, _two_steps(first, second))

    assert len(resolve_chains(load_chains_file(path), IDS)) == 1


def test_the_shared_document_check_runs_after_resolving_aliases(tmp_path: Path) -> None:
    steps = (
        "- step: problem\n  date: 2020-10-14\n"
        '  texts: [{document: "kep:1", section: "Motivation"}]\n'
        '- step: proposal\n  date: 2021-03-12\n  texts: [{document: "kep-old:1"}]'
    )
    path = _write(tmp_path, steps)

    assert _errors(path, {**IDS, "kep-old:1": "kep:1"}) == [
        'kep:1: problem and proposal share kep:1 with nested labels: "Motivation" and '
        "(whole document)"
    ]


def _gold(step: Step, form: Form = "texts", *labels: Label, day: date | None = None) -> GoldStep:
    return GoldStep(step=step, form=form, date=day, labels=list(labels))


COMMENTS = Label(canonical_id="gh:s/discussions/12", section=["Comments"])
OPENING = Label(canonical_id="gh:s/discussions/12", section=["Opening post · @erin · 2020-10-14"])
DIMS = Label(canonical_id="gh:e/pull/7", section=["Comments", "@dims · 2021-04-19"])


def test_a_section_matches_the_headings_it_starts_with() -> None:
    gold = _gold("discussion", "texts", COMMENTS)

    assert step_right(gold, Pick(canonical_id="gh:s/discussions/12", heading_path=["Comments"]))
    assert step_right(
        gold,
        Pick(canonical_id="gh:s/discussions/12", heading_path=["Comments", "@kim · 2020-10-15"]),
    )
    # Another document with the same section; the right document, no text; heading by heading.
    assert not step_right(gold, Pick(canonical_id="gh:s/discussions/13", heading_path=["Comments"]))
    assert not step_right(gold, Pick())
    narrow = _gold(
        "decision", "texts", Label(canonical_id="gh:e/pull/7", section=["Comments", "@dims"])
    )
    assert not step_right(
        narrow, Pick(canonical_id="gh:e/pull/7", heading_path=["Comments", "@dims · 2021-04-19"])
    )


def test_a_shared_documents_steps_are_told_apart_by_section() -> None:
    # Discussion #12 holds both problem (its opening post) and discussion (its comments); PR #7
    # holds the decision in a comment, not in its opening post.
    opening_post = Pick(
        canonical_id="gh:s/discussions/12", heading_path=["Opening post · @erin · 2020-10-14"]
    )
    pr_opening = Pick(canonical_id="gh:e/pull/7", heading_path=["Opening post · @sam · 2021-03-12"])

    assert step_right(_gold("problem", "texts", OPENING), opening_post)
    assert not step_right(_gold("discussion", "texts", COMMENTS), opening_post)
    assert not step_right(_gold("decision", "texts", DIMS), pr_opening)


def test_a_whole_document_label_matches_any_chunk_of_it() -> None:
    gold = _gold("current_docs", "texts", Label(canonical_id="web:/docs/x/", section=None))

    assert step_right(gold, Pick(canonical_id="web:/docs/x/", heading_path=[]))
    assert step_right(gold, Pick(canonical_id="web:/docs/x/", heading_path=["A", "B"]))
    assert not step_right(gold, Pick(canonical_id="web:/docs/y/", heading_path=[]))


def test_the_intro_section_matches_only_the_text_before_the_first_heading() -> None:
    gold = _gold("implementation", "texts", Label(canonical_id="web:/blog/y/", section=[]))

    assert step_right(gold, Pick(canonical_id="web:/blog/y/", heading_path=[]))
    assert not step_right(
        gold, Pick(canonical_id="web:/blog/y/", heading_path=["Project Velocity"])
    )


def test_any_acceptable_text_counts() -> None:
    gold = _gold("problem", "texts", OPENING, Label(canonical_id="kep:1", section=["Motivation"]))

    assert step_right(gold, Pick(canonical_id="kep:1", heading_path=["Motivation", "Goals"]))


def test_not_public_counts_only_when_missing_as_not_public() -> None:
    gold = _gold("discussion", "not_public")

    assert step_right(gold, Pick(missing_reason="not_public"))
    assert not step_right(gold, Pick(missing_reason="no_link"))
    assert not step_right(gold, Pick())  # the control's empty step has no reason
    assert not step_right(gold, Pick(canonical_id="kep:1", heading_path=["Motivation"]))


def test_none_counts_when_the_step_is_missing_for_any_reason() -> None:
    gold = _gold("decision", "none")

    assert step_right(gold, Pick(missing_reason="no_link"))
    assert step_right(gold, Pick(missing_reason="not_merged"))
    assert step_right(gold, Pick())  # the control's empty step
    assert not step_right(gold, Pick(canonical_id="gh:e/pull/7", heading_path=["Comments"]))


def test_not_stored_never_counts() -> None:
    gold = _gold("decision", "not_stored")

    assert not step_right(gold, Pick(missing_reason="not_ingested"))
    assert not step_right(gold, Pick(missing_reason="no_link"))
    assert not step_right(gold, Pick())
    assert not step_right(gold, Pick(canonical_id="gh:e/pull/7", heading_path=["Comments"]))


def test_right_with_the_same_utc_day() -> None:
    gold = _gold("decision", "texts", DIMS, day=date(2021, 4, 23))
    cited = {"canonical_id": "gh:e/pull/7", "heading_path": ["Comments", "@dims · 2021-04-19"]}

    # The merge time, 15:38 UTC on the gold day.
    assert right_same_day(
        gold, Pick(**cited, occurred_at=datetime(2021, 4, 23, 15, 38, 3, tzinfo=UTC))
    )
    # 22:30 at UTC-5 on the 22nd is 03:30 UTC on the 23rd; 00:30 at UTC+2 on the 23rd is 22:30
    # UTC on the 22nd.
    minus_5 = timezone(timedelta(hours=-5))
    plus_2 = timezone(timedelta(hours=2))
    assert right_same_day(
        gold, Pick(**cited, occurred_at=datetime(2021, 4, 22, 22, 30, tzinfo=minus_5))
    )
    assert not right_same_day(
        gold, Pick(**cited, occurred_at=datetime(2021, 4, 23, 0, 30, tzinfo=plus_2))
    )
    # The right text a day early; the gold day with the wrong text.
    assert not right_same_day(gold, Pick(**cited, occurred_at=datetime(2021, 4, 22, tzinfo=UTC)))
    wrong = Pick(canonical_id="gh:e/pull/7", heading_path=["Opening post · @sam · 2021-03-12"])
    assert not right_same_day(
        gold, wrong.model_copy(update={"occurred_at": datetime(2021, 4, 23, tzinfo=UTC)})
    )


def _hit(canonical_id: str, source_type: str, heading_path: list[str], **changes: Any) -> Hit:
    hit = Hit(
        chunk_id=1,
        content_hash="a" * 64,
        distance=0.3,
        text="text",
        canonical_id=canonical_id,
        source_type=source_type,
        heading_path=heading_path,
        release_windows=[(30, None)],
        current=True,
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="website",
        snapshot_sha="0" * 40,
        source_path="x.md",
        metadata={},
    )
    return hit.model_copy(update=changes)


LATEST = 34


@pytest.mark.parametrize(
    ("hit", "expected"),
    [
        # A discussion's opening post, a heading inside it, its comments and replies.
        (
            _hit("gh:s/discussions/12", "discussion", ["Opening post · @erin · 2020-10-14"]),
            "problem",
        ),
        (
            _hit("gh:s/discussions/12", "discussion", ["Opening post · @erin · 2020-10-14", "Why"]),
            "problem",
        ),
        (
            _hit("gh:s/discussions/12", "discussion", ["Comments", "@kim · 2020-10-15"]),
            "discussion",
        ),
        (
            _hit("gh:s/discussions/12", "discussion", ["Comments", "@kim · 2020-10-15 · reply"]),
            "discussion",
        ),
        # Every post of an issue, its opening post included.
        (_hit("gh:e/issues/1", "discussion", ["Opening post · @erin · 2021-01-01"]), "discussion"),
        (_hit("gh:e/issues/1", "discussion", ["Comments", "@kim · 2021-01-02"]), "discussion"),
        # Every post of a PR.
        (_hit("gh:e/pull/7", "discussion", ["Opening post · @sam · 2021-03-12"]), "decision"),
        (
            _hit("gh:e/pull/7", "discussion", ["Comments", "@dims · 2021-04-19 · review"]),
            "decision",
        ),
        (_hit("kep:1", "kep", ["KEP-1", "Motivation"]), "proposal"),
        (_hit("web:/blog/2021/07/20/x/", "blog_post", []), "implementation"),
        # A CHANGELOG, even one not valid at the latest release.
        (
            _hit("changelog:1.22", "release_record", ["v1.22.0"], release_windows=[(22, 22)]),
            "implementation",
        ),
        # Current docs: valid at the latest release, by any version holding the text.
        (_hit("web:/docs/x/", "docs_page", ["A"]), "current_docs"),
        (_hit("gate:X", "feature_gate_reference", []), "current_docs"),
        (_hit("web:/releases/release/", "release_record", ["The Release Cycle"]), "current_docs"),
        (_hit("community:governance.md", "governance_doc", []), "current_docs"),
        (
            _hit("web:/docs/x/", "docs_page", ["A"], release_windows=[(20, 30), (33, 34)]),
            "current_docs",
        ),
        (_hit("web:/docs/x/", "docs_page", ["A"], release_windows=[(34, 34)]), "current_docs"),
        # Not valid at the latest release: no step.
        (_hit("web:/docs/x/", "docs_page", ["A"], release_windows=[(20, 33)]), None),
        (_hit("gate:X", "feature_gate_reference", [], release_windows=[(25, 30)]), None),
        (_hit("web:/releases/x/", "release_record", [], release_windows=[(20, 33)]), None),
        (_hit("community:governance.md", "governance_doc", [], release_windows=[(35, None)]), None),
    ],
)
def test_the_controls_lookup_table(hit: Hit, expected: Step | None) -> None:
    assert control_step(hit, LATEST) == expected


def test_the_best_ranked_hit_fills_each_step() -> None:
    hits = [
        _hit("kep:1", "kep", ["KEP-1", "Motivation"]),
        _hit("web:/docs/old/", "docs_page", ["A"], release_windows=[(20, 30)]),
        _hit("kep:1", "kep", ["KEP-1", "Summary"]),
        _hit("gh:s/discussions/12", "discussion", ["Comments", "@kim · 2020-10-15"]),
    ]

    assert control_picks(hits, LATEST) == {
        "proposal": Pick(canonical_id="kep:1", heading_path=["KEP-1", "Motivation"], rank=1),
        "discussion": Pick(
            canonical_id="gh:s/discussions/12",
            heading_path=["Comments", "@kim · 2020-10-15"],
            rank=4,
        ),
    }


@pytest.mark.parametrize(
    ("builder", "control", "line"),
    [
        (5, 3, "builder 5, control 3: beats"),
        (4, 3, "builder 4, control 3: beats"),
        (3, 3, "builder 3, control 3: does not beat"),
        (2, 3, "builder 2, control 3: does not beat"),
    ],
)
def test_the_verdict_needs_at_least_1_more_step_right(
    builder: int, control: int, line: str
) -> None:
    assert verdict(builder, control) == line


def _built(
    step: Step,
    canonical_id: str | None = None,
    heading_path: list[str] | None = None,
    occurred_at: datetime | None = None,
    missing_reason: MissingReason | None = None,
    found_by: FoundBy | None = None,
) -> ChainStep:
    return ChainStep(
        step=step,
        occurred_at=occurred_at,
        chunk_id=None if canonical_id is None else 1,
        canonical_id=canonical_id,
        heading_path=heading_path,
        source_type=None,
        source_url=None,
        tier=None,
        found_by=found_by,
        via_chunk_id=None,
        via_canonical_id=None,
        via_heading_path=None,
        missing_reason=missing_reason,
    )


def test_a_chain_is_scored_step_by_step_beside_the_control() -> None:
    gold = GoldChain(
        seed="kep:1",
        role="held-out",
        question="Why?",
        steps=[
            _gold(
                "problem",
                "texts",
                OPENING,
                Label(canonical_id="kep:1", section=["KEP-1", "Motivation"]),
                day=date(2020, 10, 14),
            ),
            _gold("discussion", "texts", COMMENTS, day=date(2020, 10, 14)),
            _gold(
                "proposal",
                "texts",
                Label(canonical_id="kep:1", section=["KEP-1", "Summary"]),
                day=date(2021, 3, 12),
            ),
            _gold("decision", "none"),
            _gold("implementation", "not_stored"),
            _gold("current_docs", "texts", Label(canonical_id="web:/docs/x/", section=None)),
        ],
    )
    built = Chain(
        seed="kep:1",
        title="X",
        built_at=datetime(2026, 10, 13, tzinfo=UTC),
        steps=[
            # right, same day
            _built(
                "problem",
                "gh:s/discussions/12",
                ["Opening post · @erin · 2020-10-14"],
                datetime(2020, 10, 14, tzinfo=UTC),
                found_by="template_field",
            ),
            # right, a day late
            _built(
                "discussion",
                "gh:s/discussions/12",
                ["Comments", "@kim · 2020-10-15"],
                datetime(2020, 10, 15, tzinfo=UTC),
                found_by="template_field",
            ),
            # right, same day
            _built(
                "proposal",
                "kep:1",
                ["KEP-1", "Summary"],
                datetime(2021, 3, 12, 9, tzinfo=UTC),
                found_by="seed",
            ),
            # right: none, missing for any reason
            _built("decision", missing_reason="no_link"),
            # wrong: not_stored never counts
            _built("implementation", missing_reason="no_linking_text"),
            # right (undated)
            _built(
                "current_docs",
                "web:/docs/x/",
                ["Overview"],
                datetime(2026, 1, 1, tzinfo=UTC),
                found_by="similarity",
            ),
        ],
    )
    hits = [
        _hit("kep:1", "kep", ["KEP-1", "Motivation"]),  # fills proposal: wrong section
        _hit("gh:s/discussions/12", "discussion", ["Comments", "@kim · 2020-10-15"]),  # right
        _hit("kep:1", "kep", ["KEP-1", "Summary"]),  # proposal already filled
        _hit("web:/docs/old/", "docs_page", ["A"], release_windows=[(20, 30)]),  # no step
        _hit("gh:s/discussions/12", "discussion", ["Opening post · @erin · 2020-10-14"]),  # right
        _hit("web:/blog/2021/x/", "blog_post", []),  # implementation: not_stored, wrong
    ]  # no PR hit: decision is empty, which none accepts; no current docs: wrong

    score = score_chain(gold, built, hits, LATEST)

    assert [
        (row.step, row.right, row.right_with_date, row.control_right) for row in score.rows
    ] == [
        ("problem", True, True, True),
        ("discussion", True, False, True),
        ("proposal", True, True, False),
        ("decision", True, None, True),
        ("implementation", False, None, False),
        ("current_docs", True, None, False),
    ]
    assert (score.right, score.steps) == (5, 6)
    assert (score.right_with_date, score.dated) == (2, 3)
    assert score.control_right == 3
    assert score.verdict == "builder 5, control 3: beats"
    assert summary_lines(score) == [
        "steps right: 5 of 6",
        "right with the same UTC day: 2 of 3",
        "control steps right: 3 of 6",
        "builder 5, control 3: beats",
    ]
    assert [hit.step for hit in score.control_hits] == [
        "proposal",
        "discussion",
        "proposal",
        None,
        "problem",
        "implementation",
    ]


def test_the_table_cells_name_the_citation_its_date_and_how_found() -> None:
    cited = Pick(
        canonical_id="gh:s/discussions/12",
        heading_path=["Comments", "@kim · 2020-10-15"],
        occurred_at=datetime(2020, 10, 15, 23, 30, tzinfo=timezone(timedelta(hours=-5))),
        found_by="template_field",
    )

    # The date is the UTC day: 23:30 at UTC-5 is 04:30 UTC the next day.
    assert built_cell(cited) == (
        "gh:s/discussions/12 \u203a Comments > @kim · 2020-10-15, 2020-10-16, template_field"
    )
    assert built_cell(Pick(missing_reason="no_link")) == "missing: no_link"
    assert control_cell(Pick(canonical_id="kep:1", heading_path=["KEP-1", "Summary"], rank=3)) == (
        "#3 kep:1 \u203a KEP-1 > Summary"
    )
    assert control_cell(Pick()) == "no hit"
    assert built_cell(
        Pick(canonical_id="web:/x/", heading_path=["a | b"], found_by="similarity")
    ) == ("web:/x/ \u203a a \\| b, undated, similarity")
