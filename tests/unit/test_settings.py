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


def test_a_settings_error_never_shows_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # S04-T7 edge case: secrets never appear on stderr. A missing DATABASE_URL fails validation,
    # and the error message must not echo the other values it was given.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, anthropic_api_key="sk-ant-FAKESECRET")

    assert "database_url" in str(error.value)
    assert "FAKESECRET" not in str(error.value)


def test_ingestion_settings_default_to_the_full_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example:5432/app")
    for name in ("CORPUS_CACHE_DIR", "CORPUS_LOCK_PATH", "INGEST_SCOPE", "CLAIM_SYNONYMS"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    # The run contracts' defaults (S04-R1; the scope from S05-R1, "Claude's calls"); the synonym
    # is ADR-003 D5's only one.
    assert settings.ingest_scope == "full"
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


def test_retrieval_top_k_defaults_to_10(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RETRIEVAL_TOP_K", raising=False)

    # S04-R2 decision 6.
    assert Settings(_env_file=None, database_url="x").retrieval_top_k == 10


@pytest.mark.parametrize("k", [0, 41])
def test_retrieval_top_k_outside_1_to_40_is_refused(k: int) -> None:
    # 40 is pgvector's default hnsw.ef_search: an HNSW index scan returns at most that many rows.
    with pytest.raises(ValidationError, match="retrieval_top_k"):
        Settings(_env_file=None, database_url="x", retrieval_top_k=k)


def test_retrieval_top_k_of_40_is_accepted() -> None:
    assert Settings(_env_file=None, database_url="x", retrieval_top_k=40).retrieval_top_k == 40


def test_generation_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GENERATION_MODEL",
        "GENERATION_EFFORT",
        "GENERATION_MAX_TOKENS",
        "GENERATION_PRICE_INPUT_USD_PER_MTOK",
        "GENERATION_PRICE_OUTPUT_USD_PER_MTOK",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # ADR-006 D1 and the S04-R2 contract, "Claude's calls", Settings.
    assert settings.generation_model == "claude-opus-5-5"
    assert settings.generation_effort == "medium"
    assert settings.generation_max_tokens == 16_000
    assert settings.anthropic_api_key is None
    # ADR-006 D1's prices, $4 / $20 per million tokens (S08-R1, "Claude's calls", Settings).
    assert settings.generation_price_input_usd_per_mtok == 4.0
    assert settings.generation_price_output_usd_per_mtok == 20.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_effort", "turbo"),
        ("generation_max_tokens", 0),
        ("generation_max_tokens", 21_334),
    ],
)
def test_bad_generation_settings_are_refused(field: str, value: object) -> None:
    # 21,333 is the SDK's limit for a non-streaming call (anthropic 1.11, checked 2026-10-06).
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: value})


def test_hybrid_retrieval_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL_MODE", "RETRIEVAL_CANDIDATES", "RRF_K", "HNSW_EF_SEARCH"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # S07-R1 decision 3; the mode is authority since S09-T8's eval (S09-R2 decision 10,
    # docs/evaluation.md).
    assert settings.retrieval_mode == "authority"
    assert settings.retrieval_candidates == 20
    assert settings.rrf_k == 60
    assert settings.hnsw_ef_search == 100


def test_a_search_width_below_the_candidates_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # An HNSW index scan returns at most hnsw.ef_search rows: 10 can't give 20 candidates.
    monkeypatch.setenv("HNSW_EF_SEARCH", "10")
    monkeypatch.delenv("RETRIEVAL_CANDIDATES", raising=False)
    monkeypatch.delenv("RETRIEVAL_TOP_K", raising=False)

    with pytest.raises(ValidationError, match="hnsw_ef_search"):
        Settings(_env_file=None, database_url="x")


def test_a_search_width_below_the_top_k_is_refused() -> None:
    with pytest.raises(ValidationError, match="hnsw_ef_search"):
        Settings(
            _env_file=None,
            database_url="x",
            retrieval_top_k=30,
            retrieval_candidates=20,
            hnsw_ef_search=25,
        )


def test_a_search_width_equal_to_the_larger_search_is_accepted() -> None:
    settings = Settings(
        _env_file=None, database_url="x", retrieval_candidates=20, hnsw_ef_search=20
    )

    assert settings.hnsw_ef_search == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retrieval_mode", "sparse"),
        ("retrieval_candidates", 0),
        ("retrieval_candidates", 1001),
        ("rrf_k", 0),
        ("hnsw_ef_search", 1001),
    ],
)
def test_bad_hybrid_retrieval_settings_are_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: value})


def test_rerank_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RERANK_MODEL", "RERANK_REVISION", "RERANK_MAX_LENGTH", "RERANK_BATCH_SIZE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # ADR-008 D1 and D3; the S08-R1 contract, "Claude's calls", Settings.
    assert settings.rerank_model == "BAAI/bge-reranker-base"
    assert settings.rerank_revision == "2cfc18c9415c912f9d8155881c133215df768a70"
    assert settings.rerank_max_length == 512
    assert settings.rerank_batch_size == 8


def test_rerank_mode_is_accepted() -> None:
    assert Settings(_env_file=None, database_url="x", retrieval_mode="rerank").retrieval_mode == (
        "rerank"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # 512 tokens is the model's longest input (ADR-008 D3).
        ("rerank_max_length", 0),
        ("rerank_max_length", 513),
        ("rerank_batch_size", 0),
        ("rerank_batch_size", 257),
    ],
)
def test_bad_rerank_settings_are_refused(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: value})


