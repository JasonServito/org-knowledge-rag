"""Answer checks: score one question's answer against AC1-AC3 (product spec), and flag a false
refusal (S06-R1 pinned formats).

Pure: a question, its hits and its answer in, a record out. No database, no network. The
answer is None when the ask failed (an error row).
"""

from collections.abc import Sequence

from pydantic import BaseModel

from orgknow.db.models import Hit
from orgknow.eval.golden import Question
from orgknow.generation.schema import Answer


class AnswerChecks(BaseModel):
    """One question's checks: True (pass), False (fail) or None (n/a). The field names are the
    results file's `checks` keys."""

    ac1: bool | None  # an `answered` answer has citations, each with its provenance and tier
    ac2: bool | None  # every cited chunk was retrieved for this question
    ac3: bool | None  # an unanswerable question got `insufficient_evidence` with a reason
    false_refusal: bool | None  # an answerable question got `insufficient_evidence`


def check_answer(question: Question, hits: Sequence[Hit], answer: Answer | None) -> AnswerChecks:
    """The checks for one question. With no answer (an error row), only AC3 applies: an
    unanswerable question fails it; an answerable one is n/a throughout, counted under errors."""
    return AnswerChecks(
        ac1=_ac1(answer),
        ac2=_ac2(hits, answer),
        ac3=_ac3(question, answer),
        false_refusal=_false_refusal(question, answer),
    )


def _ac1(answer: Answer | None) -> bool | None:
    """When `answered`: at least 1 citation, each with a source URL, a release window, a source
    type, and a tier or the superseded-proposal flag (S09-T6; S06-R1 decision 4)."""
    if answer is None or answer.answer_status != "answered":
        return None
    return bool(answer.evidence) and all(
        citation.source_url
        and citation.release_windows
        and citation.source_type
        and (citation.tier is not None or citation.superseded_proposal)
        for citation in answer.evidence
    )


def _ac2(hits: Sequence[Hit], answer: Answer | None) -> bool | None:
    """When there is an answer: every cited chunk id is among the retrieved hits."""
    if answer is None:
        return None
    retrieved = {hit.chunk_id for hit in hits}
    return all(citation.chunk_id in retrieved for citation in answer.evidence)


def _ac3(question: Question, answer: Answer | None) -> bool | None:
    """When unanswerable: `insufficient_evidence` with a non-blank reason. An error row fails."""
    if question.answerable:
        return None
    return (
        answer is not None
        and answer.answer_status == "insufficient_evidence"
        and bool((answer.insufficient_evidence_reason or "").strip())
    )


def _false_refusal(question: Question, answer: Answer | None) -> bool | None:
    """When answerable and answered at all: whether the answer is `insufficient_evidence`."""
    if not question.answerable or answer is None:
        return None
    return answer.answer_status == "insufficient_evidence"
