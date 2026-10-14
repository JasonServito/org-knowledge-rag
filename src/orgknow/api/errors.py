"""The API's error codes and the HTTP status of each (S14-R1 decision 1; docs/interfaces.md)."""

ERROR_CODES: dict[str, int] = {
    "invalid_request": 422,
    "not_found": 404,
    "upstream_failed": 502,
    "database_unavailable": 503,
    "internal": 500,
}
