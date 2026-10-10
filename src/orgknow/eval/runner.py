"""The eval run (S06-T4): every golden question through retrieval and one answer call, scored
with the metrics (T2) and the answer checks (T3), written to one results folder per run.

The run order is pinned (S06-R1, Claude's calls): load and validate the golden file → the label
check (a label matching no stored text stops the run before any paid call) → embed, in one
Voyage request, the questions with no stored vector, and save them → per question: retrieve,
answer, score → write the folder. `__main__` then rebuilds the ablation table (`table.py`).

Retrieval reads each question's vector from the vector file (S06-R1 decision 7), so every run of
one golden set retrieves exactly the same hits. A failed ask is a row with its error, never a
crash. No Langfuse trace: the results folder is the record.

`score_retrieval_only` (S07-T3, `make eval-retrieval`) runs the same label check and retrieval,
from stored vectors only, and scores the hits with no answer call: free, and it writes nothing. It
also times each question's retrieval (S08-T4), which `timing_line` reports, counts the S09 time
metrics (S09-T3), which `time_line` reports, and authority selection and the CURRENT questions'
MRR (S09-T7), which `authority_line` reports.

Both read each labeled document's tier (S09-T7): its newest version's, at the latest release.
`run` writes each question's label tiers in its row, so the summary can count authority selection.

In rerank, temporal and authority modes (S08-T2, S09-T4, S09-T7), both get the reranker the caller
loaded once, before the question loop.

`resummarize` (S08-T3, `make eval-resummarize`) rebuilds a folder's `summary.json` from its saved
rows, so a summary written before a new summary field gains it with no new run.

The question routes (S09-T2, ADR-009 D3) are stored like the vectors, one file per router model,
keyed the same way: `route_missing` (`make eval-routes`) routes only questions with no route. In
temporal and authority modes (S09-T4, S09-T7), `run` fills the missing routes too, and both `run`
and `score_retrieval_only` give each question its stored route to `retrieve`; `router_line`
reports the routes against the golden modes and windows.
"""

import hashlib
import json
import math
import statistics
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow
from pydantic import BaseModel, ConfigDict, Field

from orgknow.cli import ASK_ERRORS
from orgknow.db.lifecycle import newest_versions, observations
from orgknow.db.models import Authority, Hit, TemporalFilter
from orgknow.db.releases import list_releases
from orgknow.embeddings.embedder import DIMENSIONS, Embedder, EmbedResult, InputType
from orgknow.eval.checks import AnswerChecks, check_answer
from orgknow.eval.golden import (
    GoldenSet,
    Label,
    LabelCount,
    Mode,
    Question,
    check_labels,
    check_line,
    load_golden_file,
)
from orgknow.eval.metrics import (
    AuthorityQuestion,
    GoldenWindow,
    RetrievalMetrics,
    authority_count,
    router_count,
    score_retrieval,
    stale_count,
    temporal_count,
)
from orgknow.generation.generator import GenerationError, Generator, answer
from orgknow.generation.schema import Answer, TokenUsage
from orgknow.retrieval.authority import kep_gates, tier
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.retrieve import retrieve, temporal_plan
from orgknow.retrieval.router import SYSTEM_PROMPT, Route, Router, TimeScope
from orgknow.retrieval.temporal import Window
from orgknow.settings import Settings


class EvalError(Exception):
    """A problem that stops the run, as one line."""


# The results folder's 3 files (S06-R1, pinned formats). Field order is the files' key order.


class RunSettings(BaseModel):
    """The settings a result depends on."""

    embedding_model: str
    retrieval_top_k: int
    # S07-T3: a new run writes all 4; None in a folder written before them (the dense baseline).
    retrieval_mode: str | None = None
    retrieval_candidates: int | None = None
    rrf_k: int | None = None
    hnsw_ef_search: int | None = None
    # S08-T2: the reranker's model and its thread count, in rerank, temporal and authority modes;
    # None in other modes and older folders.
    rerank_model: str | None = None
    rerank_revision: str | None = None
    rerank_max_length: int | None = None
    rerank_batch_size: int | None = None
    torch_threads: int | None = None
    # S09-T4: the router and slack of temporal and authority modes; None in other modes and older
    # folders.
    router_model: str | None = None
    router_effort: str | None = None
    history_window_slack: int | None = None
    # S09-T7: authority mode's weights; None in other modes and older folders.
    authority_boost: float | None = None
    authority_demote: float | None = None
    generation_model: str
    generation_effort: str
    generation_max_tokens: int


class RunInfo(BaseModel):
    """`run.json`: what was run, on which code and golden file."""

    name: str
    started_at: datetime  # UTC, to the second
    finished_at: datetime
    git_sha: str
    git_dirty: bool  # tracked files differ from git_sha
    golden_path: str
    golden_sha256: str  # of the file's bytes: a changed file is another table row
    smoke: bool
    questions: int
    settings: RunSettings
    # Seconds to load the reranker, once per run (S08-T2); None in other modes and older folders.
    rerank_load_s: float | None = None


