"""The answer step (S04-T6): prompt, one model call, validate, fill in (ADR-006 D1-D2).

`answer()` is the only entry point; the CLI (T7) calls it with an `AnthropicGenerator`, and tests
call it with a fake. A refusal or a cut-off answer is a `GenerationError`, never a crash.
"""

from collections.abc import Sequence
from typing import Protocol

import anthropic
import pydantic

from orgknow.db.models import Hit
from orgknow.generation.conflicts import Conflict, model_conflicts
from orgknow.generation.prompt import SYSTEM_PROMPT, user_prompt
from orgknow.generation.schema import (
    Answer,
    AnswerTrace,
    Generation,
    ModelAnswer,
    TokenUsage,
)
from orgknow.generation.validate import cited_ids, fill_in, out_of_set_ids, rejection_reason
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.settings import Settings


class GenerationError(Exception):
    """The model gave no usable answer: it refused, was cut off, or returned no output."""

    def __init__(
        self, message: str, stop_reason: str | None, usage: TokenUsage | None = None
    ) -> None:
        super().__init__(message)
        self.stop_reason = stop_reason  # None when the SDK lost it (output off the schema)
        self.usage = usage


class Generator(Protocol):
    """One model call: a system prompt and a user message in, a `Generation` out."""

    def generate(self, system: str, prompt: str) -> Generation: ...


class AnthropicGenerator:
    """The `Generator` on the Anthropic API: `messages.parse` with the answer schema.

    The SDK's defaults stay: a 10-minute timeout and 2 retries. No `fallbacks` parameter: a
    refusal is an error here, not a reroute to another model (ADR-006).
    """

    def __init__(self, client: anthropic.Anthropic, settings: Settings) -> None:
        self._client = client
        self._model = settings.generation_model
        self._effort = settings.generation_effort
        self._max_tokens = settings.generation_max_tokens

    def generate(self, system: str, prompt: str) -> Generation:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=ModelAnswer,
                # The SDK merges the schema into output_config as its `format`. Opus 5.5 always
                # reasons (no `thinking` parameter); effort sets how much.
                output_config={"effort": self._effort},
            )
        except pydantic.ValidationError as error:
            # The SDK parses the output before it returns: text that isn't the schema's JSON
            # (cut off or refused partway) raises here, and the stop reason is lost with it.
            message = (
                "the model's output was cut off or refused partway (stop reason unknown): "
                "it doesn't match the answer schema"
            )
            raise GenerationError(message, stop_reason=None) from error
        details = response.usage.output_tokens_details
        return Generation(
            output=response.parsed_output,
            stop_reason=response.stop_reason,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                thinking_tokens=None if details is None else details.thinking_tokens,
            ),
        )


def checked_output(generation: Generation) -> ModelAnswer:
    """The model's answer, if it finished one. A refusal, a cut-off (`max_tokens`) or any other
    stop but `end_turn`, or no output at all, raises GenerationError."""
    if generation.stop_reason != "end_turn" or generation.output is None:
        raise GenerationError(
            f"no usable answer from the model (stop reason: {generation.stop_reason})",
            generation.stop_reason,
            generation.usage,
        )
    return generation.output


def answer(
    question: str,
    hits: Sequence[Hit],
    generator: Generator,
    settings: Settings,
    rule_conflicts: Sequence[Conflict] = (),
) -> Answer:
    """Answer `question` from `hits` with one model call, then validate and fill in citations.

    No hits: `insufficient_evidence` without calling the model, and no conflicts. A rejected
    answer becomes `insufficient_evidence` (decision 8); the rejected output stays in `trace`.
    Raises GenerationError when the model gives no usable answer.

    `rule_conflicts` are the hits' rule-found conflicts (`conflicts.rule_conflicts`, S10-T4):
    the prompt lists them after the evidence, and every answer with hits carries them, rejected
    or not. After them come the pairs the model listed that `model_conflicts` keeps (S10-T5);
    the rest go to `trace.dropped_conflicts`. A rejected answer keeps none of the model's pairs:
    its output isn't trusted. No conflict id goes through the citation check (ADR-010 D3), so a
    bad pair never changes the answer.
    """
    if not hits:
        return _insufficient(question, "no evidence retrieved", settings, trace=None, conflicts=[])
    repo_urls = load_repo_urls(settings.corpus_manifest_path)  # before the paid call
    prompt = user_prompt(question, hits, rule_conflicts)
    generation = generator.generate(SYSTEM_PROMPT, prompt)
    output = checked_output(generation)

    by_id = {hit.chunk_id: hit for hit in hits}
    rejection = rejection_reason(output, by_id.keys())
    if rejection is None:
        found, dropped = model_conflicts(output.conflicts, hits, rule_conflicts)
    else:
        found, dropped = [], list(output.conflicts)
    trace = AnswerTrace(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        effort=settings.generation_effort,
        generation=generation,
        rejection=rejection,
        rejected_ids=out_of_set_ids(output, by_id.keys()),
        dropped_conflicts=dropped,
    )
    if rejection is not None:
        return _insufficient(question, rejection, settings, trace, conflicts=list(rule_conflicts))
    return Answer(
        question=question,
        answer_status=output.answer_status,
        answer=output.answer,
        evidence=[fill_in(by_id[chunk_id], repo_urls) for chunk_id in cited_ids(output)],
        conflicts=[*rule_conflicts, *found],
        insufficient_evidence_reason=output.insufficient_evidence_reason,
        model=settings.generation_model,
        trace=trace,
    )


def _insufficient(
    question: str,
    reason: str,
    settings: Settings,
    trace: AnswerTrace | None,
    conflicts: list[Conflict],
) -> Answer:
    return Answer(
        question=question,
        answer_status="insufficient_evidence",
        answer="",
        evidence=[],
        conflicts=conflicts,
        insufficient_evidence_reason=reason,
        model=settings.generation_model,
        trace=trace,
    )
