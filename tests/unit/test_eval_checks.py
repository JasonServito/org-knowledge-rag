"""Answer checks AC1-AC3 and the false-refusal flag on hand-built answers (S06-T3; AC1's tier,
S09-T6), the losing-side flag (S10-T5, ADR-010 D3), and the AC5 and AC6 rules (S12-T1, S12-R1
decisions 3 and 4).

Every expected record is a hand-written literal: True (pass), False (fail) or None (n/a).
The retrieved hits are chunks 11, 12 and 13; chunk 99 was not retrieved.
"""

from typing import Any

import pytest

from orgknow.db.models import Hit
from orgknow.eval.checks import AnswerChecks, check_ac5, check_ac6, check_answer
from orgknow.eval.golden import Label, Question
from orgknow.generation.conflicts import Conflict
from orgknow.generation.schema import Answer, Evidence


def _hit(chunk_id: int) -> Hit:
    """A retrieved hit; the checks read only its chunk id."""
    return Hit(
        chunk_id=chunk_id,
        content_hash="a" * 64,
        distance=0.3,
        text="text",
        canonical_id="web:/docs/a/",
        source_type="docs_page",
        heading_path=["Install"],
        release_windows=[(30, None)],
        current=True,
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="website",
        snapshot_sha="0" * 40,
        source_path="content/en/docs/a.md",
        metadata={},
    )


HITS = [_hit(11), _hit(12), _hit(13)]

ANSWERABLE = Question(
    id="q01",
    question="How do I install it?",
    mode="CURRENT",
    answerable=True,
    expected_answer="Like this.",
    smoke=False,
    labels=[Label(canonical_id="web:/docs/a/", section=["Install"])],
)
UNANSWERABLE = Question(
    id="q02",
    question="What did the private design doc decide?",
    answerable=False,
    expected_answer="insufficient_evidence: the doc is not public.",
    smoke=False,
    labels=[],
)


def _citation(chunk_id: int, **changes: Any) -> Evidence:
    """A citation with every AC1 field filled in, then `changes` applied."""
    fields: dict[str, Any] = {
        "chunk_id": chunk_id,
        "document": "web:/docs/a/",
        "title": "A",
        "section": "Install",
        "source_type": "docs_page",
        "release_windows": [("1.30", None)],
        "claimed_status": None,
        "claimed_stage": None,
        "tier": 1,
        "source_url": "https://github.com/kubernetes/website/blob/0/content/en/docs/a.md",
    }
    return Evidence(**(fields | changes))


def _answered(*citations: Evidence) -> Answer:
    return Answer(
        question="q",
        answer_status="answered",
        answer="Like this.",
        evidence=list(citations),
        insufficient_evidence_reason=None,
        model="m",
    )


def _refused(reason: str | None, *citations: Evidence) -> Answer:
    return Answer(
        question="q",
        answer_status="insufficient_evidence",
        answer="",
        evidence=list(citations),
        insufficient_evidence_reason=reason,
        model="m",
    )


def test_the_record_keys_are_the_results_file_checks_keys() -> None:
    assert list(AnswerChecks.model_fields) == [
        "ac1",
        "ac2",
        "ac3",
        "false_refusal",
        "loser_only",
    ]


# Answerable questions: AC1 and AC2 apply, AC3 is n/a.


def test_answered_with_complete_retrieved_citations_passes() -> None:
    answer = _answered(_citation(11), _citation(13))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=True, ac3=None, false_refusal=False, loser_only=False
    )


def test_answered_with_no_citations_fails_ac1() -> None:
    # AC2 passes: no citation is outside the hits.
    assert check_answer(ANSWERABLE, HITS, _answered()) == AnswerChecks(
        ac1=False, ac2=True, ac3=None, false_refusal=False, loser_only=False
    )


@pytest.mark.parametrize(
    "changes",
    [{"source_url": ""}, {"release_windows": []}, {"source_type": ""}],
    ids=["empty source_url", "no release windows", "empty source_type"],
)
def test_a_citation_missing_a_field_fails_ac1(changes: dict[str, Any]) -> None:
    # One complete citation, one missing a field: each citation must be complete.
    answer = _answered(_citation(11), _citation(12, **changes))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=False, ac2=True, ac3=None, false_refusal=False, loser_only=False
    )


def test_a_citation_with_no_tier_that_isnt_a_superseded_proposal_fails_ac1() -> None:
    # S09-T6: e.g. a hit that never had its authority attached.
    answer = _answered(_citation(11), _citation(12, tier=None))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=False, ac2=True, ac3=None, false_refusal=False, loser_only=False
    )


def test_a_superseded_proposal_with_no_tier_passes_ac1() -> None:
    citation = _citation(12, source_type="kep", tier=None, superseded_proposal=True)
    answer = _answered(_citation(11), citation)
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=True, ac3=None, false_refusal=False, loser_only=False
    )


