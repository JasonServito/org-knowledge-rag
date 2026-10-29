"""The ingestion report's pure parts (S05-T8): the fingerprint, and skip lines.

Every expected value is written by hand. The pinned fingerprint was computed outside Python, with
printf and sha256sum (see `test_a_tiny_database_has_this_hand_computed_fingerprint`).
"""

from datetime import UTC, datetime, timedelta, timezone

from orgknow.db.models import StoredAlias, StoredChunk, StoredDocument, StoredVersion
from orgknow.ingestion.git_reader import Skip
from orgknow.ingestion.manifest import Snapshot
from orgknow.ingestion.report import fingerprint, skip_lines, snapshot_labels

PAGE = "web:/docs/a/"
D20 = datetime(2020, 12, 8, tzinfo=UTC)  # 1.20's release date, 00:00 UTC
D21 = datetime(2021, 4, 8, tzinfo=UTC)  # 1.21's
HASH_1 = "1" * 64
HASH_2 = "2" * 64
SHA = "0123456789abcdef0123456789abcdef01234567"

DOCUMENT = StoredDocument(canonical_id=PAGE, source_type="docs_page")
ALIAS = StoredAlias(canonical_id=PAGE, alias="web:/docs/b/")
VERSION = StoredVersion(
    canonical_id=PAGE,
    content_hash=HASH_1,
    source_path="content/en/docs/a.md",
    snapshot_repo="website",
    snapshot_ref="release-1.20",
    snapshot_sha=SHA,
    valid_from_release=20,
    valid_until_release=20,
    valid_from_date=D20,
    valid_until_date=D21,
    metadata={"title": "Café", "weight": 2},
)
CHUNK = StoredChunk(
    canonical_id=PAGE,
    valid_from_date=D20,
    ordinal=0,
    heading_path=["Overview"],
    content_hash=HASH_2,
)


def _fingerprint(
    documents: list[StoredDocument] | None = None,
    aliases: list[StoredAlias] | None = None,
    versions: list[StoredVersion] | None = None,
    chunks: list[StoredChunk] | None = None,
) -> str:
    """The fingerprint of the tiny database above, with any of its four lists replaced."""
    return fingerprint(
        [DOCUMENT] if documents is None else documents,
        [ALIAS] if aliases is None else aliases,
        [VERSION] if versions is None else versions,
        [CHUNK] if chunks is None else chunks,
    )


def test_an_empty_database_has_the_sha256_of_the_empty_string() -> None:
    # `printf '' | sha256sum`
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert fingerprint([], [], [], []) == empty


def test_a_tiny_database_has_this_hand_computed_fingerprint() -> None:
    # The 4 rows typed by hand, sorted, joined with "\n" (no newline at the end), hashed by
    # `printf '%s\n%s\n%s\n%s' '<alias row>' '<chunk row>' '<document row>' '<version row>' |
    # sha256sum` in a UTF-8 shell (é is the 2 bytes c3 a9):
    #   ["alias","web:/docs/a/","web:/docs/b/"]
    #   ["chunk","web:/docs/a/","2020-12-08T00:00:00+00:00",0,["Overview"],"2222…2222"]
    #   ["document","web:/docs/a/","docs_page"]
    #   ["version","web:/docs/a/","1111…1111","content/en/docs/a.md","website","release-1.20",
    #    "0123456789abcdef0123456789abcdef01234567",20,20,"2020-12-08T00:00:00+00:00",
    #    "2021-04-08T00:00:00+00:00",null,null,{"title":"Café","weight":2}]
    expected = "f90f59f0f38866adf119d0f5d1baac15e7086c469c7bd953e4ec631e39aeda8c"
    assert _fingerprint() == expected
    # Dates print in UTC: the same instants at +01:00 give the same rows.
    plus_one = timezone(timedelta(hours=1))
    version = VERSION.model_copy(
        update={
            "valid_from_date": D20.astimezone(plus_one),
            "valid_until_date": D21.astimezone(plus_one),
        }
    )
    chunk = CHUNK.model_copy(update={"valid_from_date": D20.astimezone(plus_one)})
    assert _fingerprint(versions=[version], chunks=[chunk]) == expected


def test_the_order_of_the_records_does_not_matter() -> None:
    other = StoredDocument(canonical_id="kep:2579", source_type="kep")
    second = CHUNK.model_copy(update={"ordinal": 1, "content_hash": "3" * 64})

    assert _fingerprint(documents=[DOCUMENT, other], chunks=[CHUNK, second]) == _fingerprint(
        documents=[other, DOCUMENT], chunks=[second, CHUNK]
    )


def test_metadata_keys_in_another_order_give_the_same_fingerprint() -> None:
    reordered = VERSION.model_copy(update={"metadata": {"weight": 2, "title": "Café"}})

    assert _fingerprint(versions=[reordered]) == _fingerprint()


def test_one_changed_value_of_each_kind_changes_the_fingerprint() -> None:
    changed = [
        _fingerprint(documents=[DOCUMENT.model_copy(update={"source_type": "release_record"})]),
        _fingerprint(aliases=[ALIAS.model_copy(update={"alias": "web:/docs/c/"})]),
        _fingerprint(
            versions=[VERSION.model_copy(update={"valid_until_date": D21 + timedelta(1)})]
        ),
        _fingerprint(versions=[VERSION.model_copy(update={"metadata": {"title": "Cafe"}})]),
        _fingerprint(chunks=[CHUNK.model_copy(update={"content_hash": "3" * 64})]),
    ]

    assert _fingerprint() not in changed
    assert len(set(changed)) == 5


def test_a_chunk_changed_only_in_its_content_hash_changes_the_fingerprint() -> None:
    # The chunk text is covered through its hash (R13): a text change is a hash change.
    assert _fingerprint(chunks=[CHUNK.model_copy(update={"content_hash": "3" * 64})]) != (
        _fingerprint()
    )


# --- Skip lines: one per (file, reason), with its snapshots --------------------------------


def _at(release: int | None) -> Snapshot:
    return Snapshot(release, "main", SHA)


def test_a_file_skipped_at_three_snapshots_is_one_line() -> None:
    skips = [Skip(_at(r), "keps/sig-auth/OWNERS", "not a .md/.yaml file") for r in (20, 21, 22)]

    assert skip_lines(skips) == ["keps/sig-auth/OWNERS: not a .md/.yaml file (1.20\N{EN DASH}1.22)"]


def test_skip_lines_are_sorted_and_their_snapshots_are_in_release_order() -> None:
    skips = [
        Skip(_at(None), "b.md", "symlink"),
        Skip(_at(21), "b.md", "symlink"),
        Skip(_at(20), "b.md", "symlink"),
        Skip(_at(20), "a.png", "not a .md file"),
    ]

    assert skip_lines(skips) == [
        "a.png: not a .md file (1.20)",
        "b.md: symlink (1.20\N{EN DASH}1.21, head)",
    ]


def test_consecutive_releases_make_a_range_and_a_gap_starts_a_new_one() -> None:
    snapshots = [_at(r) for r in (25, 20, 21, 22, 27, 28, None)]

    assert snapshot_labels(snapshots) == "1.20\N{EN DASH}1.22, 1.25, 1.27\N{EN DASH}1.28, head"
    assert snapshot_labels([_at(None)]) == "head"
