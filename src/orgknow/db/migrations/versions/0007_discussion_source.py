"""Add the `discussion` source type and the `gh:` id prefix (S13-T1).

GitHub issues, PRs and discussions a decision chain links to are `discussion` documents (ADR-003
D1, tier 7), with ids `gh:<repo key>/<issues|pull|discussions>/<number>` (ADR-002 D4 as changed
in the S13-R1 design review; ADR-012 D3). This replaces 0002's R2 checks (the id and alias prefixes)
and its R4 check (the source types). Downgrade restores 0002's checks; it fails while a
`discussion` document or a `gh:` id or alias is stored.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-13 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
            DROP CONSTRAINT documents_canonical_id_check,
            ADD CONSTRAINT documents_canonical_id_check
                CHECK (canonical_id ~ '^(web|gate|kep|changelog|community|sig-release|gh):'),
            DROP CONSTRAINT documents_source_type_check,
            ADD CONSTRAINT documents_source_type_check CHECK (source_type IN (
                'docs_page', 'release_record', 'feature_gate_reference',
                'kep', 'blog_post', 'governance_doc', 'discussion'
            ))
        """
    )
    op.execute(
        """
        ALTER TABLE document_aliases
            DROP CONSTRAINT document_aliases_alias_check,
            ADD CONSTRAINT document_aliases_alias_check
                CHECK (alias ~ '^(web|gate|kep|changelog|community|sig-release|gh):')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
            DROP CONSTRAINT documents_canonical_id_check,
            ADD CONSTRAINT documents_canonical_id_check
                CHECK (canonical_id ~ '^(web|gate|kep|changelog|community|sig-release):'),
            DROP CONSTRAINT documents_source_type_check,
            ADD CONSTRAINT documents_source_type_check CHECK (source_type IN (
                'docs_page', 'release_record', 'feature_gate_reference',
                'kep', 'blog_post', 'governance_doc'
            ))
        """
    )
    op.execute(
        """
        ALTER TABLE document_aliases
            DROP CONSTRAINT document_aliases_alias_check,
            ADD CONSTRAINT document_aliases_alias_check
                CHECK (alias ~ '^(web|gate|kep|changelog|community|sig-release):')
        """
    )