class RankedHit(BaseModel):
    """One retrieved hit, as much as the metrics and AC2 need to score it again, and why it
    ranked there (S07-R1 decision 4): the `Hit` fields of the same names."""

    rank: int
    chunk_id: int
    canonical_id: str
    heading_path: list[str]
    distance: float | None  # None when only lexical search found the text
    # Hybrid and rerank only. Absent in the dense baseline's folders (S06), written before S07.
    rrf_score: float | None = None
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rerank_score: float | None = None  # rerank only (S08-T2); absent in older folders
    # What the S09 time metrics read (S09-T3); absent in older folders.
    current: bool | None = None
    release_windows: list[tuple[int, int | None]] | None = None
    # The tier and a KEP's stage at the target release (S09-T6); absent in older folders.
    authority: Authority | None = None
    # Authority mode only (S09-T7): sigmoid(rerank_score) times the hit's factor; absent in
    # older folders.
    authority_score: float | None = None


class RouteRecord(BaseModel):
    """A question's route in temporal and authority modes (S09-T4): the router's mode and time
    scope, the release window that scope resolved to (before slack; None when it names none), and
    the filter both searches applied (None: no filter)."""

    mode: Mode
    time_scope: TimeScope
    window: Window | None
    filter: TemporalFilter | None


class QuestionRow(BaseModel):
    """One line of `questions.jsonl`: one question's hits, answer, scores and cost."""

    id: str
    mode: Mode | None
    # The golden release window as minors, [from, until], None an open end (S09-T3); None when
    # the question has none, and in older folders.
    release_window: GoldenWindow | None = None
    # Each golden label's document tier at the latest release, in the golden file's label order
    # (S09-T7; None = a superseded proposal); [] for a question with no labels. None in older
    # folders.
    label_tiers: list[int | None] | None = None
    # Temporal and authority modes only (S09-T4); None in other modes and older folders.
    route: RouteRecord | None = None
    answerable: bool
    hits: list[RankedHit]
    answer: Answer | None  # the `ask` JSON; None when the ask failed
    metrics: RetrievalMetrics | None  # None when unanswerable
    checks: AnswerChecks
    usage: TokenUsage | None  # None when the model wasn't called (no hits)
    latency_s: float  # retrieve + answer
    retrieve_s: float | None = None  # the retrieve stage alone (S08-T3); absent in older folders
    error: str | None  # "<Type>: <message>" when the ask failed


class Rate(BaseModel):
    """How many of the rows (or hits) a check applies to passed it."""

    # `pass` is a Python keyword: the field is `pass_`, written as "pass".
    model_config = ConfigDict(serialize_by_alias=True, validate_by_name=True)

    pass_: int = Field(alias="pass")
    total: int


class Count(BaseModel):
    """How many of the rows (or hits) a flag applies to have it."""

    count: int
    total: int


class RouterStats(BaseModel):
    """The routes of the answerable questions against their golden modes and windows (S09-T4),
    for `router_line`."""

    router: Rate | None  # routes whose mode is the golden mode; None with no golden mode
    windows: int  # resolved windows (before slack) equal to the golden one
    golden_windows: int  # questions with a golden window
    extra: int  # windows resolved for questions with no golden window
    current_only: int  # questions per plan: CURRENT's filter
    windowed: int  # HISTORY with a window
    unfiltered: int  # no filter


class Summary(BaseModel):
    """`summary.json`: the run's totals, what the ablation table reads."""

    name: str
    golden_sha256: str
    started_at: datetime
    questions: int
    answerable: int
    errors: int
    # Means over the answerable questions; None when there are none.
    recall: float | None
    hit: float | None
    mrr: float | None
    ndcg: float | None
    distinct_sections: float | None
    ac1: Rate
    ac2: Rate
    ac3: Rate
    false_refusals: Count
    input_tokens: int
    output_tokens: int
    latency_s_mean: float
    # S08-T3: nearest-rank p95s over the rows that have the value (`retrieve_s_p95` None when no
    # row has it), and the mean cost of the rows with usage at the settings' prices. None in a
    # summary written before S08-T3, until `make eval-resummarize` refills it.
    latency_s_p95: float | None = None
    retrieve_s_p95: float | None = None
    cost_usd_mean: float | None = None
    # S09-T3 (S09-R1 decision 1), pooled over hits: the stale hits of the CURRENT questions, the
    # hits in the golden window of the questions with one, and the routes matching the golden
    # mode of the answerable questions. None when no row applies, and in a summary of rows
    # written before S09-T3.
    stale: Count | None = None
    temporal: Rate | None = None
    router: Rate | None = None
    # S09-T7: authority selection over the CURRENT questions whose labels span 2+ tiers. None when
    # none does, and in a summary of rows written before S09-T7.
    authority: Rate | None = None


class RetrievalScores(BaseModel):
    """What `score_retrieval_only` returns for `make eval-retrieval` to print."""

    metrics: list[RetrievalMetrics]  # per answerable question, in file order
    retrieve_s: list[float]  # each question's retrieve time in seconds (S08-T4)
    # The S09 counts over the top K hits (S09-T3, S09-T7), as `summarize` counts them.
    stale: Count | None
    temporal: Rate | None
    authority: Rate | None
    current_mrr: float | None  # the mean MRR of the golden CURRENT questions; None with none
    router: RouterStats | None  # temporal and authority modes only (S09-T4)


