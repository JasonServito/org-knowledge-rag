"""The conflict set (S10-T6, ADR-007 D4): its file format and loader, matching, the metrics
(precision, recall, AC4), the summary and `make eval-conflicts`' lines, and `make eval-routes`
for the set's new questions. No database, no network.

Every bad file below is a valid file with one rule broken; its expected error lines are written by
hand from the rule. Every expected count is by hand from the hand-built hits and flags: the chunk
ids, documents and sections are real ones from v0's hits (the S09 run `authority-20261011T051924Z`),
copied to make the cases readable, but nothing here reads the database.
"""

import copy
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import anthropic
import pytest
import yaml  # type: ignore[import-untyped]
from tests.conftest import FakeEmbedder, FakeGenerator

from orgknow.db.models import Release
from orgknow.eval import __main__ as eval_main
from orgknow.eval import runner
from orgknow.eval.checks import AnswerChecks
from orgknow.eval.conflicts import (
    ConflictCounts,
    ConflictSet,
    ConflictSetError,
    LabeledConflict,
    SeedResult,
    load_conflict_file,
    matches,
    reachable,
    reachable_line,
    resolve_sides,
    rule_line,
    score_conflicts,
    seeds_line,
    set_line,
)
from orgknow.eval.golden import Label, load_golden_file
from orgknow.eval.runner import (
    QuestionRow,
    RankedHit,
    Rate,
    RunInfo,
    Summary,
    load_routes,
    load_vectors,
    question_key,
    summarize,
    summary_line,
)
from orgknow.generation.conflicts import Conflict, ConflictKind
from orgknow.retrieval.router import Route
from orgknow.settings import Settings

DEMO_SAMPLE = Path(__file__).parents[1] / "fixtures" / "conflicts" / "demo-sample.yaml"
DEMO_GOLDEN = Path(__file__).parents[1] / "fixtures" / "eval" / "demo.yaml"
# The golden ids the files below reference (golden set v0's).
GOLDEN_IDS = ["q01", "q08", "q18", "q21", "q32"]
VERSIONING = "sig-release:release-engineering/versioning.md"
SKEW = "Kubernetes Release Versioning > Release versioning > Supported releases and component skew"
HISTORY = "KEP-2579: Pod Security Admission Control > Implementation History"
C01 = "In Kubernetes 1.30, how long was a minor release supported?"


def _valid() -> dict[str, Any]:
    """A valid conflict file: one new question and the 4 seeds of the S10-R2 contract."""
    return {
        "version": "v0",
        "questions": [{"id": "c01", "question": C01}],
        "conflicts": [
            {
                "id": "k01",
                "question": "q18",
                "kind": "claim_mismatch",
                "seed": True,
                "note": "KEP-4858 claims stable; the 1.37 reference says beta.",
                "first": [{"document": "kep:4858"}],
            },
            {
                "id": "k02",
                "question": "q01",
                "kind": "texts",
                "seed": True,
                "note": "KEP-2572 claims alpha; the docs say three releases a year.",
                "first": [{"document": "kep:2572"}],
                "second": [
                    {"document": "web:/releases/release/"},
                    {"document": "web:/docs/setup/release/"},
                ],
            },
            {
                "id": "k03",
                "question": "q08",
                "kind": "history_date",
                "seed": True,
                "note": "KEP-2579 says 2021-11-03; v1.23 was released 2021-12-07.",
                "first": [{"document": "kep:2579", "section": HISTORY}],
            },
            {
                "id": "k04",
                "question": "c01",
                "kind": "texts",
                "seed": True,
                "note": "versioning.md says every three months; at 1.30, three a year.",
                "first": [{"document": VERSIONING, "section": SKEW}],
                "second": [{"document": "web:/docs/setup/release/version-skew-policy/"}],
            },
        ],
    }


def _errors(tmp_path: Path, data: dict[str, Any]) -> list[str]:
    """Load `data` as a conflict file and return its error lines ([] if it is valid)."""
    path = tmp_path / "conflicts.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    try:
        load_conflict_file(path, GOLDEN_IDS)
    except ConflictSetError as error:
        return error.errors
    return []


# --- Loading ------------------------------------------------------------------------------------


def test_the_valid_file_and_the_demo_sample_load() -> None:
    sample = load_conflict_file(DEMO_SAMPLE, GOLDEN_IDS)

    # Read by hand from tests/fixtures/conflicts/demo-sample.yaml.
    assert sample.questions == []
    assert [(c.id, c.question, c.kind, c.seed) for c in sample.conflicts] == [
        ("k01", "q18", "claim_mismatch", True),
        ("k02", "q01", "texts", True),
        ("k03", "q08", "history_date", True),
        ("k04", "q21", "texts", True),
        ("k05", "q32", "claim_mismatch", False),  # `seed` absent: false
    ]
    k02 = sample.conflicts[1]
    assert [e.document for e in k02.first] == ["kep:2572"]
    assert k02.second is not None
    assert [e.document for e in k02.second] == [
        "web:/releases/release/",
        "web:/docs/setup/release/",
    ]
    assert sample.conflicts[0].second is None


