"""`python -m orgknow.eval <command>`: the eval harness's commands (S06).

- `check`: validate the golden file (EVAL_GOLDEN_PATH), then print one line per label with the
  number of distinct chunk texts it matches in the database, then a total. Exits 1 if the file
  is invalid or a label matches nothing.
- `sections CANONICAL_ID`: list a document's sections (canonical_id or alias) as labels write
  them, one line per distinct heading path in any version, first appearance first, each with
  its number of distinct texts.
- `run [--smoke] [--name NAME]`: run the golden set (with `--smoke`, its `smoke: true`
  questions) through retrieval and one answer call each, write a results folder under
  EVAL_RESULTS_DIR (`runner.py`), then rebuild the ablation table. Paid: one Anthropic call per
  question with hits, one Voyage request when a question has no stored vector, and in temporal
  and authority modes one ROUTER_MODEL call per question with no stored route. NAME defaults to
  RETRIEVAL_MODE (`dense`, `hybrid`, `rerank`, `temporal` or `authority`); with `--smoke`,
  `<mode>-smoke`, so smoke runs get their own ablation-table row.
- `retrieval`: retrieve for every answerable golden question with its stored vector (and in
  temporal and authority modes its stored route), in RETRIEVAL_MODE, and print the retrieval
  metrics (S07-T3), the stale-result rate and temporal accuracy (S09-T3), authority selection and
  the CURRENT questions' MRR (S09-T7), in temporal and authority modes the router line (S09-T4),
  then the retrieve time's p50 and p95 and, in rerank, temporal and authority modes, the
  reranker's load time (S08-T4). Free: no Voyage or Anthropic call; a missing vector or route is
  an error. Writes nothing.

In rerank, temporal and authority modes, `run` and `retrieval` load the cross-encoder once, before
the question loop, and time the load (S08-T2).
- `routes`: route every golden question (all of them, answerable or not) with no stored route in
  EVAL_ROUTES_DIR/<ROUTER_MODEL>.json, saving each route as it comes (S09-T2, ADR-009 D3), then
  print how many, the route time's p50 and p95, and the cost. Paid: one ROUTER_MODEL call per
  missing route; the Anthropic key is needed only then.
- `table`: rebuild the ablation table from every results folder (`table.py`).
- `resummarize`: rebuild the `summary.json` of every results folder that has one and a
  `questions.jsonl`, from its saved rows (S08-T3), so an older folder gains the newer summary
  fields. Prints one line per folder and writes nothing else; `table` then shows them.

Errors go to stderr, one line each. Exit codes: 0 done, 1 an error, 2 bad usage (argparse).
"""

import argparse
import sys
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

import anthropic
import psycopg

from orgknow.cli import load_reranker
from orgknow.db.eval import canonical_ids, document_texts
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.golden import (
    GoldenSetError,
    check_labels,
    check_line,
    list_sections,
    load_golden_file,
    section_line,
)
from orgknow.eval.table import write_table
from orgknow.generation.generator import AnthropicGenerator
from orgknow.retrieval.router import ClaudeRouter
from orgknow.settings import Settings

if TYPE_CHECKING:  # for the annotation only: importing the module loads torch
    from orgknow.retrieval.cross_encoder import CrossEncoderReranker


def check(settings: Settings) -> int:
    """`make eval-check`: print the label check; 0 if every label matches a stored text."""
    path = settings.eval_golden_path
    try:
        golden_file = load_golden_file(path)
        with psycopg.connect(settings.database_url) as conn:
            _, counts = check_labels(conn, golden_file)
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {path}: {line}", file=sys.stderr)
        return 1
    for count in counts:
        print(check_line(count))
    unmatched = sum(1 for count in counts if count.texts == 0)
    print(f"Labels: {len(counts)}. Unmatched: {unmatched}.")
    return 1 if unmatched else 0


def sections(settings: Settings, document: str) -> int:
    """`make eval-sections DOC=...`: print the document's sections; 1 if it isn't stored."""
    with psycopg.connect(settings.database_url) as conn:
        canonical_id = canonical_ids(conn, [document]).get(document)
        if canonical_id is None:
            print(f"error: no document or alias {document!r}", file=sys.stderr)
            return 1
        texts = document_texts(conn, canonical_id)
    for section, count in list_sections(texts):
        print(section_line(section, count))
    return 0


def _load_reranker(settings: Settings) -> tuple["CrossEncoderReranker | None", float | None]:
    """`load_reranker` and its load time in seconds; (None, None) outside rerank, temporal and
    authority modes. Raises OSError when the model isn't cached and Hugging Face can't be
    reached."""
    start = time.monotonic()
    reranker = load_reranker(settings)
    return reranker, None if reranker is None else round(time.monotonic() - start, 3)


def _load_failed(error: OSError) -> int:
    """Print why the reranker didn't load, on one line; return 1."""
    print(f"error: {' '.join(str(error).split())}", file=sys.stderr)
    return 1


