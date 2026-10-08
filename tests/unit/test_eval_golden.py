"""The golden-set file format and its pure rules (S06-T1, ADR-007 D1-D2).

Every bad file below is hand-written and breaks one rule; its expected error lines are written by
hand from the rule (question id, then the field, then the problem).
"""

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from orgknow.db.models import SectionText
from orgknow.eval.__main__ import main
from orgknow.eval.golden import (
    GoldenSetError,
    Label,
    LabelCount,
    check_line,
    format_section,
    label_matches,
    list_sections,
    load_golden_file,
    parse_section,
    resolve,
    section_line,
    section_matches,
)
from orgknow.settings import Settings

DEMO = Path(__file__).parents[1] / "fixtures" / "eval" / "demo.yaml"
HEADER = "version: v0\nquestions:\n"


def _load(tmp_path: Path, text: str) -> list[str]:
    """Load `text` as a golden file and return its error lines ([] if it is valid)."""
    path = tmp_path / "golden.yaml"
    path.write_text(text, encoding="utf-8")
    try:
        load_golden_file(path)
    except GoldenSetError as error:
        return error.errors
    return []


# --- Loading a valid file -------------------------------------------------------------------


def test_loads_the_demo_file() -> None:
    golden_file = load_golden_file(DEMO)

    # Read by hand from tests/fixtures/eval/demo.yaml.
    assert golden_file.version == "demo"
    assert [q.id for q in golden_file.questions] == ["q06", "q13", "q10"]
    q06, q13, q10 = golden_file.questions
    assert (q06.mode, q06.answerable, q06.smoke) == ("CURRENT", True, True)
    assert q06.release_window is None
    assert q06.question == "What enforces pod security standards in-tree?"
    assert q06.expected_answer == "PodSecurity admission, GA since v1.25."
    assert [(label.document, label.section) for label in q13.labels] == [
        ("changelog:1.30", "v1.30.0 > Changes by Kind > Other (Cleanup or Flake)"),
        ("gate:LegacyServiceAccountTokenCleanUp", None),
    ]
    assert (q10.mode, q10.answerable, q10.labels) == (None, False, [])


def test_resolving_parses_each_section() -> None:
    # Every document is its own canonical_id here: no aliases.
    names = {
        "web:/docs/concepts/security/pod-security-admission/",
        "web:/blog/2022/08/25/pod-security-admission-stable/",
        "changelog:1.30",
        "gate:LegacyServiceAccountTokenCleanUp",
    }

    golden = resolve(load_golden_file(DEMO), {name: name for name in names})

    q06, q13, q10 = golden.questions
    assert q06.labels == [
        Label(canonical_id="web:/docs/concepts/security/pod-security-admission/", section=[]),
        Label(canonical_id="web:/blog/2022/08/25/pod-security-admission-stable/", section=[]),
    ]
    assert q13.labels == [
        Label(
            canonical_id="changelog:1.30",
            section=["v1.30.0", "Changes by Kind", "Other (Cleanup or Flake)"],
        ),
        Label(canonical_id="gate:LegacyServiceAccountTokenCleanUp", section=None),
    ]
    assert q10.labels == []
    # Every other field is carried over as written.
    assert (q13.id, q13.mode, q13.answerable, q13.smoke) == ("q13", "CHANGE", True, True)


def test_valid_label_combinations_load(tmp_path: Path) -> None:
    # The intro is nested in no section; one section in two documents is two labels; an
    # unanswerable question needs no mode; one end of a release window is enough.
    text = HEADER + (
        "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    release_window: {until: '1.23'}\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - {document: 'web:/a/', section: ''}\n"
        "      - {document: 'web:/a/', section: Install}\n"
        "      - {document: 'web:/b/', section: Install}\n"
        "  - id: q102\n"
        "    question: What did the private doc say?\n"
        "    answerable: false\n"
        "    expected_answer: Insufficient evidence.\n"
        "    smoke: true\n"
        "    labels: []\n"
    )

    assert _load(tmp_path, text) == []


