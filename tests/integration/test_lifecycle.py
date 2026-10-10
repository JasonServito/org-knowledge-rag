"""The `observed_lifecycle` table (migration 0006) and its write and read (S09-T5), and the read
of documents' newest versions (S09-T6).

The rows are typed by hand. The rejected rows break the migration's pinned constraints on purpose.
"""

from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import TupleRow

from orgknow.db.documents import create_document
from orgknow.db.lifecycle import newest_versions, observations, replace_observations
from orgknow.db.models import NewestVersion, NewVersion, Observation
from orgknow.db.versions import insert_version

Conn = psycopg.Connection[TupleRow]

PODSECURITY_22 = Observation(
    gate="PodSecurity", release=22, stage="alpha", status_confidence="high"
)
PODSECURITY_25 = Observation(
    gate="PodSecurity", release=25, stage="stable", status_confidence="high"
)
CSI_AWS_20 = Observation(gate="CSIMigrationAWS", release=20, stage=None, status_confidence="low")
LEGACY_20 = Observation(
    gate="LegacyNodeRoleBehavior", release=20, stage="True", status_confidence="low"
)
ROWS = [PODSECURITY_22, PODSECURITY_25, CSI_AWS_20, LEGACY_20]
ALL_GATES = ["PodSecurity", "CSIMigrationAWS", "LegacyNodeRoleBehavior"]


def test_observations_are_the_gates_rows_up_to_a_release(conn: Conn, seeded_releases: None) -> None:
    replace_observations(conn, ROWS)

    # By gate, then release; PodSecurity at 25 is after 22, LegacyNodeRoleBehavior isn't asked.
    assert observations(conn, ["PodSecurity", "CSIMigrationAWS"], 22) == [
        CSI_AWS_20,
        PODSECURITY_22,
    ]


def test_a_rebuild_deletes_every_old_row(conn: Conn, seeded_releases: None) -> None:
    replace_observations(conn, ROWS)
    replace_observations(conn, [PODSECURITY_25])

    assert observations(conn, ALL_GATES, 37) == [PODSECURITY_25]


@pytest.mark.parametrize(
    ("bad_row", "error", "constraint"),
    [
        # high needs a stage from the vocabulary; `True` is kept only as a low row.
        (
            Observation(gate="X", release=20, stage="True", status_confidence="high"),
            errors.CheckViolation,
            "observed_lifecycle_high_check",
        ),
        # 1.99 isn't in `releases`.
        (
            Observation(gate="X", release=99, stage="beta", status_confidence="high"),
            errors.ForeignKeyViolation,
            "observed_lifecycle_release_fkey",
        ),
    ],
)
def test_a_bad_row_rejects_the_whole_rebuild(
    conn: Conn,
    seeded_releases: None,
    bad_row: Observation,
    error: type[psycopg.Error],
    constraint: str,
) -> None:
    replace_observations(conn, ROWS)

    with pytest.raises(error) as caught:
        replace_observations(conn, [PODSECURITY_22, bad_row])

    assert caught.value.diag.constraint_name == constraint
    # All or nothing: the delete and the good row were rolled back with the bad one.
    assert observations(conn, ALL_GATES, 37) == [
        CSI_AWS_20,
        LEGACY_20,
        PODSECURITY_22,
        PODSECURITY_25,
    ]


# The newest version of given documents (S09-T6), for the golden labels' tiers.

D21 = datetime(2021, 4, 8, tzinfo=UTC)  # release dates from the manifest (00:00 UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)
GATES = [{"name": "PodSecurity", "components": ["kube-apiserver"]}]


def _version(
    conn: Conn,
    document_id: int,
    releases: tuple[int, int | None],
    dates: tuple[datetime, datetime | None],
    claim: tuple[str | None, str | None] = (None, None),
    metadata: dict[str, Any] | None = None,
) -> None:
    insert_version(
        conn,
        NewVersion(
            document_id=document_id,
            content_hash="0" * 64,
            source_path="page.md",
            snapshot_repo="enhancements",
            snapshot_ref="master",
            snapshot_sha="1" * 40,
            valid_from_release=releases[0],
            valid_until_release=releases[1],
            valid_from_date=dates[0],
            valid_until_date=dates[1],
            claimed_status=claim[0],
            claimed_stage=claim[1],
            metadata=metadata or {},
        ),
    )


def test_newest_versions_reads_each_documents_newest_version(
    conn: Conn, seeded_releases: None
) -> None:
    kep = create_document(conn, "kep:2579", "kep")
    # Stored newest first, so only the date can pick the newest.
    _version(
        conn, kep, (25, None), (D25, None), ("implemented", "stable"), {"feature-gates": GATES}
    )
    _version(conn, kep, (21, 24), (D21, D25), ("implementable", "beta"))
    _version(conn, create_document(conn, "web:/test/psa/", "docs_page"), (21, None), (D21, None))

    # By canonical id; an id with no document is left out.
    assert newest_versions(conn, ["web:/test/psa/", "web:/test/missing/", "kep:2579"]) == [
        NewestVersion(
            canonical_id="kep:2579",
            source_type="kep",
            claimed_status="implemented",
            claimed_stage="stable",
            metadata={"feature-gates": GATES},
        ),
        NewestVersion(
            canonical_id="web:/test/psa/",
            source_type="docs_page",
            claimed_status=None,
            claimed_stage=None,
            metadata={},
        ),
    ]
