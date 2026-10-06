"""Configuration read from environment variables, falling back to a local `.env` file."""

from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# The API's effort levels: how much the model reasons before it answers (ADR-006 D1).
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error (e.g. a missing DATABASE_URL) would otherwise echo
    # every value it was given, API keys included, in its message.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

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
    # `make embed` (S04-R1 decision 7). No key: `make embed` stops with a message; tests use a
    # fake. SecretStr shows "**********" when settings are printed or logged.
    voyage_api_key: SecretStr | None = None
    voyage_api_url: str = "https://api.voyageai.com/v1/embeddings"
    # Vectors are stored under this name, so a new model embeds everything again.
    embedding_model: str = "voyage-4-large"
    # One request holds at most this many texts and estimated tokens (characters / 4). A single
    # text over the token budget is sent alone. Both must be at least 1.
    embed_batch_max_texts: PositiveInt = 128
    embed_batch_max_tokens: PositiveInt = 60_000
    # `make embed` refuses to start when the texts it would send exceed this many estimated
    # tokens: a guard against embedding far more than planned (CLAUDE.md, spending).
    embed_max_tokens_per_run: int = 2_000_000
    # How many chunk texts dense retrieval returns (S04-R2 decision 6). At most 40, pgvector's
    # default `hnsw.ef_search`: an HNSW index scan returns at most that many rows. No similarity
    # threshold: the top k are always returned.
    retrieval_top_k: int = Field(default=10, ge=1, le=40)
    # The answer step (ADR-006 D1). Opus 5.5 always reasons, and effort sets how much; there is
    # no temperature (Opus 5.5 rejects it). Reasoning counts toward the max tokens and is billed
    # as output. At most 21,333: above that, the SDK refuses a non-streaming call (it expects
    # it to take over 10 minutes).
    generation_model: str = "claude-opus-5-5"
    generation_effort: Effort = "medium"
    generation_max_tokens: int = Field(default=16_000, ge=1, le=21_333)
    # No key: the answer step can't run (tests use a fake generator).
    anthropic_api_key: SecretStr | None = None
    # Langfuse tracing (ADR-006 D3): one trace per `ask`. Either key unset: tracing off, and `ask`
    # still runs. The public key is a SecretStr too, so neither key is ever printed.
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    # Langfuse Cloud's EU region, the SDK's default. The US region: https://us.cloud.langfuse.com.
    langfuse_base_url: str = "https://cloud.langfuse.com"