def golden_window(question: Question) -> GoldenWindow | None:
    """The question's golden release window as minors, (20, 28) for 1.20 to 1.28, None an open
    end; None when it has none."""
    window = question.release_window
    if window is None:
        return None

    def minor(release: str | None) -> int | None:
        return None if release is None else int(release.removeprefix("1."))

    return minor(window.from_), minor(window.until)


def document_tiers(
    conn: psycopg.Connection[TupleRow], questions: Sequence[Question]
) -> dict[str, int | None]:
    """The tier of every document the questions' labels name, by canonical id (S09-R2 decision
    4): its newest version's, at the latest release, by the same `tier` rule as the hits. One
    read of the newest versions and one of their gates' observations."""
    canonical_ids = sorted({label.canonical_id for q in questions for label in q.labels})
    if not canonical_ids:
        return {}
    latest = list_releases(conn)[-1].minor  # oldest first; a labeled text implies a release
    versions = newest_versions(conn, canonical_ids)
    gates = {
        v.canonical_id: kep_gates(v.metadata) if v.source_type == "kep" else [] for v in versions
    }
    rows = observations(conn, sorted({gate for names in gates.values() for gate in names}), latest)
    return {
        v.canonical_id: tier(v.source_type, v.claimed_status, gates[v.canonical_id], rows, latest)
        for v in versions
    }


def question_key(question: str) -> str:
    """A question's key in the vector file: the sha256 hex of its UTF-8 text."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def load_vectors(path: Path) -> dict[str, list[float]]:
    """The stored question vectors by key. A missing or empty file holds none; a vector of the
    wrong length is an EvalError."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    vectors: dict[str, list[float]] = json.loads(text) if text.strip() else {}
    for key, vector in vectors.items():
        if len(vector) != DIMENSIONS:
            raise EvalError(
                f"{path}: the vector for {key} has {len(vector)} numbers, expected {DIMENSIONS}"
            )
    return vectors


def save_vectors(path: Path, vectors: Mapping[str, list[float]]) -> None:
    """Write the vector file, keys sorted, so the same vectors always write the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vectors, sort_keys=True) + "\n", encoding="utf-8")


def embed_missing(
    questions: Sequence[str], vectors: dict[str, list[float]], embedder: Embedder | None
) -> int:
    """Embed, in one request, each question with no vector in `vectors`, and add the new vectors
    to it. Returns how many were embedded: 0 means no request. With no embedder (no Voyage key),
    a missing vector is an EvalError."""
    missing = {question_key(q): q for q in questions if question_key(q) not in vectors}
    if not missing:
        return 0
    if embedder is None:
        raise EvalError(
            f"{len(missing)} questions have no stored vector and VOYAGE_API_KEY is not set: add "
            "the key to .env (see .env.example)."
        )
    try:
        result = embedder.embed(list(missing.values()), "query")
    except ASK_ERRORS as error:
        raise EvalError(f"embedding the questions failed: {_one_line(error)}") from error
    vectors.update(zip(missing, result.vectors, strict=True))
    return len(missing)


class StoredRoutes(BaseModel):
    """The route file: the router prompt's hash, and each question's route by its key."""

    prompt_sha256: str
    routes: dict[str, Route]


# The hash the route file records: a file made with another prompt is an error (ADR-009 D3).
ROUTER_PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def load_routes(path: Path) -> dict[str, Route]:
    """The stored question routes by key. A missing or empty file holds none; a file made with a
    different router prompt is an EvalError."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if not text.strip():
        return {}
    stored = StoredRoutes.model_validate_json(text)
    if stored.prompt_sha256 != ROUTER_PROMPT_SHA256:
        raise EvalError(
            f"{path}: made with a different router prompt: delete it and run `make eval-routes`"
        )
    return stored.routes