# --- One hand-written file per rule ---------------------------------------------------------

# A valid question, for the rules about the file around it.
GOOD = (
    "  - id: q01\n"
    "    question: How do I install it?\n"
    "    mode: CURRENT\n"
    "    answerable: true\n"
    "    expected_answer: Like this.\n"
    "    smoke: false\n"
    "    labels:\n"
    "      - document: web:/a/\n"
)

BAD_FILES = {
    "missing field": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: expected_answer: Field required"],
    ),
    "missing id": (
        HEADER + "  - question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["question 1: id: Field required"],
    ),
    "unknown question key": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    tags: [current]\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: tags: Extra inputs are not permitted"],
    ),
    "unknown label key": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n"
        "        sections: Install\n",
        ["q01: labels.0.sections: Extra inputs are not permitted"],
    ),
    "unknown top-level key": (
        HEADER + GOOD + "as_of: '1.30'\n",
        ["as_of: Extra inputs are not permitted"],
    ),
    "duplicate id": (
        HEADER + GOOD + GOOD,
        ["q01: id: duplicate (questions 1 and 2)"],
    ),
    "mode missing when answerable": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: mode: required when answerable is true"],
    ),
    "labels on an unanswerable question": (
        HEADER + "  - id: q01\n"
        "    question: What did the private doc say?\n"
        "    answerable: false\n"
        "    expected_answer: Insufficient evidence.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: labels: must be empty when answerable is false"],
    ),
    "no labels on an answerable question": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels: []\n",
        ["q01: labels: required when answerable is true"],
    ),
    "release window from after until": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: HISTORY\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    release_window: {from: '1.25', until: '1.23'}\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: release_window: Value error, from 1.25 is after until 1.23"],
    ),
    "release window with no key": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: HISTORY\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    release_window: {}\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        ["q01: release_window: Value error, needs from, until or both"],
    ),
    "release window not 1.N": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: HISTORY\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    release_window: {from: v1.25}\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n",
        [r"q01: release_window.from: String should match pattern '^1\.(0|[1-9][0-9]*)$'"],
    ),
    "nested labels": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n"
        "        section: Install\n"
        "      - document: web:/a/\n"
        "        section: Install > Linux\n",
        ['q01: labels: web:/a/ "Install > Linux" is nested in web:/a/ "Install"'],
    ),
    "whole document next to a section": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n"
        "        section: Install\n"
        "      - document: web:/a/\n",
        ['q01: labels: web:/a/ "Install" is nested in web:/a/ (whole document)'],
    ),
    "the same label twice": (
        HEADER + "  - id: q01\n"
        "    question: How do I install it?\n"
        "    mode: CURRENT\n"
        "    answerable: true\n"
        "    expected_answer: Like this.\n"
        "    smoke: false\n"
        "    labels:\n"
        "      - document: web:/a/\n"
        "        section: ''\n"
        "      - document: web:/a/\n"
        "        section: ''\n",
        ['q01: labels: web:/a/ "" is listed twice'],
    ),
}


@pytest.mark.parametrize(("text", "expected"), BAD_FILES.values(), ids=BAD_FILES.keys())
def test_a_malformed_file_fails_with_the_question_id_and_field(
    tmp_path: Path, text: str, expected: list[str]
) -> None:
    assert _load(tmp_path, text) == expected


def test_a_file_that_is_not_yaml_is_one_error(tmp_path: Path) -> None:
    [line] = _load(tmp_path, "version: v0\nquestions: [\n")

    assert line.startswith("not valid YAML: ")


def test_a_missing_file_is_one_error(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError) as error:
        load_golden_file(tmp_path / "missing.yaml")

    assert error.value.errors == ["no such file"]


def test_check_with_a_missing_file_prints_one_line_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "missing.yaml"
    # The file is read before any connection, so this URL is never used.
    settings = Settings(_env_file=None, database_url="postgresql://unused", eval_golden_path=path)

    assert main(["check"], settings) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {path}: no such file\n"


