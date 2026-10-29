"""Writes to and reads from the `releases` table."""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow, class_row

from orgknow.db.models import Release


def upsert_releases(conn: psycopg.Connection[TupleRow], releases: Sequence[Release]) -> None:
    """Insert new releases and update the dates of existing ones. Never deletes a release.

    The caller owns the transaction.
    """
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO releases (minor, version, release_date, end_of_life_date)
            VALUES (%(minor)s, %(version)s, %(release_date)s, %(end_of_life_date)s)
            ON CONFLICT (minor) DO UPDATE
            SET release_date = EXCLUDED.release_date,
                end_of_life_date = EXCLUDED.end_of_life_date
            """,
            [
                {
                    "minor": release.minor,
                    "version": release.version,
                    "release_date": release.release_date,
                    "end_of_life_date": release.end_of_life_date,
                }
                for release in releases
            ],
        )


def list_releases(conn: psycopg.Connection[TupleRow]) -> list[Release]:
    """Return every stored release, oldest first. Read-only: `make ingest` compares these with
    the manifest and never writes them (`make seed` does)."""
    with conn.cursor(row_factory=class_row(Release)) as cur:
        cur.execute("SELECT version, release_date, end_of_life_date FROM releases ORDER BY minor")
        return cur.fetchall()
