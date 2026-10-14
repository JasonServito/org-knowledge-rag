import importlib.util
from pathlib import Path

import psycopg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from psycopg.errors import CheckViolation
from psycopg.rows import TupleRow
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from orgknow.db.documents import add_alias, create_document
from orgknow.db.url import with_psycopg_driver
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

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


def test_embeddings_are_keyed_by_text_and_model(settings: Settings) -> None:
    # Migration 0003 (S04-R1 decision 4): one vector per (content_hash, model), and an index
    # on chunks.content_hash for looking vectors up by chunk text.
    with psycopg.connect(settings.database_url) as conn:
        primary_key = conn.execute(
            """
            SELECT k.column_name
            FROM information_schema.table_constraints t
            JOIN information_schema.key_column_usage k
              ON k.constraint_schema = t.constraint_schema AND k.constraint_name = t.constraint_name
            WHERE t.table_name = 'embeddings' AND t.constraint_type = 'PRIMARY KEY'
            ORDER BY k.ordinal_position
            """
        ).fetchall()
        index = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'chunks_content_hash_idx'"
        ).fetchone()

    assert primary_key == [("content_hash",), ("model",)]
    assert index == (
        "CREATE INDEX chunks_content_hash_idx ON public.chunks USING btree (content_hash)",
    )


def test_embeddings_have_an_hnsw_cosine_index(settings: Settings) -> None:
    # Migration 0004 (S04-R2 decision 6): an HNSW index for the cosine operator `<=>`, with
    # pgvector's default m and ef_construction, so the definition has no WITH clause.
    with psycopg.connect(settings.database_url) as conn:
        index = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'embeddings_embedding_hnsw_idx'"
        ).fetchone()

    assert index == (
        "CREATE INDEX embeddings_embedding_hnsw_idx ON public.embeddings "
        "USING hnsw (embedding vector_cosine_ops)",
    )


def test_chunks_have_a_generated_search_vector_with_a_gin_index(settings: Settings) -> None:
    # Migration 0005 (S07-R1 decision 2): the database computes `search_vector` from `text`, so
    # ingestion writes nothing new; a GIN index serves the full-text match `@@`. Postgres prints
    # the expression with its `regconfig` cast.
    with psycopg.connect(settings.database_url) as conn:
        column = conn.execute(
            """
            SELECT data_type, is_generated, generation_expression
            FROM information_schema.columns
            WHERE table_name = 'chunks' AND column_name = 'search_vector'
            """
        ).fetchone()
        index = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'chunks_search_vector_idx'"
        ).fetchone()

    assert column == ("tsvector", "ALWAYS", "to_tsvector('english'::regconfig, text)")
    assert index == (
        "CREATE INDEX chunks_search_vector_idx ON public.chunks USING gin (search_vector)",
    )


# --- 0007: the `discussion` source type and the `gh:` prefix (S13-T1) ----------------------------

MIGRATIONS = Path(__file__).parents[2] / "src" / "orgknow" / "db" / "migrations" / "versions"


def test_0007_allows_a_discussion_with_a_gh_id_and_alias(conn: Conn) -> None:
    document_id = create_document(conn, "gh:sig-release/discussions/1290", "discussion")
    add_alias(conn, document_id, "gh:sig-release/discussions/1")

    # Every other prefix and type is still refused (R2, R4).
    with pytest.raises(CheckViolation, match="documents_source_type_check"), conn.transaction():
        create_document(conn, "gh:enhancements/issues/1", "mailing_list")
    with pytest.raises(CheckViolation, match="documents_canonical_id_check"), conn.transaction():
        create_document(conn, "slack:release/1", "discussion")
    with pytest.raises(CheckViolation, match="document_aliases_alias_check"), conn.transaction():
        add_alias(conn, document_id, "slack:release/1")


def _refused(connection: Connection, sql: str, constraint: str) -> bool:
    """Whether `sql` fails on `constraint`, in a savepoint that is then rolled back."""
    try:
        with connection.begin_nested():
            connection.execute(text(sql))
    except IntegrityError as error:
        return constraint in str(error)
    return False


