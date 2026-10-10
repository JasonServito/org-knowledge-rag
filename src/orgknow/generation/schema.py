"""The answer step's models (S04-R2 decision 7): what the model returns, and what `ask` prints.

The model returns chunk ids only. Code fills each citation in from the retrieved hits, which
came from the database, so the model can never supply provenance.
"""

from typing import Literal

from pydantic import BaseModel, Field

from orgknow.db.models import Confidence

AnswerStatus = Literal["answered", "insufficient_evidence"]


# The schema the model's output is constrained to (`messages.parse`). Comments, not docstrings,
# on this class: pydantic would send a docstring to the model as the schema's description.
class ModelAnswer(BaseModel):
    answer_status: AnswerStatus
    answer: str
    evidence: list[int] = Field(description="The ids of the chunks that support the answer.")
    insufficient_evidence_reason: str | None = Field(
        description="Why the evidence can't answer the question; null when answered."
    )


class TokenUsage(BaseModel):
    """The tokens one model call used, as the API reports them."""

    input_tokens: int
    output_tokens: int  # the billed total, reasoning included
    thinking_tokens: int | None  # the reasoning part of output_tokens; None when not reported


class Generation(BaseModel):
    """One model call: what a `Generator` returns."""

    output: ModelAnswer | None  # None: no answer came back (e.g. a refusal)
    stop_reason: str | None
    usage: TokenUsage


class Evidence(BaseModel):
    """One citation, filled in from a retrieved hit (never from the model)."""

    chunk_id: int
    document: str  # the canonical id
    title: str
    section: str | None  # the heading path joined with " > "; None before any heading
    source_type: str
    release_windows: list[tuple[str, str | None]]  # ("1.24", "1.29"); None: still valid
    claimed_status: str | None
    claimed_stage: str | None
    # The hit's authority at the target release (S09-T6). Defaults, so answers saved before it
    # still load: no tier and not a superseded proposal, which AC1 fails.
    tier: int | None = None  # None: a superseded proposal, or no authority on the hit
    superseded_proposal: bool = False  # a KEP claiming withdrawn, rejected or replaced
    effective_stage: str | None = None  # a KEP's stage at the target release
    stage_confidence: Confidence | None = None  # high: observed; low: the claim
    source_url: str  # the file on GitHub at the snapshot commit


class AnswerTrace(BaseModel):
    """What the trace logs about one model call (T7), so no step runs twice."""

    system: str
    prompt: str
    effort: str
    generation: Generation  # the raw output stays here, even when it was rejected
    rejection: str | None  # the rejection reason; None: the citations passed
    rejected_ids: list[int]  # cited ids outside the retrieved set


class Answer(BaseModel):
    """The answer to one question: `ask` prints it as JSON (S04-R2, pinned format)."""

    question: str
    answer_status: AnswerStatus
    answer: str
    evidence: list[Evidence]
    insufficient_evidence_reason: str | None
    model: str
    trace_id: str | None = None  # set by the CLI when tracing is on (T7)
    # Not printed. None when the model wasn't called (no hits).
    trace: AnswerTrace | None = Field(default=None, exclude=True)
