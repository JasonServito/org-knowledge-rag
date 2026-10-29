"""Add `ingestion_jobs`: one row per rebuild job, the queue `make worker` reads (S14-T4).

ADR-013 D1, D4, D6: the table is the queue; a job's 4 steps (ingest, lifecycle, embed, chains)
are a JSON list in its row, each with its status, times, counts and error; at most one job is
queued or running, which the database enforces, so 2 POSTs at the same instant make 1 job.
Pinned in the S14-R2 run plan ("Pinned: T4").

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ingestion_jobs (
            id          bigint GENERATED ALWAYS AS IDENTITY,
            status      text NOT NULL DEFAULT 'queued',
            created_at  timestamptz NOT NULL DEFAULT now(),
            started_at  timestamptz,
            finished_at timestamptz,
            -- Runs and resumes started (ADR-013 D5).
            attempts    integer NOT NULL DEFAULT 0,
            error       text,  -- a failed job's one-line reason
            request_id  text,  -- the X-Request-ID of the POST that created it
            steps       jsonb NOT NULL,
            CONSTRAINT ingestion_jobs_pkey PRIMARY KEY (id),
            CONSTRAINT ingestion_jobs_status_check
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            CONSTRAINT ingestion_jobs_attempts_check CHECK (attempts >= 0)
        )
        """
    )
    # The one-active-job rule (ADR-013 D4): every queued or running row has the same key, `true`,
    # so a second one is a unique violation; a finished job is outside the partial index.
    op.execute(
        """
        CREATE UNIQUE INDEX ingestion_jobs_one_active ON ingestion_jobs ((true))
            WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingestion_jobs")  # its indexes go with it
