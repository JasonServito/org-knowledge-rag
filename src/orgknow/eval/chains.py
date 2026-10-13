"""The gold decision chains (EVAL_CHAINS_PATH, ADR-012 D4): their label check (S13-T1) and the
decision-chain completeness score (S13-T4; the S13-R1 contract, "Pinned: T4").

**The label check** (`text_labels`, `count_texts`): every `texts` entry of the gold file must match
at least 1 stored chunk, by ADR-007 D2's section rule (`section_matches`) against the chunk's
heading path, its document named by canonical id or alias.

**The score** (`make eval-chain`). The gold file goes through two stages, as the golden set's:
`load_chains_file` checks its shape and each step's rules with no database (a known step, not
repeated, exactly one of the 4 forms, a date on an event step with texts), and `resolve_chains`
maps each document to its canonical id and rejects two steps whose texts share a document with
nested labels (either one whole-document, or one section a prefix of the other's, heading by
heading). Then, per chain, pure functions grade each step:

- **The builder** (the stored chain, `load_chain`): `step_right` by the step's form. `texts`: the
  step cites a chunk of an acceptable document whose heading path matches the section; `not_public`:
  the step is missing as `not_public`; `none`: missing, for any reason; `not_stored`: never.
  `right_same_day` also needs the step's UTC day to be the gold date (event steps with texts).
- **The control** (S13-R1 decision 5): the chain's question, retrieved in authority mode with the
  mode WHY (no router call), top RETRIEVAL_TOP_K, from its stored vector. `control_step` gives each
  hit a step by its document (the pinned lookup table); the best-ranked hit per step fills it
  (`control_picks`), and is graded by `step_right` alone (the headline). A step no hit fills is
  missing, with no reason.
- **The verdict:** the builder beats the control on a chain with at least 1 more step right.
"""

import datetime
import json
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Literal, Self, get_args

import psycopg

# PyYAML ships no type hints, so safe_load returns Any.
import yaml  # type: ignore[import-untyped]
from psycopg.rows import TupleRow
from pydantic import AwareDatetime, BaseModel, Field, ValidationError, model_validator

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import Hit, SectionText, Step
from orgknow.db.releases import list_releases
from orgknow.eval.golden import (
    AS_WRITTEN,
    GoldenSetError,
    Label,
    LabelEntry,
    format_section,
    label_matches,
    parse_section,
    section_matches,
)
from orgknow.eval.runner import EvalError, StoredVectors
from orgknow.provenance.chain import SECTION_MARK, Chain, ChainStep, load_chain
from orgknow.provenance.rules import is_opening_post
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.retrieve import retrieve
from orgknow.retrieval.router import Route, TimeScope
from orgknow.settings import Settings

# The 6 steps, in chain order; every step but current docs is an event, with a date.
STEPS: tuple[Step, ...] = get_args(Step)
CURRENT_DOCS: Step = "current_docs"
# A gold step's 4 forms: the texts that count, or why no stored text can.
Form = Literal["texts", "not_public", "not_stored", "none"]
FORMS: tuple[Form, ...] = get_args(Form)
Role = Literal["built-on", "held-out"]
# The control's route (S13-R1 decision 5): the mode set to WHY, no time scope, no router call.
WHY = Route(mode="WHY", time_scope=TimeScope(kind="none", start=None, end=None))
# The source types whose texts, valid at the latest release, the control reads as current docs.
CURRENT_DOCS_TYPES = ("docs_page", "feature_gate_reference", "release_record", "governance_doc")
# `make eval-chain`'s folder under EVAL_RESULTS_DIR (the S13-R1 contract).
RESULTS_FOLDER = "s13-chains"


class ChainLabel(BaseModel):
    """One acceptable text of a gold step: a document and, optionally, a section."""

    seed: str  # the chain's seed KEP, e.g. kep:2572
    step: str  # problem, discussion, proposal, decision, implementation or current_docs
    document: str  # a canonical id or an alias
    section: str | None = None  # None: the whole document; "": the intro; "A > B": headings