def test_a_cited_id_outside_the_hits_fails_ac2() -> None:
    answer = _answered(_citation(11), _citation(99))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=False, ac3=None, false_refusal=False, loser_only=False
    )


def test_a_refusal_citing_an_id_outside_the_hits_fails_ac2() -> None:
    # AC2 applies to every answer, not only `answered` ones.
    answer = _refused("Not covered.", _citation(99))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=None, ac2=False, ac3=None, false_refusal=True, loser_only=False
    )


def test_an_answerable_question_refused_is_a_false_refusal() -> None:
    # AC1 is n/a: it applies only to `answered` answers.
    assert check_answer(ANSWERABLE, HITS, _refused("Not covered.")) == AnswerChecks(
        ac1=None, ac2=True, ac3=None, false_refusal=True, loser_only=False
    )


def test_an_answerable_error_row_is_all_na() -> None:
    # T4 counts it under errors instead.
    assert check_answer(ANSWERABLE, HITS, None) == AnswerChecks(
        ac1=None, ac2=None, ac3=None, false_refusal=None
    )


# Unanswerable questions: AC3 applies, false refusal is n/a.


def test_an_unanswerable_question_refused_with_a_reason_passes_ac3() -> None:
    assert check_answer(UNANSWERABLE, HITS, _refused("The doc is not public.")) == AnswerChecks(
        ac1=None, ac2=True, ac3=True, false_refusal=None, loser_only=False
    )


def test_an_unanswerable_question_answered_fails_ac3() -> None:
    # Its citations are complete and retrieved, so AC1 and AC2 still pass.
    answer = _answered(_citation(12))
    assert check_answer(UNANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=True, ac3=False, false_refusal=None, loser_only=False
    )


@pytest.mark.parametrize("reason", ["", "   ", None], ids=["empty", "blank", "None"])
def test_a_refusal_without_a_reason_fails_ac3(reason: str | None) -> None:
    assert check_answer(UNANSWERABLE, HITS, _refused(reason)) == AnswerChecks(
        ac1=None, ac2=True, ac3=False, false_refusal=None, loser_only=False
    )


def test_an_unanswerable_error_row_fails_ac3() -> None:
    assert check_answer(UNANSWERABLE, HITS, None) == AnswerChecks(
        ac1=None, ac2=None, ac3=False, false_refusal=None
    )


# The losing-side flag (S10-T5): a model-found conflict's prevailing chunk not cited, the other
# one cited. Chunk 12 prevails over chunk 11 in MODEL_PAIR (by tier, say).

MODEL_PAIR = Conflict(
    kind="contradiction",
    found_by="model",
    chunk_ids=[11, 12],
    documents=["web:/docs/a/"],
    summary="11 says four releases; 12 says three.",
    resolution="lower_tier",
    prevails=12,
)
UNRESOLVED_PAIR = MODEL_PAIR.model_copy(update={"resolution": "unresolved", "prevails": None})


def _with(answer: Answer, *conflicts: Conflict) -> Answer:
    return answer.model_copy(update={"conflicts": list(conflicts)})


@pytest.mark.parametrize(
    ("cited", "conflicts", "loser_only"),
    [
        ([11], [MODEL_PAIR], True),  # the loser cited, the winner not
        ([11, 12], [MODEL_PAIR], False),  # both cited
        ([12], [MODEL_PAIR], False),  # the winner alone
        ([13], [MODEL_PAIR], False),  # neither
        ([11], [UNRESOLVED_PAIR], False),  # nothing prevails
        ([11], [], False),  # no conflict
    ],
    ids=["loser-only", "both", "winner-only", "neither", "unresolved", "no-conflict"],
)
def test_loser_only_on_an_answer(
    cited: list[int], conflicts: list[Conflict], loser_only: bool
) -> None:
    answer = _with(_answered(*(_citation(chunk_id) for chunk_id in cited)), *conflicts)

    assert check_answer(ANSWERABLE, HITS, answer).loser_only is loser_only


def test_loser_only_on_a_refusal_citing_the_loser() -> None:
    # The model's own insufficient_evidence is still an answer, with its citations.
    answer = _with(_refused("They disagree.", _citation(11)), MODEL_PAIR)

    assert check_answer(ANSWERABLE, HITS, answer).loser_only is True


def test_loser_only_ignores_a_rule_found_conflict() -> None:
    # A rule-found conflict never sets `prevails`; a hand-built one that did is still ignored.
    rule = MODEL_PAIR.model_copy(update={"found_by": "rule"})
    answer = _with(_answered(_citation(11)), rule)

    assert check_answer(ANSWERABLE, HITS, answer).loser_only is False


def test_loser_only_is_na_with_no_answer() -> None:
    assert check_answer(ANSWERABLE, HITS, None).loser_only is None


