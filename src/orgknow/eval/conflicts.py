"""The conflict set (S10-T6, ADR-007 D4): its file format and loader, the side check, and the
conflict metrics (precision, recall and AC4), as the S10-R2 run contract pins them.

The conflict set is the answer key of every disagreement among each eval question's top-K hits,
written before the runs. Like the golden set (`golden.py`), it goes through two stages:
- **As written** (`ConflictFile`, `NewQuestion`, `ConflictEntry`): `load_conflict_file` reads
  and validates the YAML file against the golden question ids, with no database.
- **Resolved** (`ConflictSet`, `LabeledConflict`): `check_sides` maps each side entry's document
  to its canonical_id and counts the texts each entry matches. The metrics use only this stage.

A side is a list of `{document, section?}` entries, "any of", each matched by ADR-007 D2's rule
(`golden.label_matches`). The metrics are pure: each question's id, top-K hits and flagged
conflicts in, counts out.
"""

from collections.abc import Collection, Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

import psycopg

# PyYAML ships no type hints, so safe_load returns Any: pydantic validates all of it below.
import yaml  # type: ignore[import-untyped]
from psycopg.rows import TupleRow
from pydantic import BaseModel, Field, ValidationError

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.eval.golden import (
    AS_WRITTEN,
    GoldenSetError,
    Label,
    LabelEntry,
    _overlap_errors,
    format_section,
    label_matches,
    parse_section,
    section_matches,
)
from orgknow.generation.conflicts import Conflict

# A conflict's kind in the set (ADR-007 D4): the two rule kinds, each matched only by the rule
# that finds it, and `texts`, two texts that disagree, matched only by a model-found pair.
SetKind = Literal["claim_mismatch", "history_date", "texts"]
RULE_KINDS = ("claim_mismatch", "history_date")
SEEDS = 4  # AC4's seed cases, fixed in the S10-R2 sitting


class ConflictSetError(GoldenSetError):
    """A conflict file that can't be used. Each error is one line, `<conflict or question id>:
    <field>: <problem>`; a problem outside any conflict or question has no id."""


class NewQuestion(BaseModel):
    """A question the conflict set adds to the pool; it runs in full runs only."""

    model_config = AS_WRITTEN

    id: str = Field(pattern=r"^c[0-9]{2,3}$")  # never a golden id, which starts with q
    question: str = Field(min_length=1)


class ConflictEntry(BaseModel):
    """A conflict as written."""

    model_config = AS_WRITTEN

    id: str = Field(pattern=r"^k[0-9]{2,3}$")
    question: str  # a golden question's id, or one of the file's new questions'
    kind: SetKind
    seed: bool = False
    note: str = Field(min_length=1)  # quotes both values
    first: list[LabelEntry] = Field(min_length=1)
    second: Annotated[list[LabelEntry], Field(min_length=1)] | None = None  # texts only


class ConflictFile(BaseModel):
    """A conflict file as written, after `load_conflict_file` validated it."""

    model_config = AS_WRITTEN

    version: str
    questions: list[NewQuestion]  # new questions only; golden ones are referenced by id
    conflicts: list[ConflictEntry]


class LabeledConflict(BaseModel):
    """A conflict whose side entries are resolved to canonical_ids (`golden.Label`)."""

    id: str
    question: str
    kind: SetKind
    seed: bool
    first: list[Label]
    second: list[Label] | None  # None for a rule kind


class ConflictSet(BaseModel):
    """A validated conflict file whose sides are resolved: what the metrics score against."""

    version: str
    questions: list[NewQuestion]
    conflicts: list[LabeledConflict]


class SideCount(BaseModel):
    """One side entry and how many distinct chunk texts it matches."""

    conflict_id: str
    question_id: str
    side: str  # "first" or "second"
    document: str  # as written in the file
    section: list[str] | None
    texts: int


class SeedResult(BaseModel):
    """AC4 for one seed whose question ran: whether search retrieved both its sides
    (`retrieved`: reachable) and whether a flagged conflict matched it (`surfaced`)."""

    conflict_id: str
    question_id: str
    retrieved: bool
    surfaced: bool


