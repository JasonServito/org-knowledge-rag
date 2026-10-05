from datetime import date
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from orgknow.db.models import Release
from orgknow.db.releases import upsert_releases
from orgknow.ingestion.manifest import load_releases
from orgknow.settings import Settings

# These tests write through the `conn` fixture, so nothing they do is committed. The table may
# already hold the seeded releases (`make seed`), so each test works whether it's empty or not.


@pytest.fixture
def releases(settings: Settings) -> list[Release]:
    return load_releases(settings.corpus_manifest_path)


def _rows(conn: psycopg.Connection[TupleRow]) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT minor, version, release_date, end_of_life_date FROM releases ORDER BY minor"
    ).fetchall()


def test_upsert_twice_changes_nothing(
    conn: psycopg.Connection[TupleRow], releases: list[Release]
) -> None:
    upsert_releases(conn, releases)
    once = _rows(conn)
    upsert_releases(conn, releases)

    assert _rows(conn) == once
    # Expected values typed from config/corpus_manifest.yaml.
    assert len(once) == 18
    assert once[0] == (20, "1.20", date(2020, 12, 8), date(2022, 2, 28))
    assert once[4] == (24, "1.24", date(2022, 5, 3), date(2023, 7, 28))
    assert once[-1] == (37, "1.37", date(2026, 8, 26), date(2027, 10, 28))


def test_upsert_updates_dates_in_place(
    conn: psycopg.Connection[TupleRow], releases: list[Release]
) -> None:
    upsert_releases(conn, releases)
    before = _rows(conn)

    # A planned end of life slips, and the release date is corrected by a day.
    changed = Release(
        version="1.34", release_date=date(2025, 8, 28), end_of_life_date=date(2026, 12, 1)
    )
    upsert_releases(conn, [changed])

    after = _rows(conn)
    assert len(after) == 18
    assert (34, "1.34", date(2025, 8, 28), date(2026, 12, 1)) in after
    assert [row for row in after if row[0] != 34] == [row for row in before if row[0] != 34]


def test_upsert_of_a_shorter_list_deletes_nothing(
    conn: psycopg.Connection[TupleRow], releases: list[Release]
) -> None:
    upsert_releases(conn, releases)
    before = _rows(conn)

    upsert_releases(conn, releases[:5])

    assert _rows(conn) == before
    assert len(before) == 18