# AC5 and AC6 (S12-T1): one answer each, with the latest release 1.37 (minor 37) and, for AC6, the
# golden window 1.20 to 1.23 (minors 20 to 23) unless a test says otherwise. Which questions each
# applies to is the summary's part (test_eval_summary.py). A citation's release windows are
# ("from", "until") strings, an open until None, as the answer prints them.

LATEST = 37
WINDOW = (20, 23)


def _cited(*windows: list[tuple[str, str | None]]) -> Answer:
    """An `answered` answer with one citation per list of release windows."""
    return _answered(*(_citation(11, release_windows=w) for w in windows))


def test_ac5_an_open_window_is_valid_at_the_latest_release() -> None:
    assert check_ac5(_cited([("1.24", None)]), LATEST) is True


def test_ac5_a_window_ending_exactly_at_the_latest_release_is_valid() -> None:
    # A 1.37 CHANGELOG section (changelog:1.37): from 1.37 until 1.37 holds 1.37.
    assert check_ac5(_cited([("1.37", "1.37")]), LATEST) is True


def test_ac5_a_window_ending_one_release_before_the_latest_fails() -> None:
    assert check_ac5(_cited([("1.30", "1.36")]), LATEST) is False


def test_ac5_a_citation_is_valid_when_any_one_of_its_windows_holds_the_latest() -> None:
    # One citation, two windows (a text valid 1.20-1.22, then again from 1.35): the second holds 37.
    assert check_ac5(_cited([("1.20", "1.22"), ("1.35", None)]), LATEST) is True


def test_ac5_needs_every_citation_valid_one_old_citation_fails_it() -> None:
    # The mixed-citation case: the first citation is open (valid), the second ended at 1.30.
    assert check_ac5(_cited([("1.24", None)], [("1.20", "1.30")]), LATEST) is False


def test_ac5_two_valid_citations_pass() -> None:
    assert check_ac5(_cited([("1.24", None)], [("1.37", "1.37")]), LATEST) is True


def test_ac5_a_refusal_fails_even_with_valid_citations() -> None:
    answer = _refused("The sources don't say.", _citation(11, release_windows=[("1.24", None)]))

    assert check_ac5(answer, LATEST) is False


def test_ac5_an_error_row_fails() -> None:
    assert check_ac5(None, LATEST) is False


def test_ac5_an_answered_answer_with_no_citations_fails() -> None:
    # The pipeline rejects it (AC1, `rejection_reason`); a hand-built one fails AC5 too.
    assert check_ac5(_answered(), LATEST) is False


def test_ac6_one_citation_in_the_window_is_enough() -> None:
    # The first citation is 1.24 on (after 1.23: outside), the second 1.21 alone (inside).
    assert check_ac6(_cited([("1.24", None)], [("1.21", "1.21")]), WINDOW) is True


@pytest.mark.parametrize(
    ("windows", "expected"),
    [
        ([("1.18", "1.20")], True),  # ends at the window's first release: inside
        ([("1.23", None)], True),  # starts at the window's last release: inside
        ([("1.17", "1.19")], False),  # ends 1 release before the window: outside, no slack
        ([("1.24", None)], False),  # starts 1 release after the window: outside, no slack
    ],
    ids=["ends-at-from", "starts-at-until", "ends-one-before", "starts-one-after"],
)
def test_ac6_the_window_is_exact_at_both_ends(
    windows: list[tuple[str, str | None]], expected: bool
) -> None:
    assert check_ac6(_cited(windows), WINDOW) is expected


@pytest.mark.parametrize(
    ("window", "windows", "expected"),
    [
        ((None, 20), [("1.10", "1.21")], True),  # "until 1.20": 1.10-1.21 overlaps it
        ((None, 20), [("1.21", None)], False),  # "until 1.20": 1.21 on doesn't
        ((30, None), [("1.24", None)], True),  # "from 1.30": an open 1.24 on overlaps it
        ((30, None), [("1.24", "1.29")], False),  # "from 1.30": 1.24-1.29 doesn't
    ],
    ids=["until-in", "until-out", "from-in", "from-out"],
)
def test_ac6_an_open_golden_end_is_open(
    window: tuple[int | None, int | None], windows: list[tuple[str, str | None]], expected: bool
) -> None:
    assert check_ac6(_cited(windows), window) is expected


def test_ac6_a_refusal_fails_even_with_a_citation_in_the_window() -> None:
    answer = _refused("The sources don't say.", _citation(11, release_windows=[("1.21", None)]))

    assert check_ac6(answer, WINDOW) is False


def test_ac6_an_error_row_fails() -> None:
    assert check_ac6(None, WINDOW) is False


def test_ac6_an_answered_answer_with_no_citations_fails() -> None:
    assert check_ac6(_answered(), WINDOW) is False
