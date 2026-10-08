"""Ingest a manifest scope: read files at the locked SHAs, derive versions, store them, chunk them.

Run with `make ingest` (INGEST_SCOPE, default full), after `make seed`. Safe to re-run: each
document's derived history is compared with what's stored (`plan_changes`), and only versions
with no chunks are chunked, so a re-run writes nothing.

1. Check (DB, read-only): the `releases` table must hold every manifest release with the same
   dates, since windows are derived from them. Otherwise stop, before any git read or write,
   and ask for `make seed`. Ingest never writes `releases`; extra rows in it are fine.
2. Read (git): every snapshot of the scope, the release-scoped groups first (docs pages,
   website release records, feature gates, with each release's redirect file), then the
   CHANGELOGs at the kubernetes lock head, with that commit's time, then the date-scoped groups
   (KEPs, governance docs), with the merge time of each change, then the blog's first-parent log
   and each post's files by blob id. A git failure stops here, before any write.
3. Derive (pure): link the files of a page, gate or governance doc that moved into one chain
   (`renames.py`; the unmatched adds and deletes are logged per snapshot pair), group a KEP's
   files by its number, then per document normalize and hash each snapshot with its group's
   strip list and build its versions. A CHANGELOG-1.R has one version, `[R, R]`. A blog post's
   versions start at its publication (`blog.py`); posts out of scope are counted. A document
   that can't be parsed, a link between two source types, or two chains with one id is
   reported; the others continue.
4. Store (DB): one transaction per document. A history mismatch or an R3 conflict (an id that
   is another document's alias) is reported, leaves that document untouched, and makes the
   exit code non-zero.
5. Chunk: every stored version with no chunks is re-read from git at its snapshot and chunked
   (`chunker.py`), one transaction per version.
6. Report (`report.py`, S05-T8): this run's counts, each skipped file once with its snapshots,
   each failure (starting with its snapshot's label where it happened at one), then the
   database part that `make ingest-report` prints alone, with the fingerprint.
"""

import logging
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

import psycopg
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_chunks, versions_without_chunks
from orgknow.db.documents import add_alias, create_document, find_document, resolve_document
from orgknow.db.models import NewVersion, Release, VersionData
from orgknow.db.releases import list_releases
from orgknow.db.versions import close_version, insert_version, list_versions
from orgknow.ingestion.blog import (
    Entry,
    Publication,
    commit_label,
    hugo_url,
    out_of_scope,
    post_versions,
    publication,
)
from orgknow.ingestion.chunker import changelog_title, chunk_version, governance_title
from orgknow.ingestion.git_reader import (
    PostCommit,
    Skip,
    commit_time,
    first_present,
    merge_time,
    post_histories,
    read_blob,
    read_file,
    read_files,
    similar_renames,
)
from orgknow.ingestion.history import (
    HistoryMismatch,
    Observed,
    changelog_version,
    date_history,
    plan_changes,
    release_history,
)
from orgknow.ingestion.identity import (
    KEP_FOLDER_FILES,
    alias_id,
    blog_canonical_id,
    changelog_canonical_id,
    docs_canonical_id,
    gate_canonical_id,
    governance_canonical_id,
    kep_file_canonical_id,
)
from orgknow.ingestion.manifest import (
    BlogGroup,
    ChangelogGroup,
    DateGroup,
    ReleaseGroup,
    Scope,
    Snapshot,
    SnapshotError,
    load_normalization,
    load_releases,
    load_scope,
)
from orgknow.ingestion.normalize import (
    FileState,
    content_hash,
    decode,
    docs_state,
    governance_state,
    kep_state,
    single_kep_state,
)
from orgknow.ingestion.renames import (
    REDIRECT_FILES,
    Chains,
    SimilarRenames,
    build_chains,
    date_link_rules,
    gate_link_rules,
    page_url,
    parse_redirects,
    web_link_rules,
)
from orgknow.ingestion.report import database_report, skip_lines, snapshot_labels
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
    skipped: list[Skip] = field(default_factory=list)  # files, at each snapshot skipped
    skipped_versions: list[str] = field(default_factory=list)  # with no text to chunk
    failures: list[str] = field(default_factory=list)  # documents or versions, with the reason


def failure_line(what: str, exc: ValueError) -> str:
    """A failure line, "<what>: <reason>", after the snapshot's label when the failure happened
    at one snapshot (a SnapshotError): "1.24 <what>: <reason>" (S05-T8)."""
    line = f"{what}: {exc}"
    return f"{exc.label} {line}" if isinstance(exc, SnapshotError) else line


