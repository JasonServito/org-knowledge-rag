"""Time scope → release window → retrieval filter (S09-T2, ADR-009 D2, ADR-003 D4). Pure: the
caller passes the `releases` table's rows in.

- `resolve_window`: the releases a route's time scope names, by the S09-R1 contract's pinned
  table. A release value ("1.28") is exact; a year means the releases in effect during it.
- `plan`: the filter the mode's retrieval plan applies (S09-R1 decisions 2-3): CURRENT keeps
  current text only; HISTORY with a window keeps texts valid in it, widened by `slack` releases;
  everything else has no filter.
"""

import re
from collections.abc import Sequence
from datetime import date
from typing import Literal, NamedTuple

from pydantic import BaseModel

from orgknow.db.models import Release, TemporalFilter
from orgknow.retrieval.router import Mode, TimeScope

# "1.28", "v1.28" or "1.28.3": minor 28. A patch is read as its minor (no patch-level windows).
_RELEASE = re.compile(r"v?1\.([0-9]+)(\.[0-9]+)?")
# A 4-digit year from 1000 to 2999, so the year before and after are both valid dates.
_YEAR = re.compile(r"[12][0-9]{3}")


class Window(BaseModel):
    """The releases a time scope names, by minor (27 for 1.27), both ends inclusive; None is an
    open end. Never both None."""

    from_release: int | None = None
    until_release: int | None = None


class _Value(NamedTuple):
    """A time-scope value as code reads it: a release's minor, or a year."""

    unit: Literal["release", "year"]
    number: int


def resolve_window(scope: TimeScope, releases: Sequence[Release]) -> Window | None:
    """The release window `scope` names, or None when it names none.

    For every kind but `between`, the value is `start`, or `end` when `start` is empty. With
    `_first` and `_last` the first and last release a value covers (below):

    - before v → until the last release of the value before v (1.27 for 1.28, 2020 for 2021)
    - in v → from the first to the last release of v
    - after v → from the first release of the value after v (1.31 for 1.30, 2022 for 2021)
    - since v → from the first release of v
    - between a and b → from the first release of a to the last release of b

    No window when a value isn't a release or a year, a year's end has no release yet, or a window
    would end before it starts. A release outside the table is kept as a number ("before 1.15" →
    until 14), so a filter on it matches nothing.
    """
    if scope.kind == "none":
        return None
    if scope.kind == "between":
        start, end = _parse(scope.start), _parse(scope.end)
        if start is None or end is None:
            return None
        return _closed(_first(start, releases), _last(end, releases))
    value = _parse(scope.start or scope.end)
    if value is None:
        return None
    if scope.kind == "in":
        return _closed(_first(value, releases), _last(value, releases))
    if scope.kind == "since":
        start_release = _first(value, releases)
        return None if start_release is None else Window(from_release=start_release)
    if scope.kind == "after":
        after = _first(value._replace(number=value.number + 1), releases)
        return None if after is None else Window(from_release=after)
    before = _last(value._replace(number=value.number - 1), releases)  # kind "before"
    return None if before is None else Window(until_release=before)


def plan(mode: Mode, window: Window | None, slack: int) -> TemporalFilter | None:
    """The filter both searches apply for a route of `mode` whose time scope resolved to `window`.

    CURRENT: current text only, whatever the window. HISTORY with a window: from - slack to
    until + slack, an open end staying open. Every other route, a HISTORY one with no window
    included: None, no filter.
    """
    if mode == "CURRENT":
        return TemporalFilter(current_only=True, from_release=None, until_release=None)
    if mode == "HISTORY" and window is not None:
        return TemporalFilter(
            current_only=False,
            from_release=None if window.from_release is None else window.from_release - slack,
            until_release=None if window.until_release is None else window.until_release + slack,
        )
    return None


def _parse(text: str | None) -> _Value | None:
    """A release ("1.N", "v1.N", "1.N.P") or a year ("2021"), exactly; anything else is None."""
    if text is None:
        return None
    release = _RELEASE.fullmatch(text)
    if release is not None:
        return _Value("release", int(release.group(1)))
    if _YEAR.fullmatch(text):
        return _Value("year", int(text))
    return None


def _first(value: _Value, releases: Sequence[Release]) -> int | None:
    """The first release a value covers: 1.N → N; a year → the release in effect on its
    January 1, or the first release if none was out yet (None with no releases)."""
    if value.unit == "release":
        return value.number
    in_effect = _in_effect(date(value.number, 1, 1), releases)
    if in_effect is not None:
        return in_effect
    return min((release.minor for release in releases), default=None)


def _last(value: _Value, releases: Sequence[Release]) -> int | None:
    """The last release a value covers: 1.N → N; a year → the release in effect on its
    December 31 (None if none was out yet)."""
    if value.unit == "release":
        return value.number
    return _in_effect(date(value.number, 12, 31), releases)


def _in_effect(day: date, releases: Sequence[Release]) -> int | None:
    """The release in effect on `day`: the latest whose release date is on or before it (ADR-002
    D3). None before the first release."""
    return max((r.minor for r in releases if r.release_date <= day), default=None)


def _closed(start: int | None, end: int | None) -> Window | None:
    """A window with both ends, or None when an end is missing or it would end before it starts."""
    if start is None or end is None or start > end:
        return None
    return Window(from_release=start, until_release=end)
