"""Time scope → release window, and the mode's retrieval plan (S09-T2, ADR-009 D2).

Every expected window is worked out by hand from the pinned table in the S09-R1 contract
("Pinned: time scope → release window") and the release dates typed below from
`config/corpus_manifest.yaml`. "In effect on day d" is the latest release whose release date is
on or before d (ADR-002 D3). None is computed by the code under test.
"""

from datetime import date
from typing import Any, cast

import pytest
from tests.conftest import FakeEmbedder, FakeReranker

from orgknow.db.models import Release, TemporalFilter
from orgknow.retrieval.retrieve import retrieve
from orgknow.retrieval.router import Mode, TimeScope
from orgknow.retrieval.temporal import Window, plan, resolve_window
from orgknow.settings import Settings

# (version, release date, end of life), typed from the manifest's `releases.list`.
RELEASES = [
    Release(
        version=version,
        release_date=date.fromisoformat(day),
        end_of_life_date=date.fromisoformat(eol),
    )
    for version, day, eol in [
        ("1.20", "2020-12-08", "2022-02-28"),
        ("1.21", "2021-04-08", "2022-06-28"),
        ("1.22", "2021-08-04", "2022-12-08"),
        ("1.23", "2021-12-07", "2023-02-28"),
        ("1.24", "2022-05-03", "2023-07-28"),
        ("1.25", "2022-08-23", "2023-10-28"),
        ("1.26", "2022-12-08", "2024-02-28"),
        ("1.27", "2023-04-11", "2024-07-16"),
        ("1.28", "2023-08-15", "2024-10-22"),
        ("1.29", "2023-12-13", "2025-02-28"),
        ("1.30", "2024-04-17", "2025-07-15"),
        ("1.31", "2024-08-13", "2025-11-11"),
        ("1.32", "2024-12-11", "2026-02-28"),
        ("1.33", "2025-04-23", "2026-06-28"),
        ("1.34", "2025-08-27", "2026-10-27"),
        ("1.35", "2025-12-17", "2027-02-28"),
        ("1.36", "2026-04-22", "2027-06-28"),
        ("1.37", "2026-08-26", "2027-10-28"),
    ]
]


def _scope(kind: str, start: str | None, end: str | None = None) -> TimeScope:
    return TimeScope.model_validate({"kind": kind, "start": start, "end": end})


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        # The contract's 8 hand-worked examples.
        (_scope("before", "1.28"), Window(until_release=27)),
        # In effect on 2020-12-31: 1.20 (2020-12-08); 1.21 came 2021-04-08.
        (_scope("before", "2021"), Window(until_release=20)),
        (_scope("in", "1.20"), Window(from_release=20, until_release=20)),
        # In effect on 2022-01-01: 1.23 (2021-12-07); on 2022-12-31: 1.26 (2022-12-08).
        (_scope("in", "2022"), Window(from_release=23, until_release=26)),
        (_scope("after", "1.30"), Window(from_release=31)),
        (_scope("since", "1.30"), Window(from_release=30)),
        # In effect on 2019-12-31: none (the first release, 1.20, is 2020-12-08).
        (_scope("before", "2020"), None),
        (_scope("in", "v1.28.3"), Window(from_release=28, until_release=28)),
        # The proof map's 4 more.
        (_scope("between", "1.24", "1.26"), Window(from_release=24, until_release=26)),
        (_scope("between", "1.26", "1.24"), None),
        (_scope("none", None), None),
        (_scope("before", None, "1.28"), Window(until_release=27)),
        # The year rows of after, since and between.
        # After 2021: in effect on 2022-01-01, 1.23.
        (_scope("after", "2021"), Window(from_release=23)),
        # Since 2022: in effect on 2022-01-01, 1.23.
        (_scope("since", "2022"), Window(from_release=23)),
        # Since 2019: none in effect on 2019-01-01 yet, so the first release.
        (_scope("since", "2019"), Window(from_release=20)),
        # Between 2021 and 2022: in effect on 2021-01-01, 1.20 (2020-12-08); on 2022-12-31, 1.26.
        (_scope("between", "2021", "2022"), Window(from_release=20, until_release=26)),
        # In 2019: none in effect on 2019-12-31.
        (_scope("in", "2019"), None),
        # A window outside the corpus is kept as numbers (contract, edge cases).
        (_scope("before", "1.15"), Window(until_release=14)),
        (_scope("in", "1.40"), Window(from_release=40, until_release=40)),
        # Anything else gives no window.
        (_scope("before", "Kubernetes 1.28"), None),
        (_scope("before", None, None), None),
        (_scope("between", "1.24", None), None),
    ],
)
def test_a_time_scope_becomes_a_release_window(scope: TimeScope, expected: Window | None) -> None:
    assert resolve_window(scope, RELEASES) == expected


def test_current_searches_current_text_only() -> None:
    assert plan("CURRENT", None, slack=1) == TemporalFilter(
        current_only=True, from_release=None, until_release=None
    )


def test_history_until_20_with_slack_1_searches_until_21() -> None:
    assert plan("HISTORY", Window(until_release=20), slack=1) == TemporalFilter(
        current_only=False, from_release=None, until_release=21
    )


def test_history_in_28_with_slack_1_searches_27_to_29() -> None:
    window = Window(from_release=28, until_release=28)

    assert plan("HISTORY", window, slack=1) == TemporalFilter(
        current_only=False, from_release=27, until_release=29
    )


@pytest.mark.parametrize(
    ("mode", "window"),
    [
        ("HISTORY", None),
        ("CHANGE", Window(from_release=28, until_release=28)),
        ("WHY", Window(until_release=27)),
    ],
)
def test_other_routes_have_no_filter(mode: Mode, window: Window | None) -> None:
    assert plan(mode, window, slack=1) is None


def test_temporal_mode_without_a_route_raises_before_any_call() -> None:
    # S09-T4: the route is required in temporal mode. The check comes before the question is
    # embedded or any query runs, so no database is needed here (the connection is never used).
    settings = Settings(_env_file=None, database_url="x", retrieval_mode="temporal")
    embedder = FakeEmbedder()

    with pytest.raises(ValueError, match="temporal mode needs a route: none was given"):
        retrieve("q", embedder, cast(Any, None), settings, FakeReranker({}))

    assert embedder.calls == []
