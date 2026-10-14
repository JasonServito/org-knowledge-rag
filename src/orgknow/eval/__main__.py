"""`python -m orgknow.eval <command>`: the eval harness's commands (S06).

- `check`: validate the golden file (EVAL_GOLDEN_PATH), then print one line per label with the
  number of distinct chunk texts it matches in the database, then a total. Exits 1 if the file
  is invalid or a label matches nothing.
- `check-chains`: print one line per `texts` label of the gold chains file (EVAL_CHAINS_PATH,
  ADR-012 D4) with the number of distinct stored chunk texts it matches, then a total (S13-T1).
  Exits 1 if a label matches nothing, naming it.
- `chain`: score each gold decision chain (EVAL_CHAINS_PATH; S13-T4, ADR-012 D4): its stored chain
  and the control (its question retrieved in authority mode with the mode WHY, no router call),
  then print and write `chains.json` and `chains.md` under EVAL_RESULTS_DIR/s13-chains
  (`chains.py`). The file is checked against the database first. Paid only once: a question with
  no stored vector is embedded (one Voyage request) and saved beside the golden questions'
  vectors, so a re-run makes no request. No Anthropic call. Exits 1 on an invalid file or a chain
  that isn't stored.
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
  the rule-found conflicts of the hits (S10-T2), then the retrieve time's p50 and p95 and, in
  rerank, temporal and authority modes, the reranker's load time (S08-T4). Free: no Voyage or
  Anthropic call; a missing vector or route is an error. Writes nothing.

In rerank, temporal and authority modes, `run` and `retrieval` load the cross-encoder once, before
the question loop, and time the load (S08-T2).
- `conflicts`: check the conflict set (EVAL_CONFLICTS_PATH, ADR-007 D4) against the golden set and
  the stored texts, retrieve in RETRIEVAL_MODE for every golden question and the set's new
  questions, from their stored vectors and routes, and print the set's counts, how many conflicts
  and seeds search retrieved, and the rule-found conflicts' precision and recall (S10-T6). Free:
  no Voyage or Anthropic call; a missing vector or route is an error. Writes nothing. Exits 1 with
  no conflict file.
- `routes`: route every golden question (all of them, answerable or not) with no stored route in
  EVAL_ROUTES_DIR/<ROUTER_MODEL>.json, saving each route as it comes (S09-T2, ADR-009 D3), then
  print how many, the route time's p50 and p95, and the cost. Paid: one ROUTER_MODEL call per
  missing route; the Anthropic key is needed only then. With a conflict file, its new questions
  are routed too, and those with no stored vector are embedded in one Voyage request (S10-T6);
  the Voyage key is needed only then.
- `table`: rebuild the ablation table from every results folder (`table.py`).
- `resummarize`: rebuild the `summary.json` of every results folder that has one and a
  `questions.jsonl`, from its saved rows (S08-T3), so an older folder gains the newer summary
  fields. AC5 and AC6 (S12-T1) read the golden file (EVAL_GOLDEN_PATH, its labels checked as `run`
  checks them) and the latest release in the database. Prints one line per folder and writes
  nothing else; `table` then shows them.

Errors go to stderr, one line each. Exit codes: 0 done, 1 an error, 2 bad usage (argparse).
"""

import argparse
import hashlib
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic
import psycopg

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import Release
from orgknow.db.releases import list_releases
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.chains import (
    RESULTS_FOLDER,
    ChainsReport,
    chain_documents,
    count_texts,
    label_line,
    load_chains_file,
    report_text,
    resolve_chains,
    score_chains,
    text_labels,
    write_report,
)
from orgknow.eval.conflicts import (
    ConflictFile,
    ConflictSetError,
    load_conflict_file,
    reachable_line,
    rule_line,
    seeds_line,
    set_line,
)
from orgknow.eval.golden import (
    GoldenSet,
    GoldenSetError,
    check_labels,
    check_line,
    list_sections,
    load_golden_file,
    section_line,
)
from orgknow.eval.table import write_table
from orgknow.generation.generator import AnthropicGenerator
from orgknow.ingestion.manifest import load_repo_urls
from orgknow.pipeline import load_reranker
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


