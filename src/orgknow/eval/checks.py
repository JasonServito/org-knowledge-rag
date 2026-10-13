"""Answer checks: score one question's answer against AC1-AC3 (product spec), flag a false
refusal (S06-R1 pinned formats), and flag an answer citing only the losing side of a model-found
conflict (S10-T5, ADR-010 D3). And the AC5 and AC6 rules on one answer's citations (S12-T1),
which the summary applies per golden question.

Pure: a question, its hits and its answer in, a record out. No database, no network. The
answer is None when the ask failed (an error row).
"""

from collections.abc import Sequence

from pydantic import BaseModel

from orgknow.db.models import Hit
from orgknow.eval.golden import Question
from orgknow.eval.metrics import GoldenWindow, in_window
from orgknow.generation.schema import Answer, Evidence


class AnswerChecks(BaseModel):
    """One question's checks: True (pass), False (fail) or None (n/a). The field names are the
    results file's `checks` keys."""

    ac1: bool | None  # an `answered` answer has citations, each with its provenance and tier
    ac2: bool | None  # every cited chunk was retrieved for this question
    ac3: bool | None  # an unanswerable question got `insufficient_evidence` with a reason
    false_refusal: bool | None  # an answerable question got `insufficient_evidence`
    # S10-T5: the answer cites only the losing side of a model-found conflict. None in older
    # folders.
    loser_only: bool | None = None


def check_answer(question: Question, hits: Sequence[Hit], answer: Answer | None) -> AnswerChecks:
    """The checks for one question. With no answer (an error row), only AC3 applies: an
    unanswerable question fails it; an answerable one is n/a throughout, counted under errors."""
    return AnswerChecks(
        ac1=_ac1(answer),
        ac2=_ac2(hits, answer),
        ac3=_ac3(question, answer),
        false_refusal=_false_refusal(question, answer),
        loser_only=_loser_only(answer),
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


def _loser_only(answer: Answer | None) -> bool | None:
    """When there is an answer: whether, for some model-found conflict with a prevailing chunk,
    the evidence cites the other chunk but not the prevailing one (ADR-010 D3)."""
    if answer is None:
        return None
    cited = {citation.chunk_id for citation in answer.evidence}
    return any(
        conflict.found_by == "model"
        and conflict.prevails is not None
        and conflict.prevails not in cited
        and any(chunk_id in cited for chunk_id in conflict.chunk_ids)
        for conflict in answer.conflicts
    )


# AC5 and AC6 (S12-T1; S12-R1 decisions 3 and 4). The summary picks the questions each applies to,
# from the golden file: AC5 the answerable CURRENT ones, AC6 the answerable HISTORY ones with a
# golden window. A refusal or an error row (no answer) fails both.


def check_ac5(answer: Answer | None, latest: int) -> bool:
    """AC5: the answer is `answered` and every citation is valid at the latest release (`latest`,
    a minor): one of its release windows holds it, from <= latest <= until, an open until holding
    it. An `answered` answer with no citations fails, as AC1 does."""
    return (
        answer is not None
        and answer.answer_status == "answered"
        and bool(answer.evidence)
        # Holding a release is overlapping the one-release window [latest, latest].
        and all(in_window(_minors(c), (latest, latest)) for c in answer.evidence)
    )


def check_ac6(answer: Answer | None, window: GoldenWindow) -> bool:
    """AC6: the answer is `answered` and at least one citation's release windows overlap the
    golden `window` (minors), exactly: `in_window`, with no slack."""
    return (
        answer is not None
        and answer.answer_status == "answered"
        and any(in_window(_minors(c), window) for c in answer.evidence)
    )


def _minors(citation: Evidence) -> list[tuple[int, int | None]]:
    """A citation's release windows as minors: ("1.24", None) is (24, None)."""

    def minor(release: str) -> int:
        return int(release.removeprefix("1."))

    return [
        (minor(start), None if until is None else minor(until))
        for start, until in citation.release_windows
    ]
