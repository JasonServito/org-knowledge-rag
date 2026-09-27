"""Enable the pgvector extension.

No domain tables yet; those arrive in S03.

Revision ID: 0001
Revises:
Create Date: 2026-09-26 18:34:37.826306
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic already skips applied revisions; IF NOT EXISTS also covers a database where
    # the extension was created outside Alembic.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