def check_chains(settings: Settings) -> int:
    """`make eval-check-chains`: print the chain label check; 0 if every label matches a stored
    text, else 1, with an error line naming each label that matches none."""
    labels = text_labels(settings.eval_chains_path)
    with psycopg.connect(settings.database_url) as conn:
        counts = count_texts(conn, labels)
    for label, count in zip(labels, counts, strict=True):
        print(label_line(label, count))
    unmatched = [label for label, count in zip(labels, counts, strict=True) if count == 0]
    for label in unmatched:
        print(f"error: no stored text matches {label_line(label, 0)}", file=sys.stderr)
    print(f"Labels: {len(labels)}. Unmatched: {len(unmatched)}.")
    return 1 if unmatched else 0


def chain(settings: Settings) -> int:
    """`make eval-chain`: check the gold chains file, embed (once) a question with no stored
    vector, score each chain and its control, then write and print the report; 1 on an error."""
    # The control's mode is pinned (S13-R1 decision 5): authority, whatever RETRIEVAL_MODE says.
    settings = settings.model_copy(update={"retrieval_mode": "authority"})
    path = settings.eval_chains_path
    vectors_path = settings.eval_vectors_dir / f"{settings.embedding_model}.json"
    embedder = None  # needed only for a question with no stored vector: the runner says so
    if settings.voyage_api_key:
        embedder = VoyageEmbedder(
            settings.voyage_api_url, settings.voyage_api_key, settings.embedding_model
        )
    try:
        reranker, _ = _load_reranker(settings)
    except OSError as error:
        return _load_failed(error)
    try:
        chains_file = load_chains_file(path)
        with psycopg.connect(settings.database_url) as conn:
            chains = resolve_chains(chains_file, canonical_ids(conn, chain_documents(chains_file)))
            # After the file's checks, before any search: the only paid step.
            vectors = runner.load_vectors(vectors_path)
            questions = [gold.question for gold in chains]
            embedded = runner.embed_missing(questions, vectors, embedder)
            if embedded:
                runner.save_vectors(vectors_path, vectors)
            print(runner.vectors_line(vectors_path, embedded, len(questions)))
            repo_urls = load_repo_urls(settings.corpus_manifest_path)
            scores = score_chains(conn, chains, vectors, settings, reranker, repo_urls)
    except GoldenSetError as error:
        return _invalid(path, error)
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report = ChainsReport(
        gold_path=str(path),
        gold_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        gold_version=chains_file.version,
        control=(
            f"authority mode, mode WHY (no router call), top {settings.retrieval_top_k}, "
            "the best-ranked hit per step by the lookup table"
        ),
        chains=scores,
    )
    folder = settings.eval_results_dir / RESULTS_FOLDER
    write_report(folder, report)
    print(report_text(report), end="")
    print(f"Wrote {folder / 'chains.json'} and {folder / 'chains.md'}.")
    return 0


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
    except ConflictSetError as error:  # before GoldenSetError, which it extends
        return _invalid(settings.eval_conflicts_path, error)
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
    selection, in temporal and authority modes the router line, the rule-found conflicts, and the
    retrieve time; 1 on an error."""
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
    print(runner.conflict_line(scores.rule_conflicts))
    print(runner.timing_line(scores.retrieve_s, load_s))
    return 0


def conflicts(settings: Settings) -> int:
    """`make eval-conflicts`: print the conflict set's line, how many of its conflicts and seeds
    search retrieved, and the rule-found conflicts' precision and recall; 1 on an error, or with
    no conflict file (checked before the reranker loads)."""
    path = settings.eval_conflicts_path
    if not path.is_file():
        print(f"error: Conflict set: none ({path} not found).", file=sys.stderr)
        return 1
    try:
        reranker, _ = _load_reranker(settings)
    except OSError as error:
        return _load_failed(error)
    try:
        with psycopg.connect(settings.database_url) as conn:
            check = runner.score_conflicts_only(conn, settings, reranker)
    except ConflictSetError as error:  # before GoldenSetError, which it extends
        return _invalid(path, error)
    except GoldenSetError as error:
        return _invalid(settings.eval_golden_path, error)
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(set_line(check.path, check.sha256, check.conflict_set, check.golden_questions))
    print(reachable_line(check.counts))
    print(seeds_line(check.counts))
    print(rule_line(check.flagged, check.counts))
    return 0


def routes(settings: Settings) -> int:
    """`make eval-routes`: route each golden question, and each new question of the conflict set
    when its file exists, with no stored route, then print the routes line; then embed the new
    questions with no stored vector, in one Voyage request, and print the vectors line. 1 on an
    error. Routes made before an error stay saved."""
    golden_path, conflicts_path = settings.eval_golden_path, settings.eval_conflicts_path
    conflict_file: ConflictFile | None = None
    try:
        golden = load_golden_file(golden_path)
        if conflicts_path.is_file():
            ids = [question.id for question in golden.questions]
            conflict_file = load_conflict_file(conflicts_path, ids)
    except ConflictSetError as error:  # before GoldenSetError, which it extends
        return _invalid(conflicts_path, error)
    except GoldenSetError as error:
        return _invalid(golden_path, error)
    new = [] if conflict_file is None else [q.question for q in conflict_file.questions]
    # Each key is needed only when a route or a vector is missing: the runner says so if one is.
    router = None
    if settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        router = ClaudeRouter(client, settings)
    embedder = None
    if settings.voyage_api_key:
        embedder = VoyageEmbedder(
            settings.voyage_api_url, settings.voyage_api_key, settings.embedding_model
        )
    path = settings.eval_routes_dir / f"{settings.router_model}.json"
    vectors_path = settings.eval_vectors_dir / f"{settings.embedding_model}.json"
    questions = [question.question for question in golden.questions] + new
    try:
        stored = runner.load_routes(path)
        already = sum(runner.question_key(question) in stored for question in questions)
        times = runner.route_missing(questions, stored, router, path)
        tokens = (0, 0) if router is None else (router.input_tokens, router.output_tokens)
        print(runner.routes_line(settings, times, already, *tokens))
        if conflict_file is not None:
            vectors = runner.load_vectors(vectors_path)
            embedded = runner.embed_missing(new, vectors, embedder)
            if embedded:
                runner.save_vectors(vectors_path, vectors)
            print(runner.vectors_line(vectors_path, embedded, len(new)))
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _invalid(path: Path, error: GoldenSetError) -> int:
    """Print each line of an invalid golden or conflict file's error, naming the file; return 1."""
    for line in error.errors:
        print(f"error: {path}: {line}", file=sys.stderr)
    return 1


