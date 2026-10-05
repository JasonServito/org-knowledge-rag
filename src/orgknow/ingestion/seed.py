"""Seed the `releases` table from the corpus manifest. Run with `make seed`; safe to re-run."""

import psycopg

from orgknow.db.releases import upsert_releases
from orgknow.ingestion.manifest import load_releases
from orgknow.settings import Settings


def main() -> None:
    settings = Settings()
    # Validate the whole list before touching the database.
    releases = load_releases(settings.corpus_manifest_path)
    # The `with` block is one transaction: committed at the end, rolled back on any error.
    with psycopg.connect(settings.database_url) as conn:
        upsert_releases(conn, releases)
    print(
        f"Upserted {len(releases)} releases ({releases[0].version} to {releases[-1].version}) "
        f"from {settings.corpus_manifest_path}"
    )


if __name__ == "__main__":
    main()
