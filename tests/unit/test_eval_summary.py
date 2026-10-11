"""The summary's p95 latencies and cost per question (S08-T3), its stale and temporal counts
(S09-T3), its authority selection (S09-T7), and `make eval-resummarize`, from hand-built rows; and
`make eval-retrieval`'s timing line (S08-T4), time line (S09-T3), authority line (S09-T7) and
rule-conflict line (S10-T2), from hand-written values.

Every expected value is by hand: a nearest-rank p95 is the value at sorted index
ceil(n * 0.95) - 1 (0-based), a median of an even count is the mean of the 2 middle values, a
question's cost is (input * $4 + output * $20) / 1,000,000, and a rate is count / total.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orgknow.db.models import Authority
from orgknow.eval import __main__ as eval_main
from orgknow.eval.checks import AnswerChecks
from orgknow.eval.golden import Label, Mode
from orgknow.eval.runner import (
    Count,
    QuestionRow,
    RankedHit,
    Rate,
    RouteRecord,
    RouterStats,
    Summary,
    authority_line,
    conflict_line,
    resummarize,
    router_line,
    summarize,
    time_line,
    timing_line,
)
from orgknow.generation.conflicts import Conflict, ConflictKind
from orgknow.generation.schema import TokenUsage
from orgknow.retrieval.router import TimeScope
from orgknow.settings import Settings

STARTED_AT = datetime(2026, 10, 8, 10, tzinfo=UTC)
SHA = "0123456789abcdef" * 4


def _settings(**values: object) -> Settings:
    """ADR-006 D1's prices, set explicitly, so the expected costs don't rest on the defaults."""
    return Settings(
        _env_file=None,
        database_url="x",
        generation_price_input_usd_per_mtok=4.0,
        generation_price_output_usd_per_mtok=20.0,
        **values,
    )


def _row(
    latency_s: float,
    retrieve_s: float | None = None,
    usage: tuple[int, int] | None = None,
    error: str | None = None,
    mode: Mode | None = None,
    release_window: tuple[int | None, int | None] | None = None,
    hits: list[RankedHit] | None = None,
) -> QuestionRow:
    """An unanswerable question's row unless `mode` is given (no hits by default); `usage` is
    (input, output) tokens. It passes AC3 unless the ask failed. The fields the new summary
    values don't read are filler."""
    return QuestionRow(
        id="q01",
        mode=mode,
        release_window=release_window,
        answerable=False,
        hits=[] if hits is None else hits,
        answer=None,
        metrics=None,
        checks=AnswerChecks(ac1=None, ac2=None, ac3=error is None, false_refusal=None),
        usage=None
        if usage is None
        else TokenUsage(input_tokens=usage[0], output_tokens=usage[1], thinking_tokens=None),
        latency_s=latency_s,
        retrieve_s=retrieve_s,
        error=error,
    )


def _summary(rows: list[QuestionRow]) -> Summary:
    return summarize("dense", SHA, STARTED_AT, rows, _settings())


def test_the_p95_latency_of_1_to_20_s_is_19() -> None:
    # ceil(20 * 0.95) - 1 = 18: the 19th smallest. Given largest first.
    rows = [_row(float(latency)) for latency in range(20, 0, -1)]

    assert _summary(rows).latency_s_p95 == 19.0


def test_the_p95_latency_of_43_questions_is_the_41st_smallest() -> None:
    # ceil(43 * 0.95) - 1 = ceil(40.85) - 1 = 40: the 41st smallest, 41 * 0.5 = 20.5 s.
    rows = [_row(n * 0.5) for n in (*range(43, 21, -1), *range(1, 22))]

    assert len(rows) == 43
    assert _summary(rows).latency_s_p95 == 20.5


def test_the_retrieve_p95_reads_only_the_rows_that_have_it() -> None:
    # 1.0, 2.0, 3.0: ceil(3 * 0.95) - 1 = 2, the largest.
    rows = [
        _row(5.0),
        _row(5.0, retrieve_s=3.0),
        _row(5.0, retrieve_s=1.0),
        _row(5.0, retrieve_s=2.0),
    ]

    assert _summary(rows).retrieve_s_p95 == 3.0


def test_the_retrieve_p95_is_none_when_no_row_has_it() -> None:
    # A folder written before S08-T3: no row times the retrieve stage.
    assert _summary([_row(5.0), _row(6.0)]).retrieve_s_p95 is None


