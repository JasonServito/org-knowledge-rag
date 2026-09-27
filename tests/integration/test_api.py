import socket

import pytest
from fastapi.testclient import TestClient

from orgknow.api.app import create_app
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