def text_labels(path: Path) -> list[ChainLabel]:
    """Every `texts` entry of the gold file, in file order. A step labeled `not_public`,
    `not_stored` or `none` cites no stored text, so it has none."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        ChainLabel(
            seed=chain["seed"],
            step=step["step"],
            document=text["document"],
            section=text.get("section"),
        )
        for chain in data["chains"]
        for step in chain["steps"]
        for text in step.get("texts", [])
    ]


def count_texts(conn: psycopg.Connection[TupleRow], labels: Sequence[ChainLabel]) -> list[int]:
    """How many distinct stored chunk texts each label matches, in order. A document that is
    neither a canonical id nor an alias matches nothing."""
    ids = canonical_ids(conn, sorted({label.document for label in labels}))
    texts: dict[str, list[SectionText]] = {}
    counts = []
    for label in labels:
        canonical_id = ids.get(label.document)
        if canonical_id is None:
            counts.append(0)
            continue
        if canonical_id not in texts:
            texts[canonical_id] = document_texts(conn, canonical_id)
        section = parse_section(label.section)
        matched = {
            text.content_hash
            for text in texts[canonical_id]
            if section_matches(section, text.heading_path)
        }
        counts.append(len(matched))
    return counts


def label_line(label: ChainLabel, count: int) -> str:
    """`kep:2572 decision  gh:enhancements/pull/2567  "Comments > @dims · 2021-04-19"  2 texts`."""
    section = format_section(parse_section(label.section))
    return f"{label.seed} {label.step}  {label.document}  {section}  {count} texts"


class GoldStepEntry(BaseModel):
    """A gold step as written: its step, its date, and exactly one of the 4 forms."""

    model_config = AS_WRITTEN

    step: Step
    date: datetime.date | None = None  # the event's UTC day; absent for current docs
    texts: list[LabelEntry] | None = None  # "any of", ADR-007 D2's section rule
    not_public: str | None = None  # the evidence exists, but isn't public
    not_stored: str | None = None  # public, but not linked by the template fields
    none: str | None = None  # the step has no record

    @model_validator(mode="after")
    def _one_form_and_a_date(self) -> Self:
        forms = [form for form in FORMS if getattr(self, form) is not None]
        if len(forms) != 1:
            found = f"found {len(forms)}" + (f": {', '.join(forms)}" if forms else "")
            raise ValueError(f"needs exactly one of {', '.join(FORMS)} ({found})")
        if self.texts is not None and self.step != CURRENT_DOCS and self.date is None:
            raise ValueError("an event step with texts needs a date")
        return self

    @property
    def form(self) -> Form:
        """The step's one form (the validator checked there is exactly one)."""
        return next(form for form in FORMS if getattr(self, form) is not None)


class GoldChainEntry(BaseModel):
    """A gold chain as written: its seed KEP, its role, the control's question and its steps."""

    model_config = AS_WRITTEN

    seed: str
    role: Role
    question: str = Field(min_length=1)
    steps: list[GoldStepEntry]

    @model_validator(mode="after")
    def _no_repeated_step(self) -> Self:
        written = [entry.step for entry in self.steps]
        repeated = [step for step in STEPS if written.count(step) > 1]
        if repeated:
            raise ValueError(f"step {', '.join(repeated)} is repeated")
        return self


class ChainsFile(BaseModel):
    """A gold chains file as written, after `load_chains_file` validated it."""

    model_config = AS_WRITTEN

    version: str
    chains: list[GoldChainEntry]


class GoldStep(BaseModel):
    """A gold step whose texts are resolved: `labels` is empty for the forms other than texts."""

    step: Step
    form: Form
    date: datetime.date | None
    labels: list[Label]


class GoldChain(BaseModel):
    """A gold chain whose documents are resolved: what the score grades against."""

    seed: str
    role: Role
    question: str
    steps: list[GoldStep]  # in the file's order


class Pick(BaseModel):
    """What a chain puts in one step, as the score reads it: a cited text (its document and
    heading path), or nothing (`canonical_id` None). The builder's pick also has its date and how
    it was found, or its missing reason; the control's, its hit's rank (from 1)."""

    canonical_id: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    occurred_at: AwareDatetime | None = None
    found_by: str | None = None
    missing_reason: str | None = None
    rank: int | None = None


class ControlHit(BaseModel):
    """One of the control's hits, with the step the lookup table gives it (None: no step)."""

    rank: int
    canonical_id: str
    heading_path: list[str]
    source_type: str
    step: Step | None


class StepRow(BaseModel):
    """One row of a chain's table."""

    step: Step
    gold: str  # `gold_cell`
    built: Pick
    right: bool
    right_with_date: bool | None  # None: not an event step with texts, so not counted
    control: Pick
    control_right: bool


