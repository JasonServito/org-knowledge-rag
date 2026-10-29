"""S02-T3 spike: per-release files and versions after ADR-002 normalization (T3a), then
tokens, chunks, embedding cost and vector storage (T3b).

Run: uv run python spikes/measure.py [--dry-run]

Lists every in-scope file at every snapshot in config/corpus_manifest.lock.yaml, batch-downloads
the file contents into the CORPUS_CACHE_DIR clones, and prints markdown tables for
docs/research/corpus-spike-report.md. --dry-run prints the blob counts and stops before downloading.

Throwaway spike code (S02; see docs/research/corpus-spike-report.md): never imported by src/.
Normalization, hashing and chunking are rewritten properly in S04.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from fetch import LOCK, MANIFEST, cache_dir_or_exit, git

FETCH_BATCH = 1000  # blob ids per fetch request

# Estimation rules agreed at the T3 plan review (slice doc, T3 notes). The real chunker is S04.
CHARS_PER_TOKEN = 4  # heuristic; likely underestimates code and YAML, which tokenize denser
CHUNK_SIZES = (256, 512, 1024)  # max tokens per chunk: 512 is the default, the others sensitivity
DEFAULT_CHUNK = 512
HEADER_TOKENS = 40  # the metadata header embedded with every chunk
SMALL_SECTION = 64  # sections under this many tokens: a chunk-count inflation signal for S04
# Standard rates, docs.voyageai.com/docs/pricing (updated 2026-09-29, read 2026-09-30).
PRICE_PER_M_TOKENS = {"voyage-4-lite": 0.02, "voyage-4": 0.06, "voyage-4-large": 0.12}
# voyage-4 family: 1024 is the default, docs.voyageai.com/docs/embeddings (updated 2026-08-10).
DIMENSIONS = (1024, 512, 256)

FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
LINK_TARGET = re.compile(r"\]\([^)]*\)")  # [text](url) -> [text]
LINK_DEFINITION = re.compile(r"^(\s*\[[^\]]+\]:)[ \t]*\S.*$", re.M)  # [id]: url -> [id]:
HEADING = re.compile(r"^#{1,6}\s")
FENCE = re.compile(r"^\s*(```|~~~)")

Seq = list[tuple[int, str | None]]  # (row, blob id, or None once the file is gone), oldest first


# --- Normalization and hashing (ADR-002 D2) -------------------------------------------------


def bad_strip_keys(normalization: dict[str, Any]) -> list[str]:
    """Strip-list keys that are on never_strip (identity, time and lifecycle keys)."""
    never = {key.lower() for key in normalization["never_strip"]}
    strip_lists = normalization["strip_front_matter"].values()
    return sorted({key for keys in strip_lists for key in keys if key.lower() in never})


def load_mapping(text: str) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def split_front_matter(text: str) -> tuple[dict[str, Any] | None, str]:
    """(front matter, body). With no parseable YAML front matter: (None, whole text).
    Tolerates a byte-order mark, CRLF line endings and blank lines before the opening ---."""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").lstrip("\n")
    match = FRONT_MATTER.match(text)
    meta = load_mapping(match.group(1)) if match else None
    if match is None or meta is None:
        return None, text
    return meta, text[match.end() :]


def clean_text(text: str) -> str:
    """Drop link targets and collapse whitespace, so link and spacing churn isn't a new version."""
    text = LINK_DEFINITION.sub(r"\1", LINK_TARGET.sub("]", text))
    return " ".join(text.split())


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def content_hash(meta: dict[str, Any] | None, body: str, strip: frozenset[str]) -> str:
    """Hash of the kept front-matter keys (sorted; `strip` is lowercase) plus the cleaned body."""
    kept = {str(k): v for k, v in (meta or {}).items() if str(k).lower() not in strip}
    return sha256_hex(json.dumps(kept, sort_keys=True, default=str) + "\n" + clean_text(body))


# --- Token and chunk estimates (T3b) --------------------------------------------------------


