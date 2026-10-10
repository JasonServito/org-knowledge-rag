"""Writes to and reads from `observed_lifecycle` (migration 0006), and the read of a release's
feature-gate reference that `make lifecycle` builds it from (S09-T5)."""

from collections.abc import Sequence
from typing import Any, Literal

import psycopg
from psycopg.rows import TupleRow, class_row
from pydantic import BaseModel

Confidence = Literal["high", "low"]  # ADR-003 D5's status_confidence


class Observation(BaseModel):
    """One `observed_lifecycle` row: a feature gate's stage at a minor release, as that release's
    own feature-gate reference gives it (ADR-003 D2). The table's CHECKs, not this model, check
    that a high row has a stage from the vocabulary."""

    gate: str  # the name the release's reference gives it
    release: int  # the minor: 24 for v1.24
    stage: str | None  # None: no stage could be read (always low)
    status_confidence: Confidence


class ReferenceVersion(BaseModel):
    """A `feature_gate_reference` version: where to re-read its file, and its front matter."""

    canonical_id: str  # `gate:<name>` for a gate file, the page's URL id for a table page
    snapshot_repo: str
    snapshot_sha: str
    source_path: str
    metadata: dict[str, Any]


def reference_versions(conn: psycopg.Connection[TupleRow], release: int) -> list[ReferenceVersion]:
    """Return every `feature_gate_reference` version whose release window contains `release`, by
    canonical id: the table pages and the gate files of that release's own reference."""
    with conn.cursor(row_factory=class_row(ReferenceVersion)) as cur:
        cur.execute(
            """
            SELECT d.canonical_id, v.snapshot_repo, v.snapshot_sha, v.source_path, v.metadata
            FROM document_versions v
            JOIN documents d ON d.id = v.document_id
            WHERE d.source_type = 'feature_gate_reference'
              AND v.valid_from_release <= %(release)s
              AND (v.valid_until_release IS NULL OR %(release)s <= v.valid_until_release)
            ORDER BY d.canonical_id
            """,
            {"release": release},
        )
        return cur.fetchall()


def replace_observations(conn: psycopg.Connection[TupleRow], rows: Sequence[Observation]) -> None:
    """Delete every row, then insert `rows`, in one transaction: a row the table rejects raises,
    and the old rows stay. Inside a caller's transaction the block is a savepoint."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM observed_lifecycle")
        cur.executemany(
            """
            INSERT INTO observed_lifecycle (gate, release, stage, status_confidence)
            VALUES (%(gate)s, %(release)s, %(stage)s, %(status_confidence)s)
            """,
            [row.model_dump() for row in rows],
        )


def observations(
    conn: psycopg.Connection[TupleRow], gates: Sequence[str], until_release: int
) -> list[Observation]:
    """Return the rows of `gates` (names as written) at releases up to `until_release`, by gate,
    then release. A gate with no row is left out."""
    with conn.cursor(row_factory=class_row(Observation)) as cur:
        cur.execute(
            """
            SELECT gate, release, stage, status_confidence
            FROM observed_lifecycle
            WHERE gate = ANY(%(gates)s) AND release <= %(until_release)s
            ORDER BY gate, release
            """,
            {"gates": list(gates), "until_release": until_release},
        )
        return cur.fetchall()