def report_missing(missing: Sequence[str], snapshots: Sequence[Snapshot], summary: Summary) -> None:
    """A manifest path absent at every snapshot is a failure: the manifest is wrong (its
    missing-path rule). One absent from some snapshots only is logged by `read_files`."""
    for path in missing:
        summary.failures.append(
            f"{snapshot_labels(snapshots)}: manifest path {path} is absent at every snapshot"
        )


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


def read_redirects(repo: Path, snapshot: Snapshot) -> dict[str, str]:
    """The website's redirect rules at `snapshot`: static/_redirects, else static/_redirects.base.
    No redirect file means no redirect rules."""
    path = first_present(repo, snapshot.sha, REDIRECT_FILES)
    if path is None:
        log.info("no redirect file at %s", snapshot.label)
        return {}
    return parse_redirects(decode(read_file(repo, snapshot.sha, path)))


def file_states(
    group: ReleaseGroup, chain: Sequence[tuple[str, bytes] | None], keys: frozenset[str]
) -> list[FileState | None]:
    """Each snapshot's file in a chain normalized and hashed (`docs_state`), None where absent.
    Raises SnapshotError, with that snapshot's label, if a file can't be parsed."""
    states: list[FileState | None] = []
    for snapshot, link in zip(group.snapshots, chain, strict=True):
        try:
            states.append(None if link is None else docs_state(link[0], link[1], keys))
        except ValueError as exc:
            raise SnapshotError(snapshot.label, str(exc)) from exc
    return states


def document_from_chain(
    group: ReleaseGroup,
    chain: Sequence[tuple[str, bytes] | None],
    strip: Mapping[str, frozenset[str]],
    releases: Sequence[Release],
) -> Document:
    """One document of a release-scoped group from its chain of files: at each of the group's
    snapshots, the (path, raw content) holding the document, or None where it's absent.

    The canonical id is the first file's URL (ADR-002 D4). The chain's later URLs and the
    front-matter `aliases` are its aliases, except its own id. Hashes use the strip list of the
    group's source type (ADR-002 D2). Raises SnapshotError if a file can't be parsed.
    """
    states = file_states(group, chain, strip[group.source_type])
    observed = [Observed(s, state) for s, state in zip(group.snapshots, states, strict=True)]
    paths = [link[0] for link in chain if link is not None]
    canonical_id = docs_canonical_id(paths[0])
    urls = {docs_canonical_id(path) for path in paths}
    declared = {alias_id(a) for state in states if state is not None for a in state.aliases}
    return Document(
        canonical_id,
        group.source_type,
        release_history(group.repo, observed, releases),
        sorted((urls | declared) - {canonical_id}),
    )


def gate_document_from_chain(
    group: ReleaseGroup,
    chain: Sequence[tuple[str, bytes] | None],
    strip: Mapping[str, frozenset[str]],
    releases: Sequence[Release],
) -> Document:
    """One feature gate from its chain of files, as `document_from_chain` for a page.

    The canonical id is `gate:` + the first file's front-matter `title`, as written (ADR-002
    D4); each later title is an alias. `former_titles` never become aliases: the gate a former
    title names can keep its own file (`PodHasNetworkCondition`). Raises SnapshotError if a
    file can't be parsed or has no title.
    """
    states = file_states(group, chain, strip[group.source_type])
    observed = [Observed(s, state) for s, state in zip(group.snapshots, states, strict=True)]
    ids = []
    for snapshot, state in zip(group.snapshots, states, strict=True):
        if state is not None:
            try:
                ids.append(gate_canonical_id(state.metadata.get("title")))
            except ValueError as exc:
                raise SnapshotError(snapshot.label, str(exc)) from exc
    return Document(
        ids[0],
        group.source_type,
        release_history(group.repo, observed, releases),
        sorted(set(ids) - {ids[0]}),
    )


def is_gate_file(group: ReleaseGroup, path: str) -> bool:
    """Whether a file is one feature gate, not a page. The feature-gates pages are the files the
    manifest names one by one (up to 1.28) and each folder's index.md (a page bundle, from 1.29).
    Every other file in the manifest's folders is one gate, which Hugo doesn't render."""
    return (
        group.source_type == "feature_gate_reference"
        and path not in group.paths
        and PurePosixPath(path).name not in ("index.md", "_index.md")
    )


