"""Versions and windows from snapshots (domain model, "How windows are derived"), and the
compare-and-extend plan for a re-ingest (S04-R1 decision 2)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orgknow.db.models import Release, Version, VersionData
from orgknow.ingestion.history import (
    Close,
    HistoryMismatch,
    Observed,
    date_history,
    plan_changes,
    release_history,
)
from orgknow.ingestion.manifest import Snapshot, load_releases
from orgknow.ingestion.normalize import FileState, kep_state

ROOT = Path(__file__).parents[2]
RELEASES: list[Release] = load_releases(ROOT / "config" / "corpus_manifest.yaml")
README = "keps/sig-auth/2579-psp-replacement/README.md"


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


def _times(*iso: str) -> tuple[datetime, ...]:
    return tuple(datetime.fromisoformat(t) for t in iso)


# --- KEP-2579: a date-scoped source -------------------------------------------------------------


def _kep(release: str) -> FileState:
    """The real kep.yaml of that snapshot; the README is a stand-in (it only feeds the hash)."""
    kep_yaml = (ROOT / "tests" / "fixtures" / "kep_2579" / f"{release}.kep.yaml").read_bytes()
    strip = frozenset({"reviewers", "approvers", "editor", "last-updated"})
    state = kep_state(README, b"# KEP-2579 (stand-in)\n", kep_yaml, strip, {"GA": "stable"})
    assert state is not None
    return state


# Enhancements `master` at each release date (config/corpus_manifest.lock.yaml), then head. The
# snapshots between 1.26 and 1.37 hold the same files as 1.26, so they add nothing and are left out.
# Commit times are the real `git log --format=%cI` output, newest first, with the committers'
# own offsets: the commits touching README.md or kep.yaml since the previous snapshot. Only the
# newest and oldest of each range are listed (1.22 has 47).
KEP_2579 = [
    Observed(Snapshot(20, "master", "2df83383d452cf5dd029de73e1963543dbf37998"), None),
    Observed(Snapshot(21, "master", "a500df8dc9597839caf8616ec4d03885274593f4"), None),
    Observed(
        Snapshot(22, "master", "96fd20c76108d86a94abbbe9929cf862bdf82986"),
        _kep("1.22"),
        _times(
            "2021-05-11T13:46:27-07:00",  # 182464a6 fix typo
            "2021-05-11T13:42:01-07:00",  # 18948fdb fill in monitoring requirements
            "2021-03-30T14:48:34-07:00",  # 56b19d92 Rename to placeholder name
        ),
    ),
    Observed(
        Snapshot(23, "master", "789f79c47e11ddf542b660ced225d7051160ab4b"),
        _kep("1.23"),
        _times(
            "2021-11-04T21:29:13-04:00",  # 69d3fac5 kep-2579: PodSecurity beta updates
            "2021-10-05T16:38:34-07:00",  # 1140e3b6 [PodSecurity] Update monitoring proposal
        ),
    ),
    Observed(Snapshot(24, "master", "afd1749ed97f63b39c20e7d91f93e2ff4ee87086"), _kep("1.23")),
    Observed(
        Snapshot(25, "master", "1360780fdac95441a071b9fa05406b095d882391"),
        _kep("1.25"),
        _times(
            "2022-06-01T17:05:45-07:00",  # cd5f4f26 PSA GA KEP compliance
            "2022-05-11T11:18:45-07:00",  # da76cd07 Pod Security GA plan
        ),
    ),
    Observed(
        Snapshot(26, "master", "0ffd37f8925d8a9af7ce7a7409007db8285a30b1"),
        _kep("1.26"),
        _times(
            "2022-09-22T10:28:05+02:00",  # 313ad8b5 Cleanup prr-approvers from kep.yaml
            "2022-08-31T15:51:14-04:00",  # 9f14627a Update implemented status for sig-auth keps
        ),
    ),
    Observed(Snapshot(37, "master", "c4f439c2dd4acb928094660be0ea771bf63f2b76"), _kep("1.26")),
    Observed(Snapshot(None, "master", "4be81e27aef5d252972fd02b5a9479a18982dfe5"), _kep("1.26")),
]


def _window(v: VersionData) -> tuple[Any, ...]:
    return (
        v.valid_from_date,
        v.valid_until_date,
        v.valid_from_release,
        v.valid_until_release,
        v.claimed_status,
        v.claimed_stage,
        v.snapshot_sha,
    )


def test_kep_2579_windows_and_claims() -> None:
    versions = date_history("enhancements", KEP_2579, RELEASES)

    # Expected values from the S04-R1 sitting (`TZ=UTC git log --date=iso-strict-local`): each
    # version starts at the LAST commit before its snapshot; each `until` is the next `from`.
    v1_from = _utc(2021, 5, 11, 20, 46, 27)  # 182464a6
    v2_from = _utc(2021, 11, 5, 1, 29, 13)  # 69d3fac5
    v3_from = _utc(2022, 6, 2, 0, 5, 45)  # cd5f4f26
    v4_from = _utc(2022, 9, 22, 8, 28, 5)  # 313ad8b5
    assert [_window(v) for v in versions] == [
        (
            v1_from,
            v2_from,
            21,
            22,
            "implementable",
            "alpha",
            "96fd20c76108d86a94abbbe9929cf862bdf82986",
        ),
        (
            v2_from,
            v3_from,
            22,
            24,
            "implementable",
            "beta",
            "789f79c47e11ddf542b660ced225d7051160ab4b",
        ),
        (
            v3_from,
            v4_from,
            24,
            25,
            "implementable",
            "stable",
            "1360780fdac95441a071b9fa05406b095d882391",
        ),
        (
            v4_from,
            None,
            25,
            None,
            "implemented",
            "stable",
            "0ffd37f8925d8a9af7ce7a7409007db8285a30b1",
        ),
    ]
    assert {(v.snapshot_repo, v.snapshot_ref, v.source_path) for v in versions} == {
        ("enhancements", "master", README)
    }
    # Every from/until is UTC-aware, never a local time read as UTC.
    assert all(v.valid_from_date.utcoffset() is not None for v in versions)


def test_kep_removal_closes_the_version_at_the_last_commit() -> None:
    removed = Observed(
        Snapshot(27, "master", "d1b916cc418f7c53bcb4578bb96a08c99043c7e3"),
        None,
        _times("2023-01-10T12:00:00+00:00"),  # a hand-made deletion commit
    )

    versions = date_history("enhancements", [*KEP_2579[:7], removed], RELEASES)

    assert _window(versions[-1])[:4] == (_utc(2022, 9, 22, 8, 28, 5), _utc(2023, 1, 10, 12), 25, 26)


def test_a_content_change_without_a_commit_is_an_error() -> None:
    no_commits = Observed(KEP_2579[2].snapshot, KEP_2579[2].state)

    with pytest.raises(ValueError, match="no commit"):
        date_history("enhancements", [*KEP_2579[:2], no_commits], RELEASES)


def test_a_change_dated_before_the_version_it_replaces_is_an_error() -> None:
    # A hand-made commit time before v1's start (2021-05-11T20:46:27Z): v1's window would be empty.
    backdated = Observed(
        KEP_2579[3].snapshot, KEP_2579[3].state, _times("2021-05-01T00:00:00+00:00")
    )

    with pytest.raises(ValueError, match="not after the version it replaces"):
        date_history("enhancements", [*KEP_2579[:3], backdated], RELEASES)


def test_a_version_from_before_the_first_release_is_an_error() -> None:
    too_early = Observed(
        KEP_2579[0].snapshot, KEP_2579[2].state, _times("2020-12-07T23:59:59+00:00")
    )

    with pytest.raises(ValueError, match=r"before the first release \(1\.20, 2020-12-08\)"):
        date_history("enhancements", [too_early], RELEASES)


# --- Docs: a release-scoped source -------------------------------------------------------------


def _page(content_hash: str) -> FileState:
    return FileState(
        content_hash=content_hash * 64,
        source_path="content/en/docs/concepts/security/example.md",
        metadata={"title": "Example"},
    )


def _release(minor: int, state: FileState | None) -> Observed:
    return Observed(Snapshot(minor, f"release-1.{minor}", f"{minor:040d}"), state)


def test_docs_windows_with_a_gap_and_a_return_to_earlier_text() -> None:
    # A at 24-25, absent at 26, B at 27, A again at 28.
    observed = [
        _release(24, _page("a")),
        _release(25, _page("a")),
        _release(26, None),
        _release(27, _page("b")),
        _release(28, _page("a")),
    ]

    versions = release_history("website", observed, RELEASES)

    # Release dates from config/corpus_manifest.yaml at 00:00 UTC; release `until` = R2 - 1.
    assert [(v.content_hash[0], *_window(v)) for v in versions] == [
        ("a", _utc(2022, 5, 3), _utc(2022, 12, 8), 24, 25, None, None, f"{24:040d}"),
        ("b", _utc(2023, 4, 11), _utc(2023, 8, 15), 27, 27, None, None, f"{27:040d}"),
        ("a", _utc(2023, 8, 15), None, 28, None, None, None, f"{28:040d}"),
    ]
    assert versions[0].snapshot_ref == "release-1.24"
    assert versions[0].metadata == {"title": "Example"}


# --- plan_changes: compare and extend ----------------------------------------------------------

HASH_A, HASH_B, HASH_C = "a" * 64, "b" * 64, "c" * 64
D24, D25, D30 = _utc(2022, 5, 3), _utc(2022, 8, 23), _utc(2024, 4, 17)


def _derived(
    content_hash: str,
    from_release: int,
    from_date: datetime,
    until_release: int | None = None,
    until_date: datetime | None = None,
) -> VersionData:
    return VersionData(
        content_hash=content_hash,
        source_path="content/en/docs/concepts/security/example.md",
        snapshot_repo="website",
        snapshot_ref=f"release-1.{from_release}",
        snapshot_sha="0" * 40,
        valid_from_release=from_release,
        valid_until_release=until_release,
        valid_from_date=from_date,
        valid_until_date=until_date,
    )


def _stored(version_id: int, derived: VersionData) -> Version:
    return Version(id=version_id, document_id=1, **derived.model_dump())


def test_nothing_stored_inserts_every_version() -> None:
    derived = [_derived(HASH_A, 24, D24, 24, D25), _derived(HASH_B, 25, D25)]

    plan = plan_changes([], derived)

    assert plan.close is None
    assert plan.insert == derived


def test_an_equal_history_changes_nothing() -> None:
    derived = [_derived(HASH_A, 24, D24, 24, D25), _derived(HASH_B, 25, D25)]
    stored = [_stored(7, derived[0]), _stored(8, derived[1])]

    plan = plan_changes(stored, derived)

    assert plan.close is None
    assert plan.insert == []


def test_a_stored_prefix_with_an_open_last_version_is_closed_and_extended() -> None:
    # Stored when 1.29 was the latest release; 1.30 then changed the page.
    stored = [_stored(7, _derived(HASH_A, 24, D24, 24, D25)), _stored(8, _derived(HASH_B, 25, D25))]
    derived = [
        _derived(HASH_A, 24, D24, 24, D25),
        _derived(HASH_B, 25, D25, 29, D30),
        _derived(HASH_C, 30, D30),
    ]

    plan = plan_changes(stored, derived)

    assert plan.close == Close(version_id=8, valid_until_release=29, valid_until_date=D30)
    assert plan.insert == [derived[2]]


def test_a_stored_prefix_with_a_closed_last_version_is_extended() -> None:
    # The page was removed at 1.25 and came back at 1.30.
    stored = [_stored(7, _derived(HASH_A, 24, D24, 24, D25))]
    derived = [_derived(HASH_A, 24, D24, 24, D25), _derived(HASH_B, 30, D30)]

    plan = plan_changes(stored, derived)

    assert plan.close is None
    assert plan.insert == [derived[1]]


@pytest.mark.parametrize(
    "derived",
    [
        # An earlier version's text changed (e.g. the lock moved an old release branch).
        [_derived(HASH_C, 24, D24, 24, D25), _derived(HASH_B, 25, D25)],
        # The current version now starts at another release.
        [_derived(HASH_A, 24, D24, 24, D25), _derived(HASH_B, 26, _utc(2022, 12, 8))],
        # Fewer versions than stored.
        [_derived(HASH_A, 24, D24, 24, D25)],
    ],
)
def test_a_diverged_history_is_a_mismatch(derived: list[VersionData]) -> None:
    stored = [_stored(7, _derived(HASH_A, 24, D24, 24, D25)), _stored(8, _derived(HASH_B, 25, D25))]

    with pytest.raises(HistoryMismatch):
        plan_changes(stored, derived)
