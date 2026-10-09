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
from stored vectors only, and scores the hits with no answer call: free, and it writes nothing.

In rerank mode (S08-T2), both get the reranker the caller loaded once, before the question loop.
"""

import hashlib
import json
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow
from pydantic import BaseModel, ConfigDict, Field

from orgknow.cli import ASK_ERRORS
from orgknow.embeddings.embedder import DIMENSIONS, Embedder, EmbedResult, InputType
from orgknow.eval.checks import AnswerChecks, check_answer
from orgknow.eval.golden import (
    GoldenSet,
    LabelCount,
    Mode,
    Question,
    check_labels,
    check_line,
    load_golden_file,
)
from orgknow.eval.metrics import RetrievalMetrics, score_retrieval
from orgknow.generation.generator import GenerationError, Generator, answer
from orgknow.generation.schema import Answer, TokenUsage
from orgknow.retrieval.rerank import Reranker
from orgknow.retrieval.retrieve import retrieve
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
    # S08-T2: rerank mode's model and its thread count; None in other modes and older folders.
    rerank_model: str | None = None
    rerank_revision: str | None = None
    rerank_max_length: int | None = None
    rerank_batch_size: int | None = None
    torch_threads: int | None = None
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
    rrf_score: float | None  # hybrid and rerank only
    dense_rank: int | None
    lexical_rank: int | None
    rerank_score: float | None = None  # rerank only (S08-T2); absent in older folders


class QuestionRow(BaseModel):
    """One line of `questions.jsonl`: one question's hits, answer, scores and cost."""

    id: str
    mode: Mode | None
    answerable: bool
    hits: list[RankedHit]
    answer: Answer | None  # the `ask` JSON; None when the ask failed
    metrics: RetrievalMetrics | None  # None when unanswerable
    checks: AnswerChecks
    usage: TokenUsage | None  # None when the model wasn't called (no hits)
    latency_s: float  # retrieve + answer
    error: str | None  # "<Type>: <message>" when the ask failed


class Rate(BaseModel):
    """How many of the rows a check applies to passed it."""

    # `pass` is a Python keyword: the field is `pass_`, written as "pass".
    model_config = ConfigDict(serialize_by_alias=True, validate_by_name=True)

    pass_: int = Field(alias="pass")
    total: int


class Count(BaseModel):
    """How many of the rows a flag applies to have it."""

    count: int
    total: int


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
) -> Path:
    """Run the golden set (only its `smoke: true` questions with `smoke`) and write its results
    folder; return the folder. `embedder` is called only for questions with no stored vector.
    Rerank mode needs `reranker`; `run.json` records its load time and torch's thread count.

    Raises GoldenSetError for an invalid golden file, and EvalError when a label matches no
    stored text, a vector is missing with no embedder, or embedding fails: all before any
    Anthropic call.
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

    # Created before the first ask, so a name clash stops the run before it costs anything.
    folder = settings.eval_results_dir / f"{name}-{started_at:%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    stored = StoredVectors(settings.embedding_model, vectors)
    rows = []
    for question in questions:
        row = _run_question(question, conn, stored, generator, settings, reranker)
        status = row.answer.answer_status if row.answer else row.error
        print(f"{row.id}  {status}  {row.latency_s:.1f} s")
        rows.append(row)

    rerank_mode = settings.retrieval_mode == "rerank"
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
            generation_model=settings.generation_model,
            generation_effort=settings.generation_effort,
            generation_max_tokens=settings.generation_max_tokens,
        ),
        rerank_load_s=rerank_load_s,
    )
    summary = summarize(name, golden_sha256, started_at, rows)
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
) -> QuestionRow:
    """Retrieve, answer and score one question. An ask error (`cli.ASK_ERRORS`) becomes the row's
    `error`. Retrieval reads a stored vector, so it makes no network call: its failure is a bug
    or a database failure, and stops the run."""
    start = time.monotonic()
    hits = retrieve(question.question, embedder, conn, settings, reranker)
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
            )
            for rank, hit in enumerate(hits, start=1)
        ],
        answer=result,
        metrics=score_retrieval(question, hits, settings.retrieval_top_k),
        checks=check_answer(question, hits, result),
        usage=usage,
        latency_s=round(time.monotonic() - start, 3),
        error=error,
    )


def score_retrieval_only(
    conn: psycopg.Connection[TupleRow], settings: Settings, reranker: Reranker | None = None
) -> list[RetrievalMetrics]:
    """`make eval-retrieval` (S07-R1 decision 5): retrieve, in the settings' mode, for every
    answerable golden question with its stored vector, and score the hits; return the metrics in
    file order. No Voyage call, no Anthropic call, nothing written.

    Raises GoldenSetError and EvalError as `run` does, and EvalError when a question has no
    stored vector: this command never embeds. Rerank mode needs `reranker`.
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
    stored = StoredVectors(settings.embedding_model, vectors)
    scores = []
    for question in questions:
        hits = retrieve(question.question, stored, conn, settings, reranker)
        metrics = score_retrieval(question, hits, settings.retrieval_top_k)
        if metrics is not None:  # always: an answerable question has labels (ADR-007)
            scores.append(metrics)
    return scores


def retrieval_report(settings: Settings, scores: Sequence[RetrievalMetrics]) -> str:
    """`make eval-retrieval`'s two lines (S07-R1, S08-R1, pinned formats): the mode and its
    settings, then the metric means over the answerable questions."""
    hybrid = (
        f"candidates {settings.retrieval_candidates}, k {settings.rrf_k}, "
        f"width {settings.hnsw_ef_search}"
    )
    if settings.retrieval_mode == "rerank":
        # The revision shortened to 7 characters, as git shortens a commit SHA.
        mode = (
            f"rerank ({hybrid}, model {settings.rerank_model}@{settings.rerank_revision[:7]}, "
            f"max length {settings.rerank_max_length})"
        )
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


def summarize(
    name: str, golden_sha256: str, started_at: datetime, rows: Sequence[QuestionRow]
) -> Summary:
    """The run's totals: metric means over the answerable questions, and for each check how many
    of the rows it applies to (not None) passed."""
    metrics = [row.metrics for row in rows if row.metrics is not None]
    refusals = _rate(row.checks.false_refusal for row in rows)
    usages = [row.usage for row in rows if row.usage is not None]
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
    )


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


def _rate(results: Iterable[bool | None]) -> Rate:
    """Passes and total over the results that aren't None (n/a)."""
    known = [result for result in results if result is not None]
    return Rate(pass_=sum(known), total=len(known))


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
