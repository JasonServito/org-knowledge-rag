import json
import socket
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from tests.conftest import FakeEmbedder
from tests.integration.test_cli import (
    FAKE_ANTHROPIC_KEY,
    FAKE_VOYAGE_KEY,
    MANIFEST,
    QUESTION,
    Conn,
    _answered,
    _store_one_chunk,
)

from orgknow.api import app as api_app
from orgknow.api.app import create_app
from orgknow.cli import ask
from orgknow.settings import Settings


@pytest.fixture
def closed_port() -> int:
    # Ask the OS for a free port, then close the socket: nothing is listening there now.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def test_health_and_ready_are_200_when_db_is_up(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_ready_is_503_but_health_stays_200_when_db_is_unreachable(closed_port: int) -> None:
    unreachable = Settings(
        _env_file=None,
        database_url=f"postgresql://orgknow:orgknow@127.0.0.1:{closed_port}/orgknow",
    )
    client = TestClient(create_app(unreachable))

    ready = client.get("/ready")
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}
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
    monkeypatch.setattr(api_app.psycopg, "connect", lambda *args, **kwargs: nullcontext(conn))
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
    assert response.json() == {"detail": "database unreachable"}
    assert embedder.calls == []