def test_the_cost_of_1000_input_and_100_output_tokens_is_0_006() -> None:
    # (1,000 * 4 + 100 * 20) / 1,000,000 = (4,000 + 2,000) / 1,000,000 = $0.006.
    assert _summary([_row(5.0, usage=(1000, 100))]).cost_usd_mean == pytest.approx(0.006)


def test_the_cost_is_the_mean_over_the_rows_with_usage() -> None:
    # $0.006, then (2,000 * 4 + 400 * 20) / 1,000,000 = $0.016; the error row with no usage is
    # left out: (0.006 + 0.016) / 2 = $0.011.
    rows = [
        _row(5.0, usage=(1000, 100)),
        _row(5.0, usage=(2000, 400)),
        _row(5.0, error="APIConnectionError: Connection error."),
    ]

    assert _summary(rows).cost_usd_mean == pytest.approx(0.011)


def test_the_cost_is_none_when_no_row_has_usage() -> None:
    assert (
        _summary([_row(5.0, error="APIConnectionError: Connection error.")]).cost_usd_mean is None
    )


def test_a_summary_without_the_new_fields_still_loads() -> None:
    summary = Summary.model_validate_json(OLD_SUMMARY_JSON)

    assert (summary.latency_s_p95, summary.retrieve_s_p95, summary.cost_usd_mean) == (None,) * 3
    assert (summary.stale, summary.temporal, summary.router) == (None,) * 3
    assert summary.authority is None


def test_a_row_written_before_s07_still_loads() -> None:
    # The dense baseline's rows (S06): hits with only a distance, and no `retrieve_s` or
    # `release_window`.
    hit = {
        "rank": 1,
        "chunk_id": 7,
        "canonical_id": "kep:2572",
        "heading_path": [],
        "distance": 0.4,
    }
    row = json.loads(_row(5.0).model_dump_json(exclude={"retrieve_s", "release_window"}))

    loaded = QuestionRow.model_validate({**row, "hits": [hit]})

    assert (loaded.retrieve_s, loaded.release_window) == (None, None)
    assert (loaded.hits[0].rrf_score, loaded.hits[0].dense_rank) == (None, None)
    assert loaded.hits[0].lexical_rank is None
    assert (loaded.hits[0].current, loaded.hits[0].release_windows) == (None, None)
    # S09-T6 and S09-T7: no tier, score or label tiers.
    assert (loaded.hits[0].authority, loaded.hits[0].authority_score) == (None, None)
    assert loaded.label_tiers is None


def _ranked(current: bool | None, windows: list[tuple[int, int | None]] | None = None) -> RankedHit:
    """A hit as the results file stores it; the time counts read only `current` and the
    release windows (None in a file written before S09-T3)."""
    return RankedHit(
        rank=1,
        chunk_id=7,
        canonical_id="web:/docs/a/",
        heading_path=[],
        current=current,
        release_windows=windows,
        distance=0.4,
    )


def test_the_summary_counts_stale_current_hits_and_hits_in_the_golden_window() -> None:
    rows = [
        # CURRENT: 1 stale of 3.
        _row(5.0, mode="CURRENT", hits=[_ranked(True), _ranked(False), _ranked(True)]),
        # HISTORY "until 1.20": [20, 22] overlaps it, [24, open] doesn't: 1 of 2. Its stale hit
        # isn't counted as stale: the question isn't CURRENT.
        _row(
            5.0,
            mode="HISTORY",
            release_window=(None, 20),
            hits=[_ranked(False, [(20, 22)]), _ranked(True, [(24, None)])],
        ),
        # HISTORY with no golden window: in neither count.
        _row(5.0, mode="HISTORY", hits=[_ranked(False, [(20, 20)])]),
        _row(5.0),  # unanswerable, no hits
    ]

    summary = _summary(rows)

    assert summary.stale == Count(count=1, total=3)
    assert summary.temporal == Rate(pass_=1, total=2)
    assert summary.router is None  # no row has a route


def test_the_time_counts_are_none_for_rows_written_before_s09_t3() -> None:
    # The hits have no `current` and no release windows; the row has no golden window.
    rows = [_row(5.0, mode="CURRENT", hits=[_ranked(None), _ranked(None)])]

    summary = _summary(rows)

    assert (summary.stale, summary.temporal, summary.router) == (None, None, None)


