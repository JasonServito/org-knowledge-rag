"""Ingest a manifest scope: read files at the locked SHAs, derive versions, store them, chunk them.

Run with `make ingest` (INGEST_SCOPE, default s04), after `make seed`. Safe to re-run: each
document's derived history is compared with what's stored (`plan_changes`), and only versions
with no chunks are chunked, so a re-run writes nothing.

1. Check (DB, read-only): the `releases` table must hold every manifest release with the same
   dates, since windows are derived from them. Otherwise stop, before any git read or write,
   and ask for `make seed`. Ingest never writes `releases`; extra rows in it are fine.
2. Read (git): every snapshot of the scope. A git failure stops here, before any write.
3. Derive (pure): per document, normalize and hash each snapshot, then build its versions.
   A document that can't be parsed is reported and left out; the others continue.
4. Store (DB): one transaction per document. A history mismatch is reported, leaves that
   document untouched, and makes the exit code non-zero.
5. Chunk: every stored version with no chunks is re-read from git at its snapshot and chunked
   (`chunker.py`), one transaction per version.
"""

import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_chunks, versions_without_chunks
from orgknow.db.documents import add_alias, create_document, resolve_document
from orgknow.db.models import NewVersion, Release, VersionData
from orgknow.db.releases import list_releases
from orgknow.db.versions import close_version, insert_version, list_versions
from orgknow.ingestion.chunker import chunk_version
from orgknow.ingestion.git_reader import commit_times, read_file, read_files
from orgknow.ingestion.history import (
    HistoryMismatch,
    Observed,
    date_history,
    plan_changes,
    release_history,
)
from orgknow.ingestion.identity import alias_id, docs_canonical_id, kep_canonical_id
from orgknow.ingestion.manifest import Scope, load_normalization, load_releases, load_scope
from orgknow.ingestion.normalize import docs_state, kep_state
from orgknow.settings import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    """One document's derived history, ready to store."""

    canonical_id: str
    source_type: str
    versions: list[VersionData]
    aliases: list[str]


@dataclass
class Summary:
    documents: dict[str, int] = field(default_factory=dict)  # by source type
    new_documents: int = 0
    new_versions: int = 0
    closed_versions: int = 0
    unchanged_documents: int = 0
    new_chunks: int = 0
    skipped: list[str] = field(default_factory=list)  # files or versions, with the reason
    failures: list[str] = field(default_factory=list)  # documents or versions, with the reason


class ReleasesMismatch(Exception):
    """The `releases` table lacks a manifest release or holds other dates for it."""


def release_problems(manifest: Sequence[Release], stored: Sequence[Release]) -> list[str]:
    """Each manifest release the table lacks, or holds with other dates (both compared). Rows
    the manifest doesn't list are not a problem."""
    by_version = {release.version: release for release in stored}
    problems = []
    for release in manifest:
        row = by_version.get(release.version)
        if row is None:
            problems.append(f"{release.version} is missing")
        elif row != release:
            problems.append(
                f"{release.version} differs (table: {row.release_date} to "
                f"{row.end_of_life_date}; manifest: {release.release_date} to "
                f"{release.end_of_life_date})"
            )
    return problems