def test_a_valid_file_loads(tmp_path: Path) -> None:
    assert _errors(tmp_path, _valid()) == []


def _set(path: list[str | int], value: Any) -> Callable[[dict[str, Any]], None]:
    """A change to a valid file: put `value` at `path` (None deletes the key)."""

    def change(data: dict[str, Any]) -> None:
        *parents, last = path
        target: Any = data
        for part in parents:
            target = target[part]
        if value is None:
            del target[last]
        else:
            target[last] = value

    return change


def _add_conflict(conflict: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    return lambda data: data["conflicts"].append(conflict)


K02_SWAPPED = {
    # k02's sides swapped, not a seed: the same sides in either order.
    "id": "k05",
    "question": "q01",
    "kind": "texts",
    "note": "The docs say three releases a year; KEP-2572 claims alpha.",
    "first": [{"document": "web:/docs/setup/release/"}, {"document": "web:/releases/release/"}],
    "second": [{"document": "kep:2572"}],
}

BAD = {
    "unknown key": (
        _set(["conflicts", 0, "status"], "open"),
        ["k01: status: Extra inputs are not permitted"],
    ),
    "unknown top-level key": (
        _set(["golden"], "v0.yaml"),
        ["golden: Extra inputs are not permitted"],
    ),
    "bad kind": (
        _set(["conflicts", 0, "kind"], "stale_claim"),
        ["k01: kind: Input should be 'claim_mismatch', 'history_date' or 'texts'"],
    ),
    "no value is converted": (
        _set(["conflicts", 0, "seed"], "yes"),
        ["k01: seed: Input should be a valid boolean"],
    ),
    "an empty note": (
        _set(["conflicts", 0, "note"], ""),
        ["k01: note: String should have at least 1 character"],
    ),
    "a rule kind with second": (
        _set(["conflicts", 0, "second"], [{"document": "gate:StrictIPCIDRValidation"}]),
        ["k01: second: not allowed for claim_mismatch"],
    ),
    "a rule kind with a non-KEP first": (
        _set(["conflicts", 2, "first"], [{"document": "web:/releases/release/"}]),
        ["k03: first: history_date needs exactly one entry, a kep: document"],
    ),
    "a rule kind with two entries": (
        _set(["conflicts", 0, "first"], [{"document": "kep:4858"}, {"document": "kep:3299"}]),
        ["k01: first: claim_mismatch needs exactly one entry, a kep: document"],
    ),
    "texts without second": (
        _set(["conflicts", 1, "second"], None),
        ["k02: second: required for texts"],
    ),
    "an empty first side": (
        _set(["conflicts", 1, "first"], []),
        ["k02: first: List should have at least 1 item after validation, not 0"],
    ),
    "an empty second side": (
        _set(["conflicts", 1, "second"], []),
        ["k02: second: List should have at least 1 item after validation, not 0"],
    ),
    "3 seeds": (
        _set(["conflicts", 3, "seed"], False),
        ["seed: 3 conflicts are seeds; exactly 4 must be"],
    ),
    "5 seeds": (
        _add_conflict({**K02_SWAPPED, "question": "q21", "seed": True}),
        ["seed: 5 conflicts are seeds; exactly 4 must be"],
    ),
    "an unknown question id": (
        _set(["conflicts", 0, "question"], "q99"),
        ["k01: question: q99 is neither a golden question nor one of this file's"],
    ),
    "duplicate conflict ids": (
        _set(["conflicts", 1, "id"], "k01"),
        ["k01: id: duplicate (conflicts 1 and 2)"],
    ),
    "duplicate question ids": (
        _set(["questions"], [{"id": "c01", "question": C01}, {"id": "c01", "question": "Why?"}]),
        ["c01: id: duplicate (questions 1 and 2)"],
    ),
    # New ids start with c, golden ids with q: the pattern keeps them apart.
    "a new id equal to a golden id": (
        _set(["questions", 0, "id"], "q18"),
        ["q18: id: String should match pattern '^c[0-9]{2,3}$'"],
    ),
    "a nested entry": (
        _set(
            ["conflicts", 1, "second"],
            [
                {"document": "web:/releases/release/"},
                {"document": "web:/releases/release/", "section": "The Release Cycle"},
            ],
        ),
        [
            'k02: second: web:/releases/release/ "The Release Cycle" is nested in '
            "web:/releases/release/ (whole document)"
        ],
    ),
    "an entry twice": (
        _set(["conflicts", 1, "first"], [{"document": "kep:2572"}, {"document": "kep:2572"}]),
        ["k02: first: kep:2572 (whole document) is listed twice"],
    ),
    "a duplicate conflict": (
        _add_conflict(K02_SWAPPED),
        ["k05: duplicate of k02 (same question, kind and sides)"],
    ),
}


@pytest.mark.parametrize(("change", "expected"), BAD.values(), ids=BAD.keys())
def test_a_bad_file_fails_with_one_line_naming_the_conflict_and_field(
    tmp_path: Path, change: Callable[[dict[str, Any]], None], expected: list[str]
) -> None:
    data = copy.deepcopy(_valid())
    change(data)

    assert _errors(tmp_path, data) == expected


def test_a_texts_conflict_may_hold_one_section_on_both_sides(tmp_path: Path) -> None:
    # Old vs. new text of one section: the same entry on both sides is allowed.
    data = _valid()
    data["conflicts"][3]["second"] = [{"document": VERSIONING, "section": SKEW}]

    assert _errors(tmp_path, data) == []


def test_a_missing_file_is_one_error(tmp_path: Path) -> None:
    with pytest.raises(ConflictSetError) as error:
        load_conflict_file(tmp_path / "missing.yaml", GOLDEN_IDS)

    assert error.value.errors == ["no such file"]


def test_resolving_maps_each_document_and_parses_each_section() -> None:
    sample = load_conflict_file(DEMO_SAMPLE, GOLDEN_IDS)
    # An alias of versioning.md (its 1.37 path) resolves to it; the other names are their own.
    ids = {
        "kep:2579": "kep:2579",
        "sig-release:release-engineering/versioning.md": VERSIONING,
    }

    conflict_set = resolve_sides(sample, ids)

    k03, k04 = conflict_set.conflicts[2], conflict_set.conflicts[3]
    assert k03.first == [
        Label(
            canonical_id="kep:2579",
            section=["KEP-2579: Pod Security Admission Control", "Implementation History"],
        )
    ]
    assert k03.second is None
    assert k04.first == [Label(canonical_id=VERSIONING, section=SKEW.split(" > "))]
    # A name `ids` lacks is kept as written, and matches nothing stored.
    assert k04.second == [
        Label(canonical_id="web:/docs/setup/release/version-skew-policy/", section=None)
    ]


def test_the_conflict_path_defaults_to_conflicts_v0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    monkeypatch.delenv("EVAL_CONFLICTS_PATH", raising=False)

    # The run contract's default (S10-R2, T6's files in scope).
    expected = Path("eval/golden_set/conflicts-v0.yaml")
    assert Settings(_env_file=None).eval_conflicts_path == expected


# --- Matching (ADR-007 D4 (a); S10-R2, pinned) ----------------------------------------------------


def _hit(chunk_id: int, canonical_id: str, heading_path: str = "") -> RankedHit:
    """A hit as a results file stores it; matching reads only the id, document and section."""
    path = heading_path.split(" > ") if heading_path else []
    return RankedHit(
        rank=1, chunk_id=chunk_id, canonical_id=canonical_id, heading_path=path, distance=None
    )


def _flag(found_by: str, kind: ConflictKind, *chunk_ids: int) -> Conflict:
    """A flagged conflict; matching reads only who found it, its kind and its chunk ids."""
    return Conflict.model_validate(
        {
            "kind": kind,
            "found_by": found_by,
            "chunk_ids": list(chunk_ids),
            "documents": [],
            "summary": "s",
            "resolution": "unresolved",
            "prevails": None,
        }
    )


def _labeled(
    conflict_id: str,
    question: str,
    kind: str,
    first: list[Label],
    second: list[Label] | None = None,
    seed: bool = False,
) -> LabeledConflict:
    return LabeledConflict.model_validate(
        {
            "id": conflict_id,
            "question": question,
            "kind": kind,
            "seed": seed,
            "first": first,
            "second": second,
        }
    )


def _doc(canonical_id: str, section: str | None = None) -> Label:
    return Label(
        canonical_id=canonical_id, section=None if section is None else section.split(" > ")
    )


# q18: the gate page and a KEP-4858 chunk.
GATE_PAGE = _hit(10420, "gate:StrictIPCIDRValidation")
KEP_4858 = _hit(31011, "kep:4858", "KEP-4858: IP/CIDR Validation Improvements > Design Details")
CLAIM = _labeled("k01", "q18", "claim_mismatch", [_doc("kep:4858")], seed=True)
# q01: two KEP-2572 chunks, the release page and /docs/setup/release/.
KEP_SUMMARY = _hit(33440, "kep:2572", "KEP-2572: Defining the Kubernetes Release Cadence > Summary")
KEP_MOTIVATION = _hit(33441, "kep:2572", "KEP-2572: Defining the Kubernetes Release Cadence")
RELEASE_PAGE = _hit(7600, "web:/releases/release/", "The Release Cycle")
SETUP_RELEASE = _hit(6946, "web:/docs/setup/release/")
TEXTS = _labeled(
    "k02",
    "q01",
    "texts",
    [_doc("kep:2572")],
    [_doc("web:/releases/release/"), _doc("web:/docs/setup/release/")],
)
# versioning.md's skew section in two versions (chunks 36376 and 36383), old vs. new.
SKEW_OLD = _hit(36376, VERSIONING, SKEW)
SKEW_NEW = _hit(36383, VERSIONING, SKEW)
SAME_SECTION = _labeled("k04", "q21", "texts", [_doc(VERSIONING, SKEW)], [_doc(VERSIONING, SKEW)])


def test_a_claim_label_matches_only_its_rule_conflict() -> None:
    hits = [GATE_PAGE, KEP_4858]

    assert matches(_flag("rule", "claim_mismatch", 31011), CLAIM, hits)
    # The model pairing the KEP with its gate page repeats the code's conflict: not a match.
    assert not matches(_flag("model", "contradiction", 31011, 10420), CLAIM, hits)
    # A history_date on the same KEP is another kind.
    assert not matches(_flag("rule", "history_date", 31011), CLAIM, hits)


def test_a_texts_label_matches_a_model_pair_in_either_order() -> None:
    hits = [SETUP_RELEASE, RELEASE_PAGE, KEP_MOTIVATION, KEP_SUMMARY]

    assert matches(_flag("model", "contradiction", 33440, 7600), TEXTS, hits)
    assert matches(_flag("model", "contradiction", 7600, 33440), TEXTS, hits)
    # "Any of": the second side's other document.
    assert matches(_flag("model", "contradiction", 33440, 6946), TEXTS, hits)
    # Two chunks on the first side only.
    assert not matches(_flag("model", "supersession", 33440, 33441), TEXTS, hits)
    # Two chunks on the second side only.
    assert not matches(_flag("model", "contradiction", 6946, 7600), TEXTS, hits)
    # The right chunks, found by a rule: a texts label is matched only by the model.
    assert not matches(_flag("rule", "claim_mismatch", 33440, 7600), TEXTS, hits)


def test_a_flag_s_chunks_are_read_from_the_question_s_hits() -> None:
    # Chunk 7600 isn't among these hits, so the pair has one known chunk: no match.
    assert not matches(_flag("model", "contradiction", 33440, 7600), TEXTS, [KEP_SUMMARY])


def test_a_same_section_label_needs_two_different_hits() -> None:
    # Old vs. new versions of one section: two different chunks, one per side.
    assert reachable(SAME_SECTION, [SKEW_OLD, GATE_PAGE, SKEW_NEW])
    assert matches(_flag("model", "supersession", 36376, 36383), SAME_SECTION, [SKEW_OLD, SKEW_NEW])
    # One hit can't be both sides.
    assert not reachable(SAME_SECTION, [SKEW_NEW, GATE_PAGE])


def test_reachable_needs_a_hit_on_each_side() -> None:
    assert reachable(CLAIM, [GATE_PAGE, KEP_4858])
    assert not reachable(CLAIM, [GATE_PAGE])
    assert reachable(TEXTS, [KEP_SUMMARY, SETUP_RELEASE])
    assert not reachable(TEXTS, [KEP_SUMMARY, KEP_MOTIVATION])


# --- Metrics (S10-R2, pinned) --------------------------------------------------------------------

# q08's KEP-2579 hit outside "Implementation History": the history_date seed isn't retrieved.
KEP_2579_INTRO = _hit(15239, "kep:2579", "KEP-2579: Pod Security Admission Control")
DATE = _labeled("k03", "q08", "history_date", [_doc("kep:2579", HISTORY)], seed=True)


def test_precision_recall_and_the_unreachable_count() -> None:
    questions = [
        # q18: the rule's claim_mismatch matches k01.
        ("q18", [GATE_PAGE, KEP_4858], [_flag("rule", "claim_mismatch", 31011)]),
        # q01: one model pair matches k02, the other pairs two second-side texts.
        (
            "q01",
            [SETUP_RELEASE, RELEASE_PAGE, KEP_SUMMARY],
            [
                _flag("model", "contradiction", 33440, 7600),
                _flag("model", "contradiction", 6946, 7600),
            ],
        ),
        # q08: k03's section isn't retrieved.
        ("q08", [KEP_2579_INTRO], []),
    ]

    counts = score_conflicts([CLAIM, TEXTS, DATE], questions)

    # 3 flags, 2 matching: rule 1 of 1, model 1 of 2. Reachable: k01 and k02, both matched: rule
    # 1 of 1, texts 1 of 1. k03 is unreachable: listed, not in recall.
    assert counts.precision == (2, 3)
    assert (counts.precision_rule, counts.precision_model) == ((1, 1), (1, 2))
    assert counts.recall == (2, 2)
    assert (counts.recall_rule, counts.recall_texts) == ((1, 1), (1, 1))
    assert [c.id for c in counts.unreachable] == ["k03"]


# c01's two hits, old and new text of versioning.md's skew section.
C01_SEED = _labeled("k04", "c01", "texts", [_doc(VERSIONING, SKEW)], [_doc(VERSIONING, SKEW)], True)
SEED_TEXTS = TEXTS.model_copy(update={"seed": True})
SEED_QUESTIONS = [
    ("q18", [KEP_4858], [_flag("rule", "claim_mismatch", 31011)]),  # surfaced
    ("q01", [RELEASE_PAGE, KEP_SUMMARY], []),  # retrieved, no flag: missed
    ("q08", [KEP_2579_INTRO], []),  # not retrieved
    ("c01", [SKEW_OLD, SKEW_NEW], [_flag("model", "supersession", 36383, 36376)]),  # surfaced
]


def test_ac4_reports_each_seed_retrieved_and_surfaced() -> None:
    counts = score_conflicts([CLAIM, SEED_TEXTS, DATE, C01_SEED], SEED_QUESTIONS)

    assert counts.seeds == [
        SeedResult(conflict_id="k01", question_id="q18", retrieved=True, surfaced=True),
        SeedResult(conflict_id="k02", question_id="q01", retrieved=True, surfaced=False),
        SeedResult(conflict_id="k03", question_id="q08", retrieved=False, surfaced=False),
        SeedResult(conflict_id="k04", question_id="c01", retrieved=True, surfaced=True),
    ]


def test_a_smoke_subset_scores_only_the_questions_it_ran() -> None:
    # Only q18 and q01 ran: k03 (q08) and k04 (c01) are in no count and no list.
    counts = score_conflicts([CLAIM, SEED_TEXTS, DATE, C01_SEED], SEED_QUESTIONS[:2])

    assert counts.precision == (1, 1)
    assert counts.recall == (1, 2)  # k01 matched, k02 missed
    assert counts.unreachable == []
    assert [(s.conflict_id, s.surfaced) for s in counts.seeds] == [("k01", True), ("k02", False)]


def test_a_flag_on_a_question_with_no_conflict_counts_against_precision() -> None:
    # A question with no conflict has no disagreement: its flag matches nothing.
    counts = score_conflicts(
        [CLAIM], [("q16", [KEP_4858], [_flag("rule", "claim_mismatch", 31011)])]
    )

    assert counts.precision == (0, 1)
    assert counts.recall == (0, 0)


# --- The summary, its line and the table ---------------------------------------------------------

STARTED_AT = datetime(2026, 10, 11, 10, tzinfo=UTC)
SHA = "0123456789abcdef" * 4


def _settings(**values: Any) -> Settings:
    return Settings(
        _env_file=None,
        database_url="x",
        generation_price_input_usd_per_mtok=4.0,
        generation_price_output_usd_per_mtok=20.0,
        **values,
    )


def _row(question_id: str, hits: list[RankedHit], flags: list[Conflict]) -> QuestionRow:
    """A row with no answer; the conflict metrics read only its id, hits and conflicts."""
    return QuestionRow(
        id=question_id,
        mode=None,
        answerable=True,
        hits=hits,
        answer=None,
        conflicts=flags,
        metrics=None,
        checks=AnswerChecks(ac1=None, ac2=None, ac3=None, false_refusal=None),
        usage=None,
        latency_s=5.0,
        error=None,
    )


SEED_SET = ConflictSet(version="v0", questions=[], conflicts=[CLAIM, SEED_TEXTS, DATE, C01_SEED])


def _seed_summary() -> Summary:
    # The golden rows are q18, q01 and q08; c01 is a new question's row.
    *golden, new = [_row(qid, list(hits), list(flags)) for qid, hits, flags in SEED_QUESTIONS]
    return summarize("conflict", SHA, STARTED_AT, golden, _settings(), None, SEED_SET, [new])


def test_the_summary_holds_the_conflict_metrics_over_golden_and_new_rows() -> None:
    summary = _seed_summary()

    # Flags: q18's and c01's, both matching. Reachable: k01, k02, k04; matched: k01 and k04.
    assert summary.conflict_precision == Rate(pass_=2, total=2)
    assert summary.conflict_precision_rule == Rate(pass_=1, total=1)
    assert summary.conflict_precision_model == Rate(pass_=1, total=1)
    assert summary.conflict_recall == Rate(pass_=2, total=3)
    assert summary.conflict_recall_rule == Rate(pass_=1, total=1)
    assert summary.conflict_recall_texts == Rate(pass_=1, total=2)
    assert summary.conflict_unreachable == 1
    assert summary.ac4 == Rate(pass_=2, total=4)
    assert summary.ac4_seeds is not None
    assert [s.conflict_id for s in summary.ac4_seeds] == ["k01", "k02", "k03", "k04"]
    # The golden fields stay golden-only: 3 rows, not 4.
    assert summary.questions == 3


def test_the_summary_line_ends_with_precision_recall_and_ac4() -> None:
    # 2 / 2 = 1.000; 2 / 3 = 0.667; seeds in file order: q01 missed, q08 not retrieved.
    assert summary_line(_seed_summary()).endswith(
        " Conflict precision 1.000 (2 of 2), recall 0.667 (2 of 3 reachable), "
        "AC4 2 of 4 (q01: missed; q08: not retrieved)."
    )


def test_the_contract_s_example_summary_line() -> None:
    # The S10-R2 contract's example: 17 / 20 = 0.850, 16 / 20 = 0.800, q08 not retrieved.
    seeds = [
        SeedResult(conflict_id="k01", question_id="q18", retrieved=True, surfaced=True),
        SeedResult(conflict_id="k02", question_id="q01", retrieved=True, surfaced=True),
        SeedResult(conflict_id="k03", question_id="q08", retrieved=False, surfaced=False),
        SeedResult(conflict_id="k04", question_id="c01", retrieved=True, surfaced=True),
    ]
    summary = _seed_summary().model_copy(
        update={
            "conflict_precision": Rate(pass_=17, total=20),
            "conflict_recall": Rate(pass_=16, total=20),
            "ac4": Rate(pass_=3, total=4),
            "ac4_seeds": seeds,
        }
    )

    assert summary_line(summary).endswith(
        " Conflicts: 2 (1 rule, 1 model), 0 loser-only answers. Conflict precision 0.850 (17 of "
        "20), recall 0.800 (16 of 20 reachable), AC4 3 of 4 (q08: not retrieved)."
    )


def test_with_no_conflict_set_the_fields_are_none_and_the_line_adds_nothing() -> None:
    rows = [_row("q18", [KEP_4858], [_flag("rule", "claim_mismatch", 31011)])]

    summary = summarize("authority", SHA, STARTED_AT, rows, _settings())

    assert summary.conflict_precision is None
    assert (summary.conflict_recall, summary.ac4, summary.ac4_seeds) == (None, None, None)
    assert summary.conflict_unreachable is None
    assert summary_line(summary).endswith(" Conflicts: 1 (1 rule, 0 model), 0 loser-only answers.")


def test_a_summary_written_before_s10_t6_loads_with_none() -> None:
    # S09's authority run 3, written before S10: read only.
    path = Path(__file__).parents[2] / "eval/results/authority-20261011T051924Z/summary.json"

    summary = Summary.model_validate_json(path.read_text(encoding="utf-8"))

    fields = (
        *("conflict_precision", "conflict_precision_rule", "conflict_precision_model"),
        *("conflict_recall", "conflict_recall_rule", "conflict_recall_texts"),
        *("conflict_unreachable", "ac4", "ac4_seeds"),
    )
    assert [getattr(summary, field) for field in fields] == [None] * 9
    assert "Conflict precision" not in summary_line(summary)


# --- `make eval-conflicts`' lines (S10-R2, pinned) -----------------------------------------------

# The contract's pinned demo-sample counts, by hand: 7 rule flags, 2 matching (k01 on q18, k05 on
# q32); reachable rule kinds k01 and k05, both matched; k03 (q08) not reachable.
K05 = _labeled("k05", "q32", "claim_mismatch", [_doc("kep:3299")])
PINNED = ConflictCounts(
    precision=(2, 7),
    precision_rule=(2, 7),
    precision_model=(0, 0),
    recall=(2, 4),
    recall_rule=(2, 2),
    recall_texts=(0, 2),
    unreachable=[DATE],
    seeds=[
        SeedResult(conflict_id="k01", question_id="q18", retrieved=True, surfaced=True),
        SeedResult(conflict_id="k02", question_id="q01", retrieved=True, surfaced=False),
        SeedResult(conflict_id="k03", question_id="q08", retrieved=False, surfaced=False),
        SeedResult(conflict_id="k04", question_id="q21", retrieved=True, surfaced=False),
    ],
)


def test_the_eval_conflicts_lines_follow_the_pinned_format() -> None:
    conflict_set = ConflictSet(
        version="demo",
        questions=[],
        conflicts=[CLAIM, SEED_TEXTS, DATE, SAME_SECTION.model_copy(update={"seed": True}), K05],
    )
    flagged = ["q16", "q17", "q18", "q19", "q20", "q32", "q48"]

    assert set_line(Path("tests/fixtures/conflicts/demo-sample.yaml"), SHA, conflict_set, 43) == (
        "Conflict set tests/fixtures/conflicts/demo-sample.yaml (01234567): 5 conflicts (4 seeds) "
        "on 43 questions (0 new). Unmatched sides: 0."
    )
    assert reachable_line(PINNED) == "Reachable: 4 of 5 (not reachable: k03 q08)."
    assert seeds_line(PINNED) == "Seeds retrieved: 3 of 4 (not retrieved: k03 q08)."
    assert rule_line(flagged, PINNED) == (
        "Rule-found: 7 flagged (q16 q17 q18 q19 q20 q32 q48); precision 0.286 (2 of 7); "
        "recall 1.000 (2 of 2 reachable)."
    )


def test_with_every_conflict_reachable_and_no_flag_the_lines_list_nothing() -> None:
    every = PINNED.model_copy(
        update={
            "precision_rule": (0, 0),
            "recall": (5, 5),
            "recall_rule": (0, 0),
            "unreachable": [],
            "seeds": [s.model_copy(update={"retrieved": True}) for s in PINNED.seeds],
        }
    )

    assert reachable_line(every) == "Reachable: 5 of 5."
    assert seeds_line(every) == "Seeds retrieved: 4 of 4."
    assert rule_line([], every) == (
        "Rule-found: 0 flagged; precision n/a (0 of 0); recall n/a (0 of 0 reachable)."
    )


def test_eval_conflicts_with_no_conflict_file_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "conflicts.yaml"
    # Checked before the reranker loads or the database is read, so this URL is never used.
    settings = _settings(eval_conflicts_path=path)

    assert eval_main.main(["conflicts"], settings) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: Conflict set: none ({path} not found).\n"


# --- `make eval-routes` with a conflict set (fakes, no network) ----------------------------------

ROUTE = Route.model_validate(
    {"mode": "CURRENT", "time_scope": {"kind": "none", "start": None, "end": None}}
)
C02 = "When was Pod Security Admission's beta released?"


class _Router:
    """`ClaudeRouter`'s stand-in in the command: one route for every question, no tokens."""

    def __init__(self, client: anthropic.Anthropic, settings: Settings) -> None:
        self.calls: list[str] = []
        self.input_tokens = self.output_tokens = 0

    def route(self, question: str) -> Route:
        self.calls.append(question)
        return ROUTE


def _demo_conflicts(path: Path) -> None:
    """A conflict file on the demo golden set (q06, q13, q10) with 2 new questions."""
    entry = [{"document": "web:/docs/a/"}]
    conflicts = [
        {"id": f"k0{n}", "question": qid, "kind": "texts", "seed": True, "note": "n"}
        | {"first": entry, "second": entry}
        for n, qid in enumerate(["q06", "q13", "c01", "c02"], start=1)
    ]
    questions = [{"id": "c01", "question": C01}, {"id": "c02", "question": C02}]
    data = {"version": "v0", "questions": questions, "conflicts": conflicts}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_eval_routes_routes_and_embeds_the_conflict_set_s_new_questions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routers: list[_Router] = []
    embedders: list[FakeEmbedder] = []

    def router(client: anthropic.Anthropic, settings: Settings) -> _Router:
        routers.append(_Router(client, settings))
        return routers[-1]

    def embedder(
        url: str, key: str, model: str, *, timeout_s: int, max_retries: int
    ) -> FakeEmbedder:
        embedders.append(FakeEmbedder())
        return embedders[-1]

    monkeypatch.setattr(eval_main, "ClaudeRouter", router)
    monkeypatch.setattr(eval_main, "VoyageEmbedder", embedder)
    conflicts = tmp_path / "conflicts.yaml"
    _demo_conflicts(conflicts)
    settings = _settings(
        anthropic_api_key="test-key",
        voyage_api_key="test-key",
        embedding_model="fake-model",
        eval_golden_path=DEMO_GOLDEN,
        eval_conflicts_path=conflicts,
        eval_routes_dir=tmp_path / "routes",
        eval_vectors_dir=tmp_path / "vectors",
    )

    assert eval_main.main(["routes"], settings) == 0

    # The demo set's 3 questions, then c01 and c02: 5 routes; the 2 new questions embedded in 1
    # request (the golden ones are `make eval`'s to embed).
    assert routers[0].calls[3:] == [C01, C02]
    assert len(load_routes(tmp_path / "routes" / "claude-opus-5-5.json")) == 5
    assert embedders[0].calls == [("query", [C01, C02])]
    vectors = load_vectors(tmp_path / "vectors" / "fake-model.json")
    assert sorted(vectors) == sorted([question_key(C01), question_key(C02)])
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("Routed 5 questions with claude-opus-5-5 (0 already stored).")
    assert out[1:] == [
        f"Question vectors ({tmp_path / 'vectors' / 'fake-model.json'}): 2 of 2 embedded. "
        "Voyage requests: 1."
    ]

    # A re-run makes no call of either kind.
    assert eval_main.main(["routes"], settings) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Routed 0 questions with claude-opus-5-5 (5 already stored).",
        f"Question vectors ({tmp_path / 'vectors' / 'fake-model.json'}): 0 of 2 embedded. "
        "Voyage requests: 0.",
    ]
    assert routers[1].calls == []
    assert embedders[1].calls == []


