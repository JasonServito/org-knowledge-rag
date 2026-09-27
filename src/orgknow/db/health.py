"""Database reachability check, used by the API's readiness endpoint."""

import psycopg


def is_reachable(database_url: str, connect_timeout_s: int) -> bool:
    """Return True if a new connection can be opened and can run a trivial query."""
    try:
        with psycopg.connect(database_url, connect_timeout=connect_timeout_s) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        return False
    return True
