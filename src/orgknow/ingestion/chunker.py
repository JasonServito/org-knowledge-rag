"""Split a version's Markdown into chunks by heading (S04-R1 decisions 5 and 6, S05-R3).

- Every heading (H1-H6) starts a section; a chunk never spans two sections. A section with no
  text of its own (a heading right before a subheading) makes no chunk. No merging, no overlap.
- A section longer than `max_tokens` (estimated as characters / 4) is packed into several
  chunks by whole blocks. A block is a paragraph, a code block or an HTML table. A block longer
  than `max_tokens` is a chunk on its own, except an oversize list or pipe table, which is cut
  (S05-R3 decision 1):
  - a list between its items: the lines at the block's smallest list-marker indent
  - a pipe table between its rows, each later piece starting with the table's header row and
    delimiter row
  The pieces are packed like blocks. Code blocks and HTML tables are never cut.
- A chunk's text is the header, a blank line, then the body (docs/domain-model.md, "Chunk
  header"). The body is the raw Markdown as written, shortcodes included, not the normalized
  text, minus HTML comment blocks (rule 6).
- A heading's text loses its inline HTML comments and a trailing Hugo `{#id}` anchor (S05-R3
  decision 3): `## Example {#example} <!-- omit in toc -->` is the section `Example`.
- A feature gate's body starts with its `stages` (and `removed`) front matter as YAML, then a
  blank line (S05-R1 decision 1): the gate's stages live only in its front matter.
- A KEP folder's README, a governance doc and a CHANGELOG have no front matter: the whole file is
  the body.
- No source keeps a section under a `## Downloads for …` heading (the sha512 download tables,
  S05-R2 decision 8 and S05-R3 decision 4). A CHANGELOG also drops the text before its first
  heading (the generated TOC).

Headings and blocks come from a hand-written line scanner with 6 rules (decision 6; rules 5 and
6 from S05-R3 decision 2):
1. A line starting at column 0 with 1-6 `#` and then a space or a tab is a heading, unless
   inside a code block, an HTML table or an HTML comment.
2. A fence (``` or ~~~, 3 or more) closes only on a line holding the same character, at least
   as long.
3. A fence opened with indent N also closes at the first non-blank line indented less than N
   (its list item ended).
4. `{{< highlight … >}}` … `{{< /highlight >}}` is a code block.
5. Outside a code block, a line starting (after at most 3 spaces) with `<table` (any case) opens
   an HTML table, which runs to the first line containing `</table>`.
6. Outside a code block, a line starting (after at most 3 spaces) with `<!--` opens an HTML
   comment block, which runs to the first line containing `-->` (the opening line counts). It
   makes no text and no heading.
Rules 5 and 6 also end a paragraph. A table or comment that never closes runs to the end of the
body. A one-line comment inside a paragraph line, or a comment inside a code block, stays.

Pure functions: text in, chunks out.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

# PyYAML ships no type hints; safe_dump only writes plain values.
import yaml  # type: ignore[import-untyped]

from orgknow.db.models import NewChunk
from orgknow.ingestion.normalize import decode, split_front_matter

CHARS_PER_TOKEN = 4

HEADING = re.compile(r"^(#{1,6})[ \t](.*)$")  # rule 1
FENCE = re.compile(r"^( *)(`{3,}|~{3,})")  # rules 2 and 3: the indent and the marker
HIGHLIGHT_OPEN = re.compile(r"^\s*\{\{<\s*highlight\b.*>\}\}\s*$")  # rule 4
HIGHLIGHT_CLOSE = re.compile(r"^\s*\{\{<\s*/highlight\s*>\}\}\s*$")
TABLE_OPEN = re.compile(r"^ {0,3}<table", re.IGNORECASE)  # rule 5
COMMENT_OPEN = re.compile(r"^ {0,3}<!--")  # rule 6
HTML_COMMENT = re.compile(r"<!--.*?-->")  # an inline comment in a heading
ANCHOR = re.compile(r"\s*\{#[^}]*\}\s*$")  # a Hugo heading id at the end of a heading
LIST_ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])[ \t]")  # a list marker and its indent
DOWNLOADS = "Downloads for "  # a heading over sha512 download tables (S05-R2 decision 8)


@dataclass(frozen=True)
class Heading:
    level: int  # 1-6
    text: str  # without inline comments or a trailing `{#id}` anchor; shortcodes stay
    line: int  # its line in the body, from 0


@dataclass(frozen=True)
class Block:
    """Lines `[start, end)` of the body: a paragraph, a code block or an HTML table, or a piece of
    a cut list or pipe table (`pieces`)."""

    start: int
    end: int
    # A later piece of a cut pipe table: the table's first 2 lines (header and delimiter rows),
    # written before the piece when it starts a chunk.
    header: tuple[str, ...] = ()


@dataclass(frozen=True)
class Comment:
    """Lines `[start, end)` of the body: an HTML comment block (rule 6). It makes no text."""

    start: int
    end: int


@dataclass(frozen=True)
class Section:
    heading_path: tuple[str, ...]  # the headings above the text, outermost first; () before any
    blocks: tuple[Block, ...]


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _is_blank(line: str) -> bool:
    return not line.strip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _opens_code_block(line: str) -> bool:
    return FENCE.match(line) is not None or HIGHLIGHT_OPEN.match(line) is not None


def _ends_paragraph(line: str) -> bool:
    return (
        _is_blank(line)
        or HEADING.match(line) is not None
        or _opens_code_block(line)
        or TABLE_OPEN.match(line) is not None
        or COMMENT_OPEN.match(line) is not None
    )


def heading_text(raw: str) -> str:
    """A heading's text without inline HTML comments, then without a trailing `{#id}` anchor."""
    return ANCHOR.sub("", HTML_COMMENT.sub("", raw)).strip()


