"""Answer checks AC1-AC3 and the false-refusal flag on hand-built answers (S06-T3).

Every expected record is a hand-written literal: True (pass), False (fail) or None (n/a).
The retrieved hits are chunks 11, 12 and 13; chunk 99 was not retrieved.
"""

from typing import Any

import pytest

from orgknow.db.models import Hit
from orgknow.eval.checks import AnswerChecks, check_answer
from orgknow.eval.golden import Label, Question
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
    assert list(AnswerChecks.model_fields) == ["ac1", "ac2", "ac3", "false_refusal"]


# Answerable questions: AC1 and AC2 apply, AC3 is n/a.


def test_answered_with_complete_retrieved_citations_passes() -> None:
    answer = _answered(_citation(11), _citation(13))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=True, ac3=None, false_refusal=False
    )


def test_answered_with_no_citations_fails_ac1() -> None:
    # AC2 passes: no citation is outside the hits.
    assert check_answer(ANSWERABLE, HITS, _answered()) == AnswerChecks(
        ac1=False, ac2=True, ac3=None, false_refusal=False
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
        ac1=False, ac2=True, ac3=None, false_refusal=False
    )


def test_a_cited_id_outside_the_hits_fails_ac2() -> None:
    answer = _answered(_citation(11), _citation(99))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=False, ac3=None, false_refusal=False
    )


def test_a_refusal_citing_an_id_outside_the_hits_fails_ac2() -> None:
    # AC2 applies to every answer, not only `answered` ones.
    answer = _refused("Not covered.", _citation(99))
    assert check_answer(ANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=None, ac2=False, ac3=None, false_refusal=True
    )


def test_an_answerable_question_refused_is_a_false_refusal() -> None:
    # AC1 is n/a: it applies only to `answered` answers.
    assert check_answer(ANSWERABLE, HITS, _refused("Not covered.")) == AnswerChecks(
        ac1=None, ac2=True, ac3=None, false_refusal=True
    )


def test_an_answerable_error_row_is_all_na() -> None:
    # T4 counts it under errors instead.
    assert check_answer(ANSWERABLE, HITS, None) == AnswerChecks(
        ac1=None, ac2=None, ac3=None, false_refusal=None
    )


# Unanswerable questions: AC3 applies, false refusal is n/a.


def test_an_unanswerable_question_refused_with_a_reason_passes_ac3() -> None:
    assert check_answer(UNANSWERABLE, HITS, _refused("The doc is not public.")) == AnswerChecks(
        ac1=None, ac2=True, ac3=True, false_refusal=None
    )


def test_an_unanswerable_question_answered_fails_ac3() -> None:
    # Its citations are complete and retrieved, so AC1 and AC2 still pass.
    answer = _answered(_citation(12))
    assert check_answer(UNANSWERABLE, HITS, answer) == AnswerChecks(
        ac1=True, ac2=True, ac3=False, false_refusal=None
    )


@pytest.mark.parametrize("reason", ["", "   ", None], ids=["empty", "blank", "None"])
def test_a_refusal_without_a_reason_fails_ac3(reason: str | None) -> None:
    assert check_answer(UNANSWERABLE, HITS, _refused(reason)) == AnswerChecks(
        ac1=None, ac2=True, ac3=False, false_refusal=None
    )


def test_an_unanswerable_error_row_fails_ac3() -> None:
    assert check_answer(UNANSWERABLE, HITS, None) == AnswerChecks(
        ac1=None, ac2=None, ac3=False, false_refusal=None
    )
