"""The golden-set label check and the section listing (S06-T1), the eval run (S06-T4) and the
retrieval-only scoring (S07-T3), against the test database; authority mode and authority
selection (S09-T7).

Every test builds its own rows inside `conn`'s rolled-back transaction; expected counts and
values are counted or calculated by hand from those rows and the fakes' outputs.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow
from tests.conftest import FakeEmbedder, FakeGenerator, FakeReranker, FakeRouter

from orgknow.db.chunks import add_chunks, add_embedding
from orgknow.db.documents import add_alias, create_document
from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.versions import insert_version
from orgknow.embeddings.embedder import DIMENSIONS
from orgknow.eval.golden import (
    GoldenSetError,
    Label,
    LabelCount,
    check_labels,
    list_sections,
    load_golden_file,
)
from orgknow.eval.runner import (
    EvalError,
    authority_line,
    load_vectors,
    retrieval_report,
    router_line,
    run,
    save_routes,
    score_retrieval_only,
    time_line,
)
from orgknow.eval.table import write_table
from orgknow.generation.generator import GenerationError
from orgknow.generation.schema import Generation, ModelAnswer, TokenUsage
from orgknow.retrieval.router import Mode, Route
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
# Release dates from the manifest (00:00 UTC).
D24 = datetime(2022, 5, 3, tzinfo=UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)
D26 = datetime(2022, 12, 8, tzinfo=UTC)


def _version(
    conn: Conn,
    document_id: int,
    releases: tuple[int, int | None],
    dates: tuple[datetime, datetime | None],
    chunks: list[tuple[list[str], str]],
) -> None:
    """Store a version holding `chunks`, (heading path, text) each, in ordinal order."""
    version_id = insert_version(
        conn,
        NewVersion(
            document_id=document_id,
            content_hash=VERSION_HASH,
            source_path="content/en/docs/test/page.md",
            snapshot_repo="website",
            snapshot_ref=f"release-1.{releases[0]}",
            snapshot_sha="1111111111111111111111111111111111111111",
            valid_from_release=releases[0],
            valid_until_release=releases[1],
            valid_from_date=dates[0],
            valid_until_date=dates[1],
        ),
    )
    new_chunks = [
        NewChunk(ordinal=i, heading_path=path, text=text) for i, (path, text) in enumerate(chunks)
    ]
    add_chunks(conn, version_id, new_chunks)


@pytest.fixture
def documents(conn: Conn, seeded_releases: None) -> None:
    """Two documents (their versions reference the releases, so those are stored first).
    `web:/test/a/` has two versions that share one text; `web:/test/b/` is also known by the
    alias `web:/test/old-b/`."""
    a = create_document(conn, "web:/test/a/", "docs_page")
    _version(
        conn,
        a,
        (24, 24),
        (D24, D25),
        [([], "a intro old"), (["Install"], "a install")],
    )
    _version(
        conn,
        a,
        (25, None),
        (D25, None),
        [
            ([], "a intro"),
            (["Install"], "a install"),
            (["Install", "Linux"], "a install linux"),
            (["Installation"], "a installation"),
        ],
    )
    b = create_document(conn, "web:/test/b/", "docs_page")
    _version(conn, b, (24, None), (D24, None), [([], "b intro"), (["Usage"], "b usage")])
    add_alias(conn, b, "web:/test/old-b/")


def _golden_file(tmp_path: Path, labels_q01: str, labels_q02: str = "") -> Path:
    """A golden file with q01 (and q02 if given) holding these YAML label lines."""
    text = "version: v0\nquestions:\n"
    for qid, labels in (("q01", labels_q01), ("q02", labels_q02)):
        if labels:
            text += (
                f"  - id: {qid}\n"
                "    question: How do I install it?\n"
                "    mode: CURRENT\n"
                "    answerable: true\n"
                "    expected_answer: Like this.\n"
                "    smoke: false\n"
                "    labels:\n" + labels
            )
    path = tmp_path / "golden.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.usefixtures("documents")
def test_an_alias_resolves_to_its_canonical_id(conn: Conn) -> None:
    names = ["web:/test/old-b/", "web:/test/b/", "web:/test/missing/"]

    # An unknown name is left out.
    assert canonical_ids(conn, names) == {
        "web:/test/old-b/": "web:/test/b/",
        "web:/test/b/": "web:/test/b/",
    }


@pytest.mark.usefixtures("documents")
def test_the_check_counts_distinct_texts_per_label_and_reports_0_matches(
    conn: Conn, tmp_path: Path
) -> None:
    path = _golden_file(
        tmp_path,
        "      - {document: 'web:/test/a/', section: Install}\n"
        "      - {document: 'web:/test/old-b/'}\n",
        "      - {document: 'web:/test/a/', section: ''}\n"
        "      - {document: 'web:/test/a/', section: Nope}\n"
        "      - {document: 'web:/test/missing/'}\n",
    )

    golden, counts = check_labels(conn, load_golden_file(path))

    assert counts == [
        # "a install" (in both versions: 1 text) and "a install linux"; not "a installation".
        LabelCount(question_id="q01", document="web:/test/a/", section=["Install"], texts=2),
        # The alias's document: "b intro" and "b usage".
        LabelCount(question_id="q01", document="web:/test/old-b/", section=None, texts=2),
        # "a intro old" and "a intro".
        LabelCount(question_id="q02", document="web:/test/a/", section=[], texts=2),
        # No such section, and no such document: both 0, so both are reported.
        LabelCount(question_id="q02", document="web:/test/a/", section=["Nope"], texts=0),
        LabelCount(question_id="q02", document="web:/test/missing/", section=None, texts=0),
    ]
    # The resolved labels name the canonical_id, so the metrics compare ids only.
    assert golden.questions[0].labels == [
        Label(canonical_id="web:/test/a/", section=["Install"]),
        Label(canonical_id="web:/test/b/", section=None),
    ]


@pytest.mark.usefixtures("documents")
def test_a_duplicate_after_resolving_aliases_is_rejected(conn: Conn, tmp_path: Path) -> None:
    # Two different names as written, one document once the alias is resolved.
    path = _golden_file(
        tmp_path, "      - {document: 'web:/test/b/'}\n      - {document: 'web:/test/old-b/'}\n"
    )
    golden_file = load_golden_file(path)  # as written, the labels don't overlap

    with pytest.raises(GoldenSetError) as error:
        check_labels(conn, golden_file)

    assert error.value.errors == [
        "q01: labels: web:/test/b/ (whole document) is listed twice after resolving aliases"
    ]


def test_sections_are_listed_by_first_appearance_across_versions(conn: Conn) -> None:
    # The newer version is stored first, so only the version date can put the older first.
    # "Setup" exists only in the newer version, so it comes after the older version's sections
    # even though its ordinal there (1) is lower than "Install"'s and "Usage"'s.
    c = create_document(conn, "web:/test/c/", "docs_page")
    _version(
        conn,
        c,
        (26, None),
        (D26, None),
        [([], "c intro"), (["Setup"], "c setup"), (["Install"], "c install new"), (["Usage"], "u")],
    )
    _version(
        conn,
        c,
        (24, 25),
        (D24, D26),
        [([], "c intro"), (["Install"], "c install old"), (["Usage"], "u")],
    )

    sections = list_sections(document_texts(conn, "web:/test/c/"))

    # "c intro" and "u" are in both versions: 1 text each. "Install" has 2 different texts.
    assert sections == [([], 1), (["Install"], 2), (["Usage"], 1), (["Setup"], 1)]


# The eval run (S06-T4). Two stored pages, each text with a vector under the fake embedder's
# model. The fake embeds every question as [0.5] * 1024, so every question gets the same 3 hits,
# by cosine distance 1 - cos: "a intro" (all ones: the same direction, 0), "a install" (e1 + e2:
# 1 - 1 / (16√2) = 0.955806) and "b usage" (e1: 1 - 0.5 / 16 = 0.96875). Every page is current
# since 1.24, so q02's golden window (1.20 to 1.23, S09-T3) holds none of them.

MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
SHA = "2222222222222222222222222222222222222222"
Q1 = "How do I install A?"
Q2 = "What is A?"
Q3 = "What did the private design doc decide?"
GOLDEN = f"""\
version: test
questions:
  - id: q01
    question: {Q1}
    mode: CURRENT
    answerable: true
    expected_answer: See Install.
    smoke: true
    labels:
      - {{document: 'web:/test/a/', section: Install}}
      - {{document: 'web:/test/b/'}}
  - id: q02
    question: {Q2}
    mode: CURRENT
    answerable: true
    expected_answer: See the intro.
    release_window: {{from: '1.20', until: '1.23'}}
    smoke: true
    labels:
      - {{document: 'web:/test/a/', section: ''}}
  - id: q03
    question: {Q3}
    answerable: false
    expected_answer: Insufficient evidence.
    smoke: false
    labels: []