def table(settings: Settings) -> int:
    """`make eval-table`: rebuild the ablation table from every results folder."""
    print(f"Ablation table: {write_table(settings.eval_results_dir)}")
    return 0


def _golden_and_latest(settings: Settings) -> tuple[GoldenSet, str, Release]:
    """What AC5 and AC6 read (S12-T1): the golden set, checked as `run` checks it, its file's
    hash, and the latest stored release."""
    path = settings.eval_golden_path
    with psycopg.connect(settings.database_url) as conn:
        golden, _ = runner.check_golden(conn, path)
        latest = list_releases(conn)[-1]  # oldest first; a labeled text implies a release
    return golden, hashlib.sha256(path.read_bytes()).hexdigest(), latest


def resummarize(settings: Settings) -> int:
    """`make eval-resummarize`: rebuild each results folder's summary from its saved rows, and
    print its p95 latencies and cost per question. A folder without both files is skipped. 1 when
    the golden file is invalid or a label matches no stored text."""

    def seconds(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f} s"

    try:
        golden, golden_sha256, latest = _golden_and_latest(settings)
    except GoldenSetError as error:
        return _invalid(settings.eval_golden_path, error)
    except runner.EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for summary_path in sorted(settings.eval_results_dir.glob("*/summary.json")):
        folder = summary_path.parent
        if not (folder / "questions.jsonl").is_file():
            continue
        summary = runner.resummarize(folder, settings, golden, golden_sha256, latest)
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
    commands.add_parser(
        "check-chains", help="check the gold chains' text labels against the database"
    )
    commands.add_parser(
        "chain",
        help="score the gold decision chains and their control, and write the results (free "
        "after one question vector)",
    )
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
    commands.add_parser(
        "conflicts", help="check the conflict set and score the rule-found conflicts (free)"
    )
    commands.add_parser(
        "routes",
        help="route every golden and conflict-set question with no stored route, and embed the "
        "conflict set's new questions with no vector (paid)",
    )
    commands.add_parser("table", help="rebuild the ablation table from every results folder")
    commands.add_parser(
        "resummarize", help="rebuild every results folder's summary.json from its saved rows"
    )
    args = parser.parse_args(argv)

    if settings is None:
        settings = Settings()
    if args.command == "check":
        return check(settings)
    if args.command == "check-chains":
        return check_chains(settings)
    if args.command == "chain":
        return chain(settings)
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
    if args.command == "conflicts":
        return conflicts(settings)
    return table(settings)


if __name__ == "__main__":
    sys.exit(main())
