import psycopg

from orgknow.settings import Settings


def test_vector_extension_is_installed(settings: Settings) -> None:
    # Checks the result of `make migrate`, which runs before `make test-int` locally and in CI.
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()

    assert row is not None, "pgvector extension missing: run `make migrate`"
