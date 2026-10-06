"""The read-only releases check `make ingest` runs before reading git (S04-R2 decision S2).

Expected values are typed by hand from config/corpus_manifest.yaml (1.29 and 1.30).
"""

from datetime import date

from orgknow.db.models import Release
from orgknow.ingestion.ingest import release_problems

R29 = Release(version="1.29", release_date=date(2023, 12, 13), end_of_life_date=date(2025, 2, 28))
R30 = Release(version="1.30", release_date=date(2024, 4, 17), end_of_life_date=date(2025, 7, 15))


def test_a_table_equal_to_the_manifest_has_no_problems() -> None:
    assert release_problems([R29, R30], [R29, R30]) == []


def test_extra_rows_in_the_table_are_not_a_problem() -> None:
    r19 = Release(
        version="1.19", release_date=date(2020, 8, 26), end_of_life_date=date(2021, 10, 28)
    )

    assert release_problems([R30], [r19, R29, R30]) == []


def test_a_release_missing_from_the_table_is_named() -> None:
    assert release_problems([R29, R30], [R29]) == ["1.30 is missing"]


def test_a_release_stored_with_another_date_is_named() -> None:
    redated = R30.model_copy(update={"release_date": date(2024, 4, 18)})

    assert release_problems([R29, R30], [R29, redated]) == [
        "1.30 differs (table: 2024-04-18 to 2025-07-15; manifest: 2024-04-17 to 2025-07-15)"
    ]


def test_an_end_of_life_date_is_compared_too() -> None:
    # A planned end of life that slipped in the manifest, while the table still has the old one.
    stale = R30.model_copy(update={"end_of_life_date": date(2025, 6, 1)})

    assert release_problems([R30], [stale]) == [
        "1.30 differs (table: 2024-04-17 to 2025-06-01; manifest: 2024-04-17 to 2025-07-15)"
    ]