def collect_docs(
    scope: Scope,
    cache_dir: Path,
    strip: frozenset[str],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """Read the scope's docs pages at every release and derive their versions."""
    snapshots = scope.docs_snapshots
    files, skipped = read_files(cache_dir / scope.docs_repo, scope.docs_paths, snapshots, (".md",))
    summary.skipped += skipped
    documents = []
    for path, contents in sorted(files.items()):
        try:
            states = [None if raw is None else docs_state(path, raw, strip) for raw in contents]
            observed = [Observed(s, state) for s, state in zip(snapshots, states, strict=True)]
            aliases = {alias_id(a) for state in states if state is not None for a in state.aliases}
            documents.append(
                Document(
                    docs_canonical_id(path),
                    "docs_page",
                    release_history(scope.docs_repo, observed, releases),
                    sorted(aliases),
                )
            )
        except ValueError as exc:
            summary.failures.append(f"{path}: {exc}")
    return documents


def collect_keps(
    scope: Scope,
    cache_dir: Path,
    strip: frozenset[str],
    synonyms: Mapping[str, str],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """Read each KEP's README + kep.yaml at every snapshot and derive its versions."""
    repo = cache_dir / scope.kep_repo
    snapshots = scope.kep_snapshots
    documents = []
    for number, directory in scope.keps:
        readme, kep_yaml = f"{directory}README.md", f"{directory}kep.yaml"
        files, skipped = read_files(repo, [readme, kep_yaml], snapshots, (".md", ".yaml"))
        summary.skipped += skipped
        readmes = files.get(readme, [None] * len(snapshots))
        kep_yamls = files.get(kep_yaml, [None] * len(snapshots))
        # Commit times are read only where the files changed since the previous snapshot.
        times: list[tuple[datetime, ...]] = []
        for i, snapshot in enumerate(snapshots):
            previous = (None, None) if i == 0 else (readmes[i - 1], kep_yamls[i - 1])
            since = None if i == 0 else snapshots[i - 1].sha
            changed = (readmes[i], kep_yamls[i]) != previous
            found = commit_times(repo, since, snapshot.sha, [readme, kep_yaml]) if changed else []
            times.append(tuple(found))
        try:
            observed = [
                Observed(snapshot, kep_state(readme, r, k, strip, synonyms), found)
                for snapshot, r, k, found in zip(snapshots, readmes, kep_yamls, times, strict=True)
            ]
            versions = date_history(scope.kep_repo, observed, releases)
            if not versions:
                raise ValueError(f"{directory} is in no snapshot")
            documents.append(Document(kep_canonical_id(number), "kep", versions, []))
        except ValueError as exc:
            summary.failures.append(f"KEP {number}: {exc}")
    return documents


def store_document(
    conn: psycopg.Connection[TupleRow], document: Document, summary: Summary
) -> None:
    """Create the document if it's new, then close/insert versions and add aliases, in one
    transaction. Raises HistoryMismatch or ValueError (rolled back) for the caller to report."""
    with conn.transaction():
        document_id = resolve_document(conn, document.canonical_id)
        is_new = document_id is None
        if document_id is None:
            document_id = create_document(conn, document.canonical_id, document.source_type)
        plan = plan_changes(list_versions(conn, document_id), document.versions)
        # Close first: the new version's open window would overlap the old one (R8).
        if plan.close is not None:
            close_version(
                conn,
                plan.close.version_id,
                plan.close.valid_until_release,
                plan.close.valid_until_date,
            )
        for version in plan.insert:
            insert_version(conn, NewVersion(document_id=document_id, **version.model_dump()))
        for alias in document.aliases:
            owner = resolve_document(conn, alias)
            if owner is None:
                add_alias(conn, document_id, alias)
            elif owner != document_id:
                raise ValueError(f"alias {alias} already points to document {owner}")
    if is_new:
        summary.new_documents += 1
    if plan.close is not None:
        summary.closed_versions += 1
    if plan.close is None and not plan.insert:
        summary.unchanged_documents += 1
    summary.new_versions += len(plan.insert)


def ingest(
    conn: psycopg.Connection[TupleRow],
    scope: Scope,
    cache_dir: Path,
    releases: Sequence[Release],
    strip: Mapping[str, frozenset[str]],
    synonyms: Mapping[str, str],
    max_tokens: int,
) -> Summary:
    """Check the `releases` table, then read, derive and store every document of `scope`, then
    chunk every version with no chunks. Each document, and each version's chunks, commits on its
    own. Raises ReleasesMismatch, before any git read or write, if the table lacks one of
    `releases` or holds other dates for it."""
    problems = release_problems(releases, list_releases(conn))
    if problems:
        raise ReleasesMismatch(
            "run `make seed` first. The releases table doesn't match the manifest: "
            + "; ".join(problems)
        )
    summary = Summary()
    documents = [
        *collect_docs(scope, cache_dir, strip["docs_page"], releases, summary),
        *collect_keps(scope, cache_dir, strip["kep_yaml"], synonyms, releases, summary),
    ]
    for document in documents:
        try:
            store_document(conn, document, summary)
        except (HistoryMismatch, ValueError) as exc:
            summary.failures.append(f"{document.canonical_id}: {exc}")
            continue
        count = summary.documents.get(document.source_type, 0)
        summary.documents[document.source_type] = count + 1
    chunk_versions(conn, cache_dir, max_tokens, summary)
    return summary


def chunk_versions(
    conn: psycopg.Connection[TupleRow], cache_dir: Path, max_tokens: int, summary: Summary
) -> None:
    """Chunk every stored version that has no chunks yet, one transaction per version.

    Each version's raw file is re-read from git at its snapshot. A version with chunks is never
    re-chunked, so a re-run adds none. A git failure stops here, like in step 2.
    """
    for version in versions_without_chunks(conn):
        where = f"{version.canonical_id} (version {version.id})"
        raw = read_file(
            cache_dir / version.snapshot_repo, version.snapshot_sha, version.source_path
        )
        try:
            chunks = chunk_version(
                version.canonical_id, version.source_type, version.metadata, raw, max_tokens
            )
        except ValueError as exc:
            summary.failures.append(f"{where}: {exc}")
            continue
        if not chunks:
            summary.skipped.append(f"{where} {version.source_path}: no text to chunk")
            continue
        with conn.transaction():
            add_chunks(conn, version.id, chunks)
        summary.new_chunks += len(chunks)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    releases = load_releases(settings.corpus_manifest_path)
    strip = load_normalization(settings.corpus_manifest_path)
    scope = load_scope(
        settings.corpus_manifest_path, settings.corpus_lock_path, settings.ingest_scope
    )
    cache_dir = settings.corpus_cache_dir.expanduser()
    # autocommit: each `conn.transaction()` block is its own committed transaction.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        try:
            summary = ingest(
                conn,
                scope,
                cache_dir,
                releases,
                strip,
                settings.claim_synonyms,
                settings.chunk_max_tokens,
            )
        except ReleasesMismatch as exc:
            sys.exit(f"Nothing ingested: {exc}.")  # exit code 1, message on stderr

    for line in summary.skipped:
        log.info("skipped %s", line)
    for line in summary.failures:
        log.error("FAILED %s", line)
    by_type = ", ".join(
        f"{n} {source_type}" for source_type, n in sorted(summary.documents.items())
    )
    print(
        f"Scope {scope.name}: {sum(summary.documents.values())} documents stored ({by_type}).\n"
        f"New documents: {summary.new_documents}. New versions: {summary.new_versions}. "
        f"Closed versions: {summary.closed_versions}. "
        f"Unchanged documents: {summary.unchanged_documents}.\n"
        f"New chunks: {summary.new_chunks}.\n"
        f"Skipped: {len(summary.skipped)} files or versions. "
        f"Failed: {len(summary.failures)} documents or versions."
    )
    if summary.failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
