"""The ask pipeline (S12-T2): route, retrieve, find the rule-found conflicts, answer. One function,
`answer_question`, that `orgknow ask` (cli.py) and `POST /query` (api/app.py) both call.

One ask embeds the question, retrieves chunk texts in RETRIEVAL_MODE (dense, S04-T5; hybrid,
S07-T3; rerank, S08-T2, which needs the cross-encoder, loaded once per process; temporal, S09-T4,
which also routes the question first, with one router call, and prints the route line on stderr;
or authority, S09-T7, which does what temporal does, then reorders by the route's authority
weights), then answers from them with one model call and validates the citations (S04-T6).
Between the two, code finds the conflicts in the hits' stored facts (S10-T4), with no network
call; the answer lists them.

With a Langfuse client (both keys set), each ask leaves one trace named `ask` (ADR-006 D3). This
module is the only caller of Langfuse, and it never puts the settings or a key in a trace.
"""

import sys
import urllib.error
from collections.abc import Sequence
from typing import TYPE_CHECKING

import anthropic
import psycopg
from langfuse import Langfuse, LangfuseSpan
from psycopg.rows import TupleRow

from orgknow.db.models import Hit, TemporalFilter
from orgknow.db.releases import list_releases
from orgknow.embeddings.embedder import Embedder
from orgknow.generation.conflicts import Conflict, rule_conflicts
from orgknow.generation.generator import GenerationError, Generator, answer
from orgknow.generation.schema import Answer, TokenUsage
from orgknow.retrieval.authority import factor
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.retrieve import retrieve, temporal_plan
from orgknow.retrieval.router import Route, Router, RouterError
from orgknow.retrieval.temporal import Window
from orgknow.settings import Settings

if TYPE_CHECKING:  # for the annotation only: importing the module loads torch
    from orgknow.retrieval.cross_encoder import CrossEncoderReranker

# The failures `answer_question` raises that its callers report in one line instead of a
# traceback (`orgknow ask`: on stderr, exit 1; `POST /query`: a 502):
# - GenerationError: the model refused, was cut off, or returned output off the schema.
# - RouterError: the router model gave no route (temporal and authority modes, S09-T4, S09-T7).
# - anthropic.APIError: no connection, a timeout, or a 4xx/5xx after ANTHROPIC_MAX_RETRIES
#   retries (the SDK's rule), for the answer or the router call.
# - The Voyage client (embeddings/voyage.py): RuntimeError for an HTTP error after
#   VOYAGE_MAX_RETRIES retries, ValueError for a malformed response, and urllib's URLError or
#   TimeoutError for no connection or a timeout (it lets those two through).
ASK_ERRORS = (
    GenerationError,
    RouterError,
    anthropic.APIError,
    RuntimeError,
    ValueError,
    urllib.error.URLError,
    TimeoutError,
)

TRACING_OFF = "tracing off: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to trace each ask"


def langfuse_client(settings: Settings) -> Langfuse | None:
    """A Langfuse client from the settings' keys and base URL. With either key unset, prints
    "tracing off" and returns None: no client is built, so the SDK reads no environment variables
    and logs nothing."""
    public_key, secret_key = settings.langfuse_public_key, settings.langfuse_secret_key
    if not public_key or not secret_key:  # unset or empty: an empty SecretStr is falsy
        print(TRACING_OFF, file=sys.stderr)
        return None
    return Langfuse(
        public_key=public_key.get_secret_value(),
        secret_key=secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
    )


def load_reranker(settings: Settings) -> "CrossEncoderReranker | None":
    """The cross-encoder of rerank, temporal and authority modes, loaded once per process; None in
    the other modes.

    Its module is imported here, not at the top, so dense and hybrid never load torch. A model
    missing from the Hugging Face cache is downloaded once at the pinned revision; with no
    connection, loading raises OSError.
    """
    if settings.retrieval_mode not in ("rerank", "temporal", "authority"):
        return None
    from orgknow.retrieval.cross_encoder import CrossEncoderReranker

    return CrossEncoderReranker(settings)


