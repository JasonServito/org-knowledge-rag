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
  question with hits, and one Voyage request when a question has no stored vector. NAME defaults
  to RETRIEVAL_MODE (`dense` or `hybrid`).
- `retrieval`: retrieve for every answerable golden question with its stored vector, in
  RETRIEVAL_MODE, and print the retrieval metrics (S07-T3). Free: no Voyage or Anthropic call; a
  missing vector is an error. Writes nothing.
- `table`: rebuild the ablation table from every results folder (`table.py`).

Errors go to stderr, one line each. Exit codes: 0 done, 1 an error, 2 bad usage (argparse).
"""

import argparse
import sys
from collections.abc import Sequence

import anthropic
import psycopg

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
from orgknow.settings import Settings


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
    try:
        with psycopg.connect(settings.database_url) as conn:
            runner.run(conn, embedder, generator, settings, smoke, name)
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {settings.eval_golden_path}: {line}", file=sys.stderr)
        return 1
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return table(settings)


def retrieval(settings: Settings) -> int:
    """`make eval-retrieval`: print the mode and the retrieval metrics; 1 on an error."""
    try:
        with psycopg.connect(settings.database_url) as conn:
            scores = runner.score_retrieval_only(conn, settings)
    except GoldenSetError as error:
        for line in error.errors:
            print(f"error: {settings.eval_golden_path}: {line}", file=sys.stderr)
        return 1
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(runner.retrieval_report(settings, scores))
    return 0


def table(settings: Settings) -> int:
    """`make eval-table`: rebuild the ablation table from every results folder."""
    print(f"Ablation table: {write_table(settings.eval_results_dir)}")
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
        help="the pipeline's name in the results (default: RETRIEVAL_MODE, dense or hybrid)",
    )
    commands.add_parser(
        "retrieval", help="score retrieval alone from the stored question vectors (free)"
    )
    commands.add_parser("table", help="rebuild the ablation table from every results folder")
    args = parser.parse_args(argv)

    if settings is None:
        settings = Settings()
    if args.command == "check":
        return check(settings)
    if args.command == "sections":
        return sections(settings, args.canonical_id)
    if args.command == "run":
        # An explicit --name is used as given; otherwise the mode names the row.
        name = settings.retrieval_mode if args.name is None else args.name
        return run(settings, args.smoke, name)
    if args.command == "retrieval":
        return retrieval(settings)
    return table(settings)


if __name__ == "__main__":
    sys.exit(main())
