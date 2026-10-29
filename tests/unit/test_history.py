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
    changelog_version,
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
# Each change carries its merge time: the committer time of the last first-parent commit touching
# README.md or kep.yaml since the previous snapshot, as `git log --first-parent --format=%cI` prints
# it (S05-R2 design review). These are master's merge commits, not the PR branches' own commits.
KEP_2579 = [
    Observed(Snapshot(20, "master", "2df83383d452cf5dd029de73e1963543dbf37998"), None),
    Observed(Snapshot(21, "master", "a500df8dc9597839caf8616ec4d03885274593f4"), None),
    Observed(
        Snapshot(22, "master", "96fd20c76108d86a94abbbe9929cf862bdf82986"),
        _kep("1.22"),
        datetime.fromisoformat("2021-05-12T16:25:28+00:00"),  # 7712007e
    ),
    Observed(
        Snapshot(23, "master", "789f79c47e11ddf542b660ced225d7051160ab4b"),
        _kep("1.23"),
        datetime.fromisoformat("2021-11-11T16:46:07+00:00"),  # 0e230b08
    ),
    Observed(Snapshot(24, "master", "afd1749ed97f63b39c20e7d91f93e2ff4ee87086"), _kep("1.23")),
    Observed(
        Snapshot(25, "master", "1360780fdac95441a071b9fa05406b095d882391"),
        _kep("1.25"),
        datetime.fromisoformat("2022-06-06T16:34:23+00:00"),  # ed335b36
    ),
    Observed(
        Snapshot(26, "master", "0ffd37f8925d8a9af7ce7a7409007db8285a30b1"),
        _kep("1.26"),
        datetime.fromisoformat("2022-09-22T15:59:06+00:00"),  # 4b87fd52
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

    # Expected values from the S05-R2 plan (`git log --first-parent`, in the design review): each
    # version starts at its merge time; each `until` is the next `from`. Windows [21,22] [22,24]
    # [24,25] [25,-]. S04 stored the branch commits' times instead (2021-05-11T20:46:27Z, ...).
    v1_from = _utc(2021, 5, 12, 16, 25, 28)
    v2_from = _utc(2021, 11, 11, 16, 46, 7)
    v3_from = _utc(2022, 6, 6, 16, 34, 23)
    v4_from = _utc(2022, 9, 22, 15, 59, 6)
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


SNAPSHOT_27 = Snapshot(27, "master", "d1b916cc418f7c53bcb4578bb96a08c99043c7e3")
SNAPSHOT_28 = Snapshot(28, "master", "6f435a9d5438c213ddef09ef6ebe1c178700d73b")


def test_kep_removal_closes_the_version_at_its_merge_time() -> None:
    removed = Observed(SNAPSHOT_27, None, _utc(2023, 1, 10, 12))  # a hand-made deletion merge

    versions = date_history("enhancements", [*KEP_2579[:7], removed], RELEASES)

    assert _window(versions[-1])[:4] == (
        _utc(2022, 9, 22, 15, 59, 6),
        _utc(2023, 1, 10, 12),
        25,
        26,
    )


def test_a_content_change_without_a_commit_is_an_error() -> None:
    no_commits = Observed(KEP_2579[2].snapshot, KEP_2579[2].state)

    with pytest.raises(ValueError, match="no commit"):
        date_history("enhancements", [*KEP_2579[:2], no_commits], RELEASES)


def test_a_change_dated_before_the_version_it_replaces_is_an_error() -> None:
    # A hand-made merge time before v1's start (2021-05-12T16:25:28Z): v1's window would be empty.
    backdated = Observed(KEP_2579[3].snapshot, KEP_2579[3].state, _utc(2021, 5, 1))

    with pytest.raises(ValueError, match="not after the version it replaces"):
        date_history("enhancements", [*KEP_2579[:3], backdated], RELEASES)


def test_a_version_older_than_the_first_release_keeps_its_date_and_starts_at_20() -> None:
    # S05-R2 decision 1: a hand-made 2019 merge time, before 1.20's release (2020-12-08). The
    # date window is authoritative for a date-scoped source; the release window starts at the
    # scope's first release, 20.
    older = Observed(KEP_2579[0].snapshot, KEP_2579[2].state, _utc(2019, 6, 29, 12))

    (version,) = date_history("enhancements", [older], RELEASES)

    assert (version.valid_from_date, version.valid_from_release) == (_utc(2019, 6, 29, 12), 20)
    assert (version.valid_until_date, version.valid_until_release) == (None, None)


def test_a_document_recreated_before_its_last_version_closed_is_an_error() -> None:
    # E1 (S05-R2): KEP-2579 removed at 1.27 by a hand-made merge on 2023-01-10, then back at 1.28.
    # Dated after the removal, the new version simply follows the closed one.
    removed = Observed(SNAPSHOT_27, None, _utc(2023, 1, 10, 12))
    back = Observed(SNAPSHOT_28, KEP_2579[6].state, _utc(2023, 5, 1))

    versions = date_history("enhancements", [*KEP_2579[:7], removed, back], RELEASES)

    assert [_window(v)[:4] for v in versions[-2:]] == [
        (_utc(2022, 9, 22, 15, 59, 6), _utc(2023, 1, 10, 12), 25, 26),
        (_utc(2023, 5, 1), None, 27, None),
    ]

    # Dated before the removal, the two date windows would overlap (R8): a ValueError for this
    # document, never a database error.
    backdated = Observed(SNAPSHOT_28, KEP_2579[6].state, _utc(2023, 1, 1))
    with pytest.raises(ValueError, match="before its previous version closed"):
        date_history("enhancements", [*KEP_2579[:7], removed, backdated], RELEASES)


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


# --- CHANGELOG: one file per release, read at the kubernetes lock head ------------------------

# The kubernetes lock head (config/corpus_manifest.lock.yaml) and its committer time, as
# `git log -1 --format=%cI 7c596ad7` prints it in the clone (S05-R2 decision 6).
KUBERNETES_HEAD = Snapshot(None, "master", "7c596ad7938d030a4cab3c1e55b16b7f61cf7ca5")
HEAD_TIME = _utc(2026, 9, 30, 1, 30, 57)


def test_a_changelog_version_speaks_for_its_release_from_the_head_commit_time() -> None:
    state = FileState(
        content_hash="c" * 64,
        source_path="CHANGELOG/CHANGELOG-1.30.md",
        metadata={"title": "CHANGELOG-1.30"},
    )

    version = changelog_version("kubernetes", KUBERNETES_HEAD, state, 30, HEAD_TIME)

    # Release window [30, 30], set at insert; date window from the head commit's time, open.
    assert _window(version) == (
        HEAD_TIME,
        None,
        30,
        30,
        None,
        None,
        "7c596ad7938d030a4cab3c1e55b16b7f61cf7ca5",
    )
    assert (version.snapshot_repo, version.snapshot_ref) == ("kubernetes", "master")
    assert (version.source_path, version.content_hash) == ("CHANGELOG/CHANGELOG-1.30.md", "c" * 64)
    assert version.metadata == {"title": "CHANGELOG-1.30"}


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