def answer_question(
    question: str,
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    generator: Generator,
    settings: Settings,
    langfuse: Langfuse | None,
    reranker: Reranker | None = None,
    router: Router | None = None,
) -> Answer:
    """Answer `question`: route, retrieve, find the rule-found conflicts, answer. Raises one of
    ASK_ERRORS on an expected failure. With `langfuse`, the ask is also recorded as one trace.
    Rerank, temporal and authority modes need `reranker`; temporal and authority modes need
    `router` too, and print the route line on stderr before retrieving."""
    if langfuse is not None:
        return _traced_answer(
            question, conn, embedder, generator, settings, langfuse, reranker, router
        )
    route, _, _ = _route(question, conn, settings, router)
    hits = retrieve(question, embedder, conn, settings, reranker, route)
    found = rule_conflicts(conn, hits, settings)
    return answer(question, hits, generator, settings, found)


def route_line(route: Route, window: Window | None, temporal: TemporalFilter | None) -> str:
    """The route line an ask prints in temporal and authority modes (S09-R1): the route's mode, then
    what both searches kept: current text only, the releases asked for and searched (the window
    widened by HISTORY_WINDOW_SLACK), or no filter."""
    if temporal is None:
        kept = "no filter"
    elif temporal.current_only:
        kept = "current text only"
    else:
        assert window is not None  # `plan` widens a window: only a HISTORY window has one
        asked = _releases(window.from_release, window.until_release)
        searched = _releases(temporal.from_release, temporal.until_release)
        kept = f"releases {asked} (searched {searched})"
    return f"Route: {route.mode}, {kept}"


def _releases(from_release: int | None, until_release: int | None) -> str:
    """A release window in words: "until 1.27", "from 1.30" or "1.23 to 1.26"."""
    if from_release is None:
        return f"until 1.{until_release}"
    if until_release is None:
        return f"from 1.{from_release}"
    return f"1.{from_release} to 1.{until_release}"


def _route(
    question: str,
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    router: Router | None,
) -> tuple[Route | None, Window | None, TemporalFilter | None]:
    """In temporal and authority modes, route `question` with one router call, print the route
    line on stderr, and return the route with its window and filter (`temporal_plan`, as
    `retrieve` derives them). In other modes: (None, None, None), and no call."""
    if settings.retrieval_mode not in ("temporal", "authority"):
        return None, None, None
    if router is None:
        raise ValueError(f"{settings.retrieval_mode} mode needs a router: none was given")
    route = router.route(question)
    window, temporal = temporal_plan(conn, route, settings)
    print(route_line(route, window, temporal), file=sys.stderr)
    return route, window, temporal


def _traced_answer(
    question: str,
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    generator: Generator,
    settings: Settings,
    langfuse: Langfuse,
    reranker: Reranker | None,
    router: Router | None,
) -> Answer:
    """`retrieve`, then `answer`, recorded as one trace named `ask` (the run plan's "Trace"):
    the question in, a `retrieve` span, a `generate` generation, a `validate` span, the final JSON
    out. With no hits the model isn't called, so there is no `generate` or `validate`: the
    output's reason says "no evidence retrieved". The rule-found conflicts (S10-T4) are found
    between `retrieve` and `generate`, which logs them. In temporal and authority modes the route
    comes first, and the `retrieve` span records it with its window and filter (S09-T4; all None
    in other modes)."""
    with langfuse.start_as_current_observation(name="ask", input=question) as root:
        try:
            route, window, temporal = _route(question, conn, settings, router)
            with root.start_as_current_observation(
                name="retrieve",
                as_type="span",
                input={
                    "mode": settings.retrieval_mode,
                    "k": settings.retrieval_top_k,
                    "model": embedder.model,
                    "route": None if route is None else route.model_dump(mode="json"),
                    "window": None if window is None else window.model_dump(),
                    "filter": None if temporal is None else temporal.model_dump(),
                },
            ) as span:
                hits = retrieve(question, embedder, conn, settings, reranker, route)
                # Per hit, why it ranked there (S07-R1 decision 4, S08-T2): a score or rank is
                # None when the mode doesn't set it or that list didn't hold the text. And its
                # tier (S09-T6; None for a superseded proposal), and in authority mode its factor
                # and the product it was ordered by (S09-T7).
                factors = _factors(conn, hits, route, settings)
                span.update(
                    output=[
                        {
                            "chunk_id": h.chunk_id,
                            "distance": h.distance,
                            "rrf_score": h.rrf_score,
                            "dense_rank": h.dense_rank,
                            "lexical_rank": h.lexical_rank,
                            "rerank_score": h.rerank_score,
                            "tier": None if h.authority is None else h.authority.tier,
                            "factor": f,
                            "authority_score": h.authority_score,
                        }
                        for h, f in zip(hits, factors, strict=True)
                    ]
                )
            if hits:
                found = rule_conflicts(conn, hits, settings)
                result = _traced_generation(root, question, hits, generator, settings, found)
            else:
                result = answer(question, hits, generator, settings)
        except ASK_ERRORS as error:
            root.update(level="ERROR", status_message=one_line(error))
            raise
        result.trace_id = root.trace_id
        root.update(output=result.model_dump(mode="json"))
    return result


