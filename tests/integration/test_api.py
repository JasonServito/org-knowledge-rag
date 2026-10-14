import json
import re
import socket
import threading
from contextlib import nullcontext

import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient
from tests.conftest import FakeEmbedder, FakeGenerator, FakeReranker, FakeRouter
from tests.integration.test_cli import (
    FAKE_ANTHROPIC_KEY,
    FAKE_VOYAGE_KEY,
    MANIFEST,
    QUESTION,
    TEXT,
    Conn,
    RaisingRouter,
    _answered,
    _route,
    _store_one_chunk,
)

from orgknow import pipeline
from orgknow.api import app as api_app
from orgknow.api.app import create_app
from orgknow.cli import ask
from orgknow.db.connect import api_connection
from orgknow.db.models import Authority, Hit
from orgknow.generation.schema import Generation
from orgknow.provenance import chain as chain_module
from orgknow.retrieval.router import RouterError
from orgknow.settings import Settings

NEW_ID = re.compile(r"[0-9a-f]{32}")  # a new random request ID (docs/interfaces.md)


@pytest.fixture
def closed_port() -> int:
    # Ask the OS for a free port, then close the socket: nothing is listening there now.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def test_health_and_ready_are_200_when_db_is_up(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    health = client.get("/health")
    assert health.json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    # Every response carries its own new request ID.
    ids = [health.headers["X-Request-ID"], ready.headers["X-Request-ID"]]
    assert all(NEW_ID.fullmatch(request_id) for request_id in ids)
    assert ids[0] != ids[1]


def test_ready_is_503_but_health_stays_200_when_db_is_unreachable(closed_port: int) -> None:
    unreachable = Settings(
        _env_file=None,
        database_url=f"postgresql://orgknow:orgknow@127.0.0.1:{closed_port}/orgknow",
    )
    client = TestClient(create_app(unreachable))

    ready = client.get("/ready")
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}  # a probe answer, not the error envelope
    assert NEW_ID.fullmatch(ready.headers["X-Request-ID"])
    # Liveness must not depend on the DB, or an orchestrator would restart a healthy process.
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


# `POST /query` (S12-T2) against the test database, with fake paid clients and no Langfuse keys.


def _query_settings(settings: Settings, **changes: object) -> Settings:
    """The test database with fake keys and no Langfuse keys (no .env), in hybrid mode unless a
    test says otherwise, so no test loads the reranker's model."""
    values: dict[str, object] = {
        "database_url": settings.database_url,
        "corpus_manifest_path": MANIFEST,
        "anthropic_api_key": FAKE_ANTHROPIC_KEY,
        "voyage_api_key": FAKE_VOYAGE_KEY,
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "retrieval_mode": "hybrid",
    }
    return Settings(_env_file=None, **{**values, **changes})


