"""`orgknow ask`'s route line in temporal mode (S09-T4), from hand-written routes, windows and
filters: the wording is the run contract's ("Route: HISTORY, releases until 1.27 (searched until
1.28)", "Route: CURRENT, current text only", "Route: WHY, no filter")."""

import pytest

from orgknow.cli import route_line
from orgknow.db.models import TemporalFilter
from orgknow.retrieval.router import Mode, Route
from orgknow.retrieval.temporal import Window


def _route(mode: Mode) -> Route:
    # The line reads only the mode; the time scope is filler.
    return Route.model_validate(
        {"mode": mode, "time_scope": {"kind": "none", "start": None, "end": None}}
    )


def _filter(
    current_only: bool = False, from_release: int | None = None, until_release: int | None = None
) -> TemporalFilter:
    return TemporalFilter(
        current_only=current_only, from_release=from_release, until_release=until_release
    )


@pytest.mark.parametrize(
    ("mode", "window", "temporal", "expected"),
    [
        ("CURRENT", None, _filter(current_only=True), "Route: CURRENT, current text only"),
        (
            "HISTORY",
            Window(until_release=27),
            _filter(until_release=28),
            "Route: HISTORY, releases until 1.27 (searched until 1.28)",
        ),
        (
            "HISTORY",
            Window(from_release=30),
            _filter(from_release=29),
            "Route: HISTORY, releases from 1.30 (searched from 1.29)",
        ),
        (
            "HISTORY",
            Window(from_release=23, until_release=26),
            _filter(from_release=22, until_release=27),
            "Route: HISTORY, releases 1.23 to 1.26 (searched 1.22 to 1.27)",
        ),
        ("HISTORY", None, None, "Route: HISTORY, no filter"),
        # A window on a WHY route plans no filter (S09-R1 decision 3).
        ("WHY", Window(from_release=28, until_release=28), None, "Route: WHY, no filter"),
        ("CHANGE", None, None, "Route: CHANGE, no filter"),
    ],
)
def test_the_route_line(
    mode: Mode, window: Window | None, temporal: TemporalFilter | None, expected: str
) -> None:
    assert route_line(_route(mode), window, temporal) == expected
