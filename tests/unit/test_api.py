"""`POST /query` (S12-T2) offline: `TestClient`, fakes for every paid client and for Langfuse, and
no database.

The steps that read the database are replaced: the per-request connection is a placeholder,
`retrieve` returns one hand-built hit (after embedding the question, as the real one does first)
and `rule_conflicts` returns hand-built conflicts. The rest of the shared pipeline runs for real:
the answer, its citations and the trace. Expected outputs are the CLI's pinned output and error
lines for the same fakes (tests/integration/test_cli.py), written by hand.
"""

import json
from collections.abc import Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import (
    FakeEmbedder,
    FakeGenerator,
    FakeLangfuse,
    FakeObservation,
    FakeReranker,
)

from orgknow import cli, pipeline
from orgknow.api import app as api_app
from orgknow.api.app import create_app
from orgknow.db.models import Authority, Hit
from orgknow.embeddings.embedder import EmbedResult, InputType
from orgknow.generation.conflicts import Conflict
from orgknow.generation.schema import Generation, ModelAnswer
from orgknow.settings import Settings

MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
QUESTION = "What enforces pod security standards in-tree?"
TEXT = "The Pod Security admission controller enforces the Pod Security Standards."
SHA = "0123456789abcdef0123456789abcdef01234567"
PATH = "content/en/docs/concepts/security/pod-security-admission.md"
TRACING_OFF = "tracing off: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to trace each ask"
# Fake secrets: none may appear in a response or a trace. The database password stands for the
# settings: a dump of them would show it (the database URL is a plain string).
ANTHROPIC_KEY = "sk-ant-fake-secret-0f1e2d3c"
VOYAGE_KEY = "pa-fake-secret-4b5a6978"
LANGFUSE_PUBLIC_KEY = "pk-lf-fake-secret-5e6f"
LANGFUSE_SECRET_KEY = "sk-lf-fake-secret-7a8b"
DB_PASSWORD = "fake-db-password-9c0d"
SECRETS = (ANTHROPIC_KEY, VOYAGE_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, DB_PASSWORD)

# The Pod Security Admission page's chunk, as tests/integration/test_cli.py stores it: current
# since 1.30, under "Exemptions", a docs page (tier 1 at the latest release, 1.37).
HIT = Hit(
    chunk_id=7,
    content_hash="a" * 64,
    distance=0.1,
    text=TEXT,
    canonical_id="web:/docs/concepts/security/pod-security-admission/",
    source_type="docs_page",
    heading_path=["Exemptions"],
    release_windows=[(30, None)],
    current=True,
    claimed_status=None,
    claimed_stage=None,
    snapshot_repo="website",
    snapshot_sha=SHA,
    source_path=PATH,
    metadata={"title": "Pod Security Admission"},
    authority=Authority(target_release=37, tier=1, effective_stage=None, stage_confidence=None),
)
# A rule-found conflict, hand-built: only the trace test's `rule_conflicts` returns it.
FOUND = Conflict(
    kind="history_date",
    found_by="rule",
    chunk_ids=[7],
    documents=["web:/docs/concepts/security/pod-security-admission/"],
    summary="The page's history line dates the release 30 days off.",
    resolution="observed_beats_claimed",
    prevails=None,
)
# The CLI's pinned `ask` output for the same fakes (tests/integration/test_cli.py), with this
# file's chunk id; trace_id is null with tracing off.
EXPECTED = {
    "question": QUESTION,
    "answer_status": "answered",
    "answer": "The Pod Security admission controller.",
    "evidence": [
        {
            "chunk_id": 7,
            "document": "web:/docs/concepts/security/pod-security-admission/",
            "title": "Pod Security Admission",
            "section": "Exemptions",
            "source_type": "docs_page",
            "release_windows": [["1.30", None]],
            "claimed_status": None,
            "claimed_stage": None,
            "tier": 1,
            "superseded_proposal": False,
            "effective_stage": None,
            "stage_confidence": None,
            "source_url": f"https://github.com/kubernetes/website/blob/{SHA}/{PATH}",
        }
    ],
    "conflicts": [],
    "insufficient_evidence_reason": None,
    "model": "claude-opus-5-5",
    "trace_id": None,
}
CONNECTION = object()  # stands in for the per-request database connection


