"""Add `chunks.search_vector` and a GIN index on it, for lexical (full-text) search (S07-T1).

S07-R1 decision 2: a stored generated column, so the database keeps it in sync with `text` and
ingestion writes nothing new. The whole text is indexed, header and body. Adding the column
computes it for every existing chunk (48,273 in the S07 sitting: no error). Spec:
docs/domain-model.md.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The 'english' configuration drops stop words and stems the rest ("tokens" → "token"). It is
    # named, not left to the server's default: Postgres refuses a generated column whose value
    # could change with a setting, and the search must parse questions with the same one.
    op.execute(
        "ALTER TABLE chunks ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    # GIN maps each word to the rows holding it: what the full-text match `@@` uses.
    op.execute("CREATE INDEX chunks_search_vector_idx ON chunks USING gin (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX chunks_search_vector_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN search_vector")