"""
USAGE = {"input_tokens": 1000, "output_tokens": 300, "thinking_tokens": 200}  # FakeGenerator's
# S09-T6: a docs page's authority with no route: tier 1 at the latest release (1.37), no stage.
DOCS_AT_37 = {"target_release": 37, "tier": 1, "effective_stage": None, "stage_confidence": None}
# A cut-off answer: the API reported its tokens, so the error row keeps them.
CUT_OFF = GenerationError(
    "no usable answer from the model (stop reason: max_tokens)",
    "max_tokens",
    TokenUsage(input_tokens=500, output_tokens=16000, thinking_tokens=15000),
)


def _vector(*components: float) -> list[float]:
    """A 1024-number vector starting with `components`, zeros after."""
    return [*components] + [0.0] * (DIMENSIONS - len(components))


def _page(
    conn: Conn,
    canonical_id: str,
    title: str,
    chunks: list[tuple[list[str], str, list[float]]],
    source_type: str = "docs_page",
) -> list[int]:
    """A docs page (or a document of `source_type`) current since 1.24 holding `chunks`, (heading
    path, text, vector) each, with each text's vector under the fake embedder's model. Returns
    the chunk ids."""
    version_id = insert_version(
        conn,
        NewVersion(
            document_id=create_document(conn, canonical_id, source_type),
            content_hash=VERSION_HASH,
            source_path="content/en/docs/test/page.md",
            snapshot_repo="website",
            snapshot_ref="release-1.24",
            snapshot_sha=SHA,
            valid_from_release=24,
            valid_from_date=D24,
            metadata={"title": title},
        ),
    )
    new_chunks = [
        NewChunk(ordinal=i, heading_path=path, text=text)
        for i, (path, text, _) in enumerate(chunks)
    ]
    for _, text, vector in chunks:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()  # rule R13
        add_embedding(conn, content_hash, FakeEmbedder.model, vector)
    return add_chunks(conn, version_id, new_chunks)


@pytest.fixture
def chunk_ids(conn: Conn, seeded_releases: None) -> dict[str, int]:
    a_intro, a_install = _page(
        conn,
        "web:/test/a/",
        "Page A",
        [([], "a intro", [1.0] * DIMENSIONS), (["Install"], "a install", _vector(1.0, 1.0))],
    )
    [b_usage] = _page(conn, "web:/test/b/", "Page B", [(["Usage"], "b usage", _vector(1.0))])
    return {"a intro": a_intro, "a install": a_install, "b usage": b_usage}


@pytest.fixture
def run_settings(settings: Settings, tmp_path: Path) -> Settings:
    """The test database, the golden file above, and results and vectors under tmp_path. No
    .env file, and the fake embedder's model, so the stored vectors above are searched. Dense
    mode, which the expected hits below assume, whatever the default mode is."""
    golden_path = tmp_path / "golden.yaml"
    golden_path.write_text(GOLDEN, encoding="utf-8")
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        corpus_manifest_path=MANIFEST,
        embedding_model=FakeEmbedder.model,
        retrieval_mode="dense",
        eval_golden_path=golden_path,
        eval_results_dir=tmp_path / "results",
        eval_vectors_dir=tmp_path / "vectors",
        eval_routes_dir=tmp_path / "routes",
    )


class ScriptedGenerator:
    """A `Generator` that returns, or raises, the next outcome per call: one call per question
    with hits, in file order."""

    def __init__(self, outcomes: list[ModelAnswer | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []  # the prompts

    def generate(self, system: str, prompt: str) -> Generation:
        self.calls.append(prompt)
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return Generation(output=outcome, stop_reason="end_turn", usage=FakeGenerator.usage)


def _refusing() -> FakeGenerator:
    """Every question answered `insufficient_evidence`: for tests that only count calls."""
    return FakeGenerator(
        ModelAnswer(
            answer_status="insufficient_evidence",
            answer="",
            evidence=[],
            insufficient_evidence_reason="Not covered.",
            conflicts=[],
        )
    )


def _rows(folder: Path) -> list[dict[str, object]]:
    lines = (folder / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _key(question: str) -> str:
    """A question's key in the vector file: the sha256 hex of its UTF-8 text."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def test_a_run_writes_the_pinned_results_format(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    generator = ScriptedGenerator(
        [
            ModelAnswer(
                answer_status="answered",
                answer="Follow page B.",
                evidence=[chunk_ids["b usage"]],
                insufficient_evidence_reason=None,
                conflicts=[],
            ),
            CUT_OFF,  # q02: an ask error, recorded as a row
            ModelAnswer(
                answer_status="insufficient_evidence",
                answer="",
                evidence=[],
                insufficient_evidence_reason="The sources don't cover it.",
                conflicts=[],
            ),
        ]
    )

    folder = run(conn, FakeEmbedder(), generator, run_settings, smoke=False, name="dense")

    golden_path = run_settings.eval_golden_path
    golden_sha256 = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    run_info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    started_at, finished_at = run_info.pop("started_at"), run_info.pop("finished_at")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", started_at)
    assert started_at <= finished_at
    # The folder is named by the run's name and its start: 2026-10-08T10:00:00Z -> 20261008T100000Z.
    assert folder.parent == run_settings.eval_results_dir
    assert folder.name == "dense-" + started_at.replace("-", "").replace(":", "")
    git_sha, git_dirty = run_info.pop("git_sha"), run_info.pop("git_dirty")
    assert re.fullmatch(r"[0-9a-f]{40}", git_sha)
    assert isinstance(git_dirty, bool)
    assert run_info == {
        "name": "dense",
        "golden_path": str(golden_path),
        "golden_sha256": golden_sha256,
        "smoke": False,
        "questions": 3,
        "settings": {
            "embedding_model": "fake-model",
            "retrieval_top_k": 10,
            # S07-T3: the retrieval settings, all 4 written in either mode (the defaults).
            "retrieval_mode": "dense",
            "retrieval_candidates": 20,
            "rrf_k": 60,
            "hnsw_ef_search": 100,
            # S08-T2: the reranker's fields are null outside rerank mode.
            "rerank_model": None,
            "rerank_revision": None,
            "rerank_max_length": None,
            "rerank_batch_size": None,
            "torch_threads": None,
            # S09-T4: the router's fields are null outside temporal mode.
            "router_model": None,
            "router_effort": None,
            "history_window_slack": None,
            # S09-T7: authority mode's weights are null outside it.
            "authority_boost": None,
            "authority_demote": None,
            # S10-T2: the rule-found conflicts' date tolerance, in every mode (the default).
            "history_date_tolerance_days": 7,
            "generation_model": "claude-opus-5-5",
            "generation_effort": "medium",
            "generation_max_tokens": 16000,
        },
        "rerank_load_s": None,
    }

    rows = _rows(folder)
    assert [list(row) for row in rows] == [
        [
            *("id", "mode", "release_window", "label_tiers", "route", "answerable", "hits"),
            *("answer", "conflicts"),  # S10-T4: the row's conflicts follow its answer
            *("metrics", "checks", "usage", "latency_s", "retrieve_s", "error"),
        ]
    ] * 3
    latencies = [row.pop("latency_s") for row in rows]
    assert all(isinstance(latency, float) and latency >= 0 for latency in latencies)
    # S08-T3: the retrieve stage alone, part of the question's latency.
    retrieve_times = [row.pop("retrieve_s") for row in rows]
    assert all(
        isinstance(t, float) and 0 <= t <= lat
        for t, lat in zip(retrieve_times, latencies, strict=True)
    )
    hits = [
        {
            "rank": 1,
            "chunk_id": chunk_ids["a intro"],
            "canonical_id": "web:/test/a/",
            "heading_path": [],
            "distance": pytest.approx(0.0, abs=1e-6),
            "rrf_score": None,
            "dense_rank": 1,
            "lexical_rank": None,
            "rerank_score": None,
            # S09-T3: the page's one version is open, since 1.24.
            "current": True,
            "release_windows": [[24, None]],
            "authority": DOCS_AT_37,
            "authority_score": None,  # authority mode only (S09-T7)
        },
        {
            "rank": 2,
            "chunk_id": chunk_ids["a install"],
            "canonical_id": "web:/test/a/",
            "heading_path": ["Install"],
            "distance": pytest.approx(0.955806, abs=1e-6),
            "rrf_score": None,
            "dense_rank": 2,
            "lexical_rank": None,
            "rerank_score": None,
            # S09-T3: the page's one version is open, since 1.24.
            "current": True,
            "release_windows": [[24, None]],
            "authority": DOCS_AT_37,
            "authority_score": None,  # authority mode only (S09-T7)
        },
        {
            "rank": 3,
            "chunk_id": chunk_ids["b usage"],
            "canonical_id": "web:/test/b/",
            "heading_path": ["Usage"],
            "distance": pytest.approx(0.96875, abs=1e-6),
            "rrf_score": None,
            "dense_rank": 3,
            "lexical_rank": None,
            "rerank_score": None,
            # S09-T3: the page's one version is open, since 1.24.
            "current": True,
            "release_windows": [[24, None]],
            "authority": DOCS_AT_37,
            "authority_score": None,  # authority mode only (S09-T7)
        },
    ]
    # q01: its 2 labels are found at ranks 2 and 3, so MRR 1/2 and
    # nDCG (1/log2(3) + 1/log2(4)) / (1 + 1/log2(3)) = 1.130930 / 1.630930 = 0.693426.
    assert rows[0] == {
        "id": "q01",
        "mode": "CURRENT",
        "release_window": None,  # the golden file gives none
        # S09-T7: both labels' documents are docs pages, tier 1, in label order.
        "label_tiers": [1, 1],
        "route": None,  # routes are temporal and authority modes' only (S09-T4)
        "answerable": True,
        "hits": hits,
        "answer": {
            "question": Q1,
            "answer_status": "answered",
            "answer": "Follow page B.",
            "evidence": [
                {
                    "chunk_id": chunk_ids["b usage"],
                    "document": "web:/test/b/",
                    "title": "Page B",
                    "section": "Usage",
                    "source_type": "docs_page",
                    "release_windows": [["1.24", None]],
                    "claimed_status": None,
                    "claimed_stage": None,
                    "tier": 1,
                    "superseded_proposal": False,
                    "effective_stage": None,
                    "stage_confidence": None,
                    "source_url": "https://github.com/kubernetes/website/blob/"
                    f"{SHA}/content/en/docs/test/page.md",
                }
            ],
            "conflicts": [],  # S10-T4: docs pages alone give no rule-found conflict
            "insufficient_evidence_reason": None,
            "model": "claude-opus-5-5",
            "trace_id": None,
        },
        "conflicts": [],
        "metrics": {
            "recall": 1.0,
            "hit": 1,
            "mrr": 0.5,
            "ndcg": pytest.approx(0.693426, abs=1e-6),
            "distinct_sections": 3,
        },
        "checks": {
            "ac1": True,
            "ac2": True,
            "ac3": None,
            "false_refusal": False,
            "loser_only": False,
        },
        "usage": USAGE,
        "error": None,
    }
    # q02: the failed ask is a row. Its retrieval is still scored (its intro label is rank 1),
    # and the checks are n/a: an answerable error row counts under errors only.
    assert rows[1] == {
        "id": "q02",
        "mode": "CURRENT",
        "release_window": [20, 23],  # the golden window as minors
        "label_tiers": [1],
        "route": None,
        "answerable": True,
        "hits": hits,
        "answer": None,
        "conflicts": [],
        "metrics": {"recall": 1.0, "hit": 1, "mrr": 1.0, "ndcg": 1.0, "distinct_sections": 3},
        "checks": {
            "ac1": None,
            "ac2": None,
            "ac3": None,
            "false_refusal": None,
            "loser_only": None,
        },
        "usage": {"input_tokens": 500, "output_tokens": 16000, "thinking_tokens": 15000},
        "error": "GenerationError: no usable answer from the model (stop reason: max_tokens)",
    }
    # q03: unanswerable, so no metrics; `insufficient_evidence` with a reason passes AC3.
    assert rows[2] == {
        "id": "q03",
        "mode": None,
        "release_window": None,
        "label_tiers": [],  # no labels
        "route": None,
        "answerable": False,
        "hits": hits,
        "answer": {
            "question": Q3,
            "answer_status": "insufficient_evidence",
            "answer": "",
            "evidence": [],
            "conflicts": [],
            "insufficient_evidence_reason": "The sources don't cover it.",
            "model": "claude-opus-5-5",
            "trace_id": None,
        },
        "conflicts": [],
        "metrics": None,
        "checks": {
            "ac1": None,
            "ac2": True,
            "ac3": True,
            "false_refusal": None,
            "loser_only": False,
        },
        "usage": USAGE,
        "error": None,
    }

    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    latency_s_mean = summary.pop("latency_s_mean")
    assert latency_s_mean == pytest.approx(sum(latencies) / 3)
    # S08-T3: a nearest-rank p95 of 3 values is at sorted index ceil(3 * 0.95) - 1 = 2, the
    # largest. Cost per question at $4 / $20 per million tokens: q01 and q03 (1,000 * 4 + 300 *
    # 20) / 1e6 = $0.010; q02, the cut-off answer, (500 * 4 + 16,000 * 20) / 1e6 = $0.322; the
    # mean, 0.342 / 3 = $0.114.
    assert summary.pop("latency_s_p95") == max(latencies)
    assert summary.pop("retrieve_s_p95") == max(retrieve_times)
    assert summary.pop("cost_usd_mean") == pytest.approx(0.114)
    # Means over q01 and q02. AC2 counts q01 and q03 (the rows with an answer); false refusals
    # count q01 only (q02 has no answer). Tokens: 1000 + 500 + 1000 in, 300 + 16000 + 300 out.
    # S09-T3: q01 and q02 are CURRENT, 3 hits each, none stale: 0 of 6. q02's golden window
    # (20 to 23) holds none of its 3 hits, all from 24 on: 0 of 3. No routes outside temporal mode.
    # S09-T7: no CURRENT question's labels span 2 tiers (q01: 1 and 1; q02: 1), so no authority
    # selection.
    assert summary == {
        "name": "dense",
        "golden_sha256": golden_sha256,
        "started_at": started_at,
        "questions": 3,
        "answerable": 2,
        "errors": 1,
        "recall": 1.0,
        "hit": 1.0,
        "mrr": 0.75,
        "ndcg": pytest.approx((0.693426 + 1.0) / 2, abs=1e-6),
        "distinct_sections": 3.0,
        "ac1": {"pass": 1, "total": 1},
        "ac2": {"pass": 2, "total": 2},
        "ac3": {"pass": 1, "total": 1},
        "false_refusals": {"count": 0, "total": 1},
        "input_tokens": 2500,
        "output_tokens": 16600,
        "stale": {"count": 0, "total": 6},
        "temporal": {"pass": 0, "total": 3},
        "router": None,
        "authority": None,
        "conflicts_rule": 0,  # S10-T4: no KEP among the hits
        "conflicts_model": 0,  # S10-T5: the fake model lists no pairs
        "loser_only_answers": 0,
    }
    assert len(generator.calls) == 3

    # The table reads the folder back; a folder without summary.json (like s04/) is skipped.
    (run_settings.eval_results_dir / "s04").mkdir()
    (run_settings.eval_results_dir / "s04" / "README.md").write_text("notes", encoding="utf-8")
    table = write_table(run_settings.eval_results_dir).read_text(encoding="utf-8")
    # nDCG (0.693426 + 1) / 2 = 0.847; errors 1 in 1 run; the p95s to 1 decimal, cost to 4;
    # stale 0 / 6 and temporal 0 / 3, both 0.000; router and authority selection n/a.
    assert table.splitlines()[4:] == [
        f"| dense | golden.yaml {golden_sha256[:8]} | 1 | 3 | 1.000 | 1.000 | 0.750 | 0.847 "
        f"| 1.000 | 1.000 | 1.000 | 1.000 | {max(latencies):.1f} | {max(retrieve_times):.1f} "
        "| 0.1140 | 0.000 | 0.000 | n/a | n/a |"
    ]


