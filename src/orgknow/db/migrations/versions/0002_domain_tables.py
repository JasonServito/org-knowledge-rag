"""Create the domain tables and their rules.

The spec is docs/domain-model.md; the R-numbers in the comments are its "Rules" table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lets the GiST index behind the R8 exclusion constraint compare document_id with `=`.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute("""
        CREATE TABLE releases (
            minor            smallint NOT NULL,
            version          text NOT NULL,
            release_date     date NOT NULL,
            end_of_life_date date NOT NULL,
            CONSTRAINT releases_pkey PRIMARY KEY (minor),
            -- R15
            CONSTRAINT releases_version_key UNIQUE (version),
            CONSTRAINT releases_release_date_key UNIQUE (release_date),
            CONSTRAINT releases_version_check CHECK (version = '1.' || minor),
            CONSTRAINT releases_end_of_life_date_check CHECK (end_of_life_date > release_date)
        )
    """)

    op.execute("""
        CREATE TABLE documents (
            id           bigint GENERATED ALWAYS AS IDENTITY,
            canonical_id text NOT NULL,
            source_type  text NOT NULL,
            CONSTRAINT documents_pkey PRIMARY KEY (id),
            -- R1
            CONSTRAINT documents_canonical_id_key UNIQUE (canonical_id),
            -- R2
            CONSTRAINT documents_canonical_id_check
                CHECK (canonical_id ~ '^(web|gate|kep|changelog|community|sig-release):'),
            -- R4
            CONSTRAINT documents_source_type_check CHECK (source_type IN (
                'docs_page', 'release_record', 'feature_gate_reference',
                'kep', 'blog_post', 'governance_doc'
            ))
        )
    """)

    op.execute("""
        CREATE TABLE document_aliases (
            alias       text NOT NULL,
            document_id bigint NOT NULL,
            -- R3 (the PK part; "no alias equals a canonical_id" is checked in code)
            CONSTRAINT document_aliases_pkey PRIMARY KEY (alias),
            CONSTRAINT document_aliases_document_id_fkey
                FOREIGN KEY (document_id) REFERENCES documents (id),
            -- R2
            CONSTRAINT document_aliases_alias_check
                CHECK (alias ~ '^(web|gate|kep|changelog|community|sig-release):')
        )
    """)

    op.execute("""
        CREATE TABLE document_versions (
            id                  bigint GENERATED ALWAYS AS IDENTITY,
            document_id         bigint NOT NULL,
            content_hash        text NOT NULL,
            source_path         text NOT NULL,
            snapshot_repo       text NOT NULL,
            snapshot_ref        text NOT NULL,
            snapshot_sha        text NOT NULL,
            valid_from_release  smallint NOT NULL,
            valid_until_release smallint,
            valid_from_date     timestamptz NOT NULL,
            valid_until_date    timestamptz,
            claimed_status      text,
            claimed_stage       text,
            metadata            jsonb NOT NULL DEFAULT '{}',
            CONSTRAINT document_versions_pkey PRIMARY KEY (id),
            CONSTRAINT document_versions_document_id_fkey
                FOREIGN KEY (document_id) REFERENCES documents (id),
            -- R11
            CONSTRAINT document_versions_content_hash_check
                CHECK (content_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT document_versions_snapshot_sha_check
                CHECK (snapshot_sha ~ '^[0-9a-f]{40}$'),
            -- R5: the date window [from, until) is not empty
            CONSTRAINT document_versions_date_window_check
                CHECK (valid_until_date IS NULL OR valid_from_date < valid_until_date),
            -- R6: the release window [from, until] is ordered, and both bounds are real releases
            CONSTRAINT document_versions_release_window_check
                CHECK (valid_until_release IS NULL OR valid_from_release <= valid_until_release),
            CONSTRAINT document_versions_valid_from_release_fkey
                FOREIGN KEY (valid_from_release) REFERENCES releases (minor),
            CONSTRAINT document_versions_valid_until_release_fkey
                FOREIGN KEY (valid_until_release) REFERENCES releases (minor),
            -- R7: a closed date window has a last release
            CONSTRAINT document_versions_closed_window_check
                CHECK (valid_until_date IS NULL OR valid_until_release IS NOT NULL),
            -- R8 and R9: date windows of one document never overlap. tstzrange's default
            -- bounds are [) and a NULL upper bound is open, so two current versions overlap.
            CONSTRAINT document_versions_date_window_excl EXCLUDE USING gist (
                document_id WITH =,
                tstzrange(valid_from_date, valid_until_date) WITH &&
            )
        )
    """)

    op.execute("""
        CREATE TABLE chunks (
            id                  bigint GENERATED ALWAYS AS IDENTITY,
            document_version_id bigint NOT NULL,
            ordinal             integer NOT NULL,
            heading_path        text[] NOT NULL,
            text                text NOT NULL,
            content_hash        text NOT NULL,
            CONSTRAINT chunks_pkey PRIMARY KEY (id),
            -- Re-chunking a version deletes its old chunks.
            CONSTRAINT chunks_document_version_id_fkey
                FOREIGN KEY (document_version_id) REFERENCES document_versions (id)
                ON DELETE CASCADE,
            CONSTRAINT chunks_ordinal_check CHECK (ordinal >= 0),
            -- R12
            CONSTRAINT chunks_document_version_id_ordinal_key
                UNIQUE (document_version_id, ordinal)
        )
    """)

    op.execute("""
        CREATE TABLE embeddings (
            chunk_id  bigint NOT NULL,
            model     text NOT NULL,
            embedding vector(1024) NOT NULL,
            -- R14: one vector per (chunk, model); vector(1024) rejects any other length
            CONSTRAINT embeddings_pkey PRIMARY KEY (chunk_id, model),
            CONSTRAINT embeddings_chunk_id_fkey
                FOREIGN KEY (chunk_id) REFERENCES chunks (id) ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    # Reverse dependency order: each table is dropped before the tables it references.
    op.execute("DROP TABLE embeddings")
    op.execute("DROP TABLE chunks")
    op.execute("DROP TABLE document_versions")
    op.execute("DROP TABLE document_aliases")
    op.execute("DROP TABLE documents")
    op.execute("DROP TABLE releases")
    # vector belongs to 0001, so it stays.
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