def without_duplicate_ids(documents: Sequence[Document], summary: Summary) -> list[Document]:
    """The documents whose canonical id no other chain has. Two chains with one id (say, two gate
    files with one title) are an error, never a silent merge: each is reported, none stored."""
    count = Counter(document.canonical_id for document in documents)
    for canonical_id, n in sorted(count.items()):
        if n > 1:
            first_files = ", ".join(
                d.versions[0].source_path for d in documents if d.canonical_id == canonical_id
            )
            summary.failures.append(
                f"{canonical_id}: {n} chains have this id, so none is stored "
                f"(first files: {first_files})"
            )
    return [document for document in documents if count[document.canonical_id] == 1]


def collect_release_scoped(
    scope: Scope,
    cache_dir: Path,
    strip: Mapping[str, frozenset[str]],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """Read the release-scoped groups' files at every release, link the files of a moved page or
    gate into one chain (`renames.py`), and derive one document per chain.

    Groups read from one repo at the same snapshots are linked together, so a link between two
    source types is seen, and refused.
    """
    pools: dict[tuple[str, tuple[Snapshot, ...]], list[ReleaseGroup]] = {}
    for group in scope.release_groups:
        pools.setdefault((group.repo, group.snapshots), []).append(group)
    documents = []
    for (repo, snapshots), groups in pools.items():
        documents += _collect_pool(cache_dir / repo, snapshots, groups, strip, releases, summary)
    return documents


def _collect_pool(
    repo: Path,
    snapshots: Sequence[Snapshot],
    groups: Sequence[ReleaseGroup],
    strip: Mapping[str, frozenset[str]],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """The documents of release groups read from one repo at the same snapshots.

    Pages and gate files are chained apart, each kind with its own link rules and ids: a gate
    file has no URL, and no rule links a gate to a page (the 316 gate files split out of the
    feature-gates tables at 1.29 are new documents). The pages of every group are chained
    together, so a link between two of their source types is seen, and refused.
    """
    pages: list[dict[str, bytes]] = [{} for _ in snapshots]  # path -> raw content
    gates: list[dict[str, bytes]] = [{} for _ in snapshots]
    group_of: dict[str, ReleaseGroup] = {}
    for group in groups:
        files, skipped, missing = read_files(repo, group.paths, snapshots, (".md",))
        summary.skipped += skipped
        report_missing(missing, snapshots, summary)
        for path, contents in files.items():
            group_of[path] = group
            listings = gates if is_gate_file(group, path) else pages
            for listing, raw in zip(listings, contents, strict=True):
                if raw is not None:
                    listing[path] = raw
    # A pair's redirect file is the one at R+1, so the first snapshot's is never read.
    redirects: list[dict[str, str]] = [{}]
    redirects += [read_redirects(repo, snapshot) for snapshot in snapshots[1:]]
    source_types = {path: group.source_type for path, group in group_of.items()}
    similar = _git_similarity(repo, snapshots)
    documents = []
    for listings, rules, derive in (
        (pages, web_link_rules(redirects), document_from_chain),
        (gates, gate_link_rules(), gate_document_from_chain),
    ):
        chains = build_chains(listings, rules, similar, source_types)
        _log_renames(chains, snapshots, redirects)
        for link in chains.crossings:
            summary.failures.append(
                f"{_pair(snapshots, link.after)}: the {link.rule} link {link.gone} -> "
                f"{link.new} crosses source types ({source_types[link.gone]} -> "
                f"{source_types[link.new]})"
            )
        for paths in chains.paths:
            chain = [
                None if path is None else (path, listing[path])
                for path, listing in zip(paths, listings, strict=True)
            ]
            first = next(path for path in paths if path is not None)
            try:
                documents.append(derive(group_of[first], chain, strip, releases))
            except ValueError as exc:
                summary.failures.append(failure_line(first, exc))
    return without_duplicate_ids(documents, summary)


def _git_similarity(repo: Path, snapshots: Sequence[Snapshot]) -> SimilarRenames:
    """git similarity between the snapshot before position `after` and the one at it."""

    def similar(after: int, paths: Sequence[str]) -> list[tuple[str, str]]:
        return similar_renames(repo, snapshots[after - 1].sha, snapshots[after].sha, paths)

    return similar


def _pair(snapshots: Sequence[Snapshot], after: int) -> str:
    return f"{snapshots[after - 1].label} -> {snapshots[after].label}"


def _log_renames(
    chains: Chains, snapshots: Sequence[Snapshot], redirects: Sequence[Mapping[str, str]] = ()
) -> None:
    """Log each snapshot pair's links, conflicts, and unmatched deletes (with the redirect
    target, if any: web pages only) and adds, in snapshot order."""
    lines: list[tuple[int, int, str]] = []  # (position of R+1, log level, message)
    for link in chains.links:
        lines.append((link.after, logging.INFO, f"linked {link.gone} -> {link.new} ({link.rule})"))
    for link in chains.conflicts:
        message = f"conflict, not linked: {link.gone} -> {link.new} ({link.rule})"
        lines.append((link.after, logging.WARNING, message))
    for after, path in chains.deleted:
        target = redirects[after].get(page_url(path)) if redirects else None
        redirect = f" (redirect -> {target})" if target else ""
        lines.append((after, logging.INFO, f"deleted {path}{redirect}"))
    for after, path in chains.added:
        lines.append((after, logging.INFO, f"added {path}"))
    for after, level, message in sorted(lines, key=lambda line: line[0]):
        log.log(level, "%s: %s", _pair(snapshots, after), message)


def changelog_document(
    group: ChangelogGroup, release: int, path: str, raw: bytes, at: datetime
) -> Document:
    """CHANGELOG-1.R from its file at the group's snapshot: `changelog:1.R`, with one version
    `[R, R]` from `at`, the snapshot commit's time (S05-R2 decision 6), and no aliases.

    It has no front matter: the whole file is hashed with no strip list, the TOC and download
    tables included, though they make no chunk. Its metadata holds only its title,
    `CHANGELOG-1.R` (decision 4). Raises ValueError if the file can't be decoded.
    """
    state = FileState(
        content_hash=content_hash({}, decode(raw), frozenset()),
        source_path=path,
        metadata={"title": changelog_title(release)},
    )
    version = changelog_version(group.repo, group.snapshot, state, release, at)
    return Document(changelog_canonical_id(release), group.source_type, [version], [])


def collect_changelogs(group: ChangelogGroup, cache_dir: Path, summary: Summary) -> list[Document]:
    """Read each CHANGELOG-1.R.md at the group's snapshot (the kubernetes lock head) and derive one
    document per release, each version dated by the snapshot commit's time. Only the files the
    group lists are read (CHANGELOG-1.38.md is out of range). A listed file absent there, or not
    valid UTF-8, is reported."""
    repo = cache_dir / group.repo
    at = commit_time(repo, group.snapshot.sha)
    paths = [path for _, path in group.files]
    # A listed file absent there is reported below, with the others' failures.
    files, skipped, _ = read_files(repo, paths, [group.snapshot], (".md",))
    summary.skipped += skipped
    label = group.snapshot.label
    documents = []
    for release, path in group.files:
        raw = files.get(path, [None])[0]
        if raw is None:
            summary.failures.append(f"{label} {path}: absent ({group.snapshot.sha})")
            continue
        try:
            documents.append(changelog_document(group, release, path, raw, at))
        except ValueError as exc:
            summary.failures.append(f"{label} {path}: {exc}")
    return documents


def _merge_times(
    repo: Path, snapshots: Sequence[Snapshot], chain: Sequence[Mapping[str, bytes]]
) -> list[datetime | None]:
    """For a date-scoped document's files at each snapshot ({path: raw content}), the merge time
    of the last change to them since the previous snapshot (the whole history for the first),
    read only where its files changed; None elsewhere. The paths are its files at both
    snapshots, so a move or a KEP folder rename is seen (S05-R2 sitting)."""
    times: list[datetime | None] = []
    for i, (snapshot, files) in enumerate(zip(snapshots, chain, strict=True)):
        before = chain[i - 1] if i > 0 else {}
        if files == before:
            times.append(None)
            continue
        since = snapshots[i - 1].sha if i > 0 else None
        times.append(merge_time(repo, since, snapshot.sha, sorted(before.keys() | files.keys())))
    return times


def is_other_kep_folder_file(path: str) -> bool:
    """Whether a file sits in a KEP folder (`keps/<sig>/<folder>/...`) but is neither its
    README.md nor its kep.yaml, e.g. images/authorizer-chain-computation.md. Such files are
    ignored: never read, never reported."""
    parts = path.split("/")
    return len(parts) > 4 or (len(parts) == 4 and parts[3] not in KEP_FOLDER_FILES)


def kep_chains(
    files: Mapping[str, Sequence[bytes | None]], snapshots: Sequence[Snapshot]
) -> tuple[dict[str, list[dict[str, bytes]]], list[Skip]]:
    """Group the files read under the KEP paths into one chain per KEP id: its files at each
    snapshot ({path: raw content}, empty where it has none). A KEP folder whose name changes
    keeps its chain (the number is the id). A file that is no KEP (sig-network's README.md
    index) is skipped at each snapshot holding it."""
    chains: dict[str, list[dict[str, bytes]]] = {}
    skipped = []
    for path, contents in sorted(files.items()):
        try:
            canonical_id = kep_file_canonical_id(path)
        except ValueError as exc:
            skipped += [
                Skip(snapshot, path, str(exc))
                for snapshot, raw in zip(snapshots, contents, strict=True)
                if raw is not None
            ]
            continue
        chain = chains.setdefault(canonical_id, [{} for _ in snapshots])
        for files_at, raw in zip(chain, contents, strict=True):
            if raw is not None:
                files_at[path] = raw
    return chains, skipped


def kep_files_state(
    files: Mapping[str, bytes], strip: frozenset[str], synonyms: Mapping[str, str]
) -> FileState | None:
    """One KEP at one snapshot, from its files there; None if it has none. An old single-file
    KEP (a file directly in `keps/<sig>/`) is hashed alone; a folder's README.md and kep.yaml
    are hashed together. Raises ValueError if the KEP's number has two folders at once."""
    if not files:
        return None
    folders = sorted({path.rsplit("/", 1)[0] for path in files})
    if len(folders) > 1:
        raise ValueError(f"{len(folders)} folders at one snapshot: {', '.join(folders)}")
    folder = folders[0]
    if folder.count("/") == 1:  # keps/<sig>: an old single-file KEP, alone under its id
        ((path, raw),) = files.items()
        return single_kep_state(path, raw, strip, synonyms)
    readme, kep_yaml = (f"{folder}/{name}" for name in KEP_FOLDER_FILES)
    return kep_state(readme, files.get(readme), files.get(kep_yaml), strip, synonyms)


def kep_document(
    group: DateGroup,
    canonical_id: str,
    chain: Sequence[Mapping[str, bytes]],
    changed_at: Sequence[datetime | None],
    strip: frozenset[str],
    synonyms: Mapping[str, str],
    releases: Sequence[Release],
) -> Document:
    """One KEP from its files at each of the group's snapshots and the merge time of each
    change (`_merge_times`). A KEP has no aliases. Raises SnapshotError if a snapshot's files
    can't be parsed or their dates can't make valid windows."""
    states = []
    for snapshot, files in zip(group.snapshots, chain, strict=True):
        try:
            states.append(kep_files_state(files, strip, synonyms))
        except ValueError as exc:
            raise SnapshotError(snapshot.label, str(exc)) from exc
    observed = [
        Observed(snapshot, state, at)
        for snapshot, state, at in zip(group.snapshots, states, changed_at, strict=True)
    ]
    return Document(
        canonical_id, group.source_type, date_history(group.repo, observed, releases), []
    )


def collect_keps(
    group: DateGroup,
    cache_dir: Path,
    strip: frozenset[str],
    synonyms: Mapping[str, str],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """Read every KEP under the group's paths at each snapshot (a folder's README.md and kep.yaml,
    or an old single-file KEP), group its files by KEP id, and derive its versions, each dated
    by its merge time."""
    repo = cache_dir / group.repo
    files, skipped, missing = read_files(
        repo, group.paths, group.snapshots, (".md", ".yaml"), ignore=is_other_kep_folder_file
    )
    report_missing(missing, group.snapshots, summary)
    chains, not_keps = kep_chains(files, group.snapshots)
    summary.skipped += skipped + not_keps
    documents = []
    for canonical_id, chain in chains.items():
        try:
            changed_at = _merge_times(repo, group.snapshots, chain)
            documents.append(
                kep_document(group, canonical_id, chain, changed_at, strip, synonyms, releases)
            )
        except ValueError as exc:
            summary.failures.append(failure_line(canonical_id, exc))
    return documents


def governance_document(
    group: DateGroup,
    chain: Sequence[tuple[str, bytes] | None],
    changed_at: Sequence[datetime | None],
    releases: Sequence[Release],
) -> Document:
    """One governance doc from its chain of files (at each of the group's snapshots, its (path,
    raw content), or None where it's absent) and the merge time of each change.

    The canonical id is `<repo>:<first path>`; each later path is an alias (ADR-002 D4, S05-R2
    decision 2). Its title is its first `# ` heading, else its path (decision 4). Raises
    SnapshotError if a file can't be decoded or the dates can't make valid windows.
    """
    states: list[FileState | None] = []
    for snapshot, link in zip(group.snapshots, chain, strict=True):
        if link is None:
            states.append(None)
            continue
        try:
            path, text = link[0], decode(link[1])
        except ValueError as exc:
            raise SnapshotError(snapshot.label, str(exc)) from exc
        states.append(governance_state(path, text, governance_title(text, path)))
    observed = [
        Observed(snapshot, state, at)
        for snapshot, state, at in zip(group.snapshots, states, changed_at, strict=True)
    ]
    ids = [governance_canonical_id(group.repo, link[0]) for link in chain if link is not None]
    return Document(
        ids[0],
        group.source_type,
        date_history(group.repo, observed, releases),
        sorted(set(ids) - {ids[0]}),
    )


def collect_governance(
    group: DateGroup, cache_dir: Path, releases: Sequence[Release], summary: Summary
) -> list[Document]:
    """Read the group's governance docs at each snapshot, link a moved file into one chain (same
    path, then git similarity, `date_link_rules`), and derive one document per chain, each
    version dated by its merge time. Two chains with one id are an error, never a merge."""
    repo = cache_dir / group.repo
    files, skipped, missing = read_files(repo, group.paths, group.snapshots, (".md",))
    summary.skipped += skipped
    report_missing(missing, group.snapshots, summary)
    listings: list[dict[str, bytes]] = [{} for _ in group.snapshots]  # path -> raw content
    for path, contents in files.items():
        for listing, raw in zip(listings, contents, strict=True):
            if raw is not None:
                listing[path] = raw
    similar = _git_similarity(repo, group.snapshots)
    chains = build_chains(
        listings, date_link_rules(), similar, {path: group.source_type for path in files}
    )
    _log_renames(chains, group.snapshots)
    documents = []
    for paths in chains.paths:
        chain = [
            None if path is None else (path, listing[path])
            for path, listing in zip(paths, listings, strict=True)
        ]
        files_at = [{} if link is None else {link[0]: link[1]} for link in chain]
        try:
            changed_at = _merge_times(repo, group.snapshots, files_at)
            documents.append(governance_document(group, chain, changed_at, releases))
        except ValueError as exc:
            first = next(path for path in paths if path is not None)
            summary.failures.append(failure_line(f"{group.repo}:{first}", exc))
    return without_duplicate_ids(documents, summary)


def blog_document(
    group: BlogGroup,
    entries: Sequence[Entry],
    published: Publication,
    releases: Sequence[Release],
) -> Document:
    """One blog post from its history and its publication (ADR-002 D3, D4).

    The canonical id is the URL at publication. The URL of each later stored version that
    differs, and the front-matter `aliases` of the stored versions, are its aliases, never the
    id itself. Raises SnapshotError, labelled with the commit's short SHA, if the version live at
    publication has no URL (no page date) or the dates can't make valid windows.
    """
    versions = post_versions(group.repo, group.ref, entries, published, releases)
    urls = [hugo_url(v.metadata, v.source_path, group.permalink) for v in versions]
    if urls[0] is None:
        raise SnapshotError(
            commit_label(entries[published.entry].sha),
            "no URL at publication: no page date to fill the permalink",
        )
    canonical_id = blog_canonical_id(urls[0])
    aliases = {blog_canonical_id(url) for url in urls[1:] if url is not None}
    for version in versions:
        front_matter = {str(key).lower(): value for key, value in version.metadata.items()}
        aliases |= {alias_id(alias) for alias in front_matter.get("aliases") or []}
    return Document(canonical_id, group.source_type, versions, sorted(aliases - {canonical_id}))


def post_entries(
    history: Sequence[PostCommit], blobs: Mapping[str, bytes], strip: frozenset[str]
) -> list[Entry]:
    """A post's history with its file at each commit normalized and hashed (ADR-002 D2; `strip`
    is the blog_post list). Raises SnapshotError, labelled with the commit's short SHA, if its
    front matter can't be parsed."""
    entries = []
    for commit in history:
        state = None
        if commit.blob is not None:
            try:
                state = docs_state(commit.path, blobs[commit.blob], strip)
            except ValueError as exc:
                raise SnapshotError(commit_label(commit.sha), f"{commit.path}: {exc}") from exc
        entries.append(Entry(commit.committed, commit.sha, commit.path, state))
    return entries


def collect_blog(
    group: BlogGroup,
    cache_dir: Path,
    strip: frozenset[str],
    releases: Sequence[Release],
    summary: Summary,
) -> list[Document]:
    """Read the blog's history (one first-parent log up to the lock head, following renames),
    normalize and hash every post's file at each commit (`strip`: the blog_post list), and
    derive one document per post in scope: ever published, with a page date at publication on
    or after `group.since`. Posts out of scope are counted in the log, not listed: never
    published, dated before `since`, or with no date. A post whose front matter can't be parsed
    is reported with the commit's short SHA and the reason."""
    repo = cache_dir / group.repo
    histories = post_histories(repo, group.head, group.paths)
    blobs: dict[str, bytes] = {}  # by blob id: each file content is read once
    for history in histories:
        for commit in history:
            if commit.blob is not None and commit.blob not in blobs:
                blobs[commit.blob] = read_blob(repo, commit.blob)
    documents = []
    never_published = 0
    out_of_scope_by = Counter[str]()  # "dated before", "no date"
    for history in histories:
        try:
            entries = post_entries(history, blobs, strip)
        except SnapshotError as exc:
            summary.failures.append(f"{exc.label} {exc}")  # the reason starts with the path
            continue
        published = publication(entries)
        if published is None:
            never_published += 1
        elif reason := out_of_scope(entries[published.entry], group.since):
            out_of_scope_by[reason] += 1
        else:
            try:
                documents.append(blog_document(group, entries, published, releases))
            except ValueError as exc:
                summary.failures.append(failure_line(history[-1].path, exc))
    log.info(
        "blog: %d posts; %d in scope; %d never published; %d dated before %s; %d with no date",
        len(histories),
        len(documents),
        never_published,
        out_of_scope_by["dated before"],
        f"{group.since:%Y-%m-%d}",
        out_of_scope_by["no date"],
    )
    return without_duplicate_ids(documents, summary)


def store_document(
    conn: psycopg.Connection[TupleRow], document: Document, summary: Summary
) -> None:
    """Create the document if it's new, then close/insert versions and add aliases, in one
    transaction. Raises HistoryMismatch or ValueError (rolled back) for the caller to report.

    The document is looked up by its canonical_id only. An id that is another document's alias
    reaches `create_document`, which raises the R3 error naming the alias.
    """
    with conn.transaction():
        document_id = find_document(conn, document.canonical_id)
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
    documents = collect_release_scoped(scope, cache_dir, strip, releases, summary)
    if scope.changelogs is not None:
        documents += collect_changelogs(scope.changelogs, cache_dir, summary)
    for group in scope.date_groups:
        if group.source_type == "kep":
            documents += collect_keps(
                group, cache_dir, strip["kep_yaml"], synonyms, releases, summary
            )
        else:
            documents += collect_governance(group, cache_dir, releases, summary)
    if scope.blog is not None:
        documents += collect_blog(scope.blog, cache_dir, strip["blog_post"], releases, summary)
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
            summary.skipped_versions.append(f"{where} {version.source_path}: no text to chunk")
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
        database = database_report(conn)

    # The report (S05-T8): every list sorted, so two ingests of the same data print the same.
    skipped = skip_lines(summary.skipped) + sorted(summary.skipped_versions)
    failures = sorted(summary.failures)
    by_type = ", ".join(
        f"{n} {source_type}" for source_type, n in sorted(summary.documents.items())
    )
    lines = [
        f"Scope {scope.name}: {sum(summary.documents.values())} documents stored ({by_type}).",
        f"New documents: {summary.new_documents}. New versions: {summary.new_versions}. "
        f"Closed versions: {summary.closed_versions}. "
        f"Unchanged documents: {summary.unchanged_documents}.",
        f"New chunks: {summary.new_chunks}.",
        f"Skipped: {len(skipped)} files or versions.",
        *(f"  {line}" for line in skipped),
        f"Failed: {len(failures)} documents or versions.",
        *(f"  {line}" for line in failures),
        *database,
    ]
    print("\n".join(lines))
    if summary.failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
