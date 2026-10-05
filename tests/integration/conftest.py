"""Shared setup for integration tests. They need the real database: run `make up` first."""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.releases import upsert_releases
from orgknow.ingestion.manifest import load_releases
from orgknow.settings import Settings

_INTEGRATION_DIR = Path(__file__).parent
# Anchored to this file, so neither the working directory nor a .env override can change it.
_MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Mark by location so a new test file here can't forget the marker. tryfirst: add the
    # marker before pytest's own `-m` filtering, which runs in this same hook.
    for item in items:
        if item.path.is_relative_to(_INTEGRATION_DIR):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def conn(settings: Settings) -> Iterator[psycopg.Connection[TupleRow]]:
    """A connection whose writes are all rolled back when the test ends, pass or fail.

    For an expected violation, use a nested `with conn.transaction():` (a savepoint) inside
    `pytest.raises`, so the failed statement doesn't abort the rest of the test.
    """
    with psycopg.connect(settings.database_url) as conn, conn.transaction(force_rollback=True):
        yield conn


@pytest.fixture
def seeded_releases(conn: psycopg.Connection[TupleRow]) -> None:
    """Upsert the manifest's 18 releases inside `conn`'s rolled-back transaction.

    Version rows reference releases. CI never runs `make seed`, and the dev DB may already
    hold the releases: an upsert works either way.
    """
    upsert_releases(conn, load_releases(_MANIFEST))
