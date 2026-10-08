"""The golden-set label check and the section listing (S06-T1) against the test database.

Every test builds its own rows inside `conn`'s rolled-back transaction; expected counts are
counted by hand from those rows.
"""

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.chunks import add_chunks
from orgknow.db.documents import add_alias, create_document
from orgknow.db.eval import canonical_ids, document_texts
from orgknow.db.models import NewChunk, NewVersion
from orgknow.db.versions import insert_version
from orgknow.eval.golden import (
    GoldenSetError,
    Label,
    LabelCount,
    check_labels,
    list_sections,
    load_golden_file,
)

Conn = psycopg.Connection[TupleRow]

pytestmark = pytest.mark.usefixtures("seeded_releases")

VERSION_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
# Release dates from the manifest (00:00 UTC).
D24 = datetime(2022, 5, 3, tzinfo=UTC)
D25 = datetime(2022, 8, 23, tzinfo=UTC)
D26 = datetime(2022, 12, 8, tzinfo=UTC)


def _version(
    conn: Conn,
    document_id: int,
    releases: tuple[int, int | None],
    dates: tuple[datetime, datetime | None],
    chunks: list[tuple[list[str], str]],
) -> None:
    """Store a version holding `chunks`, (heading path, text) each, in ordinal order."""
    version_id = insert_version(
        conn,
        NewVersion(
            document_id=document_id,
            content_hash=VERSION_HASH,
            source_path="content/en/docs/test/page.md",
            snapshot_repo="website",
            snapshot_ref=f"release-1.{releases[0]}",
            snapshot_sha="1111111111111111111111111111111111111111",
            valid_from_release=releases[0],
            valid_until_release=releases[1],
            valid_from_date=dates[0],
            valid_until_date=dates[1],
        ),
    )
    new_chunks = [
        NewChunk(ordinal=i, heading_path=path, text=text) for i, (path, text) in enumerate(chunks)
    ]
    add_chunks(conn, version_id, new_chunks)


@pytest.fixture
def documents(conn: Conn, seeded_releases: None) -> None:
    """Two documents (their versions reference the releases, so those are stored first).
    `web:/test/a/` has two versions that share one text; `web:/test/b/` is also known by the
    alias `web:/test/old-b/`."""
    a = create_document(conn, "web:/test/a/", "docs_page")
    _version(
        conn,
        a,
        (24, 24),
        (D24, D25),
        [([], "a intro old"), (["Install"], "a install")],
    )
    _version(
        conn,
        a,
        (25, None),
        (D25, None),
        [
            ([], "a intro"),
            (["Install"], "a install"),
            (["Install", "Linux"], "a install linux"),
            (["Installation"], "a installation"),
        ],
    )
    b = create_document(conn, "web:/test/b/", "docs_page")
    _version(conn, b, (24, None), (D24, None), [([], "b intro"), (["Usage"], "b usage")])
    add_alias(conn, b, "web:/test/old-b/")


def _golden_file(tmp_path: Path, labels_q01: str, labels_q02: str = "") -> Path:
    """A golden file with q01 (and q02 if given) holding these YAML label lines."""
    text = "version: v0\nquestions:\n"
    for qid, labels in (("q01", labels_q01), ("q02", labels_q02)):
        if labels:
            text += (
                f"  - id: {qid}\n"
                "    question: How do I install it?\n"
                "    mode: CURRENT\n"
                "    answerable: true\n"
                "    expected_answer: Like this.\n"
                "    smoke: false\n"
                "    labels:\n" + labels
            )
    path = tmp_path / "golden.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.usefixtures("documents")
def test_an_alias_resolves_to_its_canonical_id(conn: Conn) -> None:
    names = ["web:/test/old-b/", "web:/test/b/", "web:/test/missing/"]

    # An unknown name is left out.
    assert canonical_ids(conn, names) == {
        "web:/test/old-b/": "web:/test/b/",
        "web:/test/b/": "web:/test/b/",
    }


@pytest.mark.usefixtures("documents")
def test_the_check_counts_distinct_texts_per_label_and_reports_0_matches(
    conn: Conn, tmp_path: Path
) -> None:
    path = _golden_file(
        tmp_path,
        "      - {document: 'web:/test/a/', section: Install}\n"
        "      - {document: 'web:/test/old-b/'}\n",
        "      - {document: 'web:/test/a/', section: ''}\n"
        "      - {document: 'web:/test/a/', section: Nope}\n"
        "      - {document: 'web:/test/missing/'}\n",
    )

    golden, counts = check_labels(conn, load_golden_file(path))

    assert counts == [
        # "a install" (in both versions: 1 text) and "a install linux"; not "a installation".
        LabelCount(question_id="q01", document="web:/test/a/", section=["Install"], texts=2),
        # The alias's document: "b intro" and "b usage".
        LabelCount(question_id="q01", document="web:/test/old-b/", section=None, texts=2),
        # "a intro old" and "a intro".
        LabelCount(question_id="q02", document="web:/test/a/", section=[], texts=2),
        # No such section, and no such document: both 0, so both are reported.
        LabelCount(question_id="q02", document="web:/test/a/", section=["Nope"], texts=0),
        LabelCount(question_id="q02", document="web:/test/missing/", section=None, texts=0),
    ]
    # The resolved labels name the canonical_id, so the metrics compare ids only.
    assert golden.questions[0].labels == [
        Label(canonical_id="web:/test/a/", section=["Install"]),
        Label(canonical_id="web:/test/b/", section=None),
    ]


@pytest.mark.usefixtures("documents")
def test_a_duplicate_after_resolving_aliases_is_rejected(conn: Conn, tmp_path: Path) -> None:
    # Two different names as written, one document once the alias is resolved.
    path = _golden_file(
        tmp_path, "      - {document: 'web:/test/b/'}\n      - {document: 'web:/test/old-b/'}\n"
    )
    golden_file = load_golden_file(path)  # as written, the labels don't overlap

    with pytest.raises(GoldenSetError) as error:
        check_labels(conn, golden_file)

    assert error.value.errors == [
        "q01: labels: web:/test/b/ (whole document) is listed twice after resolving aliases"
    ]


def test_sections_are_listed_by_first_appearance_across_versions(conn: Conn) -> None:
    # The newer version is stored first, so only the version date can put the older first.
    # "Setup" exists only in the newer version, so it comes after the older version's sections
    # even though its ordinal there (1) is lower than "Install"'s and "Usage"'s.
    c = create_document(conn, "web:/test/c/", "docs_page")
    _version(
        conn,
        c,
        (26, None),
        (D26, None),
        [([], "c intro"), (["Setup"], "c setup"), (["Install"], "c install new"), (["Usage"], "u")],
    )
    _version(
        conn,
        c,
        (24, 25),
        (D24, D26),
        [([], "c intro"), (["Install"], "c install old"), (["Usage"], "u")],
    )

    sections = list_sections(document_texts(conn, "web:/test/c/"))

    # "c intro" and "u" are in both versions: 1 text each. "Install" has 2 different texts.
    assert sections == [([], 1), (["Install"], 2), (["Usage"], 1), (["Setup"], 1)]
