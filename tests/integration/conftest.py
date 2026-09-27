"""Shared setup for integration tests. They need the real database: run `make up` first."""

from pathlib import Path

import pytest

from orgknow.settings import Settings

_INTEGRATION_DIR = Path(__file__).parent


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