@pytest.mark.usefixtures("seeded_releases")
def test_query_answers_from_postgres_with_the_json_ask_prints(
    conn: Conn,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The chunk is stored inside this test's rolled-back transaction, which a new connection can't
    # see: the request gets this test's connection instead of opening its own.
    chunk_id = _store_one_chunk(conn)
    monkeypatch.setattr(api_app, "api_connection", lambda settings: nullcontext(conn))
    query_settings = _query_settings(settings)
    app = create_app(query_settings, embedder=FakeEmbedder(), generator=_answered(chunk_id))

    with TestClient(app) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    # `orgknow ask` on the same rows, with the same fakes: its pinned output (test_cli.py).
    code = ask(QUESTION, conn, FakeEmbedder(), _answered(chunk_id), query_settings, None)
    assert code == 0
    assert response.json() == json.loads(capsys.readouterr().out)
    assert response.json()["evidence"][0]["chunk_id"] == chunk_id


def test_query_opens_its_own_connection_to_postgres(settings: Settings) -> None:
    # Dense mode, and a model no stored vector has: retrieval runs its SQL on a connection the
    # request opens, and finds nothing, so the model isn't called.
    embedder, generator = FakeEmbedder(), _answered(0)
    embedder.model = "no-vectors-model"
    query_settings = _query_settings(settings, retrieval_mode="dense")

    with TestClient(create_app(query_settings, embedder=embedder, generator=generator)) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {
        "question": QUESTION,
        "answer_status": "insufficient_evidence",
        "answer": "",
        "evidence": [],
        "conflicts": [],
        "insufficient_evidence_reason": "no evidence retrieved",
        "model": "claude-opus-5-5",
        "trace_id": None,
    }
    assert embedder.calls == [("query", [QUESTION])]
    assert generator.calls == []


def test_query_is_503_when_the_database_is_unreachable(
    settings: Settings, closed_port: int
) -> None:
    unreachable = _query_settings(
        settings, database_url=f"postgresql://orgknow:orgknow@127.0.0.1:{closed_port}/orgknow"
    )
    embedder = FakeEmbedder()

    with TestClient(create_app(unreachable, embedder=embedder, generator=_answered(0))) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 503
    request_id = response.headers["X-Request-ID"]
    assert NEW_ID.fullmatch(request_id)
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "database unavailable",
            "request_id": request_id,
        }
    }
    assert embedder.calls == []


# S14-T3: the API's own connections (`db/connect.py`), autocommit with a statement timeout
# (S14-R1 decision 2; ADR-005's amendment 2026-10-13).


def test_an_api_connection_is_autocommit_with_a_10_s_statement_timeout(settings: Settings) -> None:
    with api_connection(settings) as conn:
        assert conn.autocommit
        # DB_STATEMENT_TIMEOUT_MS's default, 10000, as Postgres shows it.
        assert conn.execute("SHOW statement_timeout").fetchone() == ("10s",)


def _sleep_half_a_second(*args: object, **kwargs: object) -> None:
    """Stands in for a data-access step: a statement of 0.5 s on the request's own connection."""
    conn = next(arg for arg in args if isinstance(arg, psycopg.Connection))
    conn.execute("SELECT pg_sleep(0.5)")


@pytest.mark.parametrize(
    ("method", "path", "patch"),
    [
        ("POST", "/query", (pipeline, "retrieve")),
        ("GET", "/decisions/kep:2572", (chain_module, "stored_decision")),
    ],
    ids=["query", "decisions"],
)
def test_a_statement_past_the_statement_timeout_is_503(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    patch: tuple[object, str],
) -> None:
    # A cancelled statement is a database error, not an upstream one (S14-R1 Claude's call d).
    monkeypatch.setattr(*patch, _sleep_half_a_second)
    limited = _query_settings(settings, db_statement_timeout_ms=200)
    app = create_app(limited, embedder=FakeEmbedder(), generator=_answered(0))

    with TestClient(app) as client:
        response = client.request(method, path, json={"question": QUESTION})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "database unavailable",
            "request_id": response.headers["X-Request-ID"],
        }
    }


# A KEP hit at 1.37, so the real `rule_conflicts` reads the KEP's version, its gates' rows and the
# releases on the request's connection: the plain SELECTs that left the S14-R1 sitting's probe
# `idle in transaction`. Retrieval is replaced: the test database has no vectors a new connection
# could see.
KEP_HIT = Hit(
    chunk_id=1,
    content_hash="b" * 64,
    distance=0.1,
    text="Sidecar containers start before the app containers.",
    canonical_id="kep:753",
    source_type="kep",
    heading_path=["Summary"],
    release_windows=[(28, None)],
    current=True,
    claimed_status="implemented",
    claimed_stage="stable",
    snapshot_repo="enhancements",
    snapshot_sha="0123456789abcdef0123456789abcdef01234567",
    source_path="keps/sig-node/753-sidecar-containers/README.md",
    metadata={"title": "Sidecar Containers"},
    authority=Authority(target_release=37, tier=3, effective_stage=None, stage_confidence=None),
)
WAIT_S = 10  # the most any step of the next test waits, so a failure can't hang the suite