def _settings(**changes: Any) -> Settings:
    """No .env file and no Langfuse keys unless a test passes them, so nothing local can turn
    tracing on; hybrid mode, so no reranker loads unless a test asks for one."""
    values: dict[str, Any] = {
        "database_url": f"postgresql://orgknow:{DB_PASSWORD}@127.0.0.1:5433/orgknow",
        "corpus_manifest_path": MANIFEST,
        "anthropic_api_key": ANTHROPIC_KEY,
        "voyage_api_key": VOYAGE_KEY,
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "retrieval_mode": "hybrid",
    }
    return Settings(_env_file=None, **{**values, **changes})


def _answered() -> FakeGenerator:
    return FakeGenerator(
        ModelAnswer(
            answer_status="answered",
            answer="The Pod Security admission controller.",
            evidence=[HIT.chunk_id],
            insufficient_evidence_reason=None,
            conflicts=[],
        )
    )


class Offline:
    """What the replaced steps saw: one entry per connection opened, and the reranker each
    `retrieve` call got."""

    def __init__(self) -> None:
        self.connections: list[str] = []
        self.rerankers: list[Any] = []


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> Offline:
    seen = Offline()

    def connect(url: str, **kwargs: Any) -> nullcontext[object]:
        seen.connections.append(url)
        return nullcontext(CONNECTION)

    def retrieve(
        question: str,
        embedder: FakeEmbedder,
        conn: object,
        settings: Settings,
        reranker: Any = None,
        route: Any = None,
    ) -> list[Hit]:
        assert conn is CONNECTION
        embedder.embed([question], "query")
        seen.rerankers.append(reranker)
        return [HIT]

    monkeypatch.setattr(api_app.psycopg, "connect", connect)
    monkeypatch.setattr(pipeline, "retrieve", retrieve)
    monkeypatch.setattr(pipeline, "rule_conflicts", lambda conn, hits, settings: [])
    return seen


