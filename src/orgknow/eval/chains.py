"""The gold decision chains' label check (S13-T1): every `texts` entry of the gold file
(EVAL_CHAINS_PATH, ADR-012 D4) must match at least 1 stored chunk, by ADR-007 D2's section rule
(`section_matches`) against the chunk's heading path, its document named by canonical id or
alias.

Only the `texts` labels are read here. The gold file's full loader and the completeness score
come with S13-T4.
"""

from collections.abc import Sequence
from pathlib import Path

import psycopg

# PyYAML ships no type hints, so safe_load returns Any.
import yaml  # type: ignore[import-untyped]
from psycopg.rows import TupleRow
from pydantic import BaseModel

from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import SectionText
from orgknow.eval.golden import format_section, parse_section, section_matches


class ChainLabel(BaseModel):
    """One acceptable text of a gold step: a document and, optionally, a section."""

    seed: str  # the chain's seed KEP, e.g. kep:2572
    step: str  # problem, discussion, proposal, decision, implementation or current_docs
    document: str  # a canonical id or an alias
    section: str | None = None  # None: the whole document; "": the intro; "A > B": headings


def text_labels(path: Path) -> list[ChainLabel]:
    """Every `texts` entry of the gold file, in file order. A step labeled `not_public`,
    `not_stored` or `none` cites no stored text, so it has none."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        ChainLabel(
            seed=chain["seed"],
            step=step["step"],
            document=text["document"],
            section=text.get("section"),
        )
        for chain in data["chains"]
        for step in chain["steps"]
        for text in step.get("texts", [])
    ]


def count_texts(conn: psycopg.Connection[TupleRow], labels: Sequence[ChainLabel]) -> list[int]:
    """How many distinct stored chunk texts each label matches, in order. A document that is
    neither a canonical id nor an alias matches nothing."""
    ids = canonical_ids(conn, sorted({label.document for label in labels}))
    texts: dict[str, list[SectionText]] = {}
    counts = []
    for label in labels:
        canonical_id = ids.get(label.document)
        if canonical_id is None:
            counts.append(0)
            continue
        if canonical_id not in texts:
            texts[canonical_id] = document_texts(conn, canonical_id)
        section = parse_section(label.section)
        matched = {
            text.content_hash
            for text in texts[canonical_id]
            if section_matches(section, text.heading_path)
        }
        counts.append(len(matched))
    return counts


def label_line(label: ChainLabel, count: int) -> str:
    """`kep:2572 decision  gh:enhancements/pull/2567  "Comments > @dims · 2021-04-19"  2 texts`."""
    section = format_section(parse_section(label.section))
    return f"{label.seed} {label.step}  {label.document}  {section}  {count} texts"
