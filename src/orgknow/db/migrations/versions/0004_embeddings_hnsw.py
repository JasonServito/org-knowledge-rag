"""Add an HNSW index on `embeddings.embedding` for cosine-distance search (S04-T5).

S04-R2 decision 6: pgvector's default build settings (m = 16, ef_construction = 64), so the
statement has no WITH clause. An HNSW index is approximate: on 20 real queries it returned the
same top 10 as an exact scan (200 of 200, the S04-R2 sitting). Spec: docs/domain-model.md.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `vector_cosine_ops`: an index serves only the distance operator of its operator class, and
    # retrieval orders by cosine distance, `<=>`. One index holds every model's vectors; the
    # search filters by model.
    op.execute(
        "CREATE INDEX embeddings_embedding_hnsw_idx ON embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX embeddings_embedding_hnsw_idx")
