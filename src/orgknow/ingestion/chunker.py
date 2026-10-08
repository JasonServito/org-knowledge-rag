"""Split a version's Markdown into chunks by heading (S04-R1 decisions 5 and 6).

- Every heading (H1-H6) starts a section; a chunk never spans two sections. A section with no
  text of its own (a heading right before a subheading) makes no chunk. No merging, no overlap.
- A section longer than `max_tokens` (estimated as characters / 4) is packed into several
  chunks by whole blocks. A block is a paragraph or a code block and is never cut; one longer
  than `max_tokens` is a chunk on its own. A Markdown (pipe) table is a paragraph (a blank line
  ends it), so it is never cut either. An HTML `<table>` with a blank line inside a cell can be.
- A chunk's text is the header, a blank line, then the body (docs/domain-model.md, "Chunk
  header"). The body is the raw Markdown as written, shortcodes included, not the normalized
  text.
- A feature gate's body starts with its `stages` (and `removed`) front matter as YAML, then a
  blank line (S05-R1 decision 1): the gate's stages live only in its front matter.

Headings and code blocks come from a hand-written line scanner with exactly 4 rules (decision 6):
1. A line starting at column 0 with 1-6 `#` and then a space is a heading, unless inside a
   code block.
2. A fence (``` or ~~~, 3 or more) closes only on a line holding the same character, at least
   as long.
3. A fence opened with indent N also closes at the first non-blank line indented less than N
   (its list item ended).
4. `{{< highlight … >}}` … `{{< /highlight >}}` is a code block.

Pure functions: text in, chunks out.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# PyYAML ships no type hints; safe_dump only writes plain values.
import yaml  # type: ignore[import-untyped]

from orgknow.db.models import NewChunk
from orgknow.ingestion.normalize import decode, split_front_matter

CHARS_PER_TOKEN = 4

HEADING = re.compile(r"^(#{1,6}) (.*)$")  # rule 1
FENCE = re.compile(r"^( *)(`{3,}|~{3,})")  # rules 2 and 3: the indent and the marker
HIGHLIGHT_OPEN = re.compile(r"^\s*\{\{<\s*highlight\b.*>\}\}\s*$")  # rule 4
HIGHLIGHT_CLOSE = re.compile(r"^\s*\{\{<\s*/highlight\s*>\}\}\s*$")


@dataclass(frozen=True)
class Heading:
    level: int  # 1-6
    text: str  # as written: shortcodes and `{#id}` anchors stay


@dataclass(frozen=True)
class Block:
    """Lines `[start, end)` of the body that are never cut: a paragraph or a code block."""

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


def scan(lines: Sequence[str]) -> list[Heading | Block]:
    """The body's headings and blocks, in order. Blank lines between blocks are left out."""
    items: list[Heading | Block] = []
    i = 0
    while i < len(lines):
        heading = HEADING.match(lines[i])
        if _is_blank(lines[i]):
            end = i + 1
        elif heading is not None:
            items.append(Heading(len(heading[1]), heading[2].strip()))
            end = i + 1
        elif _opens_code_block(lines[i]):
            end = _code_block_end(lines, i)
            items.append(Block(i, end))
        else:  # a paragraph: up to a blank line, a heading or the start of a code block
            end = i + 1
            while end < len(lines) and not (
                _is_blank(lines[end]) or HEADING.match(lines[end]) or _opens_code_block(lines[end])
            ):
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


def pack(lines: Sequence[str], blocks: Sequence[Block], max_tokens: int) -> list[str]:
    """A section's bodies: consecutive whole blocks, greedily, up to `max_tokens` each.

    A body is the raw lines from its first block to its last, blank lines between included. A
    block is never cut: one longer than `max_tokens` is a body on its own.
    """
    bodies: list[str] = []
    first = last = blocks[0]
    for block in blocks[1:]:
        if estimate_tokens(_text(lines, first.start, block.end)) <= max_tokens:
            last = block
        else:
            bodies.append(_text(lines, first.start, last.end))
            first = last = block
    bodies.append(_text(lines, first.start, last.end))
    return bodies


def chunk_markdown(body: str, max_tokens: int) -> list[tuple[tuple[str, ...], str]]:
    """(heading path, body) of each chunk of a Markdown body, in order."""
    lines = body.split("\n")
    return [
        (section.heading_path, text)
        for section in split_sections(lines)
        for text in pack(lines, section.blocks, max_tokens)
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


def document_title(canonical_id: str, source_type: str, metadata: Mapping[str, Any]) -> str:
    """The title a chunk header shows: the metadata `title` on one line, and for a KEP (whose
    kep.yaml is the metadata) `KEP-<number>: <title>`. Raises ValueError when there is none."""
    title = " ".join(str(metadata.get("title") or "").split())  # one header line
    if not title:
        raise ValueError("no title in the version's metadata")
    if source_type == "kep":
        return f"KEP-{canonical_id.removeprefix('kep:')}: {title}"
    return title


def stages_yaml(front_matter: Mapping[str, Any]) -> str:
    """A gate's `stages`, then `removed` if it has one, as YAML: nothing else, keys in the file's
    own order, values as YAML read them (S05-R1 decision 1)."""
    kept = {"stages": front_matter["stages"]}
    if "removed" in front_matter:
        kept["removed"] = front_matter["removed"]
    text: str = yaml.safe_dump(kept, sort_keys=False)
    return text


def chunk_version(
    canonical_id: str, source_type: str, metadata: Mapping[str, Any], raw: bytes, max_tokens: int
) -> list[NewChunk]:
    """The chunks of one version, from its raw file.

    A docs page is chunked without its front matter. A KEP version is chunked from its README;
    its kep.yaml is the version's `metadata`, which gives the title (`document_title`). A gate
    (`gate:` id) with `stages` gets them as YAML before its body, read from the file's front
    matter: the same values as `metadata`, in the file's order (Postgres jsonb reorders keys).
    Raises ValueError for a file that can't be decoded or has no title.
    """
    title = document_title(canonical_id, source_type, metadata)
    text = decode(raw)
    if source_type == "kep":
        body = text
    else:
        front_matter, body = split_front_matter(text)
        if canonical_id.startswith("gate:") and "stages" in front_matter:
            # One blank line between the YAML and the body, also when the body starts with one.
            body = stages_yaml(front_matter) + "\n" + body.lstrip("\n")
    return [
        NewChunk(
            ordinal=ordinal,
            heading_path=list(path),
            text=chunk_text(source_type, title, canonical_id, path, part),
        )
        for ordinal, (path, part) in enumerate(chunk_markdown(body, max_tokens))
    ]