class ChainScore(BaseModel):
    """One chain's score: its rows, the builder's 2 numbers, the control's headline and the
    verdict, with the control's hits."""

    seed: str
    role: Role
    question: str
    built_at: AwareDatetime  # the scored chain's build time
    rows: list[StepRow]
    right: int  # steps right
    steps: int  # gold steps
    right_with_date: int  # right with the same UTC day
    dated: int  # gold event steps with texts
    control_right: int
    verdict: str
    control_hits: list[ControlHit]


class ChainsReport(BaseModel):
    """`make eval-chain`'s results: what was scored, how, and each chain's score."""

    gold_path: str
    gold_sha256: str
    gold_version: str
    control: str
    chains: list[ChainScore]


def load_chains_file(path: Path) -> ChainsFile:
    """Read and validate a gold chains file, with no database. Raises GoldenSetError listing every
    problem, each as `<where>: <problem>` (`chains.0.steps.2.step` is the first chain's third
    step's name)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GoldenSetError(["no such file"]) from None
    try:
        # safe_load builds only plain values (dicts, lists, strings, dates), never Python objects.
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise GoldenSetError([f"not valid YAML: {' '.join(str(error).split())}"]) from None
    try:
        return ChainsFile.model_validate(data)
    except ValidationError as error:
        lines = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
        raise GoldenSetError(lines) from None


def chain_documents(chains_file: ChainsFile) -> list[str]:
    """Every document the file's texts name (canonical ids or aliases), sorted, once each."""
    return sorted(
        {
            text.document
            for chain in chains_file.chains
            for step in chain.steps
            for text in step.texts or []
        }
    )


def resolve_chains(chains_file: ChainsFile, ids: Mapping[str, str]) -> list[GoldChain]:
    """The file's chains with each text's document replaced by its canonical id and its section
    parsed (`parse_section`). `ids` maps a stored canonical id or alias to its canonical id
    (`canonical_ids`). Raises GoldenSetError for a document `ids` lacks, and for two steps of a
    chain whose texts share a document with nested labels (`nested`), once resolved."""
    errors = []
    chains = []
    for entry in chains_file.chains:
        steps = []
        for written in entry.steps:
            labels = []
            for text in written.texts or []:
                canonical_id = ids.get(text.document)
                if canonical_id is None:
                    errors.append(
                        f"{entry.seed} {written.step}: {text.document!r} is neither a stored "
                        "canonical id nor an alias"
                    )
                    continue
                labels.append(Label(canonical_id=canonical_id, section=parse_section(text.section)))
            steps.append(
                GoldStep(step=written.step, form=written.form, date=written.date, labels=labels)
            )
        errors += _shared_document_errors(entry.seed, steps)
        chains.append(
            GoldChain(seed=entry.seed, role=entry.role, question=entry.question, steps=steps)
        )
    if errors:
        raise GoldenSetError(errors)
    return chains


def nested(a: list[str] | None, b: list[str] | None) -> bool:
    """Whether two sections of one document can match one chunk (ADR-007 D2): either is the whole
    document (None), or one is a prefix of the other, heading by heading. The intro ([]) is
    nested only in itself and the whole document."""
    return a is None or b is None or section_matches(a, b) or section_matches(b, a)


def _shared_document_errors(seed: str, steps: Sequence[GoldStep]) -> list[str]:
    """An error for each pair of labels of 2 steps that share a document with nested sections: a
    chunk matching both would credit 2 steps (ADR-012 D4)."""
    errors = []
    for first, second in combinations(steps, 2):
        for a in first.labels:
            for b in second.labels:
                if a.canonical_id == b.canonical_id and nested(a.section, b.section):
                    errors.append(
                        f"{seed}: {first.step} and {second.step} share {a.canonical_id} with "
                        f"nested labels: {format_section(a.section)} and "
                        f"{format_section(b.section)}"
                    )
    return errors


def step_right(gold: GoldStep, pick: Pick) -> bool:
    """The headline rule (ADR-012 D4), by the gold step's form. `texts`: the pick cites a chunk
    of an acceptable document whose heading path matches its section (ADR-007 D2). `not_public`:
    the pick is missing as `not_public`. `none`: the pick is missing, for any reason (the
    control's empty step included). `not_stored`: never."""
    if gold.form == "texts":
        cited = pick.canonical_id
        return cited is not None and any(
            label_matches(label, cited, pick.heading_path) for label in gold.labels
        )
    if gold.form == "not_public":
        return pick.canonical_id is None and pick.missing_reason == "not_public"
    if gold.form == "none":
        return pick.canonical_id is None
    return False  # not_stored: the text isn't stored, so no pick can cite it