def _no_secret(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


def _trace_text(observation: FakeObservation) -> str:
    """Everything a trace recorded, as one string."""
    return repr(observation.fields) + "".join(_trace_text(c) for c in observation.children)


def test_query_returns_the_json_ask_prints(
    offline: Offline, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings()
    embedder = FakeEmbedder()

    with TestClient(create_app(settings, embedder=embedder, generator=_answered())) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == EXPECTED
    assert embedder.calls == [("query", [QUESTION])]
    assert offline.rerankers == [None]  # hybrid mode: no reranker is loaded
    _no_secret(response.text)
    # `orgknow ask`, given the same fakes, prints the same JSON.
    assert cli.ask(QUESTION, CONNECTION, FakeEmbedder(), _answered(), settings, None) == 0
    assert json.loads(capsys.readouterr().out) == response.json()


def test_startup_loads_the_reranker_once_and_says_tracing_off_once(
    offline: Offline, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loads: list[str] = []
    reranker = FakeReranker({})

    def load_reranker(settings: Settings) -> FakeReranker:
        loads.append(settings.retrieval_mode)
        return reranker

    monkeypatch.setattr(api_app, "load_reranker", load_reranker)
    app = create_app(
        _settings(retrieval_mode="rerank"), embedder=FakeEmbedder(), generator=_answered()
    )

    with TestClient(app) as client:
        first = client.post("/query", json={"question": QUESTION})
        second = client.post("/query", json={"question": QUESTION})

    assert (first.status_code, second.status_code) == (200, 200)
    assert loads == ["rerank"]  # once, at startup, for 2 requests
    assert offline.rerankers == [reranker, reranker]  # both requests used it
    assert len(offline.connections) == 2  # one database connection per request
    assert capsys.readouterr().err.splitlines() == [TRACING_OFF]


class RaisingEmbedder:
    """An `Embedder` whose call fails the way the Voyage client can."""

    model = FakeEmbedder.model

    def __init__(self, error: Exception) -> None:
        self.error = error

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult:
        raise self.error


class RaisingGenerator:
    """A `Generator` whose call fails the way the Anthropic SDK can."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, system: str, prompt: str) -> Generation:
        raise self.error


# The CLI's stderr lines for the same fakes (tests/integration/test_cli.py), after "error: ".
@pytest.mark.parametrize(
    ("embedder", "generator", "detail"),
    [
        (
            FakeEmbedder(),
            FakeGenerator(None, stop_reason="refusal"),
            "no usable answer from the model (stop reason: refusal)",
        ),
        (
            FakeEmbedder(),
            RaisingGenerator(
                anthropic.APIConnectionError(
                    request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
                )
            ),
            "Connection error.",
        ),
        (
            RaisingEmbedder(RuntimeError("Voyage API returned HTTP 503: upstream\nunavailable")),
            FakeGenerator(None),
            "Voyage API returned HTTP 503: upstream unavailable",  # one line
        ),
    ],
    ids=["generation-error", "anthropic-api-error", "voyage-http-error"],
)
def test_an_ask_error_is_502_with_the_clis_error_line(
    offline: Offline,
    embedder: FakeEmbedder | RaisingEmbedder,
    generator: FakeGenerator | RaisingGenerator,
    detail: str,
) -> None:
    with TestClient(create_app(_settings(), embedder=embedder, generator=generator)) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    _no_secret(response.text)


def test_an_unreachable_database_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()

    def refuse(url: str, **kwargs: Any) -> None:
        # The message names the URL, password included: the response must not repeat it.
        raise psycopg.OperationalError(f"connection to {url} failed: Connection refused")

    monkeypatch.setattr(api_app.psycopg, "connect", refuse)
    embedder, generator = FakeEmbedder(), _answered()

    with TestClient(create_app(settings, embedder=embedder, generator=generator)) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 503
    assert response.json() == {"detail": "database unreachable"}
    assert (embedder.calls, generator.calls) == ([], [])  # no paid call without a database
    _no_secret(response.text)


@pytest.mark.parametrize(
    "body",
    [{}, {"question": ""}, {"question": "   "}, {"question": 7}, {"text": QUESTION}],
    ids=["no-question", "empty", "blank", "not-a-string", "wrong-key"],
)
def test_a_bad_body_is_422(offline: Offline, body: dict[str, object]) -> None:
    embedder = FakeEmbedder()

    with TestClient(create_app(_settings(), embedder=embedder, generator=_answered())) as client:
        response = client.post("/query", json=body)

    assert response.status_code == 422
    assert (embedder.calls, offline.connections) == ([], [])
    _no_secret(response.text)


def _traced_settings() -> Settings:
    return _settings(
        langfuse_public_key=LANGFUSE_PUBLIC_KEY, langfuse_secret_key=LANGFUSE_SECRET_KEY
    )


def test_each_request_is_one_trace_named_ask(offline: Offline) -> None:
    langfuse = FakeLangfuse()
    app = create_app(
        _traced_settings(), embedder=FakeEmbedder(), generator=_answered(), langfuse=langfuse
    )

    with TestClient(app) as client:
        responses = [client.post("/query", json={"question": QUESTION}) for _ in range(2)]

    assert [response.json()["trace_id"] for response in responses] == ["fake-trace-id"] * 2
    assert [trace.name for trace in langfuse.traces] == ["ask", "ask"]
    assert langfuse.flushes == 1  # at shutdown
    for trace in langfuse.traces:
        _no_secret(_trace_text(trace))


def test_a_failed_answer_still_traces_the_rule_found_conflicts(
    offline: Offline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "rule_conflicts", lambda conn, hits, settings: [FOUND])
    langfuse = FakeLangfuse()
    refusing = FakeGenerator(None, stop_reason="refusal")
    app = create_app(
        _traced_settings(), embedder=FakeEmbedder(), generator=refusing, langfuse=langfuse
    )

    with TestClient(app) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    [trace] = langfuse.traces
    assert [child.name for child in trace.children] == ["retrieve", "generate"]
    generate = trace.children[1]
    assert generate.fields["level"] == "ERROR"
    assert generate.fields["metadata"] == {
        "stop_reason": "refusal",
        "conflicts": [
            {
                "kind": "history_date",
                "found_by": "rule",
                "chunk_ids": [7],
                "documents": ["web:/docs/concepts/security/pod-security-admission/"],
                "summary": "The page's history line dates the release 30 days off.",
                "resolution": "observed_beats_claimed",
                "prevails": None,
            }
        ],
    }
    _no_secret(_trace_text(trace))


def test_startup_stops_on_a_missing_key_without_printing_it() -> None:
    app = create_app(_settings(voyage_api_key=None))

    with (
        pytest.raises(RuntimeError) as error,
        TestClient(app),
    ):
        pass

    assert str(error.value) == "VOYAGE_API_KEY is not set: add the key to .env (see .env.example)."