def test_router_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ROUTER_MODEL",
        "ROUTER_EFFORT",
        "ROUTER_MAX_TOKENS",
        "ROUTER_PRICE_INPUT_USD_PER_MTOK",
        "ROUTER_PRICE_OUTPUT_USD_PER_MTOK",
        "EVAL_ROUTES_DIR",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # ADR-009 D1 and the S09-R1 contract, "Claude's calls", Settings.
    assert settings.router_model == "claude-opus-5-5"
    assert settings.router_effort == "low"
    assert settings.router_max_tokens == 4096
    assert settings.router_price_input_usd_per_mtok == 4.0
    assert settings.router_price_output_usd_per_mtok == 20.0
    assert settings.eval_routes_dir == Path("eval/question_routes")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("router_effort", "turbo"),
        ("router_max_tokens", 0),
        ("router_max_tokens", 16_001),
    ],
)
def test_bad_router_settings_are_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: value})


def test_temporal_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HISTORY_WINDOW_SLACK", raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # S09-R1 decision 2: HISTORY windows widened by 1 release.
    assert settings.history_window_slack == 1


def test_temporal_mode_and_a_slack_of_0_to_5_are_accepted() -> None:
    for slack in (0, 5):
        settings = Settings(
            _env_file=None, database_url="x", retrieval_mode="temporal", history_window_slack=slack
        )
        assert (settings.retrieval_mode, settings.history_window_slack) == ("temporal", slack)


@pytest.mark.parametrize("slack", ["-1", "6"])
def test_a_slack_outside_0_to_5_is_refused(monkeypatch: pytest.MonkeyPatch, slack: str) -> None:
    monkeypatch.setenv("HISTORY_WINDOW_SLACK", slack)

    with pytest.raises(ValidationError, match="history_window_slack"):
        Settings(_env_file=None, database_url="x")


def test_authority_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AUTHORITY_BOOST", "AUTHORITY_DEMOTE", "RETRIEVAL_MODE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # S09-R2 decision 3: boost 1.25, demote 0.8. The default mode is authority since S09-T8.
    assert (settings.authority_boost, settings.authority_demote) == (1.25, 0.8)
    assert settings.retrieval_mode == "authority"


def test_authority_mode_and_the_weights_range_ends_are_accepted() -> None:
    for boost, demote in ((1.0, 1.0), (4.0, 0.01)):
        settings = Settings(
            _env_file=None,
            database_url="x",
            retrieval_mode="authority",
            authority_boost=boost,
            authority_demote=demote,
        )
        assert (settings.retrieval_mode, settings.authority_boost, settings.authority_demote) == (
            "authority",
            boost,
            demote,
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        # A boost below 1 would demote, and a demote above 1 would boost.
        ("AUTHORITY_BOOST", "0.9"),
        ("AUTHORITY_BOOST", "4.5"),
        ("AUTHORITY_DEMOTE", "1.1"),
        ("AUTHORITY_DEMOTE", "0"),
    ],
)
def test_weights_outside_their_range_are_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None, database_url="x")


def test_the_history_date_tolerance_defaults_to_7_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HISTORY_DATE_TOLERANCE_DAYS", raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # S10-R1 decision 11.
    assert settings.history_date_tolerance_days == 7


def test_a_history_date_tolerance_of_0_is_accepted_and_below_0_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None, database_url="x", history_date_tolerance_days=0)
    monkeypatch.setenv("HISTORY_DATE_TOLERANCE_DAYS", "-1")

    with pytest.raises(ValidationError, match="history_date_tolerance_days"):
        Settings(_env_file=None, database_url="x")


def test_timeout_and_retry_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        "GENERATION_TIMEOUT_S",
        "ROUTER_TIMEOUT_S",
        "ANTHROPIC_MAX_RETRIES",
        "VOYAGE_TIMEOUT_S",
        "VOYAGE_MAX_RETRIES",
        "GITHUB_TIMEOUT_S",
        "DB_STATEMENT_TIMEOUT_MS",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None, database_url="x")

    # S14-R1 Claude's call c: generation 90 s, router 30 s, Anthropic retries 2, Voyage 60 s and
    # 3 retries, GitHub 30 s, a database statement 10 s.
    assert (settings.generation_timeout_s, settings.router_timeout_s) == (90, 30)
    assert settings.anthropic_max_retries == 2
    assert (settings.voyage_timeout_s, settings.voyage_max_retries) == (60, 3)
    assert settings.github_timeout_s == 30
    assert settings.db_statement_timeout_ms == 10_000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_timeout_s", 0),
        ("router_timeout_s", 0),
        ("voyage_timeout_s", 0),
        ("github_timeout_s", 0),
        ("db_statement_timeout_ms", 0),  # 0 would turn Postgres's statement timeout off
        ("anthropic_max_retries", -1),
        ("voyage_max_retries", -1),
    ],
)
def test_a_timeout_below_1_or_a_negative_retry_count_is_refused(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url="x", **{field: value})


def test_no_retries_are_accepted() -> None:
    settings = Settings(
        _env_file=None, database_url="x", anthropic_max_retries=0, voyage_max_retries=0
    )

    assert (settings.anthropic_max_retries, settings.voyage_max_retries) == (0, 0)