class ConflictCounts(BaseModel):
    """The conflict metrics over the questions of one run, each as (matched, total)."""

    precision: tuple[int, int]  # flags matching a conflict / flags
    precision_rule: tuple[int, int]
    precision_model: tuple[int, int]
    recall: tuple[int, int]  # reachable conflicts matched / reachable conflicts
    recall_rule: tuple[int, int]
    recall_texts: tuple[int, int]
    unreachable: list[LabeledConflict]  # conflicts whose question ran, not reachable
    seeds: list[SeedResult]  # seeds whose question ran, in file order


def load_conflict_file(path: Path, golden_ids: Collection[str]) -> ConflictFile:
    """Read and validate a conflict file (ADR-007 D4; the S10-R2 contract's format) against the
    golden question ids. Raises ConflictSetError listing every problem found, each naming its
    conflict or question id and field.

    As in `golden.load_golden_file`, the shape is checked first (pydantic: fields, types, unknown
    keys, id patterns, empty sides), then, on a well-shaped file, the rules across fields and
    conflicts.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConflictSetError(["no such file"]) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConflictSetError([f"not valid YAML: {' '.join(str(error).split())}"]) from None
    try:
        conflict_file = ConflictFile.model_validate(data)
    except ValidationError as error:
        lines = [_error_line(data, e["loc"], e["msg"]) for e in error.errors()]
        raise ConflictSetError(lines) from None

    question_ids = {*golden_ids, *(question.id for question in conflict_file.questions)}
    errors = _duplicate_ids("questions", [question.id for question in conflict_file.questions])
    errors += _duplicate_ids("conflicts", [conflict.id for conflict in conflict_file.conflicts])
    first_with: dict[tuple[str, str, frozenset[frozenset[tuple[str, str | None]]]], str] = {}
    for conflict in conflict_file.conflicts:
        errors += [f"{conflict.id}: {error}" for error in _rule_errors(conflict, question_ids)]
        key = (conflict.question, conflict.kind, _sides(conflict))
        if key in first_with:
            errors.append(
                f"{conflict.id}: duplicate of {first_with[key]} (same question, kind and sides)"
            )
        first_with.setdefault(key, conflict.id)
    seeds = sum(conflict.seed for conflict in conflict_file.conflicts)
    if seeds != SEEDS:
        errors.append(f"seed: {seeds} conflicts are seeds; exactly {SEEDS} must be")
    if errors:
        raise ConflictSetError(errors)
    return conflict_file


def resolve_sides(conflict_file: ConflictFile, ids: Mapping[str, str]) -> ConflictSet:
    """The conflict set with each entry's document replaced by its canonical_id and its section
    parsed. `ids` maps a name (canonical_id or alias) to its canonical_id; a name it lacks is
    kept as written, and matches nothing."""

    def resolved(entries: Sequence[LabelEntry]) -> list[Label]:
        return [
            Label(
                canonical_id=ids.get(entry.document, entry.document),
                section=parse_section(entry.section),
            )
            for entry in entries
        ]

    conflicts = [
        LabeledConflict(
            id=conflict.id,
            question=conflict.question,
            kind=conflict.kind,
            seed=conflict.seed,
            first=resolved(conflict.first),
            second=None if conflict.second is None else resolved(conflict.second),
        )
        for conflict in conflict_file.conflicts
    ]
    return ConflictSet(
        version=conflict_file.version, questions=conflict_file.questions, conflicts=conflicts
    )


def check_sides(
    conn: psycopg.Connection[TupleRow], conflict_file: ConflictFile
) -> tuple[ConflictSet, list[SideCount]]:
    """Resolve the side entries against the database, and count the distinct chunk texts each
    entry matches (in file order), as `golden.check_labels` counts labels. A count of 0 means
    the entry's document or section isn't stored."""
    entries = [
        (conflict, side, entry)
        for conflict in conflict_file.conflicts
        for side, side_entries in (("first", conflict.first), ("second", conflict.second or []))
        for entry in side_entries
    ]
    ids = canonical_ids(conn, sorted({entry.document for _, _, entry in entries}))
    documents = {ids.get(entry.document, entry.document) for _, _, entry in entries}
    texts = {canonical_id: document_texts(conn, canonical_id) for canonical_id in documents}

    counts = []
    for conflict, side, entry in entries:
        section = parse_section(entry.section)
        stored = texts[ids.get(entry.document, entry.document)]
        matched = {t.content_hash for t in stored if section_matches(section, t.heading_path)}
        counts.append(
            SideCount(
                conflict_id=conflict.id,
                question_id=conflict.question,
                side=side,
                document=entry.document,
                section=section,
                texts=len(matched),
            )
        )
    return resolve_sides(conflict_file, ids), counts


def side_line(count: SideCount) -> str:
    """`k03  q08  first  kep:2579  "KEP-2579: ... > Implementation History"  2 texts`."""
    section = format_section(count.section)
    return (
        f"{count.conflict_id}  {count.question_id}  {count.side}  {count.document}  {section}  "
        f"{count.texts} texts"
    )


# --- Matching and the metrics (S10-R2, "Pinned: matching and metrics") ---------------------------


class LocatedHit(Protocol):
    """The 3 fields matching reads from a hit: both a `Hit` and a results file's hit have them."""

    @property
    def chunk_id(self) -> int: ...

    @property
    def canonical_id(self) -> str: ...

    @property
    def heading_path(self) -> Sequence[str]: ...


