"""The `orgknow` command (S04-T7): `orgknow ask "<question>"` prints the answer as JSON.

One ask embeds the question, retrieves chunk texts in RETRIEVAL_MODE (dense, S04-T5, or hybrid,
S07-T3), then answers from them with one model call and validates the citations (S04-T6). The
JSON goes to stdout; "tracing off" and errors go to stderr, one line each. Exit codes: 0 when an
answer prints (either status), 1 on an error, 2 on bad usage (argparse's own errors exit 2 too).

With both Langfuse keys set, each ask leaves one trace named `ask` (ADR-006 D3). This module is
the only caller of Langfuse, and it never puts the settings or a key in a trace.
"""

import argparse
import sys
import urllib.error
from collections.abc import Sequence

import anthropic
import psycopg
from langfuse import Langfuse, LangfuseSpan
from psycopg.rows import TupleRow

from orgknow.db.models import Hit
from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.generation.generator import AnthropicGenerator, GenerationError, Generator, answer
from orgknow.generation.schema import Answer, TokenUsage
from orgknow.retrieval.retrieve import retrieve
from orgknow.settings import Settings

# The failures `ask` reports as one stderr line (exit 1) instead of a traceback:
# - GenerationError: the model refused, was cut off, or returned output off the schema.
# - anthropic.APIError: no connection, a timeout, or a 4xx/5xx after the SDK's 2 retries.
# - The Voyage client (embeddings/voyage.py): RuntimeError for an HTTP error after its retries,
#   ValueError for a malformed response, and urllib's URLError or TimeoutError for no
#   connection or a timeout (it lets those two through).
ASK_ERRORS = (
    GenerationError,
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


def ask(
    question: str,
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    generator: Generator,
    settings: Settings,
    langfuse: Langfuse | None,
) -> int:
    """Answer `question`: print the answer JSON on stdout and return 0, or print one error line on
    stderr and return 1. With `langfuse`, the ask is also recorded as one trace."""
    try:
        if langfuse is None:
            hits = retrieve(question, embedder, conn, settings)
            result = answer(question, hits, generator, settings)
        else:
            result = _traced_answer(question, conn, embedder, generator, settings, langfuse)
    except ASK_ERRORS as error:
        print(f"error: {_one_line(error)}", file=sys.stderr)
        return 1
    print(result.model_dump_json())
    return 0


def _traced_answer(
    question: str,
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    generator: Generator,
    settings: Settings,
    langfuse: Langfuse,
) -> Answer:
    """`retrieve`, then `answer`, recorded as one trace named `ask` (the run contract's "Trace"):
    the question in, a `retrieve` span, a `generate` generation, a `validate` span, the final JSON
    out. With no hits the model isn't called, so there is no `generate` or `validate`: the
    output's reason says "no evidence retrieved"."""
    with langfuse.start_as_current_observation(name="ask", input=question) as root:
        try:
            with root.start_as_current_observation(
                name="retrieve",
                as_type="span",
                input={
                    "mode": settings.retrieval_mode,
                    "k": settings.retrieval_top_k,
                    "model": embedder.model,
                },
            ) as span:
                hits = retrieve(question, embedder, conn, settings)
                # Per hit, why it ranked there (S07-R1 decision 4): a score or rank is None when
                # the mode doesn't set it or that list didn't hold the text.
                span.update(
                    output=[
                        {
                            "chunk_id": h.chunk_id,
                            "distance": h.distance,
                            "rrf_score": h.rrf_score,
                            "dense_rank": h.dense_rank,
                            "lexical_rank": h.lexical_rank,
                        }
                        for h in hits
                    ]
                )
            if hits:
                result = _traced_generation(root, question, hits, generator, settings)
            else:
                result = answer(question, hits, generator, settings)
        except ASK_ERRORS as error:
            root.update(level="ERROR", status_message=_one_line(error))
            raise
        result.trace_id = root.trace_id
        root.update(output=result.model_dump(mode="json"))
    return result


def _traced_generation(
    root: LangfuseSpan,
    question: str,
    hits: Sequence[Hit],
    generator: Generator,
    settings: Settings,
) -> Answer:
    """`answer` inside a `generate` generation, then a `validate` span.

    `answer` prompts, calls the model, validates and fills in, all in one call, so `generate`
    times that whole call and both observations are filled in from `answer.trace` afterwards: no
    step runs twice. On a GenerationError, `generate` gets the error, the stop reason and any
    usage the API reported.
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
            result = answer(question, hits, generator, settings)
        except GenerationError as error:
            generation.update(
                level="ERROR",
                status_message=str(error),
                metadata={"stop_reason": error.stop_reason},
                usage_details=None if error.usage is None else _usage_details(error.usage),
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
            metadata={"stop_reason": trace.generation.stop_reason, "effort": trace.effort},
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


def _one_line(error: Exception) -> str:
    """The error's message with every run of whitespace, newlines included, as one space."""
    return " ".join(str(error).split())


def _question(argv: Sequence[str] | None) -> str:
    """The question from the command line; argparse exits 2 on bad usage or an empty question."""
    parser = argparse.ArgumentParser(prog="orgknow", description="Question the stored corpus.")
    commands = parser.add_subparsers(dest="command", required=True)
    ask_parser = commands.add_parser(
        "ask", help="answer a question from the stored chunks, printed as JSON"
    )
    ask_parser.add_argument("question")
    question: str = parser.parse_args(argv).question
    if not question.strip():
        ask_parser.error("the question is empty")
    return question


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    """`orgknow ask "<question>"`. Paid: one Voyage call and one Anthropic call per question."""
    question = _question(argv)
    settings = settings or Settings()
    anthropic_key, voyage_key = settings.anthropic_api_key, settings.voyage_api_key
    if not anthropic_key:  # unset or empty
        return _key_missing("ANTHROPIC_API_KEY")
    if not voyage_key:  # the question must be embedded
        return _key_missing("VOYAGE_API_KEY")
    langfuse = langfuse_client(settings)
    embedder = VoyageEmbedder(settings.voyage_api_url, voyage_key, settings.embedding_model)
    client = anthropic.Anthropic(api_key=anthropic_key.get_secret_value())
    generator = AnthropicGenerator(client, settings)
    try:
        with psycopg.connect(settings.database_url) as conn:
            return ask(question, conn, embedder, generator, settings, langfuse)
    finally:
        if langfuse is not None:
            langfuse.flush()  # before exit, on the error path too (ADR-006 D3)


def _key_missing(name: str) -> int:
    print(f"{name} is not set: add the key to .env (see .env.example).", file=sys.stderr)
    return 1
