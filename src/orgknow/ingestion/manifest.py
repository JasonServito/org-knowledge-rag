"""Read the corpus manifest (config/corpus_manifest.yaml)."""

from itertools import pairwise
from pathlib import Path

# PyYAML ships no type hints, so safe_load returns Any: everything it returns is checked below.
import yaml  # type: ignore[import-untyped]

from orgknow.db.models import Release


def load_releases(path: Path) -> list[Release]:
    """Return the manifest's releases, oldest first, after checking the list is complete.

    A malformed entry raises pydantic's ValidationError; a broken rule raises ValueError.
    """
    # safe_load builds only plain values (dicts, lists, strings, dates), never Python objects.
    block = yaml.safe_load(path.read_text(encoding="utf-8"))["releases"]
    first, latest = block["first"], block["latest"]
    releases = [
        Release(
            version=entry["version"],
            release_date=entry["release_date"],
            end_of_life_date=entry["end_of_life"],
        )
        for entry in block["list"]
    ]

    if not releases or releases[0].version != first or releases[-1].version != latest:
        raise ValueError(
            f"releases.list must run from releases.first ({first}) to releases.latest ({latest})"
        )
    for release in releases:
        if release.end_of_life_date <= release.release_date:
            raise ValueError(
                f"{release.version}: end of life {release.end_of_life_date} is not after "
                f"its release date {release.release_date}"
            )
    for prev, cur in pairwise(releases):
        if cur.minor != prev.minor + 1:
            raise ValueError(f"releases must be contiguous: {cur.version} follows {prev.version}")
        if cur.release_date <= prev.release_date:
            raise ValueError(
                f"release dates must be strictly ascending: {cur.version} ({cur.release_date}) "
                f"is not after {prev.version} ({prev.release_date})"
            )
    return releases
