"""A document's versions from its snapshots, and what a re-ingest changes (pure functions).

The rules are in docs/domain-model.md, "How windows are derived":
- A release date means 00:00 UTC. Release windows are inclusive; date windows are half-open.
- Docs (release-scoped): a version starts at the first release whose snapshot has its content
  and closes at the first later release R2 that differs or lacks the file: release `until` =
  R2 - 1, date `until` = R2's release date.
- KEPs (date-scoped): a version starts at the committer time of the LAST commit touching the
  files since the previous snapshot; the previous version closes at that same instant.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from orgknow.db.models import Release, Version, VersionData
from orgknow.ingestion.manifest import Snapshot
from orgknow.ingestion.normalize import FileState


@dataclass(frozen=True)
class Observed:
    """One document at one snapshot."""

    snapshot: Snapshot
    state: FileState | None  # None: the document is absent from this snapshot
    # Date-scoped sources only: committer times (UTC) of the commits touching the document's
    # files since the previous snapshot. Needed wherever the content changed.
    commit_times: tuple[datetime, ...] = ()


def midnight_utc(day: date) -> datetime:
    return datetime.combine(day, time(), UTC)


def _release_on_or_before(at: datetime, releases: Sequence[Release]) -> int:
    """The latest release whose date (00:00 UTC) is on or before `at`."""
    started = [r.minor for r in releases if midnight_utc(r.release_date) <= at]
    if not started:
        first = releases[0]
        raise ValueError(
            f"{at.isoformat()} is before the first release ({first.version}, {first.release_date})"
        )
    return max(started)


def _release_before(at: datetime, releases: Sequence[Release]) -> int:
    """The latest release whose date (00:00 UTC) is strictly before `at`."""
    return max(r.minor for r in releases if midnight_utc(r.release_date) < at)


def _hash(state: FileState | None) -> str | None:
    return None if state is None else state.content_hash


def _new_version(
    repo: str, snapshot: Snapshot, state: FileState, from_release: int, from_date: datetime
) -> VersionData:
    return VersionData(
        content_hash=state.content_hash,
        source_path=state.source_path,
        snapshot_repo=repo,
        snapshot_ref=snapshot.ref,
        snapshot_sha=snapshot.sha,
        valid_from_release=from_release,
        valid_from_date=from_date,
        claimed_status=state.claimed_status,
        claimed_stage=state.claimed_stage,
        metadata=state.metadata,
    )


def release_history(
    repo: str, observed: Sequence[Observed], releases: Sequence[Release]
) -> list[VersionData]:
    """Versions of a release-scoped document (docs), from one snapshot per release, oldest first."""
    release_dates = {r.minor: r.release_date for r in releases}
    versions: list[VersionData] = []
    previous: FileState | None = None
    for obs in observed:
        release = obs.snapshot.release
        if release is None:
            raise ValueError(f"release-scoped snapshot {obs.snapshot.sha} has no release")
        if _hash(obs.state) == _hash(previous):
            continue
        starts = midnight_utc(release_dates[release])
        if versions and versions[-1].valid_until_date is None:
            # The text changed or the file is gone: the open version spoke for up to R2 - 1.
            versions[-1] = versions[-1].model_copy(
                update={"valid_until_release": release - 1, "valid_until_date": starts}
            )
        if obs.state is not None:
            versions.append(_new_version(repo, obs.snapshot, obs.state, release, starts))
        previous = obs.state
    return versions


def date_history(
    repo: str, observed: Sequence[Observed], releases: Sequence[Release]
) -> list[VersionData]:
    """Versions of a date-scoped document (KEP), from its snapshots, oldest first."""
    versions: list[VersionData] = []
    previous: FileState | None = None
    for obs in observed:
        if _hash(obs.state) == _hash(previous):
            continue
        if not obs.commit_times:
            raise ValueError(
                f"the content changed at {obs.snapshot.label} ({obs.snapshot.sha}), "
                "but no commit since the previous snapshot touches it"
            )
        # The last commit: the stored text was exactly the live text from then on.
        at = max(obs.commit_times)
        if versions and versions[-1].valid_until_date is None:
            current = versions[-1]
            if at <= current.valid_from_date:
                raise ValueError(
                    f"the change at {obs.snapshot.label} is dated {at.isoformat()}, not after "
                    f"the version it replaces ({current.valid_from_date.isoformat()})"
                )
            versions[-1] = current.model_copy(
                update={
                    "valid_until_release": _release_before(at, releases),
                    "valid_until_date": at,
                }
            )
        if obs.state is not None:
            from_release = _release_on_or_before(at, releases)
            versions.append(_new_version(repo, obs.snapshot, obs.state, from_release, at))
        previous = obs.state
    return versions


# --- Re-ingest: compare and extend (S04-R1 decision 2) -----------------------------------------


class HistoryMismatch(Exception):
    """The stored versions aren't a prefix of the derived ones; the document is left untouched."""


@dataclass(frozen=True)
class Close:
    """Close a stored open version (`close_version`)."""

    version_id: int
    valid_until_release: int
    valid_until_date: datetime


@dataclass(frozen=True)
class Plan:
    """What re-ingesting one document writes: close at most one version, then insert."""

    close: Close | None
    insert: list[VersionData]


def _window(v: VersionData) -> tuple[object, ...]:
    """What makes two versions the same version: its content and both windows."""
    return (
        v.content_hash,
        v.valid_from_release,
        v.valid_until_release,
        v.valid_from_date,
        v.valid_until_date,
    )


def _opening(v: VersionData) -> tuple[object, ...]:
    """A version's content and where it starts; its `until` may still change while it's open."""
    return (v.content_hash, v.valid_from_release, v.valid_from_date)


def plan_changes(stored: Sequence[Version], derived: Sequence[VersionData]) -> Plan:
    """Compare a document's stored versions with the ones derived from its snapshots.

    - none stored: insert them all
    - equal: change nothing
    - stored is a prefix (a newer snapshot arrived): close the open version if the newer
      snapshot closed it, then insert the rest
    - anything else: raise HistoryMismatch
    """
    if len(stored) > len(derived):
        raise HistoryMismatch(
            f"history mismatch: {len(stored)} versions stored, only {len(derived)} derived"
        )
    close = None
    for i, old in enumerate(stored):
        new = derived[i]
        if _window(old) == _window(new):
            continue
        # Only the stored current version may differ, and only by having been closed since.
        is_open_last = i == len(stored) - 1 and old.valid_until_date is None
        if is_open_last and _opening(old) == _opening(new):
            assert new.valid_until_release is not None and new.valid_until_date is not None
            close = Close(old.id, new.valid_until_release, new.valid_until_date)
            continue
        raise HistoryMismatch(
            f"history mismatch: stored version {i + 1} (id {old.id}) {_window(old)} "
            f"differs from the derived one {_window(new)}"
        )
    return Plan(close, list(derived[len(stored) :]))
