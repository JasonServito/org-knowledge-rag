"""S05-T7 re-check: the chunker's line scanner against markdown-it (CommonMark), on the corpus.

Run: uv run --with markdown-it-py==3.0.0 python -I spikes/scanner_recheck.py

Needs `make up`, an ingested dev database (it reads the stored versions and chunks) and the
corpus clones (it reads each version's file from git at its snapshot, as `make ingest` does).

1. Headings: for every stored version, the ATX headings the scanner finds in the body it chunks
   are compared, by line, with markdown-it's. Both sides' texts lose a trailing `{#id}` anchor and
   inline HTML comments first. Each difference is classified by its cause:
   - Hugo highlight: a `#` line inside `{{< highlight >}}`, which the scanner reads as code
     (rule 4) and markdown-it as Markdown
   - backtick info string: a `#` line after a ``` line whose info string holds a backtick (an
     inline code span to CommonMark, a fence that runs on to the scanner, rule 2)
   - list-item heading: a heading inside a list item or block quote (the scanner reads only
     column-0 headings)
   - indented heading: a heading indented 1-3 spaces, at top level
   - HTML comment: a `#` line inside an HTML comment block (scanner rule 6 drops it)
   - tab: a `#` heading followed by a tab
   - other: listed one by one
   The S05-R3 sitting counted the 2nd cause with the 1st and the 4th with the 3rd.
2. Comments: every distinct stored chunk body is parsed with markdown-it, and its HTML comment
   blocks (`html_block` tokens starting with `<!--`) are counted and listed.

A sitting tool (S05-R3 sitting): never imported by src/. markdown-it-py is not a project
dependency; `uv run --with` takes it from uv's cache.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import psycopg
from markdown_it import MarkdownIt

from orgknow.ingestion.chunker import HIGHLIGHT_OPEN, Block, Heading, scan, version_body
from orgknow.ingestion.git_reader import read_file
from orgknow.ingestion.normalize import decode
from orgknow.settings import Settings

# The same cleaning on both sides (S05-R3 sitting), written out here rather than imported.
ANCHOR = re.compile(r"\s*\{#[^}]*\}\s*$")
INLINE_COMMENT = re.compile(r"<!--.*?-->")
TAB_HEADING = re.compile(r"^#{1,6}\t")
INDENTED_HEADING = re.compile(r"^ {1,3}#{1,6}[ \t]")
BACKTICK_INFO = re.compile(r"^ *`{3,}[^`]*`")  # a ``` line with a backtick after the marker
CAUSES = (
    "Hugo highlight",
    "backtick info string",
    "list-item heading",
    "indented heading",
    "HTML comment",
    "tab",
    "other",
)

VERSIONS = """
    SELECT d.canonical_id, d.source_type, v.snapshot_repo, v.snapshot_sha, v.source_path
    FROM document_versions v JOIN documents d ON d.id = v.document_id
    ORDER BY v.id
"""
TEXTS = "SELECT DISTINCT ON (content_hash) content_hash, text FROM chunks ORDER BY content_hash"


def clean(text: str) -> str:
    return ANCHOR.sub("", INLINE_COMMENT.sub("", text)).strip()


def scanner_headings(lines: list[str]) -> tuple[dict[int, tuple[int, str]], list[Block]]:
    """{line: (level, text)} of the scanner's headings, and its blocks."""
    items = scan(lines)
    headings = {h.line: (h.level, clean(h.text)) for h in items if isinstance(h, Heading)}
    return headings, [b for b in items if isinstance(b, Block)]


def markdown_it_headings(
    tokens: list[Any],
) -> tuple[dict[int, tuple[int, str, bool]], list[tuple[int, int]]]:
    """{line: (level, text, nested)} of markdown-it's ATX headings (nested: inside a list item or
    block quote), and the line ranges of its HTML comment blocks."""
    headings: dict[int, tuple[int, str, bool]] = {}
    comments: list[tuple[int, int]] = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.markup.startswith("#"):
            headings[token.map[0]] = (
                int(token.tag[1]),
                clean(tokens[i + 1].content),
                token.level > 0,
            )
        elif token.type == "html_block" and token.content.lstrip().startswith("<!--"):
            comments.append((token.map[0], token.map[1]))
    return headings, comments


