"""The ingestion report (S05-T8, S05-R3 decisions 7 and 8).

`make ingest` ends with the whole report: its run (new rows, skipped and failed files) and the
database part. `make ingest-report` prints the database part alone, without reading git: counts
per source type and per release, the alias count, the chunk id range, and the fingerprint.

The report is the same, byte for byte, for two databases holding the same values: dates print in
UTC, metadata keys sorted, and every list is sorted. Run times stay out of it.

The reads are in `db/report.py`; everything else here is pure, except `database_report` and
`main`.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.models import Counts, StoredAlias, StoredChunk, StoredDocument, StoredVersion
from orgknow.db.report import (
    chunk_id_range,
    counts_by_release,
    counts_by_source_type,
    stored_aliases,
    stored_chunks,
    stored_documents,
    stored_versions,
)
from orgknow.ingestion.git_reader import Skip
from orgknow.ingestion.manifest import Snapshot
from orgknow.settings import Settings


def _utc(at: datetime | None) -> str | None:
    return None if at is None else at.astimezone(UTC).isoformat()


def fingerprint(
    documents: Iterable[StoredDocument],
    aliases: Iterable[StoredAlias],
    versions: Iterable[StoredVersion],
    chunks: Iterable[StoredChunk],
) -> str:
    """The sha256 hex of every stored value except generated ids (S05-R3 decision 8).

    One compact JSON row per record: ["document", canonical_id, source_type], ["alias",
    canonical_id, alias], ["version", canonical_id, every version column but its ids], ["chunk",
    canonical_id, its version's valid_from_date, ordinal, heading_path, content_hash]. Dates are
    UTC ISO 8601 strings, metadata keys are sorted. The rows are sorted as strings and joined with
    "\\n", so the order of the records doesn't matter. No records: the sha256 of "".
    """
    rows: list[list[Any]] = [["document", d.canonical_id, d.source_type] for d in documents]
    rows += [["alias", a.canonical_id, a.alias] for a in aliases]
    rows += [
        [
            "version",
            v.canonical_id,
            v.content_hash,
            v.source_path,
            v.snapshot_repo,
            v.snapshot_ref,
            v.snapshot_sha,
            v.valid_from_release,
            v.valid_until_release,
            _utc(v.valid_from_date),
            _utc(v.valid_until_date),
            v.claimed_status,
            v.claimed_stage,
            v.metadata,
        ]
        for v in versions
    ]
    rows += [
        [
            "chunk",
            c.canonical_id,
            _utc(c.valid_from_date),
            c.ordinal,
            c.heading_path,
            c.content_hash,
        ]
        for c in chunks
    ]
    lines = sorted(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def snapshot_labels(snapshots: Iterable[Snapshot]) -> str:
    """The snapshots' labels: the releases in order, each run of consecutive ones as one range
    with an en dash (1.20 to 1.22 is "1.20\N{EN DASH}1.22"), then `head`."""
    snapshots = list(snapshots)
    releases = sorted({s.release for s in snapshots if s.release is not None})
    ranges: list[list[int]] = []  # runs of consecutive releases
    for release in releases:
        if ranges and release == ranges[-1][-1] + 1:
            ranges[-1].append(release)
        else:
            ranges.append([release])
    labels = [
        f"1.{run[0]}" if len(run) == 1 else f"1.{run[0]}\N{EN DASH}1.{run[-1]}" for run in ranges
    ]
    return ", ".join(labels + sorted({s.label for s in snapshots if s.release is None}))


def skip_lines(skips: Iterable[Skip]) -> list[str]:
    """One line per (file, reason), sorted, with every snapshot it was skipped at
    (`snapshot_labels`), e.g. for 1.20 to 1.37 and head:
    "keps/sig-release/OWNERS: not a .md/.yaml file (1.20\N{EN DASH}1.37, head)"."""
    at: dict[tuple[str, str], list[Snapshot]] = {}
    for skip in skips:
        at.setdefault((skip.path, skip.reason), []).append(skip.snapshot)
    return [
        f"{path}: {reason} ({snapshot_labels(snapshots)})"
        for (path, reason), snapshots in sorted(at.items())
    ]


def _table(header: Sequence[str], rows: Iterable[Sequence[str | int]]) -> list[str]:
    """Columns two spaces apart, indented by two: the first left-aligned, the others (numbers)
    right-aligned."""
    cells = [list(header), *([str(cell) for cell in row] for row in rows)]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    lines = []
    for row in cells:
        first = row[0].ljust(widths[0])
        rest = [cell.rjust(width) for cell, width in zip(row[1:], widths[1:], strict=True)]
        lines.append("  " + "  ".join([first, *rest]))
    return lines


def database_lines(
    by_type: Sequence[Counts],
    by_release: Sequence[Counts],
    aliases: int,
    chunk_ids: tuple[int, int] | None,
    fingerprint_hex: str,
) -> list[str]:
    """The report's database part, from `counts_by_source_type`, `counts_by_release`, the alias
    count, `chunk_id_range` and `fingerprint`."""
    lines = ["Stored (texts: distinct chunk texts):"]
    lines += _table(
        ["source_type", "documents", "versions", "chunks", "texts"],
        ([c.source_type or "total", c.documents, c.versions, c.chunks, c.texts] for c in by_type),
    )
    lines.append(f"Aliases: {aliases}")
    types = [c.source_type for c in by_type if c.source_type is not None]
    documents = {(c.release, c.source_type): c.documents for c in by_release}
    rows: list[list[str | int]] = []
    for c in by_release:
        if c.source_type is None:  # the release's total row
            row: list[str | int] = [f"1.{c.release}"]
            row += [documents.get((c.release, t), 0) for t in types]
            rows.append([*row, c.versions, c.chunks, c.texts])
    lines.append("Valid at each release (documents per source type; all versions, chunks, texts):")
    lines += _table(["release", *types, "versions", "chunks", "texts"], rows)
    ids = "none" if chunk_ids is None else f"{chunk_ids[0]}\N{EN DASH}{chunk_ids[1]}"
    lines.append(f"Chunk ids: {ids}")
    lines.append(f"Fingerprint: sha256:{fingerprint_hex}")
    return lines


def database_report(conn: psycopg.Connection[TupleRow]) -> list[str]:
    """Read the database and return the report's database part."""
    aliases = stored_aliases(conn)
    hex_digest = fingerprint(
        stored_documents(conn), aliases, stored_versions(conn), stored_chunks(conn)
    )
    return database_lines(
        counts_by_source_type(conn),
        counts_by_release(conn),
        len(aliases),
        chunk_id_range(conn),
        hex_digest,
    )


def main() -> None:
    """`make ingest-report`: print the database part of the ingestion report."""
    settings = Settings()
    with psycopg.connect(settings.database_url) as conn:
        lines = database_report(conn)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