def dated(gold: GoldStep) -> bool:
    """Whether the step counts toward "right with the same UTC day": an event step with texts."""
    return gold.form == "texts" and gold.step != CURRENT_DOCS


def right_same_day(gold: GoldStep, pick: Pick) -> bool:
    """Right (`step_right`), and the pick's date falls on the gold date's UTC day."""
    return (
        step_right(gold, pick)
        and gold.date is not None
        and pick.occurred_at is not None
        and pick.occurred_at.astimezone(datetime.UTC).date() == gold.date
    )


def valid_at(windows: Sequence[tuple[int, int | None]], release: int) -> bool:
    """Whether some release window (from, until; None is open; both inclusive) holds `release`."""
    return any(start <= release and (end is None or end >= release) for start, end in windows)


def control_step(hit: Hit, latest: int) -> Step | None:
    """The control's lookup table (S13-R1 decision 5, "Pinned: T4"): the step a hit fills, by its
    document. A GitHub discussion's opening post → problem; any other post of a discussion or an
    issue → discussion; any post of a PR → decision; a KEP → proposal; a blog post or a CHANGELOG
    → implementation; a docs page, feature gate, other release record or governance doc valid at
    the latest release → current_docs; anything else → None."""
    if hit.source_type == "discussion":
        kind = hit.canonical_id.split("/")[-2]  # gh:<repo key>/<issues|pull|discussions>/<n>
        if kind == "pull":
            return "decision"
        opening = is_opening_post(hit.heading_path)
        return "problem" if kind == "discussions" and opening else "discussion"
    if hit.source_type == "kep":
        return "proposal"
    if hit.source_type == "blog_post" or hit.canonical_id.startswith("changelog:"):
        return "implementation"
    if hit.source_type in CURRENT_DOCS_TYPES and valid_at(hit.release_windows, latest):
        return CURRENT_DOCS
    return None


def control_picks(hits: Sequence[Hit], latest: int) -> dict[Step, Pick]:
    """Each step the hits fill, with its best-ranked hit (`hits` is best first)."""
    picks: dict[Step, Pick] = {}
    for rank, hit in enumerate(hits, start=1):
        step = control_step(hit, latest)
        if step is not None and step not in picks:
            picks[step] = Pick(
                canonical_id=hit.canonical_id, heading_path=hit.heading_path, rank=rank
            )
    return picks


def verdict(builder: int, control: int) -> str:
    """The verdict line: the builder beats the control with at least 1 more step right."""
    outcome = "beats" if builder >= control + 1 else "does not beat"
    return f"builder {builder}, control {control}: {outcome}"


def builder_pick(step: ChainStep) -> Pick:
    """A stored chain step as the score reads it."""
    return Pick(
        canonical_id=step.canonical_id,
        heading_path=step.heading_path or [],
        occurred_at=step.occurred_at,
        found_by=step.found_by,
        missing_reason=step.missing_reason,
    )


def score_chain(gold: GoldChain, built: Chain, hits: Sequence[Hit], latest: int) -> ChainScore:
    """Grade the built chain and the control's hits (best first) against the gold chain, one row
    per gold step in chain order. `latest` is the latest release's minor (the lookup table's
    current docs). A step the built chain lacks, or no hit fills, is an empty pick."""
    built_picks = {step.step: builder_pick(step) for step in built.steps}
    control = control_picks(hits, latest)
    rows = []
    for step in sorted(gold.steps, key=lambda gold_step: STEPS.index(gold_step.step)):
        pick = built_picks.get(step.step, Pick())
        control_pick = control.get(step.step, Pick())
        rows.append(
            StepRow(
                step=step.step,
                gold=gold_cell(step),
                built=pick,
                right=step_right(step, pick),
                right_with_date=right_same_day(step, pick) if dated(step) else None,
                control=control_pick,
                control_right=step_right(step, control_pick),
            )
        )
    right = sum(row.right for row in rows)
    control_right = sum(row.control_right for row in rows)
    return ChainScore(
        seed=gold.seed,
        role=gold.role,
        question=gold.question,
        built_at=built.built_at,
        rows=rows,
        right=right,
        steps=len(rows),
        right_with_date=sum(row.right_with_date is True for row in rows),
        dated=sum(row.right_with_date is not None for row in rows),
        control_right=control_right,
        verdict=verdict(right, control_right),
        control_hits=[
            ControlHit(
                rank=rank,
                canonical_id=hit.canonical_id,
                heading_path=hit.heading_path,
                source_type=hit.source_type,
                step=control_step(hit, latest),
            )
            for rank, hit in enumerate(hits, start=1)
        ],
    )