# One question as the metrics read it: its id, its top-K hits, and the conflicts flagged on it
# (a row's `conflicts`, found by the rules and the model).
ScoredQuestion = tuple[str, Sequence[LocatedHit], Sequence[Conflict]]


def reachable(conflict: LabeledConflict, hits: Sequence[LocatedHit]) -> bool:
    """Whether search retrieved the conflict among its question's top-K `hits`: a rule kind
    when a hit matches its side; `texts` when two different hits match its sides, one each."""
    if conflict.second is None:
        return any(_on_side(conflict.first, hit) for hit in hits)
    return any(_on_both_sides(conflict, a, b) for a, b in combinations(hits, 2))


def matches(flag: Conflict, conflict: LabeledConflict, hits: Sequence[LocatedHit]) -> bool:
    """Whether a conflict flagged on the conflict's question matches it (ADR-007 D4 (a)):
    - a rule kind: the flag was found by the rule of that kind, and one of its chunks matches
      the side
    - `texts`: the flag was found by the model, and its two different chunks match the sides,
      one each, in either order

    Each chunk's document and heading path come from `hits`, by chunk id."""
    by_id = {hit.chunk_id: hit for hit in hits}
    chunks = [by_id[chunk_id] for chunk_id in flag.chunk_ids if chunk_id in by_id]
    if conflict.second is None:
        return (
            flag.found_by == "rule"
            and flag.kind == conflict.kind
            and any(_on_side(conflict.first, chunk) for chunk in chunks)
        )
    if flag.found_by != "model" or len(chunks) != 2:
        return False
    a, b = chunks
    return a.chunk_id != b.chunk_id and _on_both_sides(conflict, a, b)


