"""Seed the `releases` table from the corpus manifest. Run with `make seed`; safe to re-run."""

import sys

import psycopg

from orgknow.db.releases import upsert_releases
from orgknow.db.writer_lock import WriterBusy, writer_lock
from orgknow.ingestion.manifest import load_releases
from orgknow.settings import Settings


def main() -> None:
    settings = Settings()
    # Validate the whole list before touching the database.
    releases = load_releases(settings.corpus_manifest_path)
    # The writer lock (ADR-013 D3) is taken first, on this connection. Then the upsert is one
    # transaction (autocommit outside it), committed before the lock is released, or rolled back
    # on any error.
    try:
        with (
            psycopg.connect(settings.database_url, autocommit=True) as conn,
            writer_lock(conn),
            conn.transaction(),
        ):
            upsert_releases(conn, releases)
    except WriterBusy as busy:
        sys.exit(str(busy))
    print(
        f"Upserted {len(releases)} releases ({releases[0].version} to {releases[-1].version}) "
        f"from {settings.corpus_manifest_path}"
    )


if __name__ == "__main__":
    main()
