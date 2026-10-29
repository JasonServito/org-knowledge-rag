"""The API and `orgknow ask` build their Anthropic client and Voyage embedder with the settings'
retry counts and timeout (S14-T3). No network and no database: the real clients are built and
recorded, and nothing calls them. Each test sets values unlike the defaults, typed by hand, so
they can only have come from the settings."""

from contextlib import nullcontext
from pathlib import Path
from typing import Any

import anthropic
import pytest
from fastapi.testclient import TestClient
from tests.conftest import FakeReranker

from orgknow import cli
from orgknow.api import app as api_app
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.settings import Settings

MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"


class Built:
    """Each client the code under test built."""

    def __init__(self) -> None:
        self.anthropic: list[anthropic.Anthropic] = []
        self.voyage: list[VoyageEmbedder] = []


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> Built:
    seen = Built()
    real_anthropic, real_voyage = anthropic.Anthropic, VoyageEmbedder

    def build_anthropic(**kwargs: Any) -> anthropic.Anthropic:
        seen.anthropic.append(real_anthropic(**kwargs))
        return seen.anthropic[-1]

    def build_voyage(*args: Any, **kwargs: Any) -> VoyageEmbedder:
        seen.voyage.append(real_voyage(*args, **kwargs))
        return seen.voyage[-1]

    monkeypatch.setattr(anthropic, "Anthropic", build_anthropic)
    monkeypatch.setattr(api_app, "VoyageEmbedder", build_voyage)
    monkeypatch.setattr(cli, "VoyageEmbedder", build_voyage)
    return seen


def _settings() -> Settings:
    """Fake keys, no Langfuse keys, authority mode (the answer and the router share 1 client), and
    limits unlike the defaults (2 Anthropic retries; Voyage 60 s and 3 retries)."""
    return Settings(
        _env_file=None,
        database_url="postgresql://unused@127.0.0.1:1/x",
        corpus_manifest_path=MANIFEST,
        anthropic_api_key="sk-ant-fake",
        voyage_api_key="pa-fake",
        langfuse_public_key=None,
        langfuse_secret_key=None,
        retrieval_mode="authority",
        anthropic_max_retries=4,
        voyage_timeout_s=7,
        voyage_max_retries=5,
    )


def test_the_api_builds_its_clients_with_the_settings_limits(
    built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_app, "load_reranker", lambda settings: FakeReranker({}))

    with TestClient(api_app.create_app(_settings())):
        pass  # startup builds the clients; no request is sent

    assert [client.max_retries for client in built.anthropic] == [4]
    assert [(embedder.timeout_s, embedder.max_retries) for embedder in built.voyage] == [(7, 5)]


def test_ask_builds_its_clients_with_the_settings_limits(
    built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No reranker model, no database and no ask: `main` builds the clients before all three.
    monkeypatch.setattr(cli, "load_reranker", lambda settings: None)
    monkeypatch.setattr(cli.psycopg, "connect", lambda *args, **kwargs: nullcontext(object()))
    monkeypatch.setattr(cli, "ask", lambda *args: 0)

    assert cli.main(["ask", "Which feature gate enables sidecar containers?"], _settings()) == 0

    assert [client.max_retries for client in built.anthropic] == [4]
    assert [(embedder.timeout_s, embedder.max_retries) for embedder in built.voyage] == [(7, 5)]