def score_conflicts(
    conflicts: Sequence[LabeledConflict], questions: Sequence[ScoredQuestion]
) -> ConflictCounts:
    """The conflict metrics over the `questions` a run ran (golden and new):
    - precision: the flags matching at least one conflict of their question ÷ the flags, over
      every question, split by who found them
    - recall: the reachable conflicts matched by at least one flag ÷ the reachable conflicts,
      split into the rule kinds and `texts`
    - each seed: retrieved (reachable) and surfaced (matched)

    A conflict whose question didn't run (a smoke run) is in no count. An unreachable conflict
    is listed, never in recall: search, not conflict detection, missed it.
    """
    on_question: dict[str, list[LabeledConflict]] = {}
    for conflict in conflicts:
        on_question.setdefault(conflict.question, []).append(conflict)
    flags = [
        (flag, any(matches(flag, conflict, hits) for conflict in on_question.get(qid, [])))
        for qid, hits, found in questions
        for flag in found
    ]
    ran = {qid: (hits, found) for qid, hits, found in questions}
    results = []  # (conflict, reachable, matched), for each conflict whose question ran
    for conflict in conflicts:
        if conflict.question not in ran:
            continue
        hits, found = ran[conflict.question]
        matched = any(matches(flag, conflict, hits) for flag in found)
        results.append((conflict, reachable(conflict, hits), matched))
    reached = [(c, m) for c, r, m in results if r]  # the reachable conflicts, and if matched
    return ConflictCounts(
        precision=_ratio([m for _, m in flags]),
        precision_rule=_ratio([m for flag, m in flags if flag.found_by == "rule"]),
        precision_model=_ratio([m for flag, m in flags if flag.found_by == "model"]),
        recall=_ratio([m for _, m in reached]),
        recall_rule=_ratio([m for c, m in reached if c.kind in RULE_KINDS]),
        recall_texts=_ratio([m for c, m in reached if c.kind == "texts"]),
        unreachable=[c for c, r, _ in results if not r],
        seeds=[
            SeedResult(conflict_id=c.id, question_id=c.question, retrieved=r, surfaced=m)
            for c, r, m in results
            if c.seed
        ],
    )


# --- Output lines (S10-R2, pinned formats) -------------------------------------------------------


def rate_text(passed: int, total: int, of: str = "") -> str:
    """`0.850 (17 of 20)`, with `of` after the total (" reachable"); n/a for a total of 0."""
    value = "n/a" if total == 0 else f"{passed / total:.3f}"
    return f"{value} ({passed} of {total}{of})"


def ac4_text(seeds: Sequence[SeedResult]) -> str:
    """`3 of 4 (q08: not retrieved)`: the seeds surfaced of those whose question ran, then each
    seed that wasn't, in file order, joined by "; ": `missed` when it was retrieved."""
    surfaced = sum(seed.surfaced for seed in seeds)
    misses = "; ".join(
        f"{seed.question_id}: {'missed' if seed.retrieved else 'not retrieved'}"
        for seed in seeds
        if not seed.surfaced
    )
    return f"{surfaced} of {len(seeds)}" + (f" ({misses})" if misses else "")


def set_line(path: Path, sha256: str, conflict_set: ConflictSet, golden_questions: int) -> str:
    """The conflict set's line: its file, the first 8 characters of its hash, its counts, and the
    pool (every golden question plus the new ones). Every side entry matches a stored text by
    then: an unmatched one stops the command."""
    seeds = sum(conflict.seed for conflict in conflict_set.conflicts)
    new = len(conflict_set.questions)
    return (
        f"Conflict set {path} ({sha256[:8]}): {len(conflict_set.conflicts)} conflicts ({seeds} "
        f"seeds) on {golden_questions + new} questions ({new} new). Unmatched sides: 0."
    )


def reachable_line(counts: ConflictCounts) -> str:
    """`Reachable: 4 of 5 (not reachable: k03 q08).`, over the conflicts whose question ran."""
    reached = counts.recall[1]
    missed = "; ".join(f"{c.id} {c.question}" for c in counts.unreachable)
    listed = f" (not reachable: {missed})" if missed else ""
    return f"Reachable: {reached} of {reached + len(counts.unreachable)}{listed}."


def seeds_line(counts: ConflictCounts) -> str:
    """`Seeds retrieved: 3 of 4 (not retrieved: k03 q08).`"""
    missed = "; ".join(f"{s.conflict_id} {s.question_id}" for s in counts.seeds if not s.retrieved)
    retrieved = sum(seed.retrieved for seed in counts.seeds)
    listed = f" (not retrieved: {missed})" if missed else ""
    return f"Seeds retrieved: {retrieved} of {len(counts.seeds)}{listed}."


