"""The `observed_lifecycle` table (migration 0006) and its write and read (S09-T5).

The rows are typed by hand. The rejected rows break the migration's pinned constraints on purpose.
"""

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import TupleRow

from orgknow.db.lifecycle import Observation, observations, replace_observations

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
