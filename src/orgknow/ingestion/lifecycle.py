"""Each feature gate's stage at each minor release, as that release's own feature-gate reference
gives it, into `observed_lifecycle` (ADR-003 D2; S09-R2 decision 6 and the T5 rules).

Run with `make lifecycle`; `make ingest` runs the same step after chunking. It rebuilds the whole
table from the stored versions, for every release in `releases`, so a re-run stores the same
rows. Needs `make ingest` first.

- Release R's reference: up to 1.28, the rows of the table pages valid at R (`feature-gates`,
  and `feature-gates-removed` from 1.25), re-read from git at their snapshots; a gate on both
  pages gets both pages' rows. From 1.29, each gate file valid at R, named by its front-matter
  `title` there (a renamed gate goes by that release's name: no aliasing), with the ranges of
  its `stages`, read from the stored front matter.
- The stage at R: `stage_at`. One row per gate that has a range covering R.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.lifecycle import (
    Confidence,
    Observation,
    reference_versions,
    replace_observations,
)
from orgknow.db.releases import list_releases
from orgknow.ingestion.git_reader import read_file
from orgknow.ingestion.normalize import decode
from orgknow.settings import Settings

# ADR-003 D1: up to 1.28 the reference is pipe tables on a page; from 1.29 one file per gate.
LAST_TABLE_RELEASE = 28
# A table row: | `Name` | default | stage | from | until |, under a `Since | Until` or a
# `From | To` header (the S02 spike's pattern). A header row has no `Name` in backticks.
TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|")
OPEN_CELLS = ("", "-")  # a table's open end
# v?1.N(.P)?(-alpha|beta|rc.M)?, e.g. v1.22.0-beta.1; group 1 is the minor N.
VERSION = re.compile(r"v?1\.(\d+)(?:\.\d+)?(?:-(?:alpha|beta|rc)\.\d+)?")
# The lifecycle stages a range can give with high confidence (ADR-003 D5).
STAGES = frozenset({"alpha", "beta", "stable", "deprecated"})


@dataclass(frozen=True)
class Range:
    """One stage over a span of releases, both ends included: a table row, or an entry of a gate
    file's `stages`. The stage and bounds are as written (YAML can give a bound as a number); a
    None bound is an open end."""

    stage: str
    start: object
    end: object


def minor(version: object) -> int | None:
    """The minor N of a version string `v?1.N(.P)?(-alpha|beta|rc.M)?`: 22 for v1.22.0-beta.1.
    None for anything else, a YAML number included (an unquoted 1.30 is the number 1.3)."""
    if not isinstance(version, str):
        return None
    match = VERSION.fullmatch(version)
    return int(match.group(1)) if match else None


def table_ranges(text: str) -> dict[str, list[Range]]:
    """{gate: its rows, in page order} from a pre-1.29 table page. An empty cell or `-` is an
    open end."""
    gates: dict[str, list[Range]] = {}
    for line in text.splitlines():
        if match := TABLE_ROW.match(line):
            gate, stage, start, end = (cell.strip() for cell in match.groups())
            row = Range(
                stage, None if start in OPEN_CELLS else start, None if end in OPEN_CELLS else end
            )
            gates.setdefault(gate, []).append(row)
    return gates


def file_ranges(front_matter: Mapping[str, Any]) -> list[Range]:
    """The ranges of a 1.29+ gate file's `stages`, in file order. A missing `toVersion` is an
    open end. `defaultValue` and `locked` aren't read."""
    return [
        Range(str(entry.get("stage", "")), entry.get("fromVersion"), entry.get("toVersion"))
        for entry in front_matter.get("stages") or []
    ]


def stage_at(
    ranges: Sequence[Range], release: int, synonyms: Mapping[str, str]
) -> tuple[str | None, Confidence] | None:
    """A gate's (stage, status_confidence) at `release`, from its ranges in that release's own
    reference; None when no range covers it (no row).

    A range covers R when its from-minor <= R <= its to-minor; an open end is open. Stages are
    compared after strip, lower case and `synonyms` (`GA` -> `stable`, ADR-003 D5).
    - Any range with an unparseable bound: (None, low). The release's stage can't be read.
    - The covering ranges give one stage, in STAGES: (that stage, high).
    - One stage outside STAGES: (the first as written, stripped, low), e.g. the typo `True`.
    - 2+ stages (e.g. a change at a patch release): (None, low). One is never picked (D2).
    """
    synonyms = {key.lower(): value for key, value in synonyms.items()}
    written = []  # the covering ranges' stages, stripped
    for r in ranges:
        start, end = minor(r.start), minor(r.end)
        if (r.start is not None and start is None) or (r.end is not None and end is None):
            return None, "low"
        if (start is None or start <= release) and (end is None or release <= end):
            written.append(r.stage.strip())
    if not written:
        return None
    stages = {synonyms.get(stage.lower(), stage.lower()) for stage in written}
    if len(stages) > 1:
        return None, "low"
    (stage,) = stages
    if stage in STAGES:
        return stage, "high"
    return written[0], "low"


def release_ranges(
    conn: psycopg.Connection[TupleRow], cache_dir: Path, release: int
) -> dict[str, list[Range]]:
    """{gate: its ranges} in `release`'s own reference (see the module docstring). A table page
    is re-read from the clone under `cache_dir` at its version's snapshot; a gate file's front
    matter is the stored one."""
    gates: dict[str, list[Range]] = {}
    for version in reference_versions(conn, release):
        is_gate_file = version.canonical_id.startswith("gate:")
        if release <= LAST_TABLE_RELEASE and not is_gate_file:
            repo = cache_dir / version.snapshot_repo
            text = decode(read_file(repo, version.snapshot_sha, version.source_path))
            for gate, rows in table_ranges(text).items():
                gates.setdefault(gate, []).extend(rows)
        elif release > LAST_TABLE_RELEASE and is_gate_file:
            name = str(version.metadata.get("title"))
            gates.setdefault(name, []).extend(file_ranges(version.metadata))
    return gates


def rebuild_lifecycle(
    conn: psycopg.Connection[TupleRow], cache_dir: Path, synonyms: Mapping[str, str]
) -> list[Observation]:
    """Read every stored release's reference, then replace every `observed_lifecycle` row with
    one per gate and release (by release, then gate), in one transaction. Return the rows."""
    rows = []
    for release in list_releases(conn):
        gates = release_ranges(conn, cache_dir, release.minor)
        for gate, ranges in sorted(gates.items()):
            observed = stage_at(ranges, release.minor, synonyms)
            if observed is not None:
                stage, confidence = observed
                rows.append(
                    Observation(
                        gate=gate, release=release.minor, stage=stage, status_confidence=confidence
                    )
                )
    replace_observations(conn, rows)
    return rows


def lifecycle_line(rows: Sequence[Observation]) -> str:
    """The rebuild's one-line report: rows, releases with a row, and rows by confidence."""
    high = sum(row.status_confidence == "high" for row in rows)
    releases = len({row.release for row in rows})
    return (
        f"Observed lifecycle: {len(rows)} rows over {releases} releases "
        f"({high} high, {len(rows) - high} low)."
    )


def main() -> None:
    settings = Settings()
    # autocommit: the rebuild's `conn.transaction()` block is its own committed transaction.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        rows = rebuild_lifecycle(
            conn, settings.corpus_cache_dir.expanduser(), settings.claim_synonyms
        )
    print(lifecycle_line(rows))


if __name__ == "__main__":
    main()