# A summary as S06 and S07 wrote it, before S08-T3, for the rows `_old_rows` builds: 2 questions,
# both unanswerable, 1 error; AC3 passes on the answered one and fails on the error; 1,000 + 0
# input and 100 + 0 output tokens; mean latency (2.0 + 4.0) / 2 = 3.0 s.
OLD_SUMMARY = {
    "name": "dense",
    "golden_sha256": SHA,
    "started_at": "2026-10-08T10:00:00Z",
    "questions": 2,
    "answerable": 0,
    "errors": 1,
    "recall": None,
    "hit": None,
    "mrr": None,
    "ndcg": None,
    "distinct_sections": None,
    "ac1": {"pass": 0, "total": 0},
    "ac2": {"pass": 0, "total": 0},
    "ac3": {"pass": 1, "total": 2},
    "false_refusals": {"count": 0, "total": 0},
    "input_tokens": 1000,
    "output_tokens": 100,
    "latency_s_mean": 3.0,
}
OLD_SUMMARY_JSON = json.dumps(OLD_SUMMARY, indent=2) + "\n"


def _old_rows() -> str:
    """The 2 rows as `questions.jsonl` lines, without `retrieve_s` (S08-T3) or `release_window`
    (S09-T3), as before S08-T3."""
    rows = [_row(2.0, usage=(1000, 100)), _row(4.0, error="APIConnectionError: Connection error.")]
    old = {"retrieve_s", "release_window"}
    return "".join(row.model_dump_json(exclude=old) + "\n" for row in rows)


def test_resummarize_adds_the_new_fields_and_keeps_every_old_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "dense-20261008T100000Z"
    folder.mkdir()
    (folder / "summary.json").write_text(OLD_SUMMARY_JSON, encoding="utf-8")
    (folder / "questions.jsonl").write_text(_old_rows(), encoding="utf-8")
    # Like s04/: no summary.json, so it is skipped.
    (tmp_path / "s04").mkdir()
    (tmp_path / "s04" / "README.md").write_text("notes", encoding="utf-8")

    assert eval_main.main(["resummarize"], _settings(eval_results_dir=tmp_path)) == 0

    # p95 of 2.0 and 4.0: ceil(2 * 0.95) - 1 = 1, the larger. Cost: the one row with usage,
    # (1,000 * 4 + 100 * 20) / 1,000,000 = $0.006. No row has retrieve_s.
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    cost = summary.pop("cost_usd_mean")
    assert cost == pytest.approx(0.006)
    # No hits, so no stale or temporal count; no routes; no authority selection (S09-T7).
    assert summary == {
        **OLD_SUMMARY,
        "latency_s_p95": 4.0,
        "retrieve_s_p95": None,
        "stale": None,
        "temporal": None,
        "router": None,
        "authority": None,
    }
    # Only the summary is written: the rows are unchanged, and there is no table.
    assert (folder / "questions.jsonl").read_text(encoding="utf-8") == _old_rows()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["dense-20261008T100000Z", "s04"]
    assert capsys.readouterr().out == (
        f"{folder}: p95 latency 4.000 s, retrieve p95 n/a, cost/question $0.006000\n"
    )


def test_resummarize_keeps_the_authority_selection_run_counted(tmp_path: Path) -> None:
    # A folder `run` wrote after S09-T7: its summary holds authority selection, which needs the
    # golden labels; the rows hold only the label tiers, so resummarize keeps the value.
    folder = tmp_path / "authority-20261010T100000Z"
    folder.mkdir()
    counted = {**OLD_SUMMARY, "authority": {"pass": 9, "total": 9}}
    (folder / "summary.json").write_text(json.dumps(counted), encoding="utf-8")
    (folder / "questions.jsonl").write_text(_old_rows(), encoding="utf-8")

    summary = resummarize(folder, _settings())

    assert summary.authority == Rate(pass_=9, total=9)
    written = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert written["authority"] == {"pass": 9, "total": 9}


