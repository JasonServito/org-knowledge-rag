"""The golden-set file: its format, loading, and the label rules (ADR-007 D1-D2).

A golden set goes through two stages, each with its own models:
- **As written** (`GoldenFile`, `QuestionEntry`, `LabelEntry`): `load_golden_file` reads and
  validates the YAML file, with no database.
- **Resolved** (`GoldenSet`, `Question`, `Label`): `check_labels` maps each label's document,
  a canonical_id or an alias, to its canonical_id, and counts the texts each label matches. The
  metrics use only this stage, so they compare ids only.
"""

import json
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, Self

import psycopg

# PyYAML ships no type hints, so safe_load returns Any: pydantic validates all of it below.
import yaml  # type: ignore[import-untyped]
from psycopg.rows import TupleRow
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import SectionText

# What the query router should detect (S09).
Mode = Literal["CURRENT", "HISTORY", "CHANGE", "WHY"]
# A label's section joins headings with this, as `orgknow ask` prints a heading path. 0 stored
# headings contain it (2026-10-08), so splitting on it is exact.
SEPARATOR = " > "
# "1.N" with no leading zeros, as `Release.version`.
RELEASE = r"^1\.(0|[1-9][0-9]*)$"
# The file's own shape: an unknown key is an error, and no value is converted (strict), so
# `answerable: "yes"` or `until: 1.23` (a YAML number) is an error, not a guess.
AS_WRITTEN = ConfigDict(extra="forbid", strict=True)


class GoldenSetError(ValueError):
    """A golden file that can't be used. Each error is one line, `<question id>: <field>:
    <problem>`; a problem outside any question has no question id."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


class ReleaseWindow(BaseModel):
    """The first and last release a question asks about, inclusive. At least one end."""

    model_config = AS_WRITTEN

    # `from` is a Python keyword, so the field is `from_` and the file's key is its alias.
    from_: str | None = Field(default=None, alias="from", pattern=RELEASE)
    until: str | None = Field(default=None, pattern=RELEASE)

    @model_validator(mode="after")
    def _has_an_end_and_is_in_order(self) -> Self:
        if self.from_ is None and self.until is None:
            raise ValueError("needs from, until or both")
        if self.from_ and self.until and _minor(self.from_) > _minor(self.until):
            raise ValueError(f"from {self.from_} is after until {self.until}")
        return self


class LabelEntry(BaseModel):
    """A label as written: a document (canonical_id or alias), and a section (`parse_section`)."""

    model_config = AS_WRITTEN

    document: str
    section: str | None = None


class _QuestionFields(BaseModel):
    """A question's fields in both stages: all but its labels (ADR-007 D1)."""

    id: str = Field(pattern=r"^q[0-9]{2,3}$")
    question: str = Field(min_length=1)
    mode: Mode | None = None  # required when answerable: checked by `_rule_errors`
    answerable: bool
    expected_answer: str
    release_window: ReleaseWindow | None = None
    smoke: bool  # in the 10-15 question smoke set


class QuestionEntry(_QuestionFields):
    """A question as written."""

    model_config = AS_WRITTEN

    labels: list[LabelEntry]


class GoldenFile(BaseModel):
    """A golden file as written, after `load_golden_file` validated it."""

    model_config = AS_WRITTEN

    version: str
    questions: list[QuestionEntry]


class Label(BaseModel):
    """A resolved label: one answer location. `section` is None for the whole document, [] for
    the intro (the text before the first heading), or the headings a matching heading path
    starts with."""

    canonical_id: str
    section: list[str] | None


class Question(_QuestionFields):
    """A question whose labels are resolved."""

    labels: list[Label]


class GoldenSet(BaseModel):
    """A validated golden file whose labels are resolved: what the metrics score against."""

    version: str
    questions: list[Question]


class LabelCount(BaseModel):
    """One line of the label check: a label and how many distinct chunk texts it matches."""

    question_id: str
    document: str  # as written in the file
    section: list[str] | None
    texts: int


def parse_section(section: str | None) -> list[str] | None:
    """A label's section as headings: omitted is None (the whole document), "" is [] (the
    intro), and "A > B" is ["A", "B"]."""
    if section is None:
        return None
    return section.split(SEPARATOR) if section else []


