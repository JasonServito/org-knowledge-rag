"""`docs/interfaces.md` against the code (S14-T1): every API route has a `### METHOD /path` heading
and every `###` heading is a route; the doc's error-code table equals the code's list."""

import re
from pathlib import Path

from starlette.routing import Route

from orgknow.api.app import create_app
from orgknow.api.errors import ERROR_CODES
from orgknow.settings import Settings

DOC = Path(__file__).parents[2] / "docs" / "interfaces.md"
# FastAPI's own pages, not endpoints of this API.
FASTAPI_OWN = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
# A row of the error-code table: | `code` | status | ...
CODE_ROW = re.compile(r"^\| `([a-z_]+)` \| (\d{3}) \|")


def _routes() -> set[str]:
    """Each route as "METHOD /path". The app is built without entering its lifespan, so nothing
    connects and no API key is read."""
    app = create_app(Settings(_env_file=None, database_url="postgresql://unused@127.0.0.1:1/x"))
    routes: set[str] = set()
    for route in app.routes:
        assert isinstance(route, Route)  # this app has only HTTP routes
        if route.path not in FASTAPI_OWN:
            routes |= {f"{method} {route.path}" for method in route.methods or ()}
    return routes


def _section(heading: str) -> list[str]:
    """The doc's lines under `heading`, up to the next `## ` heading."""
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading) + 1
    ends = [i for i in range(start, len(lines)) if lines[i].startswith("## ")]
    return lines[start : ends[0] if ends else len(lines)]


def test_every_route_has_a_heading_and_every_heading_is_a_route() -> None:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    headings = {line.removeprefix("### ") for line in lines if line.startswith("### ")}
    routes = _routes()

    # The 4 routes in api/app.py, typed by hand, so an empty route list can't pass.
    assert {"GET /health", "GET /ready", "POST /query", "GET /decisions/{canonical_id}"} <= routes
    assert headings == routes


def test_the_docs_error_codes_equal_the_codes() -> None:
    rows = [match.groups() for line in _section("## Errors") if (match := CODE_ROW.match(line))]
    documented = {code: int(status) for code, status in rows}

    assert len(rows) == len(documented)  # no code listed twice
    # Decision 1's codes and statuses, typed from the run contract.
    decision_1 = {
        "invalid_request": 422,
        "not_found": 404,
        "upstream_failed": 502,
        "database_unavailable": 503,
        "internal": 500,
    }
    assert documented == ERROR_CODES == decision_1