def split_sections(body: str) -> list[str]:
    """Split at markdown headings, ignoring '#' lines inside fenced code blocks."""
    sections: list[list[str]] = [[]]
    in_fence = False
    for line in body.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        elif HEADING.match(line) and not in_fence and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    return ["\n".join(lines) for lines in sections if "".join(lines).strip()]


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate_chunks(section_tokens: Iterable[int], size: int) -> int:
    """A section of t tokens becomes ceil(t / size) chunks; a chunk never spans two sections."""
    return sum(math.ceil(tokens / size) for tokens in section_tokens)


def embed_totals(section_tokens: list[int], size: int) -> tuple[int, int]:
    """(chunks, embedded tokens), where every chunk also embeds a HEADER_TOKENS header."""
    chunks = estimate_chunks(section_tokens, size)
    return chunks, sum(section_tokens) + chunks * HEADER_TOKENS


@dataclass(frozen=True)
class Version:
    hash: str
    meta: dict[str, Any] | None
    sections: tuple[tuple[str, int], ...]  # (hash of the cleaned section, estimated tokens)


def analyse(text: str, strip: frozenset[str], is_yaml: bool) -> Version:
    if is_yaml:  # kep.yaml and PRR files: metadata, not embedded (ADR-003 D1)
        meta = load_mapping(text)
        return Version(content_hash(meta, "" if meta is not None else text, strip), meta, ())
    meta, body = split_front_matter(text)  # tokens count the body only, not the front matter
    sections = tuple((sha256_hex(clean_text(s)), estimate_tokens(s)) for s in split_sections(body))
    return Version(content_hash(meta, body, strip), meta, sections)


# --- Versions over time --------------------------------------------------------------------


def sequences(listings: list[tuple[int, dict[str, str]]]) -> dict[str, Seq]:
    """Per-snapshot listings {path: blob} -> per-path sequences, with None when a file is gone."""
    seqs: dict[str, Seq] = {}
    for row, files in listings:
        for path, seq in seqs.items():
            if path not in files and seq[-1][1] is not None:
                seq.append((row, None))
        for path, oid in files.items():
            seqs.setdefault(path, []).append((row, oid))
    return seqs


def new_versions(seq: Seq, keys: dict[str, str] | None = None) -> list[tuple[int, str]]:
    """Entries whose key differs from the previous version's. `keys` maps blob -> normalized
    hash; without it, raw blob ids are compared (no normalization)."""
    found, previous = [], None
    for row, oid in seq:
        key = None if oid is None else (keys[oid] if keys is not None else oid)
        if key is not None and key != previous:
            found.append((row, oid))
            previous = key
    return found


def present_rows(seq: Seq, n_rows: int) -> list[int]:
    """Rows at whose end the file exists; the last state carries forward."""
    rows, state, i = [], None, 0
    for row in range(n_rows):
        while i < len(seq) and seq[i][0] <= row:
            state = seq[i][1]
            i += 1
        if state is not None:
            rows.append(row)
    return rows


def release_row(committed: datetime, release_dates: list[date]) -> int:
    """Row of the first release whose cutoff (release date, 23:59:59Z) is at or after the
    commit: the lock's rule, so a commit lands in the first snapshot that contains it.
    len(release_dates) is the head row."""
    for row, day in enumerate(release_dates):
        if committed <= datetime.combine(day, time(23, 59, 59), UTC):
            return row
    return len(release_dates)


# --- Git: list, download, read -------------------------------------------------------------


@dataclass
class Doc:
    source: str  # ADR-003 D1 source_type
    repo: str
    path: str
    seq: Seq

    @property
    def is_yaml(self) -> bool:
        return self.path.endswith(".yaml")

    @property
    def strip_kind(self) -> str:  # key into the manifest's normalization.strip_front_matter
        if not self.is_yaml:
            return self.source
        return "prr_yaml" if "/prod-readiness/" in self.path else "kep_yaml"


