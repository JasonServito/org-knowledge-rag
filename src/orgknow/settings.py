"""Configuration read from environment variables, falling back to a local `.env` file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Plain libpq form, e.g. postgresql://user:password@host:port/dbname. No default: a
    # missing value should fail at startup, not silently point at some database.
    database_url: str
    # How long /ready waits for a new DB connection. libpq treats values below 2 as 2.
    db_connect_timeout_s: int = 2
    # A relative path is resolved from the working directory; the make targets run from the
    # repo root.
    corpus_manifest_path: Path = Path("config/corpus_manifest.yaml")
    # The SHAs ingestion reads, written by spikes/fetch.py.
    corpus_lock_path: Path = Path("config/corpus_manifest.lock.yaml")
    # The partial clones of the corpus repos (spikes/fetch.py), one folder per manifest repo.
    # Outside this repo. Ingestion expands `~`.
    corpus_cache_dir: Path = Path("~/corpus_cache/org-knowledge-rag")
    # The manifest `scopes:` entry `make ingest` reads.
    ingest_scope: str = "s04"
    # KEP claim synonyms, applied to claimed_status and claimed_stage. ADR-003 D5 allows only
    # this one; any other unknown value is stored as written.
    claim_synonyms: dict[str, str] = {"GA": "stable"}
    # The largest chunk body, in tokens estimated as characters / 4 (S04-R1 decision 5). A code
    # block or paragraph longer than this is still never cut: it becomes a chunk on its own.
    chunk_max_tokens: int = 512
