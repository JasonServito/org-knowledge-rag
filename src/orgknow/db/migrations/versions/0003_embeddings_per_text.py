"""Key `embeddings` by chunk text: one vector per (content_hash, model), not one per chunk.

S04-R1 decision 4: the chunk header holds no per-version field, so a section unchanged between
versions has byte-identical text, and one vector serves every chunk holding it. The table is the
embedding cache. Spec: docs/domain-model.md (`embeddings`, R14).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Vectors are a cache, so 0002's per-chunk rows are dropped, not converted: `make embed`
    # re-creates whatever is missing.
    op.execute("DROP TABLE embeddings")
    op.execute("""
        CREATE TABLE embeddings (
            content_hash text NOT NULL,
            model        text NOT NULL,
            embedding    vector(1024) NOT NULL,
            -- R14: one vector per (text, model); vector(1024) rejects any other length. No
            -- foreign key: many chunks share one text. `make embed` deletes orphans.
            CONSTRAINT embeddings_pkey PRIMARY KEY (content_hash, model),
            CONSTRAINT embeddings_content_hash_check CHECK (content_hash ~ '^[0-9a-f]{64}$')
        )
    """)
    # Vectors are found by chunk hash: the "no vector yet" read and the orphan delete.
    op.execute("CREATE INDEX chunks_content_hash_idx ON chunks (content_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX chunks_content_hash_idx")
    op.execute("DROP TABLE embeddings")
    # 0002's table, empty: vectors are a cache.
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
