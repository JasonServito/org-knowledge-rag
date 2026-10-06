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


def test_chunk_max_tokens_defaults_to_512(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    monkeypatch.delenv("CHUNK_MAX_TOKENS", raising=False)

    # S04-R1 decision 5 and "Claude's calls", Settings.
    assert Settings(_env_file=None).chunk_max_tokens == 512


def test_embedding_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    for name in (
        "VOYAGE_API_KEY",
        "VOYAGE_API_URL",
        "EMBEDDING_MODEL",
        "EMBED_BATCH_MAX_TEXTS",
        "EMBED_BATCH_MAX_TOKENS",
        "EMBED_MAX_TOKENS_PER_RUN",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    # S04-R1 decision 7 and "Claude's calls", Settings; the URL is Voyage's API reference.
    assert settings.voyage_api_key is None
    assert settings.voyage_api_url == "https://api.voyageai.com/v1/embeddings"
    assert settings.embedding_model == "voyage-4-large"
    assert settings.embed_batch_max_texts == 128
    assert settings.embed_batch_max_tokens == 60_000
    assert settings.embed_max_tokens_per_run == 2_000_000


def test_the_voyage_key_is_hidden_when_settings_are_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-secret-value")

    settings = Settings(_env_file=None)

    assert settings.voyage_api_key is not None
    assert settings.voyage_api_key.get_secret_value() == "pa-secret-value"
    assert "pa-secret-value" not in repr(settings)
    assert "pa-secret-value" not in str(settings)


@pytest.mark.parametrize("field", ["embed_batch_max_texts", "embed_batch_max_tokens"])
def test_a_batch_limit_of_zero_is_refused(field: str) -> None:
    # `batch_texts` would read 0 texts as "no limit" and 0 tokens as one request per text.
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: 0})
