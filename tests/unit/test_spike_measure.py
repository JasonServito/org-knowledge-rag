"""Tests for the S02-T3 spike, spikes/measure.py.

Replace in S04: normalization and hashing are rewritten in src/ with their own tests.
Delete this file then, together with the spike.
"""

import importlib
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"


@pytest.fixture(scope="module")
def measure() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SPIKES))  # measure.py imports its sibling fetch.py
        yield importlib.import_module("measure")


def doc_hash(measure: ModuleType, text: str) -> str:
    meta, body = measure.split_front_matter(text)
    return str(measure.content_hash(meta, body, frozenset({"reviewers"})))


def test_stripped_key_change_keeps_hash(measure: ModuleType) -> None:
    # Keys match case-insensitively, as Hugo does.
    a = doc_hash(measure, "---\ntitle: T\nReviewers: [a]\n---\nBody\n")
    b = doc_hash(measure, "---\ntitle: T\nReviewers: [b]\n---\nBody\n")
    assert a == b


def test_kept_key_change_changes_hash(measure: ModuleType) -> None:
    a = doc_hash(measure, "---\ntitle: A\n---\nBody\n")
    assert a != doc_hash(measure, "---\ntitle: B\n---\nBody\n")


def test_front_matter_variants_parse(measure: ModuleType) -> None:
    # Byte-order mark, leading blank line, CRLF: all seen in real blog posts.
    plain = "---\ntitle: T\n---\nB"
    for text in ["\ufeff" + plain, "\n" + plain, plain.replace("\n", "\r\n")]:
        assert measure.split_front_matter(text) == ({"title": "T"}, "B")


def test_strip_list_with_never_strip_key_is_rejected(measure: ModuleType) -> None:
    norm = {"never_strip": ["title", "status"], "strip_front_matter": {"x": ["weight", "Title"]}}
    assert measure.bad_strip_keys(norm) == ["Title"]


def test_link_target_and_whitespace_changes_keep_hash(measure: ModuleType) -> None:
    base = doc_hash(measure, "See [the docs](https://a.example/x) and [r].\n\n[r]: https://a/y\n")
    moved = doc_hash(measure, "See  [the docs](https://b.example/x)\nand [r].\n[r]: https://b/y\n")
    assert base == moved
    assert base != doc_hash(measure, "See [other docs](https://a.example/x) and [r].\n")


def test_sequences_mark_disappearances(measure: ModuleType) -> None:
    listings = [(0, {"x": "a"}), (1, {"x": "a", "y": "b"}), (2, {"y": "b"})]
    assert measure.sequences(listings) == {
        "x": [(0, "a"), (1, "a"), (2, None)],
        "y": [(1, "b"), (2, "b")],
    }


def test_versions_are_content_changes_not_snapshots(measure: ModuleType) -> None:
    seq = [(0, "a"), (1, "a"), (2, "b"), (3, "c"), (4, None)]
    assert measure.new_versions(seq) == [(0, "a"), (2, "b"), (3, "c")]
    # b normalizes to the same hash as a, so it is not a new version.
    assert measure.new_versions(seq, {"a": "h1", "b": "h1", "c": "h2"}) == [(0, "a"), (3, "c")]
    assert measure.present_rows(seq, 6) == [0, 1, 2, 3]
    # A -> B -> A is three versions: compare with the previous version only.
    assert len(measure.new_versions([(0, "a"), (1, "b"), (2, "a")])) == 3


def test_release_row_uses_the_lock_cutoff(measure: ModuleType) -> None:
    # Same rule as the lock: committer time (UTC) <= release date T23:59:59Z.
    dates = [date(2020, 12, 8), date(2021, 4, 8)]
    assert measure.release_row(datetime(2020, 1, 1, tzinfo=UTC), dates) == 0
    assert measure.release_row(datetime(2020, 12, 8, 23, 59, 59, tzinfo=UTC), dates) == 0
    assert measure.release_row(datetime(2020, 12, 9, 0, 0, 0, tzinfo=UTC), dates) == 1
    assert measure.release_row(datetime(2021, 4, 9, tzinfo=UTC), dates) == 2  # head row