def save_routes(path: Path, routes: Mapping[str, Route]) -> None:
    """Write the route file with the prompt's hash, keys sorted, so the same routes always write
    the same bytes. Indented, so a reviewer can read each route."""
    stored = StoredRoutes(prompt_sha256=ROUTER_PROMPT_SHA256, routes=dict(routes))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(stored.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def route_missing(
    questions: Sequence[str], routes: dict[str, Route], router: Router | None, path: Path
) -> list[float]:
    """Route, one call each in the questions' order, each question with no route in `routes`;
    add each new route to `routes` and save the file at `path` after each one, so a failure
    midway keeps the routes already paid for. Returns each call's time in seconds: an empty list
    means no call. With no router (no Anthropic key), a missing route is an EvalError; so is a
    failed call."""
    missing = {question_key(q): q for q in questions if question_key(q) not in routes}
    if not missing:
        return []
    if router is None:
        raise EvalError(
            f"{len(missing)} questions have no stored route and ANTHROPIC_API_KEY is not set: add "
            "the key to .env (see .env.example)."
        )
    times = []
    for key, question in missing.items():
        start = time.monotonic()
        try:
            routes[key] = router.route(question)
        except ASK_ERRORS as error:  # RouterError included
            raise EvalError(f"routing {question!r} failed: {_one_line(error)}") from error
        times.append(time.monotonic() - start)
        save_routes(path, routes)
    return times


def routes_line(
    settings: Settings,
    times: Sequence[float],
    stored: int,
    input_tokens: int,
    output_tokens: int,
) -> str:
    """`make eval-routes`'s line (S09-R1, pinned format): how many questions were routed and how
    many already had a stored route; when any was routed, the median and the nearest-rank p95 of
    this command's route times, and its cost at the ROUTER_PRICE_* prices."""
    line = f"Routed {len(times)} questions with {settings.router_model} ({stored} already stored)."
    if not times:
        return line
    cost = (
        input_tokens * settings.router_price_input_usd_per_mtok
        + output_tokens * settings.router_price_output_usd_per_mtok
    ) / 1e6
    return (
        f"{line} Route time: p50 {statistics.median(times):.2f} s, p95 {_p95(times):.2f} s. "
        f"Cost ${cost:.2f}."
    )


class StoredVectors:
    """The `Embedder` protocol over the stored question vectors: `retrieve` gets each question's
    vector from the file instead of from Voyage. They were embedded as queries."""

    def __init__(self, model: str, vectors: Mapping[str, list[float]]) -> None:
        self.model = model
        self._vectors = vectors

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult:
        return EmbedResult(vectors=[self._vectors[question_key(t)] for t in texts], total_tokens=0)


def check_golden(
    conn: psycopg.Connection[TupleRow], golden_path: Path
) -> tuple[GoldenSet, list[LabelCount]]:
    """Load and validate the golden file, then check its labels against the stored texts; return
    the golden set (aliases resolved) and each label's count.

    Raises GoldenSetError for an invalid file, and EvalError when a label matches no stored text.
    """
    golden, counts = check_labels(conn, load_golden_file(golden_path))
    unmatched = [count for count in counts if count.texts == 0]
    if unmatched:
        labels = "; ".join(check_line(count) for count in unmatched)
        noun = "label matches" if len(unmatched) == 1 else "labels match"
        raise EvalError(f"{len(unmatched)} {noun} no stored text (see `make eval-check`): {labels}")
    return golden, counts


def run(
    conn: psycopg.Connection[TupleRow],
    embedder: Embedder | None,
    generator: Generator,
    settings: Settings,
    smoke: bool,
    name: str,
    reranker: Reranker | None = None,
    rerank_load_s: float | None = None,
    torch_threads: int | None = None,
    router: Router | None = None,
) -> Path:
    """Run the golden set (only its `smoke: true` questions with `smoke`) and write its results
    folder; return the folder. `embedder` is called only for questions with no stored vector.
    Rerank, temporal and authority modes need `reranker`; `run.json` records its load time and
    torch's thread count. Temporal and authority modes (S09-T4, S09-T7) route, with `router`, each
    question with no stored route, saving each, then retrieve each question with its route.

    Raises GoldenSetError for an invalid golden file, and EvalError when a label matches no
    stored text, a vector is missing with no embedder, embedding fails, or a route is missing
    with no router or routing fails: all before any answer call.
    """
    started_at = _now()
    git_sha, git_dirty = _git_state()  # the code the run starts on
    golden_path = settings.eval_golden_path
    golden, counts = check_golden(conn, golden_path)
    golden_sha256 = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    questions = [question for question in golden.questions if question.smoke or not smoke]
    if not questions:
        raise EvalError(f"{golden_path}: no questions to run")
    print(
        f"Golden set {golden_path} ({golden_sha256[:8]}): {len(questions)} questions"
        f"{' (smoke)' if smoke else ''}. Labels: {len(counts)}. Unmatched: 0."
    )

    vectors_path = settings.eval_vectors_dir / f"{settings.embedding_model}.json"
    vectors = load_vectors(vectors_path)
    embedded = embed_missing([q.question for q in questions], vectors, embedder)
    if embedded:
        save_vectors(vectors_path, vectors)
    print(
        f"Question vectors ({vectors_path}): {embedded} of {len(questions)} embedded. "
        f"Voyage requests: {1 if embedded else 0}."
    )
    routed_mode = settings.retrieval_mode in ("temporal", "authority")
    routes: dict[str, Route] = {}  # none outside temporal and authority modes
    if routed_mode:
        routes_path = _routes_path(settings)
        routes = load_routes(routes_path)
        routed = route_missing([q.question for q in questions], routes, router, routes_path)
        print(f"Question routes ({routes_path}): {len(routed)} of {len(questions)} routed.")
    tiers = document_tiers(conn, questions)

    # Created before the first ask, so a name clash stops the run before it costs anything.
    folder = settings.eval_results_dir / f"{name}-{started_at:%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    stored = StoredVectors(settings.embedding_model, vectors)
    rows = []
    for question in questions:
        route = routes.get(question_key(question.question))
        row = _run_question(question, conn, stored, generator, settings, reranker, route, tiers)
        status = row.answer.answer_status if row.answer else row.error
        print(f"{row.id}  {status}  {row.latency_s:.1f} s")
        rows.append(row)

    # The 3 modes that load the reranker.
    rerank_mode = settings.retrieval_mode in ("rerank", "temporal", "authority")
    authority_mode = settings.retrieval_mode == "authority"
    run_info = RunInfo(
        name=name,
        started_at=started_at,
        finished_at=_now(),
        git_sha=git_sha,
        git_dirty=git_dirty,
        golden_path=str(golden_path),
        golden_sha256=golden_sha256,
        smoke=smoke,
        questions=len(rows),
        settings=RunSettings(
            embedding_model=settings.embedding_model,
            retrieval_top_k=settings.retrieval_top_k,
            retrieval_mode=settings.retrieval_mode,
            retrieval_candidates=settings.retrieval_candidates,
            rrf_k=settings.rrf_k,
            hnsw_ef_search=settings.hnsw_ef_search,
            rerank_model=settings.rerank_model if rerank_mode else None,
            rerank_revision=settings.rerank_revision if rerank_mode else None,
            rerank_max_length=settings.rerank_max_length if rerank_mode else None,
            rerank_batch_size=settings.rerank_batch_size if rerank_mode else None,
            torch_threads=torch_threads,
            router_model=settings.router_model if routed_mode else None,
            router_effort=settings.router_effort if routed_mode else None,
            history_window_slack=settings.history_window_slack if routed_mode else None,
            authority_boost=settings.authority_boost if authority_mode else None,
            authority_demote=settings.authority_demote if authority_mode else None,
            generation_model=settings.generation_model,
            generation_effort=settings.generation_effort,
            generation_max_tokens=settings.generation_max_tokens,
        ),
        rerank_load_s=rerank_load_s,
    )
    labels = {question.id: question.labels for question in questions}
    summary = summarize(name, golden_sha256, started_at, rows, settings, labels)
    (folder / "run.json").write_text(run_info.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (folder / "questions.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )
    (folder / "summary.json").write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Results: {folder}")
    print(summary_line(summary))
    return folder


def _run_question(
    question: Question,
    conn: psycopg.Connection[TupleRow],
    embedder: StoredVectors,
    generator: Generator,
    settings: Settings,
    reranker: Reranker | None,
    route: Route | None,
    tiers: Mapping[str, int | None],
) -> QuestionRow:
    """Retrieve (with `route`, in temporal and authority modes), answer and score one question;
    its labels' tiers come from `tiers` (`document_tiers`). An ask error (`cli.ASK_ERRORS`)
    becomes the row's `error`. Retrieval reads a stored vector and a stored route, so it makes no
    network call: its failure is a bug or a database failure, and stops the run."""
    record = None if route is None else _route_record(conn, route, settings)
    start = time.monotonic()
    hits = retrieve(question.question, embedder, conn, settings, reranker, route)
    retrieve_s = round(time.monotonic() - start, 3)
    result: Answer | None = None
    usage: TokenUsage | None = None
    error: str | None = None
    try:
        result = answer(question.question, hits, generator, settings)
        usage = None if result.trace is None else result.trace.generation.usage
    except ASK_ERRORS as exc:
        error = f"{type(exc).__name__}: {_one_line(exc)}"
        # A cut-off answer was still billed: keep the tokens the API reported.
        usage = exc.usage if isinstance(exc, GenerationError) else None
    return QuestionRow(
        id=question.id,
        mode=question.mode,
        release_window=golden_window(question),
        label_tiers=[tiers[label.canonical_id] for label in question.labels],
        route=record,
        answerable=question.answerable,
        hits=[
            RankedHit(
                rank=rank,
                chunk_id=hit.chunk_id,
                canonical_id=hit.canonical_id,
                heading_path=hit.heading_path,
                distance=hit.distance,
                rrf_score=hit.rrf_score,
                dense_rank=hit.dense_rank,
                lexical_rank=hit.lexical_rank,
                rerank_score=hit.rerank_score,
                current=hit.current,
                release_windows=hit.release_windows,
                authority=hit.authority,
                authority_score=hit.authority_score,
            )
            for rank, hit in enumerate(hits, start=1)
        ],
        answer=result,
        metrics=score_retrieval(question, hits, settings.retrieval_top_k),
        checks=check_answer(question, hits, result),
        usage=usage,
        latency_s=round(time.monotonic() - start, 3),
        retrieve_s=retrieve_s,
        error=error,
    )


def score_retrieval_only(
    conn: psycopg.Connection[TupleRow], settings: Settings, reranker: Reranker | None = None
) -> RetrievalScores:
    """`make eval-retrieval` (S07-R1 decision 5): retrieve, in the settings' mode, for every
    answerable golden question with its stored vector, and score the hits; return the metrics in
    file order, each question's retrieve time in seconds (S08-T4: the wall time of the
    `retrieve` call, rerank included), the stale and temporal counts (S09-T3) and authority
    selection (S09-T7) over the top K hits, as `summarize` counts them, the CURRENT questions'
    mean MRR, and in temporal and authority modes the routes' counts for `router_line` (S09-T4;
    None in other modes). No Voyage call, no Anthropic call, nothing written.

    Raises GoldenSetError and EvalError as `run` does, and EvalError when a question has no
    stored vector, or in temporal and authority modes no stored route: this command never embeds
    or routes. Rerank, temporal and authority modes need `reranker`.
    """
    golden, _ = check_golden(conn, settings.eval_golden_path)
    questions = [question for question in golden.questions if question.answerable]
    vectors_path = settings.eval_vectors_dir / f"{settings.embedding_model}.json"
    vectors = load_vectors(vectors_path)
    missing = [q.id for q in questions if question_key(q.question) not in vectors]
    if missing:
        raise EvalError(
            f"no stored vector for {', '.join(missing)} in {vectors_path}: eval-retrieval never "
            "calls Voyage (`make eval-smoke` or `make eval` embeds missing questions)"
        )
    routes: dict[str, Route] = {}  # none outside temporal and authority modes
    if settings.retrieval_mode in ("temporal", "authority"):
        routes_path = _routes_path(settings)
        routes = load_routes(routes_path)
        unrouted = [q.id for q in questions if question_key(q.question) not in routes]
        if unrouted:
            raise EvalError(
                f"no stored route for {', '.join(unrouted)} in {routes_path}: eval-retrieval "
                "never calls the router (`make eval-routes` routes missing questions)"
            )
    tiers = document_tiers(conn, questions)
    stored = StoredVectors(settings.embedding_model, vectors)
    scores = []
    retrieve_s = []
    by_mode: list[tuple[Mode | None, list[Hit]]] = []  # for the stale count
    by_window: list[tuple[GoldenWindow | None, list[Hit]]] = []  # for the temporal count
    by_labels: list[AuthorityQuestion] = []  # for authority selection
    current_mrr: list[float] = []  # the CURRENT questions' MRR
    records: list[tuple[Question, RouteRecord]] = []  # for the router line
    for question in questions:
        route = routes.get(question_key(question.question))
        if route is not None:
            records.append((question, _route_record(conn, route, settings)))
        start = time.monotonic()
        hits = retrieve(question.question, stored, conn, settings, reranker, route)
        retrieve_s.append(time.monotonic() - start)
        metrics = score_retrieval(question, hits, settings.retrieval_top_k)
        if metrics is not None:  # always: an answerable question has labels (ADR-007)
            scores.append(metrics)
            if question.mode == "CURRENT":
                current_mrr.append(metrics.mrr)
        top = hits[: settings.retrieval_top_k]
        by_mode.append((question.mode, top))
        by_window.append((golden_window(question), top))
        label_tiers = [tiers[label.canonical_id] for label in question.labels]
        by_labels.append((question.mode, question.labels, label_tiers, top))
    return RetrievalScores(
        metrics=scores,
        retrieve_s=retrieve_s,
        stale=_count(stale_count(by_mode)),
        temporal=_rate_of(temporal_count(by_window)),
        authority=_rate_of(authority_count(by_labels)),
        current_mrr=_mean(current_mrr),
        router=router_stats(records) if records else None,
    )


def _routes_path(settings: Settings) -> Path:
    """The route file of ROUTER_MODEL (ADR-009 D3)."""
    return settings.eval_routes_dir / f"{settings.router_model}.json"


def _route_record(
    conn: psycopg.Connection[TupleRow], route: Route, settings: Settings
) -> RouteRecord:
    """What a row records of its route: the route, and the window and filter `retrieve` derives
    from it (the same function)."""
    window, temporal = temporal_plan(conn, route, settings)
    return RouteRecord(mode=route.mode, time_scope=route.time_scope, window=window, filter=temporal)


def router_stats(records: Sequence[tuple[Question, RouteRecord]]) -> RouterStats:
    """Count the routes of the answerable questions, each given with its question: router
    accuracy (`router_count`), the resolved windows against the golden ones, and the plans."""
    windows = [
        (
            golden_window(q),
            None if r.window is None else (r.window.from_release, r.window.until_release),
        )
        for q, r in records
    ]
    filters = [r.filter for _, r in records]
    return RouterStats(
        router=_rate_of(router_count([(q.mode, r.mode) for q, r in records if q.mode is not None])),
        windows=sum(1 for golden, window in windows if golden is not None and window == golden),
        golden_windows=sum(1 for golden, _ in windows if golden is not None),
        extra=sum(1 for golden, window in windows if golden is None and window is not None),
        current_only=sum(1 for f in filters if f is not None and f.current_only),
        windowed=sum(1 for f in filters if f is not None and not f.current_only),
        unfiltered=sum(1 for f in filters if f is None),
    )


def retrieval_report(settings: Settings, scores: Sequence[RetrievalMetrics]) -> str:
    """`make eval-retrieval`'s first two lines (S07-R1, S08-R1, S09-R1, S09-R2, pinned formats):
    the mode and its settings, then the metric means over the answerable questions. `time_line`,
    `authority_line`, `router_line` (temporal and authority modes only) and `timing_line`
    follow."""
    hybrid = (
        f"candidates {settings.retrieval_candidates}, k {settings.rrf_k}, "
        f"width {settings.hnsw_ef_search}"
    )
    # The revision shortened to 7 characters, as git shortens a commit SHA.
    reranked = (
        f"{hybrid}, model {settings.rerank_model}@{settings.rerank_revision[:7]}, "
        f"max length {settings.rerank_max_length}"
    )
    routed = f"{reranked}, router {settings.router_model}, slack {settings.history_window_slack}"
    if settings.retrieval_mode == "authority":
        mode = (
            f"authority ({routed}, boost {settings.authority_boost:g}, "
            f"demote {settings.authority_demote:g})"
        )
    elif settings.retrieval_mode == "temporal":
        mode = f"temporal ({routed})"
    elif settings.retrieval_mode == "rerank":
        mode = f"rerank ({reranked})"
    elif settings.retrieval_mode == "hybrid":
        mode = f"hybrid ({hybrid})"
    else:
        mode = f"dense (width {settings.hnsw_ef_search})"

    def mean(values: Sequence[float]) -> str:
        value = _mean(values)
        return "n/a" if value is None else f"{value:.3f}"

    k = settings.retrieval_top_k
    return (
        f"Mode: {mode}. Answerable questions: {len(scores)}.\n"
        f"Recall@{k} {mean([s.recall for s in scores])}  Hit@{k} {mean([s.hit for s in scores])}"
        f"  MRR {mean([s.mrr for s in scores])}  nDCG@{k} {mean([s.ndcg for s in scores])}"
    )


def timing_line(retrieve_s: Sequence[float], load_s: float | None) -> str:
    """`make eval-retrieval`'s third line (S08-R1 decision 5, pinned format): the median (p50; of
    an even count, the mean of the 2 middle values) and the nearest-rank p95 of the questions'
    retrieve times, then, in rerank, temporal and authority modes, the reranker's load time."""

    def seconds(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f} s"

    p50 = statistics.median(retrieve_s) if retrieve_s else None
    load = "" if load_s is None else f" Reranker load {load_s:.1f} s."
    return (
        f"Retrieve time: p50 {seconds(p50)}, p95 {seconds(_p95(retrieve_s))} "
        f"({len(retrieve_s)} questions).{load}"
    )


def time_line(stale: Count | None, temporal: Rate | None) -> str:
    """`make eval-retrieval`'s S09 time line (S09-R1, pinned format), between the metrics and the
    timing line: the stale-result rate and the temporal accuracy, each as a 3-decimal rate with
    its counts; n/a for one with no hits."""
    if stale is None:
        stale_part = "Stale rate n/a (no CURRENT hits)"
    else:
        rate = stale.count / stale.total
        stale_part = f"Stale rate {rate:.3f} ({stale.count} of {stale.total} CURRENT hits)"
    if temporal is None:
        temporal_part = "Temporal accuracy n/a (no dated HISTORY hits)"
    else:
        rate = temporal.pass_ / temporal.total
        temporal_part = (
            f"Temporal accuracy {rate:.3f} ({temporal.pass_} of {temporal.total} dated HISTORY "
            "hits)"
        )
    return f"{stale_part}  {temporal_part}"


def authority_line(authority: Rate | None, current_mrr: float | None) -> str:
    """`make eval-retrieval`'s authority line (S09-R2, pinned format), after the time line:
    authority selection as a 3-decimal rate with its counts, then the CURRENT questions' mean MRR,
    printed beside it because the same tier code drives the weights and the metric; n/a for
    either with no question."""
    if authority is None:
        selection = "Authority selection n/a (no CURRENT question with labels in 2+ tiers)"
    else:
        rate = authority.pass_ / authority.total
        selection = (
            f"Authority selection {rate:.3f} ({authority.pass_} of {authority.total} CURRENT "
            "questions)"
        )
    mrr = "n/a" if current_mrr is None else f"{current_mrr:.3f}"
    return f"{selection}  CURRENT MRR {mrr}"


def router_line(stats: RouterStats) -> str:
    """`make eval-retrieval`'s router line in temporal and authority modes (S09-R1, pinned
    format), between the authority line and the timing line: router accuracy as a 3-decimal rate
    with its counts, the resolved windows equal to the golden ones, of the golden windows, with
    the windows resolved where golden has none, then how many questions got each plan."""
    if stats.router is None:
        accuracy = "n/a"
    else:
        rate = stats.router.pass_ / stats.router.total
        accuracy = f"{rate:.3f} ({stats.router.pass_} of {stats.router.total})"
    return (
        f"Router accuracy {accuracy}  Windows {stats.windows} of {stats.golden_windows} "
        f"({stats.extra} extra)  Plans: {stats.current_only} current-only, "
        f"{stats.windowed} windowed, {stats.unfiltered} unfiltered"
    )


def summarize(
    name: str,
    golden_sha256: str,
    started_at: datetime,
    rows: Sequence[QuestionRow],
    settings: Settings,
    labels: Mapping[str, Sequence[Label]] | None = None,
) -> Summary:
    """The run's totals: metric means over the answerable questions, for each check how many of
    the rows it applies to (not None) passed, the p95 latencies and the mean cost per question
    at the settings' prices (S08-T3), the S09 time counts over the rows' hits (S09-T3), router
    accuracy over the answerable rows with a route (S09-T4), and authority selection (S09-T7).

    Authority selection needs each row's golden labels, by question id in `labels`, to find its
    first labeled hit: a row holds its label tiers, not its labels. None without `labels`."""
    metrics = [row.metrics for row in rows if row.metrics is not None]
    refusals = _rate(row.checks.false_refusal for row in rows)
    usages = [row.usage for row in rows if row.usage is not None]
    # US dollars per million tokens. Output tokens include reasoning (ADR-006).
    in_price = settings.generation_price_input_usd_per_mtok
    out_price = settings.generation_price_output_usd_per_mtok
    authority = None
    if labels is not None:
        by_labels = [(row.mode, labels[row.id], row.label_tiers, row.hits) for row in rows]
        authority = _rate_of(authority_count(by_labels))
    return Summary(
        name=name,
        golden_sha256=golden_sha256,
        started_at=started_at,
        questions=len(rows),
        answerable=sum(row.answerable for row in rows),
        errors=sum(row.error is not None for row in rows),
        recall=_mean([m.recall for m in metrics]),
        hit=_mean([m.hit for m in metrics]),
        mrr=_mean([m.mrr for m in metrics]),
        ndcg=_mean([m.ndcg for m in metrics]),
        distinct_sections=_mean([m.distinct_sections for m in metrics]),
        ac1=_rate(row.checks.ac1 for row in rows),
        ac2=_rate(row.checks.ac2 for row in rows),
        ac3=_rate(row.checks.ac3 for row in rows),
        false_refusals=Count(count=refusals.pass_, total=refusals.total),
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        latency_s_mean=sum(row.latency_s for row in rows) / len(rows),
        latency_s_p95=_p95([row.latency_s for row in rows]),
        retrieve_s_p95=_p95([row.retrieve_s for row in rows if row.retrieve_s is not None]),
        cost_usd_mean=_mean(
            [(u.input_tokens * in_price + u.output_tokens * out_price) / 1e6 for u in usages]
        ),
        # A row's hits are its top K, as retrieval returned them.
        stale=_count(stale_count([(row.mode, row.hits) for row in rows])),
        temporal=_rate_of(temporal_count([(row.release_window, row.hits) for row in rows])),
        # Temporal and authority modes' rows record a route (S09-T4); no other mode's do, so None
        # there.
        router=_rate_of(
            router_count(
                [
                    (row.mode, row.route.mode)
                    for row in rows
                    if row.answerable and row.mode is not None and row.route is not None
                ]
            )
        ),
        authority=authority,
    )


def resummarize(folder: Path, settings: Settings) -> Summary:
    """`make eval-resummarize` (S08-T3): rebuild the folder's `summary.json` with `summarize` from
    its `questions.jsonl`, keeping the summary's name, golden hash, start time and authority
    selection (S09-T7: it needs the golden labels, which the rows don't hold; `run` counted it);
    write it and return it. Nothing else in the folder changes."""
    path = folder / "summary.json"
    old = Summary.model_validate_json(path.read_text(encoding="utf-8"))
    lines = (folder / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [QuestionRow.model_validate_json(line) for line in lines]
    summary = summarize(old.name, old.golden_sha256, old.started_at, rows, settings)
    summary = summary.model_copy(update={"authority": old.authority})
    path.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return summary


def summary_line(summary: Summary) -> str:
    """The summary in one line, for the terminal."""

    def number(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    def rate(rate: Rate) -> str:
        return f"{rate.pass_}/{rate.total}"

    return (
        f"{summary.questions} questions ({summary.answerable} answerable), "
        f"{summary.errors} errors. Recall@10 {number(summary.recall)}, "
        f"Hit@10 {number(summary.hit)}, MRR {number(summary.mrr)}, "
        f"nDCG@10 {number(summary.ndcg)}. AC1 {rate(summary.ac1)}, AC2 {rate(summary.ac2)}, "
        f"AC3 {rate(summary.ac3)}, false refusals {summary.false_refusals.count}/"
        f"{summary.false_refusals.total}. Tokens: {summary.input_tokens:,} in, "
        f"{summary.output_tokens:,} out. Mean latency {summary.latency_s_mean:.1f} s."
    )


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _p95(values: Sequence[float]) -> float | None:
    """The nearest-rank 95th percentile (S08-R1): the value at sorted index ceil(n * 0.95) - 1,
    0-based; None for no values."""
    if not values:
        return None
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def _rate(results: Iterable[bool | None]) -> Rate:
    """Passes and total over the results that aren't None (n/a)."""
    known = [result for result in results if result is not None]
    return Rate(pass_=sum(known), total=len(known))


def _count(parts: tuple[int, int] | None) -> Count | None:
    """A time metric's (count, total) as a `Count`; None stays None."""
    return None if parts is None else Count(count=parts[0], total=parts[1])


def _rate_of(parts: tuple[int, int] | None) -> Rate | None:
    """A time metric's (passed, total) as a `Rate`; None stays None."""
    return None if parts is None else Rate(pass_=parts[0], total=parts[1])


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _git_state(cwd: Path | None = None) -> tuple[str, bool]:
    """The checked-out commit, and whether tracked files differ from it. Untracked files (such
    as an earlier run's results folder) don't count, as in `git describe --dirty`. Nor does
    `eval/results/` (S07-T4): every run rewrites the tracked `ablation.md`, which made the next run
    say dirty on clean code. `cwd` is the repo to check (a test's); default, the current directory.
    """

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=cwd
        ).stdout.strip()

    changed = git("status", "--porcelain", "--untracked-files=no", "--", ".", ":!eval/results")
    return git("rev-parse", "HEAD"), bool(changed)


def _one_line(error: Exception) -> str:
    """The error's message with every run of whitespace, newlines included, as one space."""
    return " ".join(str(error).split())
