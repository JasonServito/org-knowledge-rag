"""Writes to the `releases` table."""

from collections.abc import Sequence

import psycopg
from psycopg.rows import TupleRow

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