def section_matches(section: list[str] | None, heading_path: Sequence[str]) -> bool:
    """Whether a chunk with `heading_path` is in `section` (ADR-007 D2). None matches any path,
    [] only the empty path, and headings any path that starts with them, compared heading by
    heading: `Install` never matches `Installation`."""
    if section is None:
        return True
    if not section:
        return not heading_path
    return list(heading_path[: len(section)]) == section


def label_matches(label: Label, canonical_id: str, heading_path: Sequence[str]) -> bool:
    """Whether a hit, given its document's canonical_id and its heading path, matches `label`."""
    return canonical_id == label.canonical_id and section_matches(label.section, heading_path)


def format_section(section: list[str] | None) -> str:
    """A section as a label writes it: "(whole document)", or the quoted section ("" is the
    intro). The quoting is JSON's, which YAML also reads, so a printed section can be pasted
    into a label as it is, backticks, shortcodes and quotes included."""
    if section is None:
        return "(whole document)"
    return json.dumps(SEPARATOR.join(section), ensure_ascii=False)


def check_line(count: LabelCount) -> str:
    """`q06  web:/docs/...  ""  4 texts`: one line of the label check."""
    section = format_section(count.section)
    return f"{count.question_id}  {count.document}  {section}  {count.texts} texts"


def section_line(section: list[str], texts: int) -> str:
    """`"A > B"  3 texts`: one line of the section listing."""
    return f"{format_section(section)}  {texts} texts"


def load_golden_file(path: Path) -> GoldenFile:
    """Read and validate a golden file (ADR-007 D1-D2). Raises GoldenSetError listing every
    problem found, each naming its question id and field.

    The checks run in two passes: first the shape (pydantic: fields, types, unknown keys, the
    release window), then, on a well-shaped file, the rules across fields and questions.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GoldenSetError(["no such file"]) from None
    try:
        # safe_load builds only plain values (dicts, lists, strings...), never Python objects.
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise GoldenSetError([f"not valid YAML: {' '.join(str(error).split())}"]) from None
    try:
        golden_file = GoldenFile.model_validate(data)
    except ValidationError as error:
        lines = [_error_line(data, e["loc"], e["msg"]) for e in error.errors()]
        raise GoldenSetError(lines) from None

    errors = _duplicate_ids(golden_file.questions)
    for question in golden_file.questions:
        errors += [f"{question.id}: {error}" for error in _rule_errors(question)]
    if errors:
        raise GoldenSetError(errors)
    return golden_file


def resolve(golden_file: GoldenFile, ids: Mapping[str, str]) -> GoldenSet:
    """The golden set with each label's document replaced by its canonical_id. `ids` maps a
    name (canonical_id or alias) to its canonical_id; a name it lacks is kept as written, and
    matches nothing. Raises GoldenSetError if two labels of a question overlap once resolved."""
    questions = []
    errors = []
    for entry in golden_file.questions:
        labels = [
            Label(
                canonical_id=ids.get(label.document, label.document),
                section=parse_section(label.section),
            )
            for label in entry.labels
        ]
        overlaps = _overlap_errors([(label.canonical_id, label.section) for label in labels])
        errors += [f"{entry.id}: {error} after resolving aliases" for error in overlaps]
        questions.append(Question.model_validate({**dict(entry), "labels": labels}))
    if errors:
        raise GoldenSetError(errors)
    return GoldenSet(version=golden_file.version, questions=questions)


def check_labels(
    conn: psycopg.Connection[TupleRow], golden_file: GoldenFile
) -> tuple[GoldenSet, list[LabelCount]]:
    """Resolve the labels against the database, and count the distinct chunk texts each label
    matches (in file order). A count of 0 means the label's document or section isn't stored.
    Raises GoldenSetError if two labels of a question overlap once aliases are resolved."""
    names = sorted({label.document for q in golden_file.questions for label in q.labels})
    golden = resolve(golden_file, canonical_ids(conn, names))
    documents = {label.canonical_id for q in golden.questions for label in q.labels}
    texts = {canonical_id: document_texts(conn, canonical_id) for canonical_id in documents}

    counts = []
    for entry, question in zip(golden_file.questions, golden.questions, strict=True):
        for written, label in zip(entry.labels, question.labels, strict=True):
            matched = {
                text.content_hash
                for text in texts[label.canonical_id]
                if section_matches(label.section, text.heading_path)
            }
            counts.append(
                LabelCount(
                    question_id=question.id,
                    document=written.document,
                    section=label.section,
                    texts=len(matched),
                )
            )
    return golden, counts


def list_sections(texts: Sequence[SectionText]) -> list[tuple[list[str], int]]:
    """Each distinct heading path in `texts`, with its number of distinct texts, in the order the
    paths first appear."""
    hashes_by_path: dict[tuple[str, ...], set[str]] = {}  # a dict keeps insertion order
    for text in texts:
        hashes_by_path.setdefault(tuple(text.heading_path), set()).add(text.content_hash)
    return [(list(path), len(hashes)) for path, hashes in hashes_by_path.items()]


def _minor(release: str) -> int:
    """24 for "1.24"."""
    return int(release.removeprefix("1."))


def _error_line(data: Any, loc: tuple[int | str, ...], message: str) -> str:
    """One pydantic error as `<question>: <field>: <problem>`. Pydantic locates a question by its
    position in the list; the line names it by its id."""
    parts = []
    if len(loc) > 1 and loc[0] == "questions" and isinstance(loc[1], int):
        parts.append(_question_name(data["questions"], loc[1]))
        loc = loc[2:]
    if loc:
        parts.append(".".join(str(part) for part in loc))
    return ": ".join([*parts, message])


def _question_name(questions: list[Any], index: int) -> str:
    """A question's id as written, or its position (from 1) when it has none."""
    question = questions[index]
    question_id = question.get("id") if isinstance(question, dict) else None
    return question_id if isinstance(question_id, str) else f"question {index + 1}"