def rule_line(flagged: Sequence[str], counts: ConflictCounts) -> str:
    """`Rule-found: 7 flagged (q16 ...); precision 0.286 (2 of 7); recall 1.000 (2 of 2
    reachable).`: the rule-found conflicts, the ids of the questions holding one in run order,
    and their precision and the rule kinds' recall."""
    questions = f" ({' '.join(flagged)})" if flagged else ""
    return (
        f"Rule-found: {counts.precision_rule[1]} flagged{questions}; precision "
        f"{rate_text(*counts.precision_rule)}; recall "
        f"{rate_text(*counts.recall_rule, ' reachable')}."
    )


def _on_side(side: Sequence[Label], hit: LocatedHit) -> bool:
    """Whether the hit matches any entry of the side ("any of")."""
    return any(label_matches(label, hit.canonical_id, hit.heading_path) for label in side)


def _on_both_sides(conflict: LabeledConflict, a: LocatedHit, b: LocatedHit) -> bool:
    """Whether hits `a` and `b` match a `texts` conflict's sides, one each, in either order."""
    first, second = conflict.first, conflict.second or []
    return (_on_side(first, a) and _on_side(second, b)) or (
        _on_side(first, b) and _on_side(second, a)
    )


def _ratio(results: Sequence[bool]) -> tuple[int, int]:
    """(True results, results)."""
    return sum(results), len(results)


def _rule_errors(conflict: ConflictEntry, question_ids: Collection[str]) -> list[str]:
    """The conflict's rules across fields, as `<field>: <problem>` lines."""
    errors = []
    if conflict.question not in question_ids:
        errors.append(
            f"question: {conflict.question} is neither a golden question nor one of this file's"
        )
    if conflict.kind in RULE_KINDS:
        if conflict.second is not None:
            errors.append(f"second: not allowed for {conflict.kind}")
        if len(conflict.first) != 1 or not conflict.first[0].document.startswith("kep:"):
            errors.append(f"first: {conflict.kind} needs exactly one entry, a kep: document")
    elif conflict.second is None:
        errors.append("second: required for texts")
    # Within one side, an entry twice or one nested in another (ADR-007 D2's label rule). The two
    # sides of a `texts` conflict may be the same section: old vs. new text.
    for side, entries in (("first", conflict.first), ("second", conflict.second or [])):
        written = [(entry.document, parse_section(entry.section)) for entry in entries]
        overlaps = _overlap_errors(written)
        errors += [f"{side}: {error.removeprefix('labels: ')}" for error in overlaps]
    return errors


def _sides(conflict: ConflictEntry) -> frozenset[frozenset[tuple[str, str | None]]]:
    """The conflict's sides as written, in no order, as matching reads a `texts` conflict's."""
    sides = [conflict.first] if conflict.second is None else [conflict.first, conflict.second]
    return frozenset(frozenset((entry.document, entry.section) for entry in side) for side in sides)


def _duplicate_ids(field: str, ids: Sequence[str]) -> list[str]:
    """An error for each id used more than once in the `field` list."""
    positions: dict[str, list[int]] = {}
    for position, item_id in enumerate(ids, start=1):
        positions.setdefault(item_id, []).append(position)
    return [
        f"{item_id}: id: duplicate ({field} {' and '.join(map(str, found))})"
        for item_id, found in positions.items()
        if len(found) > 1
    ]


def _error_line(data: Any, loc: tuple[int | str, ...], message: str) -> str:
    """One pydantic error as `<id>: <field>: <problem>`. Pydantic locates a conflict or a new
    question by its position in its list; the line names it by its id, else as "conflict 2"."""
    parts = []
    if len(loc) > 1 and loc[0] in ("questions", "conflicts") and isinstance(loc[1], int):
        item = data[loc[0]][loc[1]]
        item_id = item.get("id") if isinstance(item, dict) else None
        parts.append(item_id if isinstance(item_id, str) else f"{str(loc[0])[:-1]} {loc[1] + 1}")
        loc = loc[2:]
    if loc:
        parts.append(".".join(str(part) for part in loc))
    return ": ".join([*parts, message])
