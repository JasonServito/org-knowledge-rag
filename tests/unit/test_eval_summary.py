"""The summary's p95 latencies and cost per question (S08-T3), and `make eval-resummarize`, from
hand-built rows; and `make eval-retrieval`'s timing line (S08-T4), from hand-written times.

Every expected value is by hand: a nearest-rank p95 is the value at sorted index
ceil(n * 0.95) - 1 (0-based), a median of an even count is the mean of the 2 middle values, and a
question's cost is (input * $4 + output * $20) / 1,000,000.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orgknow.eval import __main__ as eval_main
from orgknow.eval.checks import AnswerChecks
from orgknow.eval.runner import QuestionRow, Summary, summarize, timing_line
from orgknow.generation.schema import TokenUsage
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
) -> QuestionRow:
    """An unanswerable question's row; `usage` is (input, output) tokens. It passes AC3 unless
    the ask failed. The fields the new summary values don't read are filler."""
    return QuestionRow(
        id="q01",
        mode=None,
        answerable=False,
        hits=[],
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


def test_a_row_written_before_s07_still_loads() -> None:
    # The dense baseline's rows (S06): hits with only a distance, and no `retrieve_s`.
    hit = {
        "rank": 1,
        "chunk_id": 7,
        "canonical_id": "kep:2572",
        "heading_path": [],
        "distance": 0.4,
    }
    row = json.loads(_row(5.0).model_dump_json(exclude={"retrieve_s"}))

    loaded = QuestionRow.model_validate({**row, "hits": [hit]})

    assert loaded.retrieve_s is None
    assert (loaded.hits[0].rrf_score, loaded.hits[0].dense_rank) == (None, None)
    assert loaded.hits[0].lexical_rank is None


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
    """The 2 rows as `questions.jsonl` lines, without `retrieve_s`, as before S08-T3."""
    rows = [_row(2.0, usage=(1000, 100)), _row(4.0, error="APIConnectionError: Connection error.")]
    return "".join(row.model_dump_json(exclude={"retrieve_s"}) + "\n" for row in rows)


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
    assert summary == {**OLD_SUMMARY, "latency_s_p95": 4.0, "retrieve_s_p95": None}
    # Only the summary is written: the rows are unchanged, and there is no table.
    assert (folder / "questions.jsonl").read_text(encoding="utf-8") == _old_rows()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["dense-20261008T100000Z", "s04"]
    assert capsys.readouterr().out == (
        f"{folder}: p95 latency 4.000 s, retrieve p95 n/a, cost/question $0.006000\n"
    )


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
