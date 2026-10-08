"""`python -m orgknow.eval <command>`: the eval harness's commands (S06).

- `check`: validate the golden file (EVAL_GOLDEN_PATH), then print one line per label with the
  number of distinct chunk texts it matches in the database, then a total. Exits 1 if the file
  is invalid or a label matches nothing.
- `sections CANONICAL_ID`: list a document's sections (canonical_id or alias) as labels write
  them, one line per distinct heading path in any version, first appearance first, each with
  its number of distinct texts.

Errors go to stderr, one line each. Exit codes: 0 done, 1 an error, 2 bad usage (argparse).
"""

import argparse
import sys
from collections.abc import Sequence

import psycopg

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.eval.golden import (
    GoldenSetError,
    check_labels,
    check_line,
    list_sections,
    load_golden_file,
    section_line,
)
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
    args = parser.parse_args(argv)

    if settings is None:
        settings = Settings()
    if args.command == "check":
        return check(settings)
    return sections(settings, args.canonical_id)


if __name__ == "__main__":
    sys.exit(main())