def _code_block_end(lines: Sequence[str], start: int) -> int:
    """The index just past the last line of the code block that `lines[start]` opens.

    A block that never closes runs to the end of the body. Trailing blank lines aren't part of it.
    """
    fence = FENCE.match(lines[start])  # None: a Hugo highlight block
    last = start  # the block's last non-blank line so far
    for i in range(start + 1, len(lines)):
        line, stripped = lines[i], lines[i].strip()
        if not stripped:
            continue
        if fence is None:
            if HIGHLIGHT_CLOSE.match(line):  # rule 4
                return i + 1
        elif _indent(line) < len(fence[1]):  # rule 3: the list item ended before this line
            return last + 1
        elif set(stripped) == {fence[2][0]} and len(stripped) >= len(fence[2]):  # rule 2
            return i + 1
        last = i
    return last + 1


def _closing_line_end(lines: Sequence[str], start: int, closer: str) -> int:
    """The index just past the first line from `start` on (itself included) that contains
    `closer`, ignoring case; the end of the body if none does (rules 5 and 6)."""
    for i in range(start, len(lines)):
        if closer in lines[i].lower():
            return i + 1
    return len(lines)


def scan(lines: Sequence[str]) -> list[Heading | Block | Comment]:
    """The body's headings, blocks and HTML comment blocks, in order. Blank lines between them
    are left out."""
    items: list[Heading | Block | Comment] = []
    i = 0
    while i < len(lines):
        heading = HEADING.match(lines[i])
        if _is_blank(lines[i]):
            end = i + 1
        elif COMMENT_OPEN.match(lines[i]):  # rule 6: no text, no heading
            end = _closing_line_end(lines, i, "-->")
            items.append(Comment(i, end))
        elif heading is not None:
            items.append(Heading(len(heading[1]), heading_text(heading[2]), i))
            end = i + 1
        elif _opens_code_block(lines[i]):
            end = _code_block_end(lines, i)
            items.append(Block(i, end))
        elif TABLE_OPEN.match(lines[i]):  # rule 5: kept whole, blank lines in cells included
            end = _closing_line_end(lines, i, "</table>")
            items.append(Block(i, end))
        else:  # a paragraph: up to a blank line or a line that starts another item
            end = i + 1
            while end < len(lines) and not _ends_paragraph(lines[end]):
                end += 1
            items.append(Block(i, end))
        i = end
    return items


def split_sections(lines: Sequence[str]) -> list[Section]:
    """Every heading starts a section. Its path is the enclosing headings, then itself."""
    sections: list[Section] = []
    path: list[Heading] = []
    blocks: list[Block] = []
    for item in scan(lines):
        if isinstance(item, Comment):
            continue
        if isinstance(item, Block):
            blocks.append(item)
            continue
        if blocks:  # close the open section; a heading with no text of its own makes none
            sections.append(Section(tuple(h.text for h in path), tuple(blocks)))
            blocks = []
        # A heading closes every open heading at its level or deeper.
        path = [h for h in path if h.level < item.level] + [item]
    if blocks:
        sections.append(Section(tuple(h.text for h in path), tuple(blocks)))
    return sections


