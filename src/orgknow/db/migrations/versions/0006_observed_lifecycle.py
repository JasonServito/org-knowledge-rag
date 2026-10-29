"""Add `observed_lifecycle`: each feature gate's stage at each minor release (S09-T5).

ADR-003 D2 (as changed in the S09-R2 design review): the stage read from that release's own
feature-gate reference, one row per gate x release (S09-R2 decision 6). `make lifecycle` rebuilds
every row from the stored versions; `make ingest` runs the same step. The table is pinned in the
S09-R2 run plan.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `gate` is the name the release's own reference gives (no aliasing across renames), so it
    # isn't a key into `documents`. A NULL stage is a low row whose stage couldn't be read.
    op.execute(
        """
        CREATE TABLE observed_lifecycle (
            gate              text NOT NULL,
            release           smallint NOT NULL,
            stage             text,
            status_confidence text NOT NULL,
            CONSTRAINT observed_lifecycle_pkey PRIMARY KEY (gate, release),
            CONSTRAINT observed_lifecycle_release_fkey
                FOREIGN KEY (release) REFERENCES releases (minor),
            CONSTRAINT observed_lifecycle_status_confidence_check
                CHECK (status_confidence IN ('high', 'low')),
            -- high: one stage from the vocabulary; low: no stage, or a value kept as written.
            -- IS NOT NULL: `NULL IN (...)` is NULL, which a CHECK lets through.
            CONSTRAINT observed_lifecycle_high_check CHECK (
                status_confidence = 'low'
                OR (stage IS NOT NULL AND stage IN ('alpha', 'beta', 'stable', 'deprecated')))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE observed_lifecycle")