class BlockingGenerator:
    """A `Generator` that says it has started, then waits until the test lets it answer."""

    def __init__(self, answer: FakeGenerator) -> None:
        self.answer = answer
        self.started = threading.Event()
        self.released = threading.Event()

    def generate(self, system: str, prompt: str) -> Generation:
        self.started.set()
        assert self.released.wait(WAIT_S), "the test never released the generator"
        return self.answer.generate(system, prompt)


def test_no_transaction_stays_open_while_the_answer_is_generated(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "retrieve", lambda *args, **kwargs: [KEP_HIT])
    generator = BlockingGenerator(_answered(KEP_HIT.chunk_id))
    app = create_app(
        _query_settings(settings, retrieval_mode="dense"),
        embedder=FakeEmbedder(),
        generator=generator,
    )
    responses: list[httpx2.Response] = []

    with TestClient(app) as client:
        request = threading.Thread(
            target=lambda: responses.append(client.post("/query", json={"question": QUESTION}))
        )
        request.start()
        try:
            assert generator.started.wait(WAIT_S), "the request never reached the generator"
            # While the answer is generated: every other client connection to the test database,
            # read from a connection of the test's own.
            with psycopg.connect(settings.database_url, autocommit=True) as observer:
                states = observer.execute(
                    "SELECT state FROM pg_stat_activity WHERE datname = current_database() "
                    "AND backend_type = 'client backend' AND pid <> pg_backend_pid()"
                ).fetchall()
        finally:
            generator.released.set()
            request.join(WAIT_S)

    # The request's one connection, idle between statements: never `idle in transaction`.
    assert states == [("idle",)]
    assert [response.status_code for response in responses] == [200]


# Temporal and authority modes over the API (S12-R1 input): the route, the reranker and a router
# failure, on the test's rows (`_store_one_chunk`: the PSA page, current since 1.30).


@pytest.mark.usefixtures("seeded_releases")
@pytest.mark.parametrize("mode", ["temporal", "authority"])
def test_a_routed_mode_routes_once_and_reranks_the_pool(
    conn: Conn, settings: Settings, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    chunk_id = _store_one_chunk(conn)
    monkeypatch.setattr(api_app, "api_connection", lambda settings: nullcontext(conn))
    router, reranker = FakeRouter({QUESTION: _route("CURRENT")}), FakeReranker({TEXT: 0.5})
    app = create_app(
        _query_settings(settings, retrieval_mode=mode),
        embedder=FakeEmbedder(),
        generator=_answered(chunk_id),
        router=router,
        reranker=reranker,
    )

    with TestClient(app) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 200
    assert router.calls == [QUESTION]
    assert reranker.calls == [(QUESTION, [TEXT])]  # the filtered pool: the one current text
    assert [evidence["chunk_id"] for evidence in response.json()["evidence"]] == [chunk_id]


@pytest.mark.usefixtures("seeded_releases")
def test_a_router_failure_is_502_upstream_failed(
    conn: Conn, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_app, "api_connection", lambda settings: nullcontext(conn))
    embedder, generator, reranker = FakeEmbedder(), _answered(0), FakeReranker({TEXT: 0.5})
    router = RaisingRouter(RouterError("no route from the model (stop reason: refusal)"))
    app = create_app(
        _query_settings(settings, retrieval_mode="authority"),
        embedder=embedder,
        generator=generator,
        router=router,
        reranker=reranker,
    )

    with TestClient(app) as client:
        response = client.post("/query", json={"question": QUESTION})

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "upstream_failed",
            "message": "no route from the model (stop reason: refusal)",
            "request_id": response.headers["X-Request-ID"],
        }
    }
    # It stops before the question is embedded, reranked or answered.
    assert (embedder.calls, reranker.calls, generator.calls) == ([], [], [])
