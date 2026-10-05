from pathlib import Path

import pytest
from pydantic import ValidationError

from orgknow.settings import Settings


def test_database_url_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql://u:p@db.example:5432/app"


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_ingestion_settings_default_to_the_s04_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    for name in ("CORPUS_CACHE_DIR", "CORPUS_LOCK_PATH", "INGEST_SCOPE", "CLAIM_SYNONYMS"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    # The run contract's defaults (S04-R1, "Claude's calls"); the synonym is ADR-003 D5's only one.
    assert settings.ingest_scope == "s04"
    assert settings.corpus_lock_path == Path("config/corpus_manifest.lock.yaml")
    assert settings.corpus_cache_dir == Path("~/corpus_cache/org-knowledge-rag")
    assert settings.claim_synonyms == {"GA": "stable"}