def _duplicate_ids(questions: Sequence[QuestionEntry]) -> list[str]:
    """An error for each id used by more than one question."""
    positions: dict[str, list[int]] = {}
    for position, question in enumerate(questions, start=1):
        positions.setdefault(question.id, []).append(position)
    return [
        f"{question_id}: id: duplicate (questions {' and '.join(map(str, found))})"
        for question_id, found in positions.items()
        if len(found) > 1
    ]


def _rule_errors(question: QuestionEntry) -> list[str]:
    """The question's rules across fields, as `<field>: <problem>` lines."""
    errors = []
    if question.answerable and question.mode is None:
        errors.append("mode: required when answerable is true")
    if question.answerable and not question.labels:
        errors.append("labels: required when answerable is true")
    if not question.answerable and question.labels:
        errors.append("labels: must be empty when answerable is false")
    labels = [(label.document, parse_section(label.section)) for label in question.labels]
    return errors + _overlap_errors(labels)


def _overlap_errors(labels: Sequence[tuple[str, list[str] | None]]) -> list[str]:
    """Pairs of one question's (document, section) labels that would credit one answer location
    twice: the same label twice, or one nested in another of the same document."""
    errors = []
    for (document_a, a), (document_b, b) in combinations(labels, 2):
        if document_a != document_b:
            continue
        if a == b:
            errors.append(f"labels: {_show(document_a, a)} is listed twice")
        elif _covers(a, b):
            errors.append(f"labels: {_show(document_b, b)} is nested in {_show(document_a, a)}")
        elif _covers(b, a):
            errors.append(f"labels: {_show(document_a, a)} is nested in {_show(document_b, b)}")
    return errors


def _covers(outer: list[str] | None, inner: list[str] | None) -> bool:
    """Whether every heading path section `inner` matches is also matched by section `outer`.
    Every path `inner` matches starts with `inner`, so that holds exactly when `outer` matches
    `inner` as a heading path. So the whole document covers every section, and the intro none
    but itself."""
    return inner is not None and section_matches(outer, inner)


def _show(document: str, section: list[str] | None) -> str:
    return f"{document} {format_section(section)}"
