"""Add `decisions` and `decision_evidence`: each seed KEP's decision chain (S13-T3).

ADR-012 D2: one decision per seed KEP and one evidence row per step, citing a stored chunk with
its date and how it was found, or missing with its reason. Derived data, like embeddings: `make
chains` rebuilds every chain in the manifest. Both tables cascade from what they cite, so `make
reset-corpus` (TRUNCATE ... CASCADE) empties them with the texts. Pinned in the S13-R1 run
contract ("Pinned: T3").

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-13 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE decisions (
            id          bigint GENERATED ALWAYS AS IDENTITY,
            document_id bigint NOT NULL,  -- the seed KEP
            title       text NOT NULL,
            built_at    timestamptz NOT NULL,
            CONSTRAINT decisions_pkey PRIMARY KEY (id),
            CONSTRAINT decisions_document_id_key UNIQUE (document_id),
            CONSTRAINT decisions_document_id_fkey
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE decision_evidence (
            id             bigint GENERATED ALWAYS AS IDENTITY,
            decision_id    bigint NOT NULL,
            step           text NOT NULL,
            chunk_id       bigint,
            occurred_at    timestamptz,
            found_by       text,
            -- The chunk holding the link that connects this step.
            via_chunk_id   bigint,
            missing_reason text,
            CONSTRAINT decision_evidence_pkey PRIMARY KEY (id),
            CONSTRAINT decision_evidence_decision_id_fkey
                FOREIGN KEY (decision_id) REFERENCES decisions (id) ON DELETE CASCADE,
            CONSTRAINT decision_evidence_chunk_id_fkey
                FOREIGN KEY (chunk_id) REFERENCES chunks (id) ON DELETE CASCADE,
            CONSTRAINT decision_evidence_via_chunk_id_fkey
                FOREIGN KEY (via_chunk_id) REFERENCES chunks (id) ON DELETE CASCADE,
            CONSTRAINT decision_evidence_decision_id_step_key UNIQUE (decision_id, step),
            CONSTRAINT decision_evidence_step_check CHECK (step IN (
                'problem', 'discussion', 'proposal', 'decision', 'implementation', 'current_docs'
            )),
            CONSTRAINT decision_evidence_found_by_check CHECK (found_by IN (
                'seed', 'template_field', 'merge_event', 'linking_text', 'similarity'
            )),
            CONSTRAINT decision_evidence_missing_reason_check CHECK (missing_reason IN (
                'no_tracking_issue', 'no_link', 'not_public', 'not_ingested', 'not_merged',
                'no_linking_text'
            )),
            -- A step cites a chunk or says why it can't: exactly one of the two.
            CONSTRAINT decision_evidence_cited_or_missing_check
                CHECK ((chunk_id IS NULL) <> (missing_reason IS NULL)),
            -- A cited chunk always says how it was found; a missing step never does.
            CONSTRAINT decision_evidence_found_by_set_check
                CHECK ((found_by IS NULL) = (chunk_id IS NULL))
        )
        """
    )


def downgrade() -> None:
    # decision_evidence references decisions, so it goes first.
    op.execute("DROP TABLE decision_evidence")
    op.execute("DROP TABLE decisions")