def summary_lines(score: ChainScore) -> list[str]:
    """The builder's 2 numbers, the control's headline, and the verdict."""
    return [
        f"steps right: {score.right} of {score.steps}",
        f"right with the same UTC day: {score.right_with_date} of {score.dated}",
        f"control steps right: {score.control_right} of {score.steps}",
        score.verdict,
    ]


def _citation(pick: Pick) -> str:
    """The canonical id, SECTION_MARK and the heading path, as `orgknow chain` cites a step, with
    each pipe escaped for a Markdown table."""
    text = f"{pick.canonical_id} {SECTION_MARK} {' > '.join(pick.heading_path)}"
    return text.replace("|", "\\|")


def gold_cell(gold: GoldStep) -> str:
    """The gold step in a table cell: `<n> texts, <date>`, or its form."""
    if gold.form != "texts":
        return gold.form
    count = f"{len(gold.labels)} text{'' if len(gold.labels) == 1 else 's'}"
    return count if gold.date is None else f"{count}, {gold.date}"


def built_cell(pick: Pick) -> str:
    """The built step in a table cell: its citation, its UTC day and how it was found, or
    `missing: <reason>`."""
    if pick.canonical_id is None:
        return f"missing: {pick.missing_reason}"
    day = (
        "undated"
        if pick.occurred_at is None
        else str(pick.occurred_at.astimezone(datetime.UTC).date())
    )
    return f"{_citation(pick)}, {day}, {pick.found_by}"


def control_cell(pick: Pick) -> str:
    """The control's pick in a table cell: `#<rank> <citation>`, or `no hit`."""
    return "no hit" if pick.canonical_id is None else f"#{pick.rank} {_citation(pick)}"


def _yes(value: bool | None) -> str:
    return "n/a" if value is None else ("yes" if value else "no")


def chain_text(score: ChainScore) -> list[str]:
    """One chain's section of the report: a header, the 6-row table, then `summary_lines`."""
    built = f"{score.built_at.astimezone(datetime.UTC):%Y-%m-%d %H:%M:%S}"
    lines = [
        f"## {score.seed} ({score.role})",
        "",
        f"Question: {score.question}",
        f"Chain built: {built} UTC",
        "",
        "| step | gold | built | right | right with date | control's pick | control right |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {row.step} | {row.gold} | {built_cell(row.built)} | {_yes(row.right)} | "
        f"{_yes(row.right_with_date)} | {control_cell(row.control)} | {_yes(row.control_right)} |"
        for row in score.rows
    ]
    return [*lines, "", *(f"- {line}" for line in summary_lines(score))]


def report_text(report: ChainsReport) -> str:
    """`chains.md`, which `make eval-chain` also prints."""
    lines = [
        "# Decision-chain completeness (S13-T4)",
        "",
        f"Gold: {report.gold_path} ({report.gold_version}, sha256 {report.gold_sha256}).",
        f"Control: {report.control}. Made by `make eval-chain`.",
    ]
    for score in report.chains:
        lines += ["", *chain_text(score)]
    return "\n".join(lines) + "\n"


def score_chains(
    conn: psycopg.Connection[TupleRow],
    chains: Sequence[GoldChain],
    vectors: Mapping[str, list[float]],
    settings: Settings,
    reranker: Reranker | None,
    repo_urls: Mapping[str, str],
) -> list[ChainScore]:
    """Score each gold chain: its stored chain (`load_chain`) and the control, its question
    retrieved in `settings`' mode (authority, set by the caller) with the WHY route, from its
    stored vector, with `reranker`. No API call. Raises EvalError for a chain that isn't stored,
    and KeyError for a question with no vector in `vectors`."""
    stored = StoredVectors(settings.embedding_model, vectors)
    latest = list_releases(conn)[-1].minor  # oldest first; a stored chain implies a release
    scores = []
    for gold in chains:
        built = load_chain(conn, gold.seed, repo_urls)
        if built is None:
            raise EvalError(f"no stored chain for {gold.seed}: run `make chains`")
        hits = retrieve(gold.question, stored, conn, settings, reranker, WHY)
        scores.append(score_chain(gold, built, hits, latest))
    return scores


def write_report(folder: Path, report: ChainsReport) -> None:
    """Write `chains.json` (the report, indented) and `chains.md` (`report_text`) in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False)
    (folder / "chains.json").write_text(data + "\n", encoding="utf-8")
    (folder / "chains.md").write_text(report_text(report), encoding="utf-8")