def run(settings: Settings, smoke: bool, name: str) -> int:
    """`make eval` / `make eval-smoke`: run the golden set, then rebuild the ablation table; 1 on
    an error that stops the run. A failed ask doesn't stop it: it is a row with its error."""
    anthropic_key, voyage_key = settings.anthropic_api_key, settings.voyage_api_key
    if not anthropic_key:  # unset or empty
        print(
            "ANTHROPIC_API_KEY is not set: add the key to .env (see .env.example).",
            file=sys.stderr,
        )
        return 1
    # Voyage is needed only for questions with no stored vector: the run says so if one has none.
    embedder = None
    if voyage_key:
        embedder = VoyageEmbedder(settings.voyage_api_url, voyage_key, settings.embedding_model)
    client = anthropic.Anthropic(api_key=anthropic_key.get_secret_value())
    generator = AnthropicGenerator(client, settings)
    # Temporal and authority modes route the questions with no stored route (ADR-009 D3); the key
    # is set.
    routed = settings.retrieval_mode in ("temporal", "authority")
    router = ClaudeRouter(client, settings) if routed else None
    try:
        reranker, load_s = _load_reranker(settings)
    except OSError as error:
        return _load_failed(error)
    threads = None if reranker is None else reranker.threads
    try:
        with psycopg.connect(settings.database_url) as conn:
            runner.run(
                conn, embedder, generator, settings, smoke, name, reranker, load_s, threads, router
            )
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {settings.eval_golden_path}: {line}", file=sys.stderr)
        return 1
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return table(settings)


def retrieval(settings: Settings) -> int:
    """`make eval-retrieval`: print the mode, the retrieval metrics, the time metrics, authority
    selection, in temporal and authority modes the router line, and the retrieve time; 1 on an
    error."""
    try:
        reranker, load_s = _load_reranker(settings)
    except OSError as error:
        return _load_failed(error)
    try:
        with psycopg.connect(settings.database_url) as conn:
            scores = runner.score_retrieval_only(conn, settings, reranker)
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {settings.eval_golden_path}: {line}", file=sys.stderr)
        return 1
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(runner.retrieval_report(settings, scores.metrics))
    print(runner.time_line(scores.stale, scores.temporal))
    print(runner.authority_line(scores.authority, scores.current_mrr))
    if scores.router is not None:  # temporal and authority modes
        print(runner.router_line(scores.router))
    print(runner.timing_line(scores.retrieve_s, load_s))
    return 0


def routes(settings: Settings) -> int:
    """`make eval-routes`: route each golden question with no stored route, then print the routes
    line; 1 on an error. Routes made before an error stay saved."""
    golden_path = settings.eval_golden_path
    try:
        golden = load_golden_file(golden_path)
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {golden_path}: {line}", file=sys.stderr)
        return 1
    # The key is needed only when a route is missing: the runner says so if one is.
    router = None
    if settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        router = ClaudeRouter(client, settings)
    path = settings.eval_routes_dir / f"{settings.router_model}.json"
    questions = [question.question for question in golden.questions]
    try:
        stored = runner.load_routes(path)
        already = sum(runner.question_key(question) in stored for question in questions)
        times = runner.route_missing(questions, stored, router, path)
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    tokens = (0, 0) if router is None else (router.input_tokens, router.output_tokens)
    print(runner.routes_line(settings, times, already, *tokens))
    return 0


def table(settings: Settings) -> int:
    """`make eval-table`: rebuild the ablation table from every results folder."""
    print(f"Ablation table: {write_table(settings.eval_results_dir)}")
    return 0


def resummarize(settings: Settings) -> int:
    """`make eval-resummarize`: rebuild each results folder's summary from its saved rows, and
    print its p95 latencies and cost per question. A folder without both files is skipped."""

    def seconds(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f} s"

    for summary_path in sorted(settings.eval_results_dir.glob("*/summary.json")):
        folder = summary_path.parent
        if not (folder / "questions.jsonl").is_file():
            continue
        summary = runner.resummarize(folder, settings)
        cost = "n/a" if summary.cost_usd_mean is None else f"${summary.cost_usd_mean:.6f}"
        print(
            f"{folder}: p95 latency {seconds(summary.latency_s_p95)}, "
            f"retrieve p95 {seconds(summary.retrieve_s_p95)}, cost/question {cost}"
        )
    return 0


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orgknow.eval", description="The eval harness's commands (S06)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check the golden file's labels against the database")
    sections_parser = commands.add_parser(
        "sections", help="list a document's sections as labels write them"
    )
    sections_parser.add_argument("canonical_id", help="the document's canonical_id or an alias")
    run_parser = commands.add_parser(
        "run", help="run the golden set and write a results folder (paid)"
    )
    run_parser.add_argument(
        "--smoke", action="store_true", help="run only the questions marked smoke: true"
    )
    run_parser.add_argument(
        "--name",
        help=(
            "the pipeline's name in the results (default: RETRIEVAL_MODE, dense, hybrid, "
            "rerank, temporal or authority; with --smoke, RETRIEVAL_MODE-smoke)"
        ),
    )
    commands.add_parser(
        "retrieval", help="score retrieval alone from the stored question vectors (free)"
    )
    commands.add_parser("routes", help="route every golden question with no stored route (paid)")
    commands.add_parser("table", help="rebuild the ablation table from every results folder")
    commands.add_parser(
        "resummarize", help="rebuild every results folder's summary.json from its saved rows"
    )
    args = parser.parse_args(argv)

    if settings is None:
        settings = Settings()
    if args.command == "check":
        return check(settings)
    if args.command == "sections":
        return sections(settings, args.canonical_id)
    if args.command == "run":
        # An explicit --name is used as given; otherwise the mode names the row, and a smoke run
        # gets its own row (S07-T4).
        name = args.name
        if name is None:
            name = f"{settings.retrieval_mode}-smoke" if args.smoke else settings.retrieval_mode
        return run(settings, args.smoke, name)
    if args.command == "retrieval":
        return retrieval(settings)
    if args.command == "resummarize":
        return resummarize(settings)
    if args.command == "routes":
        return routes(settings)
    return table(settings)


if __name__ == "__main__":
    sys.exit(main())