def ls_tree(repo: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """{path: blob id} under `paths` at `sha`, from local trees (no file contents needed)."""
    files = {}
    for entry in filter(None, git("ls-tree", "-r", "-z", sha, "--", *paths, repo=repo).split("\0")):
        info, path = entry.split("\t", 1)
        _, kind, oid = info.split()
        if kind == "blob":
            files[path] = oid
    return files


def snapshot_docs(
    source: str,
    repo: str,
    cache: Path,
    snapshots: list[tuple[int, str, list[str]]],
    exts: tuple[str, ...] = (".md",),
) -> list[Doc]:
    listings = []
    for row, sha, paths in snapshots:
        files = ls_tree(cache / repo, sha, paths)
        listings.append((row, {p: oid for p, oid in files.items() if p.endswith(exts)}))
    return [Doc(source, repo, path, seq) for path, seq in sequences(listings).items()]


def blog_log(
    cache: Path, head: str, paths: list[str], follow_renames: bool
) -> dict[str, list[tuple[datetime, str, str | None]]]:
    """Per post, keyed by its latest path: (commit time, path then, blob or None once deleted),
    one entry per first-parent commit on website main that touches it, oldest first (ADR-002 D3).
    follow_renames keeps a moved post one history; git needs the contents to score renames."""
    log_args = ["--first-parent", "--diff-merges=first-parent", "--raw", "--no-abbrev", "-z"]
    log_args += ["--find-renames" if follow_renames else "--no-renames", "--format=@%ct", head]
    posts = [f"{p}*.md" for p in paths]  # posts only, so rename scoring never needs an image
    log = git("log", *log_args, "--", *posts, repo=cache / "website")
    commits: list[tuple[int, list[tuple[str | None, str, str | None]]]] = []
    # -z fields: "@<time>", then per file ":<modes> <old> <new> <status>", [old path,] path.
    tokens = (t.lstrip("\n") for t in log.split("\0"))
    for token in tokens:
        if token.startswith("@"):
            commits.append((int(token[1:]), []))
        elif token.startswith(":"):
            new, status = token.split()[3:5]
            old = next(tokens) if status.startswith("R") else None
            commits[-1][1].append((old, next(tokens), None if new.strip("0") == "" else new))
    history: dict[str, list[tuple[datetime, str, str | None]]] = defaultdict(list)
    for timestamp, changes in reversed(commits):  # git log lists newest first
        committed = datetime.fromtimestamp(timestamp, UTC)
        for old, path, oid in changes:
            if old is not None:  # a moved post continues as the same document
                history[path] = history.pop(old, [])
            history[path].append((committed, path, oid))
    return history


def blog_docs(
    cache: Path, head: str, paths: list[str], release_dates: list[date], follow_renames: bool
) -> list[Doc]:
    """One entry per first-parent commit on website main that touches a post, in release rows."""
    docs = []
    for path, entries in blog_log(cache, head, paths, follow_renames).items():
        seq: Seq = [(release_row(committed, release_dates), oid) for committed, _, oid in entries]
        docs.append(Doc("blog_post", "website", path, seq))
    return docs


def collect(
    manifest: dict[str, Any], lock: dict[str, Any], cache: Path, follow_renames: bool = False
) -> list[Doc]:
    src = manifest["sources"]
    releases = manifest["releases"]["list"]
    versions = [r["version"] for r in releases]
    website = [lock["website_releases"][v]["sha"] for v in versions]

    def release_snaps(paths: list[str]) -> list[tuple[int, str, list[str]]]:
        return [(row, sha, paths) for row, sha in enumerate(website)]

    def date_snaps(repo: str, paths: list[str]) -> list[tuple[int, str, list[str]]]:
        shas = [lock["release_date_snapshots"][repo][v]["sha"] for v in versions]
        return [(row, sha, paths) for row, sha in enumerate([*shas, lock["repos"][repo]["head"]])]

    rr_website, rr_kubernetes = src["release_record"]
    k8s_head = lock["repos"]["kubernetes"]["head"]
    changelogs = [
        (row, k8s_head, [p.format(version=v) for p in rr_kubernetes["paths"]])
        for row, v in enumerate(versions)
    ]
    docs_paths = [p for paths in src["docs_page"]["sigs"].values() for p in paths]
    gate_paths = src["feature_gate_reference"]["paths"]
    kep_snaps = date_snaps("enhancements", src["kep"]["sig_dirs"] + src["kep"]["prr_dirs"])
    website_head = lock["repos"]["website"]["head"]
    release_dates = [r["release_date"] for r in releases]
    docs = [
        *snapshot_docs("docs_page", "website", cache, release_snaps(docs_paths)),
        *snapshot_docs("release_record", "website", cache, release_snaps(rr_website["paths"])),
        *snapshot_docs("release_record", "kubernetes", cache, changelogs),
        *snapshot_docs("feature_gate_reference", "website", cache, release_snaps(gate_paths)),
        *snapshot_docs("kep", "enhancements", cache, kep_snaps, (".md", ".yaml")),
        *blog_docs(cache, website_head, src["blog_post"]["paths"], release_dates, follow_renames),
    ]
    for gov in src["governance_doc"]:
        snaps = date_snaps(gov["repo"], gov["paths"])
        docs += snapshot_docs("governance_doc", gov["repo"], cache, snaps)
    return docs


def git_stdin(repo: Path, args: list[str], oids: list[str]) -> bytes:
    """Run a batch git command that reads object ids on stdin. Printed first, like fetch.git."""
    cmd = ["git", "-C", str(repo), *args]
    print("+", shlex.join(cmd), f"< {len(oids)} object ids", flush=True)
    data = "".join(f"{oid}\n" for oid in oids).encode()
    return subprocess.run(cmd, input=data, check=True, stdout=subprocess.PIPE).stdout


def prefetch(repo: Path, oids: list[str]) -> None:
    """Download blobs FETCH_BATCH at a time: the request git's lazy fetch makes, but batched.
    git skips a batch whose blobs are all present without contacting the remote."""
    # The arguments git's own lazy fetch uses (promisor-remote.c); ids are read from stdin.
    args = [
        "-c",
        "fetch.negotiationAlgorithm=noop",
        "fetch",
        "origin",
        "--no-tags",
        "--no-write-fetch-head",
        "--recurse-submodules=no",
        "--filter=blob:none",
        "--stdin",
    ]
    for i in range(0, len(oids), FETCH_BATCH):
        git_stdin(repo, args, oids[i : i + FETCH_BATCH])


def read_blobs(repo: Path, oids: list[str]) -> dict[str, str]:
    """All contents in one cat-file call. The network is blocked, so a missing blob fails."""
    out = git_stdin(repo, ["-c", "protocol.allow=never", "cat-file", "--batch"], oids)
    blobs, pos = {}, 0
    for oid in oids:  # each entry: "<oid> blob <size>\n<content>\n"
        eol = out.index(b"\n", pos)
        size = int(out[pos:eol].split()[2])
        blobs[oid] = out[eol + 1 : eol + 1 + size].decode("utf-8", errors="replace")
        pos = eol + 1 + size + 1
    return blobs


# --- Tally and report -----------------------------------------------------------------------


@dataclass
class Tally:
    files: int = 0
    versions: int = 0
    raw_versions: int = 0
    hashes: set[str] = field(default_factory=set)
    upper: list[int] = field(default_factory=list)  # tokens of every section of every new version
    lower: list[int] = field(default_factory=list)  # tokens of each unique (document, section)
    floor: dict[str, int] = field(default_factory=dict)  # section hash -> tokens, across documents


def combine(tallies: Iterable[Tally]) -> Tally:
    total = Tally()
    for t in tallies:
        total.files += t.files
        total.versions += t.versions
        total.raw_versions += t.raw_versions
        total.hashes |= t.hashes
        total.upper += t.upper
        total.lower += t.lower
        total.floor |= t.floor
    return total


def tally(
    docs: list[Doc], analysed: dict[tuple[str, str], Version], n_rows: int
) -> tuple[list[Tally], dict[str, Tally]]:
    by_row = [Tally() for _ in range(n_rows)]
    by_source: dict[str, Tally] = defaultdict(Tally)
    for doc in docs:
        label = f"{doc.source} (YAML metadata)" if doc.is_yaml else doc.source
        by_source[label].files += 1
        for row in present_rows(doc.seq, n_rows):
            by_row[row].files += 1
        for row, _ in new_versions(doc.seq):
            by_row[row].raw_versions += 1
            by_source[label].raw_versions += 1
        hashes = {oid: analysed[(oid, doc.strip_kind)].hash for _, oid in doc.seq if oid}
        doc_sections: dict[str, int] = {}  # section hash -> tokens, within this document
        for row, oid in new_versions(doc.seq, hashes):
            version = analysed[(oid, doc.strip_kind)]
            by_row[row].versions += 1
            by_source[label].versions += 1
            by_source[label].hashes.add(hashes[oid])
            by_source[label].upper += [tokens for _, tokens in version.sections]
            doc_sections.update(version.sections)
        # The chunk header holds canonical_id, so equal text in two documents is two cache entries.
        by_source[label].lower += doc_sections.values()
        by_source[label].floor |= doc_sections
    return by_row, by_source


def md_table(header: list[str], rows: Iterable[Iterable[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|---|" + "---:|" * (len(header) - 1)]
    for row in rows:
        cells = (f"{c:,}" if isinstance(c, int) else str(c) for c in row)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def print_report(labels: list[str], by_row: list[Tally], by_source: dict[str, Tally]) -> None:
    print("\n### A. Per release\n")
    rows_a = [
        [label, t.files, t.versions, t.raw_versions]
        for label, t in zip(labels, by_row, strict=True)
    ]
    print(md_table(["release", "files", "versions", "raw blob versions"], rows_a))

    print("\n### B. Per source type\n")
    rows_b = [
        [s, t.files, t.versions, t.raw_versions, len(t.hashes)]
        for s, t in sorted(by_source.items())
    ]
    total = combine(by_source.values())
    rows_b.append(["**total**", total.files, total.versions, total.raw_versions, len(total.hashes)])
    head_b = ["source", "documents", "versions", "raw blob versions", "unique content hashes"]
    print(md_table(head_b, rows_b))


def cost_row(size: int, bound: str, section_tokens: list[int]) -> list[object]:
    chunks, tokens = embed_totals(section_tokens, size)
    costs = [f"${tokens / 1e6 * price:,.2f}" for price in PRICE_PER_M_TOKENS.values()]
    storage = [f"{chunks * dim * 4 / 1e6:,.1f} MB" for dim in DIMENSIONS]  # float32: 4 bytes
    return [size, bound, chunks, tokens, *costs, *storage]


def print_cost_report(by_source: dict[str, Tally]) -> None:
    embedded = {s: t for s, t in sorted(by_source.items()) if t.upper}  # not YAML metadata
    total = combine(embedded.values())

    def cols(sections: list[int]) -> list[int]:
        return [len(sections), sum(sections), estimate_chunks(sections, DEFAULT_CHUNK)]

    print(f"\n### C. Tokens and chunks per source type (chunks @{DEFAULT_CHUNK})\n")
    rows_c = [
        [s, *cols(t.upper), *cols(t.lower)] for s, t in [*embedded.items(), ("**total**", total)]
    ]
    head_c = ["source", "upper: sections", "body tokens", "chunks"]
    head_c += ["lower: sections", "body tokens", "chunks"]
    print(md_table(head_c, rows_c))
    floor = list(total.floor.values())
    floor_chunks, floor_tokens = embed_totals(floor, DEFAULT_CHUNK)
    print(
        f"\nfloor, each section hash once across documents: {len(floor):,} sections, "
        f"{sum(floor):,} body tokens, {floor_chunks:,} chunks, {floor_tokens:,} embedded tokens"
    )
    for bound, sections in [("upper", total.upper), ("lower", total.lower)]:
        small = sum(n < SMALL_SECTION for n in sections)
        share = small / estimate_chunks(sections, DEFAULT_CHUNK)  # each is one whole chunk
        print(
            f"{bound}: {small:,} of {len(sections):,} sections ({small / len(sections):.0%}) "
            f"are under {SMALL_SECTION} tokens, {share:.0%} of the chunks"
        )

    print("\n### D. Embedding cost and vector storage\n")
    rows_d = []
    for size in CHUNK_SIZES:
        rows_d.append(cost_row(size, "upper: every new version", total.upper))
        rows_d.append(cost_row(size, "lower: unique (document, section)", total.lower))
    no_gates = combine(t for s, t in embedded.items() if s != "feature_gate_reference")
    rows_d.append(cost_row(DEFAULT_CHUNK, "upper, excl. feature_gate_reference", no_gates.upper))
    rows_d.append(cost_row(DEFAULT_CHUNK, "lower, excl. feature_gate_reference", no_gates.lower))
    head_d = ["chunk size", "bound", "chunks", "embedded tokens", *PRICE_PER_M_TOKENS]
    head_d += [f"vectors @{dim}d" for dim in DIMENSIONS]
    print(md_table(head_d, rows_d))


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the corpus subset per release.")
    parser.add_argument("--dry-run", action="store_true", help="count blobs; don't download")
    args = parser.parse_args()

    cache = cache_dir_or_exit()
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    norm = manifest["normalization"]
    if bad := bad_strip_keys(norm):
        sys.exit(f"refusing: strip_front_matter lists never_strip keys {bad}")
    releases = manifest["releases"]["list"]
    labels = [r["version"] for r in releases] + ["head"]

    # Blog moves can't be followed yet: git scores renames on contents, not downloaded yet.
    docs = collect(manifest, lock, cache)
    wanted: dict[str, set[str]] = defaultdict(set)
    for doc in docs:
        wanted[doc.repo].update(oid for _, oid in doc.seq if oid)
    print("blobs per repo:", {repo: len(oids) for repo, oids in sorted(wanted.items())})
    if args.dry_run:
        return

    texts: dict[str, str] = {}
    for repo, oids in sorted(wanted.items()):
        prefetch(cache / repo, sorted(oids))
        texts.update(read_blobs(cache / repo, sorted(oids)))
    blog_paths = sum(d.source == "blog_post" for d in docs)
    docs = collect(manifest, lock, cache, follow_renames=True)  # contents are local now

    strips = {
        kind: frozenset(k.lower() for k in keys)
        for kind, keys in norm["strip_front_matter"].items()
    }
    analysed: dict[tuple[str, str], Version] = {}
    no_front_matter: Counter[str] = Counter()
    for doc in docs:
        for oid in {oid for _, oid in doc.seq if oid}:
            if (oid, doc.strip_kind) not in analysed:
                strip = strips.get(doc.strip_kind, frozenset())
                analysed[(oid, doc.strip_kind)] = analyse(texts[oid], strip, doc.is_yaml)
        last = next(oid for _, oid in reversed(doc.seq) if oid)
        if analysed[(last, doc.strip_kind)].meta is None:
            no_front_matter[doc.source] += 1

    # Blog scope: the latest version's front-matter date is on or after from_release's date.
    blog = manifest["sources"]["blog_post"]
    since = str(next(r["release_date"] for r in releases if r["version"] == blog["from_release"]))

    def blog_in_scope(doc: Doc) -> bool:
        last = next(oid for _, oid in reversed(doc.seq) if oid)
        meta = analysed[(last, doc.strip_kind)].meta or {}
        return str(meta.get("date", ""))[:10] >= since and meta.get("draft") is not True

    kept = [d for d in docs if d.source != "blog_post" or blog_in_scope(d)]
    n_blog = sum(d.source == "blog_post" for d in docs)
    n_kept = sum(d.source == "blog_post" for d in kept)
    print(f"\nblog: {blog_paths} paths are {n_blog} posts after following moves")
    print(f"blog posts kept: {n_kept} of {n_blog} (front-matter date >= {since}, not draft)")
    print("documents without parseable YAML front matter:", dict(no_front_matter))
    by_row, by_source = tally(kept, analysed, len(labels))
    print_report(labels, by_row, by_source)
    print_cost_report(by_source)


if __name__ == "__main__":
    main()