def test_eval_routes_stops_on_an_invalid_conflict_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    conflicts = tmp_path / "conflicts.yaml"
    conflicts.write_text(json.dumps({"version": "v0", "questions": []}), encoding="utf-8")
    settings = _settings(eval_golden_path=DEMO_GOLDEN, eval_conflicts_path=conflicts)

    assert eval_main.main(["routes"], settings) == 1

    assert capsys.readouterr().err == f"error: {conflicts}: conflicts: Field required\n"


# --- `run.json` records the conflict file (S10-R2 decision R2; fakes, no database) ----------------

# R1's smoke run, written before R2: its run.json has no conflict-file fields.
R1_SMOKE_RUN = (
    Path(__file__).parents[2] / "eval" / "results" / "conflict-smoke-20261011T083501Z" / "run.json"
)


def test_run_json_records_the_conflict_file_or_none_and_older_folders_load_with_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The database reads, faked: the golden and conflict files as loaded, no tiers, and a row with
    # no hits per question. Nothing else in `run` reads the database or the network.
    golden = load_golden_file(DEMO_GOLDEN)
    monkeypatch.setattr(runner, "check_golden", lambda conn, path: (golden, []))
    monkeypatch.setattr(
        runner,
        "check_conflicts",
        lambda conn, golden, path: resolve_sides(load_conflict_file(path, GOLDEN_IDS), {}),
    )
    monkeypatch.setattr(runner, "document_tiers", lambda conn, questions: {})
    monkeypatch.setattr(runner, "_run_question", lambda question, *args: _row(question.id, [], []))
    # S12-T1: the latest release AC5 reads; the dates are filler.
    latest = Release(
        version="1.37", release_date=date(2026, 4, 22), end_of_life_date=date(2027, 6, 28)
    )
    monkeypatch.setattr(runner, "list_releases", lambda conn: [latest])

    def run_json(conflicts_path: Path, name: str) -> RunInfo:
        settings = _settings(
            retrieval_mode="dense",
            embedding_model="fake-model",
            eval_golden_path=DEMO_GOLDEN,
            eval_conflicts_path=conflicts_path,
            eval_results_dir=tmp_path / "results",
            eval_vectors_dir=tmp_path / "vectors",
        )
        generator = FakeGenerator(None)
        folder = runner.run(None, FakeEmbedder(), generator, settings, smoke=False, name=name)  # type: ignore[arg-type]
        return RunInfo.model_validate_json((folder / "run.json").read_text(encoding="utf-8"))

    with_file = run_json(DEMO_SAMPLE, "with")
    assert with_file.conflicts_path == str(DEMO_SAMPLE)
    # By `sha256sum tests/fixtures/conflicts/demo-sample.yaml`.
    assert with_file.conflicts_sha256 == (
        "7b8cfbd4a2d346a02309094ea78a9db68a0cec0296181379668c5ffa0e0f619b"
    )

    without = run_json(tmp_path / "none.yaml", "without")
    assert (without.conflicts_path, without.conflicts_sha256) == (None, None)

    older = RunInfo.model_validate_json(R1_SMOKE_RUN.read_text(encoding="utf-8"))
    assert (older.conflicts_path, older.conflicts_sha256) == (None, None)