@pytest.mark.parametrize(
    ("retrieve_s", "load_s", "expected"),
    [
        # Dense and hybrid: no reranker, so no load part. 1 to 20 s, given largest first. The
        # median, (10 + 11) / 2 = 10.5; the p95, ceil(20 * 0.95) - 1 = 18: the 19th smallest, not
        # the largest.
        (
            [float(seconds) for seconds in range(20, 0, -1)],
            None,
            "Retrieve time: p50 10.50 s, p95 19.00 s (20 questions).",
        ),
        # Rerank. Sorted: 3.0, 4.0, 4.5, 6.25. The median, (4.0 + 4.5) / 2 = 4.25; the p95,
        # ceil(4 * 0.95) - 1 = 3: the largest. The load time to 1 decimal: 3.21 -> 3.2.
        (
            [4.0, 6.25, 3.0, 4.5],
            3.21,
            "Retrieve time: p50 4.25 s, p95 6.25 s (4 questions). Reranker load 3.2 s.",
        ),
        # No answerable question, so nothing was timed.
        ([], None, "Retrieve time: p50 n/a, p95 n/a (0 questions)."),
    ],
)
def test_the_retrieve_time_line(
    retrieve_s: list[float], load_s: float | None, expected: str
) -> None:
    assert timing_line(retrieve_s, load_s) == expected


@pytest.mark.parametrize(
    ("stale", "temporal", "expected"),
    [
        # The sitting's dense baseline: 39 / 100 = 0.390; 31 / 90 = 0.3444 -> 0.344.
        (
            Count(count=39, total=100),
            Rate(pass_=31, total=90),
            "Stale rate 0.390 (39 of 100 CURRENT hits)  "
            "Temporal accuracy 0.344 (31 of 90 dated HISTORY hits)",
        ),
        # 3 / 10 = 0.300; no question with a golden window.
        (
            Count(count=3, total=10),
            None,
            "Stale rate 0.300 (3 of 10 CURRENT hits)  "
            "Temporal accuracy n/a (no dated HISTORY hits)",
        ),
        # 2 / 3 = 0.6667 -> 0.667; no CURRENT question.
        (
            None,
            Rate(pass_=2, total=3),
            "Stale rate n/a (no CURRENT hits)  Temporal accuracy 0.667 (2 of 3 dated HISTORY hits)",
        ),
    ],
)
def test_the_time_line(stale: Count | None, temporal: Rate | None, expected: str) -> None:
    assert time_line(stale, temporal) == expected


def _routed(row: QuestionRow, routed: Mode, answerable: bool = True) -> QuestionRow:
    """The row with a temporal-mode route of mode `routed` (S09-T4); the rest of the route is
    filler."""
    route = RouteRecord(
        mode=routed,
        time_scope=TimeScope(kind="none", start=None, end=None),
        window=None,
        filter=None,
    )
    return row.model_copy(update={"answerable": answerable, "route": route})


def test_router_accuracy_counts_the_answerable_rows_with_a_route() -> None:
    rows = [
        _routed(_row(5.0, mode="CURRENT"), "CURRENT"),  # a match
        _routed(_row(5.0, mode="HISTORY"), "CHANGE"),  # a miss
        _routed(_row(5.0), "WHY", answerable=False),  # unanswerable: not counted
        _row(5.0, mode="WHY").model_copy(update={"answerable": True}),  # no route: not counted
    ]

    assert _summary(rows).router == Rate(pass_=1, total=2)


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        # The run contract's pinned line: 35 / 36 = 0.9722 -> 0.972.
        (
            RouterStats(
                router=Rate(pass_=35, total=36),
                windows=7,
                golden_windows=9,
                extra=0,
                current_only=10,
                windowed=7,
                unfiltered=19,
            ),
            "Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  "
            "Plans: 10 current-only, 7 windowed, 19 unfiltered",
        ),
        # 2 / 3 = 0.6667 -> 0.667. Then no golden mode at all: n/a.
        (
            RouterStats(
                router=Rate(pass_=2, total=3),
                windows=0,
                golden_windows=0,
                extra=2,
                current_only=0,
                windowed=1,
                unfiltered=2,
            ),
            "Router accuracy 0.667 (2 of 3)  Windows 0 of 0 (2 extra)  "
            "Plans: 0 current-only, 1 windowed, 2 unfiltered",
        ),
        (
            RouterStats(
                router=None,
                windows=0,
                golden_windows=0,
                extra=0,
                current_only=1,
                windowed=0,
                unfiltered=0,
            ),
            "Router accuracy n/a  Windows 0 of 0 (0 extra)  "
            "Plans: 1 current-only, 0 windowed, 0 unfiltered",
        ),
    ],
)
def test_the_router_line(stats: RouterStats, expected: str) -> None:
    assert router_line(stats) == expected


