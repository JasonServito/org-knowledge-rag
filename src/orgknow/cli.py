"""The `orgknow` command (S04-T7): `orgknow ask "<question>"` prints the answer as JSON.

The ask itself (route, retrieve, rule-found conflicts, answer, and its Langfuse trace) is
`pipeline.answer_question`, which `POST /query` calls too (S12-T2). This module checks the keys,
builds the clients and prints. The JSON goes to stdout; "tracing off", the route line and errors
go to stderr, one line each. Exit codes: 0 when an answer prints (either status), 1 on an error,
2 on bad usage (argparse's own errors exit 2 too).
"""

import argparse
import sys
from collections.abc import Sequence

import anthropic
import psycopg
from langfuse import Langfuse
from psycopg.rows import TupleRow

from orgknow.embeddings.embedder import Embedder
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.generation.generator import AnthropicGenerator, Generator
from orgknow.pipeline import ASK_ERRORS, answer_question, langfuse_client, load_reranker, one_line

# Re-exported: the route line's tests import it from here, where it lived before S12-T2.
from orgknow.pipeline import route_line as route_line
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.router import ClaudeRouter, Router
from orgknow.settings import Settings


def ask(
    question: str,
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder,
    generator: Generator,
    settings: Settings,
    langfuse: Langfuse | None,
    reranker: Reranker | None = None,
    router: Router | None = None,
) -> int:
    """Answer `question` (`answer_question`): print the answer JSON on stdout and return 0, or
    print one error line on stderr and return 1."""
    try:
        result = answer_question(
            question, conn, embedder, generator, settings, langfuse, reranker, router
        )
    except ASK_ERRORS as error:
        print(f"error: {one_line(error)}", file=sys.stderr)
        return 1
    print(result.model_dump_json())
    return 0


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
    """`orgknow ask "<question>"`. Paid: one Voyage call and one Anthropic call per question, and
    in temporal and authority modes one more Anthropic call, the router's."""
    question = _question(argv)
    settings = settings or Settings()
    anthropic_key, voyage_key = settings.anthropic_api_key, settings.voyage_api_key
    if not anthropic_key:  # unset or empty
        return _key_missing("ANTHROPIC_API_KEY")
    if not voyage_key:  # the question must be embedded
        return _key_missing("VOYAGE_API_KEY")
    try:
        reranker = load_reranker(settings)
    except OSError as error:  # the model isn't cached and Hugging Face can't be reached
        print(f"error: {one_line(error)}", file=sys.stderr)
        return 1
    langfuse = langfuse_client(settings)
    embedder = VoyageEmbedder(settings.voyage_api_url, voyage_key, settings.embedding_model)
    client = anthropic.Anthropic(api_key=anthropic_key.get_secret_value())
    generator = AnthropicGenerator(client, settings)
    routed = settings.retrieval_mode in ("temporal", "authority")
    router = ClaudeRouter(client, settings) if routed else None
    try:
        with psycopg.connect(settings.database_url) as conn:
            return ask(question, conn, embedder, generator, settings, langfuse, reranker, router)
    finally:
        if langfuse is not None:
            langfuse.flush()  # before exit, on the error path too (ADR-006 D3)


def _key_missing(name: str) -> int:
    print(f"{name} is not set: add the key to .env (see .env.example).", file=sys.stderr)
    return 1