def _factors(
    conn: psycopg.Connection[TupleRow],
    hits: Sequence[Hit],
    route: Route | None,
    settings: Settings,
) -> list[float | None]:
    """Each hit's authority factor, as `retrieve` weighed it, in authority mode; None for each hit
    in the other modes."""
    if settings.retrieval_mode != "authority" or route is None or not hits:
        return [None] * len(hits)
    latest = list_releases(conn)[-1].minor
    boost, demote = settings.authority_boost, settings.authority_demote
    return [factor(hit, route.mode, latest, boost, demote) for hit in hits]


def _traced_generation(
    root: LangfuseSpan,
    question: str,
    hits: Sequence[Hit],
    generator: Generator,
    settings: Settings,
    found: Sequence[Conflict],
) -> Answer:
    """`answer` inside a `generate` generation, then a `validate` span.

    `answer` prompts, calls the model, validates and fills in, all in one call, so `generate`
    times that whole call and both observations are filled in from `answer.trace` afterwards: no
    step runs twice. `generate`'s metadata logs the answer's conflicts (S10-T4) and the model's
    dropped pairs (S10-T5); the rule-found ones, `found`, are in its prompt. When the answer call
    fails (one of ASK_ERRORS), `generate` gets the error and still logs `found` as its conflicts
    (S12-R1 triage g), and for a GenerationError the stop reason and any usage the API reported.
    """
    with root.start_as_current_observation(
        name="generate",
        as_type="generation",
        model=settings.generation_model,
        model_parameters={
            "effort": settings.generation_effort,
            "max_tokens": settings.generation_max_tokens,
        },
    ) as generation:
        try:
            result = answer(question, hits, generator, settings, found)
        except ASK_ERRORS as error:
            failed = error if isinstance(error, GenerationError) else None
            usage = None if failed is None else failed.usage
            generation.update(
                level="ERROR",
                status_message=str(error),
                metadata={
                    "stop_reason": None if failed is None else failed.stop_reason,
                    "conflicts": [conflict.model_dump(mode="json") for conflict in found],
                },
                usage_details=None if usage is None else _usage_details(usage),
            )
            raise
        trace = result.trace
        assert trace is not None  # `answer` called the model: there were hits
        output = trace.generation.output
        generation.update(
            input=[
                {"role": "system", "content": trace.system},
                {"role": "user", "content": trace.prompt},
            ],
            output=None if output is None else output.model_dump(mode="json"),
            usage_details=_usage_details(trace.generation.usage),
            metadata={
                "stop_reason": trace.generation.stop_reason,
                "effort": trace.effort,
                "conflicts": [conflict.model_dump(mode="json") for conflict in result.conflicts],
                "dropped_conflicts": [
                    pair.model_dump(mode="json") for pair in trace.dropped_conflicts
                ],
            },
        )
    root.start_observation(
        name="validate",
        as_type="span",
        output={"result": trace.rejection or "passed", "rejected_ids": trace.rejected_ids},
    ).end()
    return result


def _usage_details(usage: TokenUsage) -> dict[str, int]:
    """A model call's tokens as Langfuse usage details. `output` already includes the reasoning
    tokens, so `total` is set here: otherwise Langfuse sums every key and counts reasoning twice."""
    details = {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "total": usage.input_tokens + usage.output_tokens,
    }
    if usage.thinking_tokens is not None:
        details["reasoning"] = usage.thinking_tokens
    return details


def one_line(error: Exception) -> str:
    """The error's message with every run of whitespace, newlines included, as one space."""
    return " ".join(str(error).split())