# Authority selection in the summary (S09-T7): the rows' label tiers and hits, with the golden
# labels by question id. Expected counts are by hand from the rows below.

DOCS_LABEL = Label(canonical_id="web:/docs/a/", section=None)
BLOG_LABEL = Label(canonical_id="web:/blog/2024/a/", section=None)


def _tiered(canonical_id: str, tier: int | None) -> RankedHit:
    authority = Authority(target_release=37, tier=tier, effective_stage=None, stage_confidence=None)
    return RankedHit(
        rank=1, chunk_id=7, canonical_id=canonical_id, heading_path=[], distance=0.4,
        authority=authority,
    )  # fmt: skip


def test_the_summary_counts_authority_selection_with_the_golden_labels() -> None:
    def current(question_id: str, hits: list[RankedHit]) -> QuestionRow:
        row = _row(5.0, mode="CURRENT", hits=hits)
        return row.model_copy(update={"id": question_id, "label_tiers": [1, 6]})

    rows = [
        current("q01", [_tiered("web:/blog/2024/a/", 6), _tiered("web:/docs/a/", 1)]),  # wrong
        current("q02", [_tiered("web:/docs/a/", 1)]),  # right
        _row(5.0).model_copy(update={"id": "q03", "label_tiers": []}),  # unanswerable
    ]
    labels = {"q01": [DOCS_LABEL, BLOG_LABEL], "q02": [DOCS_LABEL, BLOG_LABEL], "q03": []}

    summary = summarize("authority", SHA, STARTED_AT, rows, _settings(), labels)

    assert summary.authority == Rate(pass_=1, total=2)
    # Without the labels (as `resummarize` calls it), there is none.
    assert _summary(rows).authority is None


@pytest.mark.parametrize(
    ("authority", "current_mrr", "expected"),
    [
        # The run contract's pinned lines: 9 / 9 and 5 / 9 = 0.5556 -> 0.556.
        (
            Rate(pass_=9, total=9),
            0.7833,
            "Authority selection 1.000 (9 of 9 CURRENT questions)  CURRENT MRR 0.783",
        ),
        (
            Rate(pass_=5, total=9),
            0.637,
            "Authority selection 0.556 (5 of 9 CURRENT questions)  CURRENT MRR 0.637",
        ),
        # No CURRENT question counted, and none at all.
        (
            None,
            0.5,
            "Authority selection n/a (no CURRENT question with labels in 2+ tiers)  "
            "CURRENT MRR 0.500",
        ),
        (
            None,
            None,
            "Authority selection n/a (no CURRENT question with labels in 2+ tiers)  "
            "CURRENT MRR n/a",
        ),
    ],
)
def test_the_authority_line(
    authority: Rate | None, current_mrr: float | None, expected: str
) -> None:
    assert authority_line(authority, current_mrr) == expected


# `make eval-retrieval`'s rule-conflict line (S10-T2, pinned format). The conflicts are hand-built:
# the line reads only their kinds.


def _conflict(kind: ConflictKind) -> Conflict:
    return Conflict(
        kind=kind,
        found_by="rule",
        chunk_ids=[1],
        documents=["kep:4858"],
        summary="s",
        resolution="observed_beats_claimed",
        prevails=None,
    )


CLAIM, HISTORY = _conflict("claim_mismatch"), _conflict("history_date")


@pytest.mark.parametrize(
    ("conflicts", "expected"),
    [
        # The run contract's pinned line: one claim_mismatch in each of 5 questions, in file order.
        (
            [
                ("q01", []),
                *[(qid, [CLAIM]) for qid in ("q16", "q17", "q18", "q19")],
                ("q21", []),
                ("q32", [CLAIM]),
            ],
            "Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date",
        ),
        # A question with 2 claim mismatches counts 2 and is listed once; both kinds listed.
        (
            [("q05", [CLAIM, HISTORY]), ("q07", [CLAIM, CLAIM])],
            "Rule conflicts: 3 claim_mismatch (q05 q07), 1 history_date (q05)",
        ),
        # None at all, and no questions.
        ([("q01", [])], "Rule conflicts: 0 claim_mismatch, 0 history_date"),
        ([], "Rule conflicts: 0 claim_mismatch, 0 history_date"),
    ],
)
def test_the_rule_conflict_line(conflicts: list[tuple[str, list[Conflict]]], expected: str) -> None:
    assert conflict_line(conflicts) == expected
