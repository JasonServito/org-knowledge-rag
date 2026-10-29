"""S10-T2: the KEP version valid at a release (`kep_versions_at`), and the rule-found conflicts of
one question's hits (`rule_conflicts`), on hand-typed rows in the test database.

KEP-2579's 4 versions are the stored ones (release windows, claims, latest milestones): two are
valid at 1.24, beta (1.22-1.24) and stable (1.24-1.25). PodSecurity is beta at 1.24, as stored.
Release dates are the manifest's. Every expected value is typed by hand.
"""

from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.documents import create_document
from orgknow.db.lifecycle import kep_versions_at, replace_observations
from orgknow.db.models import Authority, Hit, NewestVersion, NewVersion, Observation
from orgknow.db.versions import insert_version
from orgknow.generation.conflicts import Conflict, rule_conflicts
from orgknow.settings import Settings

Conn = psycopg.Connection[TupleRow]

GATES = [{"name": "PodSecurity"}]
# (release window, date window starts, claimed status and stage, latest milestone), oldest first.
# Each date window ends where the next starts; the last is open.
KEP_2579_VERSIONS: list[tuple[int, int | None, date, str, str, str]] = [
    (21, 22, date(2021, 5, 12), "implementable", "alpha", "v1.22"),
    (22, 24, date(2021, 11, 11), "implementable", "beta", "v1.23"),
    (24, 25, date(2022, 6, 6), "implementable", "stable", "v1.25"),
    (25, None, date(2022, 9, 22), "implemented", "stable", "v1.25"),
]


def _utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _kep_2579(conn: Conn) -> None:
    document_id = create_document(conn, "kep:2579", "kep")
    starts = [version[2] for version in KEP_2579_VERSIONS]
    for (from_release, until_release, start, status, stage, milestone), until in zip(
        KEP_2579_VERSIONS, [*starts[1:], None], strict=True
    ):
        insert_version(
            conn,
            NewVersion(
                document_id=document_id,
                content_hash="0" * 64,
                source_path="keps/sig-auth/2579-psp-replacement/README.md",
                snapshot_repo="enhancements",
                snapshot_ref="master",
                snapshot_sha="1" * 40,
                valid_from_release=from_release,
                valid_until_release=until_release,
                valid_from_date=_utc(start),
                valid_until_date=None if until is None else _utc(until),
                claimed_status=status,
                claimed_stage=stage,
                metadata={"feature-gates": GATES, "latest-milestone": milestone},
            ),
        )


def _version(status: str, stage: str, milestone: str) -> NewestVersion:
    return NewestVersion(
        canonical_id="kep:2579",
        source_type="kep",
        claimed_status=status,
        claimed_stage=stage,
        metadata={"feature-gates": GATES, "latest-milestone": milestone},
    )


def test_kep_versions_at_gives_the_newest_version_valid_at_the_release(
    conn: Conn, seeded_releases: None
) -> None:
    _kep_2579(conn)

    # 1.24: two versions are valid; the newer (stable, from 2022-06-06) is returned. kep:3453 has
    # no document, so it is left out.
    assert kep_versions_at(conn, ["kep:2579", "kep:3453"], 24) == {
        "kep:2579": _version("implementable", "stable", "v1.25")
    }
    # 1.20: before the first version (from 1.21).
    assert kep_versions_at(conn, ["kep:2579"], 20) == {}
    # 1.37, the latest: the open version.
    assert kep_versions_at(conn, ["kep:2579"], 37) == {
        "kep:2579": _version("implemented", "stable", "v1.25")
    }


def _hit(chunk_id: int, canonical_id: str, text: str = "body", **changes: Any) -> Hit:
    hit = Hit(
        chunk_id=chunk_id,
        content_hash="a" * 64,
        distance=0.3,
        text=text,
        canonical_id=canonical_id,
        source_type="kep",
        heading_path=["Implementation History"],
        release_windows=[(22, 24)],
        current=False,
        claimed_status="implementable",
        claimed_stage="beta",  # the cited version's: 1.22-1.24
        snapshot_repo="enhancements",
        snapshot_sha="1" * 40,
        source_path="README.md",
        metadata={"feature-gates": GATES, "latest-milestone": "v1.23"},
        authority=Authority(
            target_release=24, tier=3, effective_stage="beta", stage_confidence="high"
        ),
    )
    return hit.model_copy(update=changes)


# KEP-2579's real lines: 1.22 on its day, 1.23 34 days early. KEP-3453's line is changed by hand to
# 30 days early (2022-11-08; 1.26 was released 2022-12-08).
KEP_2579_HISTORY = (
    "- 2021-08-04: v1.22 Alpha version released\n- 2021-11-03: v1.23 Beta version released"
)
KEP_3453_HISTORY = "- 2022-11-08: Kubernetes 1.26 released"


def test_rule_conflicts_reads_the_version_at_the_target_and_orders_by_first_hit(
    conn: Conn, seeded_releases: None, settings: Settings
) -> None:
    _kep_2579(conn)
    replace_observations(
        conn, [Observation(gate="PodSecurity", release=24, stage="beta", status_confidence="high")]
    )
    hits = [
        _hit(1, "kep:3453", KEP_3453_HISTORY),  # no stored version: no claim to compare
        _hit(2, "kep:2579", KEP_2579_HISTORY),
        _hit(3, "web:/docs/concepts/security/pod-security-admission/", source_type="docs_page"),
        _hit(4, "kep:2579"),
    ]

    assert rule_conflicts(conn, hits, settings) == [
        Conflict(
            kind="history_date",
            found_by="rule",
            chunk_ids=[1],
            documents=["kep:3453"],
            summary=(
                "kep:3453 says v1.26 was released 2022-11-08; the releases table says 2022-12-08."
            ),
            resolution="observed_beats_claimed",
            prevails=None,
        ),
        # Both first at rank 2: the claim_mismatch comes first. Its claim is the stable version's
        # (valid at 1.24), not the cited beta version's. Its v1.25 milestone is after 1.24, so it
        # is left out (S10-T5c).
        Conflict(
            kind="claim_mismatch",
            found_by="rule",
            chunk_ids=[2, 4],
            documents=["kep:2579"],
            summary="kep:2579 claims stable; the feature-gate reference at 1.24 says beta.",
            resolution="observed_beats_claimed",
            prevails=None,
        ),
        Conflict(
            kind="history_date",
            found_by="rule",
            chunk_ids=[2],
            documents=["kep:2579"],
            summary=(
                "kep:2579 says v1.23 was released 2021-11-03; the releases table says 2021-12-07."
            ),
            resolution="observed_beats_claimed",
            prevails=None,
        ),
    ]


def test_hits_without_authority_have_no_rule_conflicts(
    conn: Conn, seeded_releases: None, settings: Settings
) -> None:
    hit = _hit(1, "kep:3453", KEP_3453_HISTORY, authority=None)

    assert rule_conflicts(conn, [hit], settings) == []
