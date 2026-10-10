"""The query router (S09-T2, ADR-009 D1): one model call sorts a question into a mode and copies
the time scope it names, before any search runs.

- `Route`: what the model returns (structured output): the mode, and the time scope's relation
  and value(s) as written ("before", "1.28"). The model never turns a value into releases;
  `temporal.resolve_window` does, from the `releases` table (ADR-009 D2).
- `Router`: the interface, question in, route out. The real one is `ClaudeRouter`; tests use a
  fake, so they never call the API (like the embedder and the reranker).
"""

from typing import Literal, Protocol

import anthropic
from pydantic import BaseModel

from orgknow.settings import Settings

# What the router picks; the golden set labels the same 4 (eval/golden.py).
Mode = Literal["CURRENT", "HISTORY", "CHANGE", "WHY"]

# The S09-R1 sitting's prompt, word for word: its measured accuracy (ADR-009) is for this text.
# It defines the modes from ADR-003 D4 and the blueprint, not from golden-set questions. The eval's
# stored routes record its hash, so editing it makes them an error (ADR-009 D3).
SYSTEM_PROMPT = """\
You sort questions about Kubernetes by what they ask for, before a search runs.

Modes:
- CURRENT: how something is now, in the latest release. Use this when the question names no \
past time and asks about present behavior or advice.
- HISTORY: how something was at a past time, in a past release, or before some change.
- CHANGE: how something changed over time: when it was introduced, promoted (alpha, beta, GA), \
deprecated, frozen or removed, or the sequence of those steps.
- WHY: the reason, motivation or rationale for a design or a change.

Time scope: only a Kubernetes release ("1.N") or a calendar year that the question names \
explicitly. Give the relation (before, in, after, since, between) and the value(s) as written \
("1.28", "2021"). If the question names no release number or year, the kind is "none"; never \
infer a release from an event.
"""


# The schema the model's output is constrained to (`messages.parse`), as the sitting measured it.
# Comments, not docstrings, on these classes: pydantic would send a docstring to the model as the
# schema's description.
class TimeScope(BaseModel):
    kind: Literal["none", "before", "in", "after", "since", "between"]
    start: str | None
    end: str | None


class Route(BaseModel):
    mode: Mode
    time_scope: TimeScope


class RouterError(Exception):
    """The model gave no route: it refused, was cut off, or stopped for another reason."""


class Router(Protocol):
    def route(self, question: str) -> Route:
        """The question's mode and the time scope it names."""
        ...


class ClaudeRouter:
    """The `Router` on the Anthropic API: `messages.parse` with the route schema, at
    ROUTER_MODEL, ROUTER_EFFORT and ROUTER_MAX_TOKENS.

    As in the generator, the SDK's defaults stay (a 10-minute timeout and 2 retries) and there is
    no `fallbacks` parameter. `input_tokens` and `output_tokens` add up the usage of every call
    this router made, refused ones included, for the cost.
    """

    def __init__(self, client: anthropic.Anthropic, settings: Settings) -> None:
        self._client = client
        self._model = settings.router_model
        self._effort = settings.router_effort
        self._max_tokens = settings.router_max_tokens
        self.input_tokens = 0
        self.output_tokens = 0  # reasoning included, as billed

    def route(self, question: str) -> Route:
        """The model's route for `question`. Raises RouterError when the model stops for any
        reason but `end_turn` or returns no route; output off the schema (cut off partway) raises
        pydantic's ValidationError inside the SDK, before any usage is counted."""
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
            output_format=Route,
            output_config={"effort": self._effort},
        )
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise RouterError(f"no route from the model (stop reason: {response.stop_reason})")
        return response.parsed_output