def classify(
    line: int,
    lines: list[str],
    only_in: str,
    blocks: list[Block],
    md: dict[int, tuple[int, str, bool]],
    comments: list[tuple[int, int]],
) -> str:
    if only_in == "markdown-it":
        opener = next((lines[b.start] for b in blocks if b.start <= line < b.end), "")
        if HIGHLIGHT_OPEN.match(opener):
            return "Hugo highlight"
        if BACKTICK_INFO.match(opener):
            return "backtick info string"
        if md[line][2]:
            return "list-item heading"
        if INDENTED_HEADING.match(lines[line]):
            return "indented heading"
        if TAB_HEADING.match(lines[line]):
            return "tab"
    elif any(start <= line < end for start, end in comments):
        return "HTML comment"
    return "other"


def recheck_headings(conn: psycopg.Connection[Any], settings: Settings, md: MarkdownIt) -> None:
    cache = settings.corpus_cache_dir.expanduser()
    differences: Counter[str] = Counter()
    files: dict[str, set[int]] = defaultdict(set)
    others: list[str] = []
    versions = conn.execute(VERSIONS).fetchall()
    headings_seen = 0
    for n, (canonical_id, source_type, repo, sha, path) in enumerate(versions):
        body = version_body(canonical_id, source_type, decode(read_file(cache / repo, sha, path)))
        lines = body.split("\n")
        ours, blocks = scanner_headings(lines)
        theirs, comments = markdown_it_headings(md.parse(body))
        headings_seen += len(theirs)
        for line in sorted(set(ours) | set(theirs)):
            if line in ours and line in theirs and ours[line] == theirs[line][:2]:
                continue
            if line in ours and line in theirs:  # same line, another level or text
                cause = "other"
            else:
                only_in = "scanner" if line in ours else "markdown-it"
                cause = classify(line, lines, only_in, blocks, theirs, comments)
            differences[cause] += 1
            files[cause].add(n)
            if cause == "other":
                others.append(
                    f"{canonical_id} {repo}@{sha[:8]}:{path} line {line + 1}: "
                    f"scanner {ours.get(line)}, markdown-it {theirs.get(line)}"
                )
    total = sum(differences.values())
    all_files = set().union(*files.values()) if files else set()
    print(f"Files: {len(versions)} stored versions; markdown-it ATX headings: {headings_seen}")
    print(f"Heading differences: {total} in {len(all_files)} files\n")
    print("| Cause | Differences | Files |\n|---|---|---|")
    for cause in CAUSES:
        print(f"| {cause} | {differences[cause]} | {len(files[cause])} |")
    for line in others:
        print(f"- other: {line}")


def recheck_comments(conn: psycopg.Connection[Any], md: MarkdownIt) -> None:
    texts = conn.execute(TEXTS).fetchall()
    found: list[str] = []
    for content_hash, text in texts:
        body = text.split("\n\n", 1)[1] if "\n\n" in text else ""
        for token in md.parse(body):
            if token.type == "html_block" and token.content.lstrip().startswith("<!--"):
                first = token.content.strip().split("\n")[0][:80]
                found.append(f"{content_hash[:12]} body line {token.map[0] + 1}: {first}")
    print(f"\nChunk bodies: {len(texts)} distinct texts; HTML comment blocks: {len(found)}")
    for line in found:
        print(f"- {line}")


def main() -> None:
    settings = Settings()
    md = MarkdownIt("commonmark")
    with psycopg.connect(settings.database_url) as conn:
        recheck_headings(conn, settings, md)
        recheck_comments(conn, md)


if __name__ == "__main__":
    main()