def _text(lines: Sequence[str], start: int, end: int) -> str:
    return "\n".join(lines[start:end])


def _is_delimiter_row(line: str) -> bool:
    """A pipe table's 2nd line: only `|`, `-`, `:` and spaces, with at least one `|` and `-`."""
    return set(line) <= set("|-: ") and "|" in line and "-" in line


def pieces(lines: Sequence[str], block: Block, max_tokens: int) -> list[Block]:
    """Where a block may be cut (S05-R3 decision 1): only a paragraph over `max_tokens`.

    - A pipe table (its 2nd line is a delimiter row) is cut between rows. The first piece is the
      header row, the delimiter row and the first row; every later row is a piece that carries
      the first 2 lines as its `header`.
    - Otherwise a list is cut before each item at the block's smallest list-marker indent. Nested
      items and continuation lines stay with their item; lines before the first item are the
      first piece.
    A code block, an HTML table, a block within the limit, or a paragraph with no list marker is
    one piece: the block itself.
    """
    first = lines[block.start]
    if (
        estimate_tokens(_text(lines, block.start, block.end)) <= max_tokens
        or _opens_code_block(first)
        or TABLE_OPEN.match(first)
    ):
        return [block]
    if block.end - block.start > 1 and _is_delimiter_row(lines[block.start + 1]):
        header = (lines[block.start], lines[block.start + 1])
        rows_from = min(block.start + 3, block.end)
        return [Block(block.start, rows_from)] + [
            Block(i, i + 1, header) for i in range(rows_from, block.end)
        ]
    indents: dict[int, int] = {}  # line -> indent of its list marker
    for i in range(block.start, block.end):
        marker = LIST_ITEM.match(lines[i])
        if marker:
            indents[i] = len(marker[1])
    if not indents:
        return [block]
    top = min(indents.values())
    cuts = sorted({block.start} | {i for i, indent in indents.items() if indent == top})
    return [Block(a, b) for a, b in pairwise([*cuts, block.end])]


def _body(lines: Sequence[str], blocks: Sequence[Block], hidden: set[int]) -> str:
    """The text of consecutive blocks of one section: the first block's `header` (a later piece
    of a cut table), then the lines from the first block to the last, blank lines between
    included, except the `hidden` ones (HTML comment blocks, rule 6)."""
    first, last = blocks[0], blocks[-1]
    kept = [lines[i] for i in range(first.start, last.end) if i not in hidden]
    return "\n".join([*first.header, *kept])


def pack(
    lines: Sequence[str], blocks: Sequence[Block], max_tokens: int, hidden: set[int]
) -> list[str]:
    """A section's bodies: consecutive blocks, greedily, up to `max_tokens` each.

    A block is never cut here (`pieces` cuts first): one longer than `max_tokens` is a body on
    its own.
    """
    bodies: list[str] = []
    group = [blocks[0]]
    for block in blocks[1:]:
        if estimate_tokens(_body(lines, [*group, block], hidden)) <= max_tokens:
            group.append(block)
        else:
            bodies.append(_body(lines, group, hidden))
            group = [block]
    bodies.append(_body(lines, group, hidden))
    return bodies


def chunk_markdown(body: str, max_tokens: int) -> list[tuple[tuple[str, ...], str]]:
    """(heading path, body) of each chunk of a Markdown body, in order."""
    lines = body.split("\n")
    hidden = {i for c in scan(lines) if isinstance(c, Comment) for i in range(c.start, c.end)}
    return [
        (section.heading_path, text)
        for section in split_sections(lines)
        for text in pack(
            lines,
            [piece for block in section.blocks for piece in pieces(lines, block, max_tokens)],
            max_tokens,
            hidden,
        )
    ]


def chunk_text(
    source_type: str, title: str, canonical_id: str, heading_path: Sequence[str], body: str
) -> str:
    """The text that is stored and embedded: header lines, a blank line, then the body.

    The header holds only fields that are the same in every version of a document (decision 4).
    """
    header = [f"Source: {source_type}", f"Title: {title}", f"Document: {canonical_id}"]
    if heading_path:
        header.append(f"Section: {' > '.join(heading_path)}")
    return "\n".join(header) + "\n\n" + body