def test_0007_downgrade_restores_both_checks_and_upgrade_adds_them_back(
    settings: Settings,
) -> None:
    # Run 0007's own downgrade() and upgrade() inside one transaction that is rolled back, so the
    # test database stays at head whatever happens.
    spec = importlib.util.spec_from_file_location(
        "migration_0007", next(MIGRATIONS.glob("0007_*.py"))
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    discussion = "INSERT INTO documents (canonical_id, source_type) VALUES ('kep:1', 'discussion')"
    gh_id = "INSERT INTO documents (canonical_id, source_type) VALUES ('gh:x/issues/1', 'kep')"
    gh_alias = (
        "INSERT INTO document_aliases (alias, document_id) "
        "VALUES ('gh:x/issues/2', (SELECT min(id) FROM documents))"
    )
    engine = create_engine(with_psycopg_driver(settings.database_url), poolclass=NullPool)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text("INSERT INTO documents (canonical_id, source_type) VALUES ('kep:2', 'kep')")
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                after_downgrade = [
                    _refused(connection, discussion, "documents_source_type_check"),
                    _refused(connection, gh_id, "documents_canonical_id_check"),
                    _refused(connection, gh_alias, "document_aliases_alias_check"),
                ]
                migration.upgrade()
                after_upgrade = [
                    _refused(connection, discussion, "documents_source_type_check"),
                    _refused(connection, gh_id, "documents_canonical_id_check"),
                    _refused(connection, gh_alias, "document_aliases_alias_check"),
                ]
        finally:
            transaction.rollback()

    assert after_downgrade == [True, True, True]
    assert after_upgrade == [False, False, False]


# --- 0008: the decision tables (S13-T3) ----------------------------------------------------------


def _tables(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'decision%'"
        )
    )
    return {name for (name,) in rows}


def test_0008_downgrade_drops_both_tables_and_upgrade_adds_them_back(settings: Settings) -> None:
    # 0008's own downgrade() and upgrade(), inside one transaction that is rolled back, as for 0007.
    spec = importlib.util.spec_from_file_location(
        "migration_0008", next(MIGRATIONS.glob("0008_*.py"))
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(with_psycopg_driver(settings.database_url), poolclass=NullPool)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            at_head = _tables(connection)
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                after_downgrade = _tables(connection)
                migration.upgrade()
                after_upgrade = _tables(connection)
        finally:
            transaction.rollback()

    assert at_head == {"decisions", "decision_evidence"}
    assert after_downgrade == set()
    assert after_upgrade == {"decisions", "decision_evidence"}


# --- 0009: the ingestion jobs table (S14-T4) -----------------------------------------------------


def _jobs_table(connection: Connection) -> tuple[set[str], set[str]]:
    """`ingestion_jobs`' columns and indexes, empty when the table doesn't exist."""
    columns = connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'ingestion_jobs'"
        )
    )
    indexes = connection.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'ingestion_jobs'")
    )
    return {name for (name,) in columns}, {name for (name,) in indexes}


def test_0009_downgrade_drops_the_jobs_table_and_upgrade_adds_it_back(settings: Settings) -> None:
    # 0009's own downgrade() and upgrade(), inside one transaction that is rolled back, as for 0007.
    spec = importlib.util.spec_from_file_location(
        "migration_0009", next(MIGRATIONS.glob("0009_*.py"))
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(with_psycopg_driver(settings.database_url), poolclass=NullPool)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            at_head = _jobs_table(connection)
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                after_downgrade = _jobs_table(connection)
                migration.upgrade()
                after_upgrade = _jobs_table(connection)
        finally:
            transaction.rollback()

    # The S14-R2 contract's columns and indexes ("Pinned: T4"), typed by hand.
    table = (
        {
            "id",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "attempts",
            "error",
            "request_id",
            "steps",
        },
        {"ingestion_jobs_pkey", "ingestion_jobs_one_active"},
    )
    assert at_head == table
    assert after_downgrade == (set(), set())
    assert after_upgrade == table
