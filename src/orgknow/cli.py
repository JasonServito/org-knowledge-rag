"""The `orgknow` command (S04-T7): `orgknow ask "<question>"` prints the answer as JSON, and
`orgknow chain <canonical_id>` prints a stored decision chain (S13-T3).

The ask itself (route, retrieve, rule-found conflicts, answer, and its Langfuse trace) is
`pipeline.answer_question`, which `POST /query` calls too (S12-T2). This module checks the keys,
builds the clients and prints. The JSON goes to stdout; "tracing off", the route line and errors
go to stderr, one line each. Exit codes: 0 when an answer prints (either status), 1 on an error,
2 on bad usage (argparse's own errors exit 2 too).

A chain is read by `provenance.chain.load_chain`, which the API calls too (T5); `make chains`
builds it, never this command. Free: no API call. Exit 0 when it prints, 1 with one stderr line
when it isn't stored.
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
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.pipeline import ASK_ERRORS, answer_question, langfuse_client, load_reranker, one_line

# Re-exported: the route line's tests import it from here, where it lived before S12-T2.
from orgknow.pipeline import route_line as route_line
from orgknow.provenance.chain import chain_lines, load_chain
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


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    """The command and its argument; argparse exits 2 on bad usage or an empty question."""
    parser = argparse.ArgumentParser(prog="orgknow", description="Question the stored corpus.")
    commands = parser.add_subparsers(dest="command", required=True)
    ask_parser = commands.add_parser(
        "ask", help="answer a question from the stored chunks, printed as JSON"
    )
    ask_parser.add_argument("question")
    chain_parser = commands.add_parser(
        "chain", help="print a seed KEP's stored decision chain (built by `make chains`)"
    )
    chain_parser.add_argument("canonical_id", help="the seed KEP, e.g. kep:2572")
    arguments = parser.parse_args(argv)
    if arguments.command == "ask" and not arguments.question.strip():
        ask_parser.error("the question is empty")
    return arguments


def chain(canonical_id: str, conn: psycopg.Connection[TupleRow], settings: Settings) -> int:
    """Print the stored chain of `canonical_id` (`load_chain`) and return 0, or print one line on
    stderr and return 1 when none is stored. Never builds."""
    stored = load_chain(conn, canonical_id, load_repo_urls(settings.corpus_manifest_path))
    if stored is None:
        print(
            f"no stored decision chain for {canonical_id}; chains are built by make chains",
            file=sys.stderr,
        )
        return 1
    print("\n".join(chain_lines(stored)))
    return 0


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    """`orgknow ask "<question>"`: paid, one Voyage call and one Anthropic call per question,
    and in temporal and authority modes one more Anthropic call, the router's. `orgknow chain
    <canonical_id>`: free."""
    arguments = _arguments(argv)
    settings = settings or Settings()
    if arguments.command == "chain":
        with psycopg.connect(settings.database_url) as conn:
            return chain(arguments.canonical_id, conn, settings)
    question: str = arguments.question
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
