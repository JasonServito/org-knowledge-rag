"""Configuration read from environment variables, falling back to a local `.env` file."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PositiveInt, SecretStr, model_validator
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
    # The manifest `scopes:` entry `make ingest` reads (S05-R1: `full`; `s04` is kept).
    ingest_scope: str = "full"
    # KEP claim synonyms, applied to claimed_status and claimed_stage. ADR-003 D5 allows only
    # this one; any other unknown value is stored as written.
    claim_synonyms: dict[str, str] = {"GA": "stable"}
    # The largest chunk body, in tokens estimated as characters / 4 (S04-R1 decision 5). A longer
    # list or pipe table is cut between items or rows (S05-R3 decision 1); any other longer block
    # is never cut: it becomes a chunk on its own.
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
    # How many chunk texts retrieval returns, in every mode (S04-R2 decision 6). At most 40, the
    # cap S04-R2 set when every search used pgvector's default width (40); the width is now
    # HNSW_EF_SEARCH, which must be at least this (checked below). No similarity threshold: the
    # top k are always returned (temporal mode returns fewer when its filter keeps fewer texts).
    retrieval_top_k: int = Field(default=10, ge=1, le=40)
    # Which retrieval `ask` and the eval use (S07-R1, S08-R1, S09-R1, S09-R2): `dense` (the
    # nearest vectors), `hybrid` (dense and lexical candidates fused with RRF), `rerank` (hybrid's
    # whole fused pool, reordered by a cross-encoder), `temporal` (rerank, with both searches
    # filtered by the question's route: ADR-009, ADR-003 D4) or `authority` (temporal, with the
    # reranked pool reordered by the route's authority weights: ADR-003 D4 as changed in S09-R2).
    # `rerank` since S08-T5's eval passed the improvement rule and the p95 latency ceiling (S08-R1
    # decision 4, docs/evaluation.md); it stays the default until S09-T8's eval.
    retrieval_mode: Literal["dense", "hybrid", "rerank", "temporal", "authority"] = "rerank"
    # Hybrid, rerank, temporal and authority: how many texts each search, dense and lexical,
    # returns before fusion (decision 3).
    retrieval_candidates: int = Field(default=20, ge=1, le=1000)
    # RRF's k: rank r in one list adds 1 / (k + r) to a text's fused score. 60 is the RRF paper's
    # value, not tuned (decision 3).
    rrf_k: int = Field(default=60, ge=1)
    # HNSW search width (pgvector's `hnsw.ef_search`, default 40, 1 to 1000), set for every dense
    # search in every mode. An HNSW index scan returns at most this many rows, and a wider search
    # is closer to an exact scan: at 100, 20 candidates matched an exact scan on all 43 golden
    # questions (decision 3).
    hnsw_ef_search: int = Field(default=100, ge=1, le=1000)
    # The cross-encoder of rerank, temporal and authority modes (ADR-008): a Hugging Face model at
    # a pinned revision (a commit SHA), downloaded once into the Hugging Face cache if missing. It
    # reads at most RERANK_MAX_LENGTH tokens of each (question, text) pair, the model's limit being
    # 512 (a longer text is cut, keeping its start), and scores RERANK_BATCH_SIZE pairs per batch.
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"
    rerank_max_length: int = Field(default=512, ge=1, le=512)
    rerank_batch_size: int = Field(default=8, ge=1, le=256)
    # Temporal and authority modes: how many releases a HISTORY question's window is widened by at
    # each closed end, 0 to 5 (S09-R1 decision 2: ADR-003 D4's ±1). "Until 1.27" searches until
    # 1.28.
    history_window_slack: int = Field(default=1, ge=0, le=5)
    # Authority mode: what the reranker's probability of a trusted source for the question's
    # routed mode is multiplied by (boost, 1 to 4), and that of a weak one (demote, above 0, at
    # most 1); every other hit's by 1 (S09-R2 decision 3, ADR-003 D4). Boost 1 and demote 1 give
    # temporal mode's ranking. Set on golden set v0; v1 is their clean test.
    authority_boost: float = Field(default=1.25, ge=1, le=4)
    authority_demote: float = Field(default=0.8, gt=0, le=1)
    # The answer step (ADR-006 D1). Opus 5.5 always reasons, and effort sets how much; there is
    # no temperature (Opus 5.5 rejects it). Reasoning counts toward the max tokens and is billed
    # as output. At most 21,333: above that, the SDK refuses a non-streaming call (it expects
    # it to take over 10 minutes).
    generation_model: str = "claude-opus-5-5"
    generation_effort: Effort = "medium"
    generation_max_tokens: int = Field(default=16_000, ge=1, le=21_333)
    # The model's prices in US dollars per million tokens (ADR-006 D1), for the eval summary's cost
    # per question (S08-T3). Output tokens include reasoning.
    generation_price_input_usd_per_mtok: float = 4.0
    generation_price_output_usd_per_mtok: float = 20.0
    # The query router (ADR-009 D1): one call per question, before retrieval, its output a mode
    # and the time scope the question names. Effort low, as the S09-R1 sitting measured it. The
    # cap (1 to 16,000) counts reasoning; the sitting's routes used ~40 output tokens each,
    # reasoning included (ADR-009). The prices, in US dollars per million tokens, give
    # `make eval-routes`'s cost.
    router_model: str = "claude-opus-5-5"
    router_effort: Effort = "low"
    router_max_tokens: int = Field(default=4096, ge=1, le=16_000)
    router_price_input_usd_per_mtok: float = 4.0
    router_price_output_usd_per_mtok: float = 20.0
    # No key: the answer step and the router can't run (tests use fakes).
    anthropic_api_key: SecretStr | None = None
    # Langfuse tracing (ADR-006 D3): one trace per `ask`. Either key unset: tracing off, and `ask`
    # still runs. The public key is a SecretStr too, so neither key is ever printed.
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    # Langfuse Cloud's EU region, the SDK's default. The US region: https://us.cloud.langfuse.com.
    langfuse_base_url: str = "https://cloud.langfuse.com"
    # The golden set (ADR-007 D1) that `make eval-check` checks and `make eval` runs. Relative to
    # the repo root.
    eval_golden_path: Path = Path("eval/golden_set/v0.yaml")
    # `make eval` writes one results folder per run here, and rebuilds the ablation table here.
    eval_results_dir: Path = Path("eval/results")
    # The stored question vectors, one file per embedding model (S06-R1 decision 7): a run embeds
    # only questions with no vector here, so retrieval is exactly repeatable.
    eval_vectors_dir: Path = Path("eval/question_vectors")
    # The stored question routes, one file per router model (ADR-009 D3): `make eval-routes`
    # routes only questions with no route here, so retrieval in temporal mode is exactly
    # repeatable.
    eval_routes_dir: Path = Path("eval/question_routes")

    @model_validator(mode="after")
    def _search_width_covers_each_search(self) -> Self:
        """An HNSW scan narrower than a search's k would silently return fewer than k texts."""
        if self.hnsw_ef_search < max(self.retrieval_top_k, self.retrieval_candidates):
            raise ValueError(
                "hnsw_ef_search must be at least retrieval_top_k and retrieval_candidates: an "
                "HNSW index scan returns at most hnsw_ef_search rows"
            )
        return self