def test_the_golden_path_defaults_to_v0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    monkeypatch.delenv("EVAL_GOLDEN_PATH", raising=False)

    # The run contract's default (S06-R1, "Claude's calls", Settings).
    assert Settings(_env_file=None).eval_golden_path == Path("eval/golden_set/v0.yaml")


# --- Sections (ADR-007 D2) ------------------------------------------------------------------


def test_a_section_splits_into_headings_on_the_separator_only() -> None:
    assert parse_section("A > B") == ["A", "B"]
    assert parse_section("") == []
    assert parse_section(None) is None
    # `->` is part of a heading (432 chunks hold it); only " > " separates headings.
    assert parse_section("Beta -> GA > Test plan") == ["Beta -> GA", "Test plan"]


def test_a_section_matches_whole_headings_only() -> None:
    assert section_matches(["Install"], ["Install"])
    assert section_matches(["Install"], ["Install", "Linux"])
    # Heading by heading, never as raw strings: "Install" is not a prefix of "Installation".
    assert not section_matches(["Install"], ["Installation"])
    assert not section_matches(["Install", "Linux"], ["Install"])


def test_the_intro_matches_only_an_empty_heading_path() -> None:
    assert section_matches([], [])
    assert not section_matches([], ["Install"])


def test_a_whole_document_label_matches_any_heading_path() -> None:
    assert section_matches(None, [])
    assert section_matches(None, ["Install", "Linux"])


def test_a_label_matches_only_its_own_document() -> None:
    label = Label(canonical_id="web:/a/", section=["Install"])

    assert label_matches(label, "web:/a/", ["Install", "Linux"])
    assert not label_matches(label, "web:/b/", ["Install", "Linux"])


# --- Output lines (the run contract's pinned formats) ----------------------------------------


def test_sections_print_as_labels_write_them() -> None:
    assert format_section(None) == "(whole document)"
    assert format_section([]) == '""'
    assert format_section(["v1.30.0", "Changes by Kind"]) == '"v1.30.0 > Changes by Kind"'


def test_a_printed_section_pastes_back_as_the_same_yaml_string() -> None:
    # Backticks, a shortcode and quotes, as real headings hold them.
    heading = 'Use `kubectl` {{< glossary_tooltip text="Pod" >}}'

    printed = format_section(["Tasks", heading])

    assert printed == '"Tasks > Use `kubectl` {{< glossary_tooltip text=\\"Pod\\" >}}"'
    assert yaml.safe_load(f"section: {printed}") == {"section": f"Tasks > {heading}"}


def test_check_lines_follow_the_pinned_format() -> None:
    intro = LabelCount(
        question_id="q06",
        document="web:/docs/concepts/security/pod-security-admission/",
        section=[],
        texts=4,
    )
    whole = LabelCount(
        question_id="q13", document="gate:LegacyServiceAccountTokenCleanUp", section=None, texts=3
    )

    # The run contract's two example lines, copied.
    assert check_line(intro) == (
        'q06  web:/docs/concepts/security/pod-security-admission/  ""  4 texts'
    )
    assert check_line(whole) == (
        "q13  gate:LegacyServiceAccountTokenCleanUp  (whole document)  3 texts"
    )


def test_sections_are_listed_once_in_order_of_first_appearance_with_distinct_texts() -> None:
    # As `document_texts` returns them: distinct (heading path, text) pairs, first appearance
    # first.
    texts = [
        SectionText(heading_path=[], content_hash="h1"),
        SectionText(heading_path=["Install"], content_hash="h2"),
        SectionText(heading_path=[], content_hash="h3"),
        SectionText(heading_path=["Usage"], content_hash="h4"),
        SectionText(heading_path=["Install"], content_hash="h5"),
    ]

    sections = list_sections(texts)

    assert sections == [([], 2), (["Install"], 2), (["Usage"], 1)]
    assert [section_line(path, count) for path, count in sections] == [
        '""  2 texts',
        '"Install"  2 texts',
        '"Usage"  1 texts',
    ]