def _is_kep_folder(canonical_id: str) -> bool:
    """A KEP with a number (`kep:2579`, a folder), not an old single-file KEP (`kep:sig-x/name`)."""
    return canonical_id.removeprefix("kep:").isdigit()


def document_title(canonical_id: str, source_type: str, metadata: Mapping[str, Any]) -> str:
    """The title a chunk header shows: the metadata `title` on one line, and for a KEP folder
    (whose kep.yaml is the metadata) `KEP-<number>: <title>`. An old single-file KEP has no
    number, so its front-matter title stays as written. Raises ValueError when there is none."""
    title = " ".join(str(metadata.get("title") or "").split())  # one header line
    if not title:
        raise ValueError("no title in the version's metadata")
    if source_type == "kep" and _is_kep_folder(canonical_id):
        return f"KEP-{canonical_id.removeprefix('kep:')}: {title}"
    return title


def governance_title(text: str, path: str) -> str:
    """A governance doc's title (S05-R2 decision 4): its first `# ` heading, else its repo path.
    Headings are the scanner's, so a `#` line in a code block or an HTML comment is none, and the
    text has no inline comment (`# Google Cloud Platform <!-- omit in toc -->`) or `{#id}`
    anchor."""
    for item in scan(text.split("\n")):
        if isinstance(item, Heading) and item.level == 1:
            return " ".join(item.text.split()) or path
    return path


def changelog_title(release: int) -> str:
    """A CHANGELOG's title: its file name, CHANGELOG-1.R (S05-R2 decision 4)."""
    return f"CHANGELOG-1.{release}"


def is_downloads(heading_path: Sequence[str]) -> bool:
    """Whether a section sits under a `## Downloads for …` heading (the sha512 download tables),
    so it makes no chunk, in any source (S05-R2 decision 8, S05-R3 decision 4)."""
    return any(h.startswith(DOWNLOADS) for h in heading_path)


def stages_yaml(front_matter: Mapping[str, Any]) -> str:
    """A gate's `stages`, then `removed` if it has one, as YAML: nothing else, keys in the file's
    own order, values as YAML read them (S05-R1 decision 1)."""
    kept = {"stages": front_matter["stages"]}
    if "removed" in front_matter:
        kept["removed"] = front_matter["removed"]
    text: str = yaml.safe_dump(kept, sort_keys=False)
    return text


def version_body(canonical_id: str, source_type: str, text: str) -> str:
    """The Markdown a version is chunked from, given its decoded file.

    A docs page, a blog post and an old single-file KEP lose their front matter. A KEP folder's
    README, a governance doc and a CHANGELOG (`changelog:` id) have none: the whole file. A gate
    (`gate:` id) with `stages` gets them as YAML before its body, read from the file's front
    matter: the same values as `metadata`, in the file's order (Postgres jsonb reorders keys).
    """
    if (
        source_type == "governance_doc"
        or canonical_id.startswith("changelog:")
        or (source_type == "kep" and _is_kep_folder(canonical_id))
    ):
        return text
    front_matter, body = split_front_matter(text)
    if canonical_id.startswith("gate:") and "stages" in front_matter:
        # One blank line between the YAML and the body, also when the body starts with one.
        body = stages_yaml(front_matter) + "\n" + body.lstrip("\n")
    return body


def chunk_version(
    canonical_id: str, source_type: str, metadata: Mapping[str, Any], raw: bytes, max_tokens: int
) -> list[NewChunk]:
    """The chunks of one version, from its raw file (its body: `version_body`).

    A KEP folder's version is chunked from its README; its kep.yaml is the version's `metadata`,
    which gives the title (`document_title`). A governance doc and a CHANGELOG are chunked under
    the title their metadata holds. No section under a `Downloads for …` heading is kept
    (`is_downloads`); a CHANGELOG (`changelog:` id) also drops the text before its first heading
    (the generated TOC). Raises ValueError for a file that can't be decoded or has no title.
    """
    title = document_title(canonical_id, source_type, metadata)
    parts = chunk_markdown(version_body(canonical_id, source_type, decode(raw)), max_tokens)
    parts = [(path, part) for path, part in parts if not is_downloads(path)]
    if canonical_id.startswith("changelog:"):
        parts = [(path, part) for path, part in parts if path]
    return [
        NewChunk(
            ordinal=ordinal,
            heading_path=list(path),
            text=chunk_text(source_type, title, canonical_id, path, part),
        )
        for ordinal, (path, part) in enumerate(parts)
    ]