def test_a_second_run_makes_no_voyage_request_and_retrieves_the_same(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    first_embedder, second_embedder = FakeEmbedder(), FakeEmbedder()

    first = run(conn, first_embedder, _refusing(), run_settings, smoke=False, name="first")
    second = run(conn, second_embedder, _refusing(), run_settings, smoke=False, name="second")

    # One request with all 3 questions, as queries; then none.
    assert first_embedder.calls == [("query", [Q1, Q2, Q3])]
    assert second_embedder.calls == []
    vectors_path = run_settings.eval_vectors_dir / "fake-model.json"
    text = vectors_path.read_text(encoding="utf-8")
    assert list(json.loads(text)) == sorted([_key(Q1), _key(Q2), _key(Q3)])  # keys sorted
    assert json.loads(text)[_key(Q1)] == [0.5] * DIMENSIONS
    # The second run read the stored vectors: the same hits and metrics.
    for before, after in zip(_rows(first), _rows(second), strict=True):
        assert (before["hits"], before["metrics"]) == (after["hits"], after["metrics"])


def test_a_deleted_vector_is_the_only_one_embedded_again(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    run(conn, FakeEmbedder(), _refusing(), run_settings, smoke=False, name="first")
    vectors_path = run_settings.eval_vectors_dir / "fake-model.json"
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    del vectors[_key(Q2)]
    vectors_path.write_text(json.dumps(vectors), encoding="utf-8")
    embedder = FakeEmbedder()

    run(conn, embedder, _refusing(), run_settings, smoke=False, name="second")

    assert embedder.calls == [("query", [Q2])]  # exactly 1 request, for exactly that question
    assert set(json.loads(vectors_path.read_text(encoding="utf-8"))) == {
        _key(Q1),
        _key(Q2),
        _key(Q3),
    }


def test_a_smoke_run_runs_only_the_smoke_questions(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    embedder = FakeEmbedder()

    folder = run(conn, embedder, _refusing(), run_settings, smoke=True, name="dense")

    assert [row["id"] for row in _rows(folder)] == ["q01", "q02"]  # q03 has smoke: false
    assert embedder.calls == [("query", [Q1, Q2])]
    run_info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert (run_info["smoke"], run_info["questions"]) == (True, 2)


# Rerank mode (S08-T2) with a fake reranker. Every question's fused pool holds the 3 texts (see
# the retrieval-only tests below); the fake scores "b usage" highest, then "a install", "a intro".
RERANK_SCORES = {"a intro": 0.1, "a install": 0.2, "b usage": 0.9}


def test_a_rerank_run_records_the_reranker_and_each_hits_score(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    settings = run_settings.model_copy(update={"retrieval_mode": "rerank"})

    folder = run(
        conn,
        FakeEmbedder(),
        _refusing(),
        settings,
        smoke=True,
        name="rerank",
        reranker=FakeReranker(RERANK_SCORES),
        rerank_load_s=3.25,
        torch_threads=11,
    )

    run_info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    # The settings defaults (ADR-008), and the load time and threads as the caller passed them.
    assert {key: run_info["settings"][key] for key in run_info["settings"] if "rerank" in key} == {
        "rerank_model": "BAAI/bge-reranker-base",
        "rerank_revision": "2cfc18c9415c912f9d8155881c133215df768a70",
        "rerank_max_length": 512,
        "rerank_batch_size": 8,
    }
    assert (run_info["settings"]["torch_threads"], run_info["rerank_load_s"]) == (11, 3.25)
    # q01's hits in the fake's order, each with its raw score.
    hits = _rows(folder)[0]["hits"]
    assert isinstance(hits, list)
    assert [(hit["chunk_id"], hit["rerank_score"]) for hit in hits] == [
        (chunk_ids["b usage"], 0.9),
        (chunk_ids["a install"], 0.2),
        (chunk_ids["a intro"], 0.1),
    ]


# Temporal mode (S09-T4) with the fake reranker and stored or fake routes. The 3 pages are current
# since 1.24, so a CURRENT filter keeps them all; HISTORY "before 1.22" (until 21, searched until
# 22 with slack 1) keeps none.


def _route(mode: Mode, kind: str = "none", start: str | None = None) -> Route:
    return Route.model_validate(
        {"mode": mode, "time_scope": {"kind": kind, "start": start, "end": None}}
    )


def _routes_path(settings: Settings) -> Path:
    return settings.eval_routes_dir / "claude-opus-5-5.json"  # the default ROUTER_MODEL


def test_a_temporal_run_fills_the_missing_routes_and_retrieves_with_each(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    settings = run_settings.model_copy(update={"retrieval_mode": "temporal"})
    save_routes(_routes_path(settings), {_key(Q1): _route("CURRENT")})  # q01's is stored
    router = FakeRouter({Q2: _route("HISTORY", "before", "1.22"), Q3: _route("WHY")})
    generator = _refusing()

    folder = run(
        conn,
        FakeEmbedder(),
        generator,
        settings,
        smoke=False,
        name="temporal",
        reranker=FakeReranker(RERANK_SCORES),
        router=router,
    )

    # Only the 2 questions with no stored route were routed, in file order, and saved.
    assert router.calls == [Q2, Q3]
    stored = json.loads(_routes_path(settings).read_text(encoding="utf-8"))["routes"]
    assert set(stored) == {_key(Q1), _key(Q2), _key(Q3)}
    rows = _rows(folder)
    no_scope = {"kind": "none", "start": None, "end": None}
    assert [row["route"] for row in rows] == [
        {
            "mode": "CURRENT",
            "time_scope": no_scope,
            "window": None,
            "filter": {"current_only": True, "from_release": None, "until_release": None},
        },
        {
            "mode": "HISTORY",
            "time_scope": {"kind": "before", "start": "1.22", "end": None},
            "window": {"from_release": None, "until_release": 21},
            "filter": {"current_only": False, "from_release": None, "until_release": 22},
        },
        {"mode": "WHY", "time_scope": no_scope, "window": None, "filter": None},
    ]
    # Each route reached retrieval: q02's filter kept no text, so no hits and no answer call.
    assert [len(row["hits"]) for row in rows] == [3, 0, 3]
    assert len(generator.calls) == 2
    run_info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert {
        key: run_info["settings"][key]
        for key in ("rerank_model", "router_model", "router_effort", "history_window_slack")
    } == {
        "rerank_model": "BAAI/bge-reranker-base",  # temporal mode reranks too
        "router_model": "claude-opus-5-5",
        "router_effort": "low",
        "history_window_slack": 1,
    }
    # q01 (CURRENT) routed CURRENT; q02 (CURRENT) routed HISTORY; q03 is unanswerable: 1 of 2.
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["router"] == {"pass": 1, "total": 2}

    # A second run routes nothing: every route is stored.
    second = FakeRouter({})
    run(
        conn,
        FakeEmbedder(),
        _refusing(),
        settings,
        smoke=False,
        name="temporal-2",
        reranker=FakeReranker(RERANK_SCORES),
        router=second,
    )
    assert second.calls == []


def test_retrieval_only_in_temporal_mode_reads_the_stored_routes(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    _store_vectors(run_settings, Q1, Q2)
    settings = run_settings.model_copy(update={"retrieval_mode": "temporal"})
    # q01 (CURRENT, no golden window) routed CURRENT "in 1.30": the mode matches, and its window
    # (30 to 30) is one golden has none for. q02 (CURRENT, golden 1.20 to 1.23) routed HISTORY
    # "between 1.20 and 1.23": the mode misses, the window (20 to 23) equals golden's. Its filter,
    # 19 to 24, keeps the 3 pages (current since 1.24), so retrieval is rerank's.
    save_routes(
        _routes_path(settings),
        {
            _key(Q1): _route("CURRENT", "in", "1.30"),
            _key(Q2): Route.model_validate(
                {
                    "mode": "HISTORY",
                    "time_scope": {"kind": "between", "start": "1.20", "end": "1.23"},
                }
            ),
        },
    )

    scores = score_retrieval_only(conn, settings, FakeReranker(RERANK_SCORES))

    # As rerank's line in the parametrized test above, plus the router and the slack.
    assert retrieval_report(settings, scores.metrics) == (
        "Mode: temporal (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, "
        "max length 512, router claude-opus-5-5, slack 1). Answerable questions: 2.\n"
        "Recall@10 1.000  Hit@10 1.000  MRR 0.667  nDCG@10 0.750"
    )
    assert time_line(scores.stale, scores.temporal) == (
        "Stale rate 0.000 (0 of 6 CURRENT hits)  "
        "Temporal accuracy 0.000 (0 of 3 dated HISTORY hits)"
    )
    assert scores.router is not None
    assert router_line(scores.router) == (
        "Router accuracy 0.500 (1 of 2)  Windows 1 of 1 (1 extra)  "
        "Plans: 1 current-only, 1 windowed, 0 unfiltered"
    )


@pytest.mark.usefixtures("chunk_ids")
def test_retrieval_only_in_temporal_mode_with_a_missing_route_is_an_error(
    conn: Conn, run_settings: Settings
) -> None:
    _store_vectors(run_settings, Q1, Q2)
    settings = run_settings.model_copy(update={"retrieval_mode": "temporal"})
    save_routes(_routes_path(settings), {_key(Q1): _route("CURRENT")})  # none for q02
    reranker = FakeReranker(RERANK_SCORES)

    with pytest.raises(EvalError) as error:
        score_retrieval_only(conn, settings, reranker)

    assert str(error.value) == (
        f"no stored route for q02 in {_routes_path(settings)}: eval-retrieval never calls the "
        "router (`make eval-routes` routes missing questions)"
    )
    assert reranker.calls == []  # it stops before any retrieval


def test_a_label_matching_nothing_stops_the_run_before_any_call(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    golden_path = run_settings.eval_golden_path
    golden_path.write_text(
        GOLDEN.replace("'web:/test/b/'", "'web:/test/missing/'"), encoding="utf-8"
    )
    embedder, generator = FakeEmbedder(), _refusing()

    with pytest.raises(EvalError) as error:
        run(conn, embedder, generator, run_settings, smoke=False, name="dense")

    assert str(error.value) == (
        "1 label matches no stored text (see `make eval-check`): "
        "q01  web:/test/missing/  (whole document)  0 texts"
    )
    assert (embedder.calls, generator.calls) == ([], [])
    assert not run_settings.eval_results_dir.exists()


def test_a_question_with_no_vector_and_no_embedder_stops_the_run(
    conn: Conn, chunk_ids: dict[str, int], run_settings: Settings
) -> None:
    generator = _refusing()

    with pytest.raises(EvalError, match="3 questions have no stored vector and VOYAGE_API_KEY"):
        run(conn, None, generator, run_settings, smoke=False, name="dense")

    assert generator.calls == []


def test_a_missing_or_empty_vector_file_holds_no_vectors(tmp_path: Path) -> None:
    path = tmp_path / "voyage-4-large.json"
    assert load_vectors(path) == {}
    path.write_text("", encoding="utf-8")
    assert load_vectors(path) == {}


def test_a_vector_of_the_wrong_length_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "voyage-4-large.json"
    path.write_text(json.dumps({"ab12": [0.5] * 1023}), encoding="utf-8")

    with pytest.raises(EvalError, match=r"the vector for ab12 has 1023 numbers, expected 1024"):
        load_vectors(path)


def test_a_question_with_no_hits_scores_0_without_a_model_call(
    conn: Conn, run_settings: Settings
) -> None:
    # The labelled texts are stored, but none has a vector: retrieval returns nothing.
    for canonical_id, path in (("web:/test/a/", "Install"), ("web:/test/b/", "Usage")):
        version_id = insert_version(
            conn,
            NewVersion(
                document_id=create_document(conn, canonical_id, "docs_page"),
                content_hash=VERSION_HASH,
                source_path="content/en/docs/test/page.md",
                snapshot_repo="website",
                snapshot_ref="release-1.24",
                snapshot_sha=SHA,
                valid_from_release=24,
                valid_from_date=D24,
                metadata={"title": "Page"},
            ),
        )
        add_chunks(
            conn,
            version_id,
            [
                NewChunk(ordinal=0, heading_path=[], text=f"{canonical_id} intro"),
                NewChunk(ordinal=1, heading_path=[path], text=f"{canonical_id} {path}"),
            ],
        )
    generator = _refusing()

    folder = run(conn, FakeEmbedder(), generator, run_settings, smoke=False, name="dense")

    rows = _rows(folder)
    assert rows[0]["hits"] == []
    assert rows[0]["metrics"] == {
        "recall": 0.0,
        "hit": 0,
        "mrr": 0.0,
        "ndcg": 0.0,
        "distinct_sections": 0,
    }
    assert rows[0]["usage"] is None
    answer = rows[0]["answer"]
    assert isinstance(answer, dict)
    assert answer["insufficient_evidence_reason"] == "no evidence retrieved"
    assert generator.calls == []
    assert [row["error"] for row in rows] == [None, None, None]


# `make eval-retrieval` (S07-T3, decision 5): retrieval scores alone, from the stored vectors, on
# the answerable questions (q01, q02). The rows are the run tests' above. Called on `conn`, like
# `run`: the command's own connection couldn't see this test's uncommitted rows. Lexical search,
# by Postgres's rules (checked with psql): Q1 "How do I install A?" keeps only 'instal', held by
# "a install"; Q2 "What is A?" is all stop words, so it matches nothing.


def _store_vectors(settings: Settings, *questions: str) -> Path:
    """Write the vector file with the fake embedder's vector for each question; return its path."""
    path = settings.eval_vectors_dir / f"{FakeEmbedder.model}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({_key(q): [0.5] * DIMENSIONS for q in questions}), encoding="utf-8")
    return path


@pytest.mark.usefixtures("chunk_ids")
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        # As in the run test: q01 MRR 1/2 and nDCG 0.693426; q02 MRR 1 and nDCG 1.
        # Means: MRR 0.75, nDCG 0.846713. Both questions are CURRENT: CURRENT MRR 0.75 too.
        (
            "dense",
            "Mode: dense (width 100). Answerable questions: 2.\n"
            "Recall@10 1.000  Hit@10 1.000  MRR 0.750  nDCG@10 0.847",
        ),
        # q01 fused: "a install" dense 2 + lexical 1 = 1/62 + 1/61 = 0.032522, then "a intro"
        # 1/61 = 0.016393, then "b usage" 1/63 = 0.015873. Labels at ranks 1 and 3: MRR 1, nDCG
        # (1 + 1/log2(4)) / (1 + 1/log2(3)) = 1.5 / 1.630930 = 0.919721. q02: no lexical hit, so
        # the dense order: MRR 1, nDCG 1. Means: MRR 1, nDCG 0.959861.
        (
            "hybrid",
            "Mode: hybrid (candidates 20, k 60, width 100). Answerable questions: 2.\n"
            "Recall@10 1.000  Hit@10 1.000  MRR 1.000  nDCG@10 0.960",
        ),
        # S08-T2, the fake reranker's order: "b usage", "a install", "a intro" for both. q01's
        # labels at ranks 1 and 2: MRR 1, nDCG 1. q02's at rank 3: MRR 1/3, nDCG
        # (1/log2(4)) / 1 = 0.5. Means: MRR 0.666667, nDCG 0.75. The model's revision is
        # shortened to 7 characters.
        (
            "rerank",
            "Mode: rerank (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, "
            "max length 512). Answerable questions: 2.\n"
            "Recall@10 1.000  Hit@10 1.000  MRR 0.667  nDCG@10 0.750",
        ),
    ],
)
def test_retrieval_only_scores_each_mode_and_writes_nothing(
    conn: Conn, run_settings: Settings, mode: str, expected: str
) -> None:
    vectors_path = _store_vectors(run_settings, Q1, Q2)  # q03 is unanswerable: no vector needed
    vectors_before = vectors_path.read_bytes()
    settings = run_settings.model_copy(update={"retrieval_mode": mode})

    # Dense and hybrid never call the reranker.
    scores = score_retrieval_only(conn, settings, FakeReranker(RERANK_SCORES))

    assert retrieval_report(settings, scores.metrics) == expected
    assert scores.router is None  # no router line outside temporal mode (S09-T4)
    # S09-T3: q01 and q02 are CURRENT, with 3 hits each in every mode, all held by an open
    # version since 1.24; q02's golden window, 1.20 to 1.23, holds none of its 3.
    assert time_line(scores.stale, scores.temporal) == (
        "Stale rate 0.000 (0 of 6 CURRENT hits)  "
        "Temporal accuracy 0.000 (0 of 3 dated HISTORY hits)"
    )
    # S09-T7: no CURRENT question's labels span 2 tiers. Both questions are CURRENT, so the
    # CURRENT MRR is the MRR above.
    assert authority_line(scores.authority, scores.current_mrr) == (
        "Authority selection n/a (no CURRENT question with labels in 2+ tiers)  "
        f"CURRENT MRR {expected.split('MRR ')[1].split()[0]}"
    )
    assert len(scores.retrieve_s) == 2  # one retrieve time per answerable question (S08-T4)
    assert all(seconds >= 0 for seconds in scores.retrieve_s)
    assert not settings.eval_results_dir.exists()
    assert vectors_path.read_bytes() == vectors_before


@pytest.mark.usefixtures("chunk_ids")
def test_retrieval_only_with_a_missing_vector_is_an_error(
    conn: Conn, run_settings: Settings
) -> None:
    vectors_path = _store_vectors(run_settings, Q1)  # none for q02

    with pytest.raises(EvalError) as error:
        score_retrieval_only(conn, run_settings)

    assert str(error.value) == (
        f"no stored vector for q02 in {vectors_path}: eval-retrieval never calls Voyage "
        "(`make eval-smoke` or `make eval` embeds missing questions)"
    )


@pytest.mark.usefixtures("chunk_ids")
def test_retrieval_only_stops_on_a_label_matching_nothing(
    conn: Conn, run_settings: Settings
) -> None:
    run_settings.eval_golden_path.write_text(
        GOLDEN.replace("'web:/test/b/'", "'web:/test/missing/'"), encoding="utf-8"
    )
    _store_vectors(run_settings, Q1, Q2)

    with pytest.raises(EvalError) as error:
        score_retrieval_only(conn, run_settings)

    assert str(error.value) == (
        "1 label matches no stored text (see `make eval-check`): "
        "q01  web:/test/missing/  (whole document)  0 texts"
    )


# Authority mode and authority selection (S09-T7), on the 3 texts above plus a blog post current
# since 1.24 ("c post"). One CURRENT question, Q1, labeled with page A's Install section (a docs
# page: tier 1) and the blog post (tier 6): its label tiers span 2 values, so it counts. Routed
# CURRENT, its filter keeps all 4 texts (all current). The fake reranker's order: the blog post
# (2.0), "a install" (1.0), "a intro" (0.0), "b usage" (-1.0). Authority mode, by hand: the blog is
# demoted, sigmoid(2) * 0.8 = 0.880797 * 0.8 = 0.704638; the docs texts are tier 1 and valid at
# 1.37, so boosted: sigmoid(1) * 1.25 = 0.913823, sigmoid(0) * 1.25 = 0.625, sigmoid(-1) * 1.25 =
# 0.336177. So "a install" (tier 1, labeled) comes first: right. Temporal mode keeps the blog first
# (tier 6, labeled): wrong. Either way the first hit is labeled: MRR 1.

AUTHORITY_SCORES = {"c post": 2.0, "a install": 1.0, "a intro": 0.0, "b usage": -1.0}
AUTHORITY_GOLDEN = f"""\
version: test
questions:
  - id: q01
    question: {Q1}
    mode: CURRENT
    answerable: true
    expected_answer: See Install.
    smoke: true
    labels:
      - {{document: 'web:/test/a/', section: Install}}
      - {{document: 'web:/blog/test/c/'}}
"""


@pytest.fixture
def authority_settings(conn: Conn, chunk_ids: dict[str, int], run_settings: Settings) -> Settings:
    """The blog post, the golden file above, Q1's stored vector and route (CURRENT), and
    authority mode."""
    _page(
        conn, "web:/blog/test/c/", "Post C", [([], "c post", _vector(0.0, 0.0, 1.0))], "blog_post"
    )
    run_settings.eval_golden_path.write_text(AUTHORITY_GOLDEN, encoding="utf-8")
    _store_vectors(run_settings, Q1)
    save_routes(_routes_path(run_settings), {_key(Q1): _route("CURRENT")})
    return run_settings.model_copy(update={"retrieval_mode": "authority"})


def test_an_authority_run_records_the_weights_the_label_tiers_and_authority_selection(
    conn: Conn, authority_settings: Settings
) -> None:
    router = FakeRouter({})  # the route is stored

    folder = run(
        conn,
        FakeEmbedder(),
        _refusing(),
        authority_settings,
        smoke=False,
        name="authority",
        reranker=FakeReranker(AUTHORITY_SCORES),
        router=router,
    )

    assert router.calls == []
    run_info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    keys = ("rerank_model", "router_model", "history_window_slack")
    assert {
        key: run_info["settings"][key] for key in (*keys, "authority_boost", "authority_demote")
    } == {
        "rerank_model": "BAAI/bge-reranker-base",
        "router_model": "claude-opus-5-5",
        "history_window_slack": 1,
        # The settings defaults (S09-R2 decision 3).
        "authority_boost": 1.25,
        "authority_demote": 0.8,
    }
    [row] = _rows(folder)
    assert row["label_tiers"] == [1, 6]
    assert isinstance(row["route"], dict) and row["route"]["mode"] == "CURRENT"
    hits = row["hits"]
    assert isinstance(hits, list)
    assert [
        (hit["canonical_id"], hit["authority"]["tier"], hit["rerank_score"]) for hit in hits
    ] == [
        ("web:/test/a/", 1, 1.0),
        ("web:/blog/test/c/", 6, 2.0),
        ("web:/test/a/", 1, 0.0),
        ("web:/test/b/", 1, -1.0),
    ]
    assert [hit["authority_score"] for hit in hits] == pytest.approx(
        [0.913823, 0.704638, 0.625, 0.336177], abs=1e-6
    )
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["authority"] == {"pass": 1, "total": 1}
    table = write_table(authority_settings.eval_results_dir).read_text(encoding="utf-8")
    # Stale 0 of 4 (all current), no golden window, router 1 of 1, authority selection 1 of 1.
    assert table.splitlines()[4].endswith("| 0.000 | n/a | 1.000 | 1.000 |")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "temporal",
            "Mode: temporal (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, "
            "max length 512, router claude-opus-5-5, slack 1). Answerable questions: 1.\n"
            "Authority selection 0.000 (0 of 1 CURRENT questions)  CURRENT MRR 1.000",
        ),
        (
            "authority",
            "Mode: authority (candidates 20, k 60, width 100, model "
            "BAAI/bge-reranker-base@2cfc18c, max length 512, router claude-opus-5-5, slack 1, "
            "boost 1.25, demote 0.8). "
            "Answerable questions: 1.\n"
            "Authority selection 1.000 (1 of 1 CURRENT questions)  CURRENT MRR 1.000",
        ),
    ],
)
def test_retrieval_only_counts_authority_selection_in_each_routed_mode(
    conn: Conn, authority_settings: Settings, mode: str, expected: str
) -> None:
    settings = authority_settings.model_copy(update={"retrieval_mode": mode})

    scores = score_retrieval_only(conn, settings, FakeReranker(AUTHORITY_SCORES))

    mode_line = retrieval_report(settings, scores.metrics).splitlines()[0]
    assert f"{mode_line}\n{authority_line(scores.authority, scores.current_mrr)}" == expected
    assert scores.router is not None  # the router line prints in both modes
