import psycopg

from orgknow.settings import Settings

# The six tables of docs/domain-model.md ("Tables"), typed by hand.
DOMAIN_TABLES = {
    "releases",
    "documents",
    "document_aliases",
    "document_versions",
    "chunks",
    "embeddings",
}


def test_vector_extension_is_installed(settings: Settings) -> None:
    # Checks the result of `make migrate`, which runs before `make test-int` locally and in CI.
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()

    assert row is not None, "pgvector extension missing: run `make migrate`"


def test_btree_gist_extension_is_installed(settings: Settings) -> None:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'").fetchone()

    assert row is not None, "btree_gist extension missing: run `make migrate`"


def test_domain_tables_exist(settings: Settings) -> None:
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()

    missing = DOMAIN_TABLES - {name for (name,) in rows}
    assert not missing, f"domain tables missing: {sorted(missing)}; run `make migrate`"
