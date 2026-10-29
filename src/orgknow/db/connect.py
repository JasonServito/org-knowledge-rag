"""The API's database connections (S14-R1 decision 2; ADR-005's amendment 2026-10-13).

One new connection per request, no pool. Autocommit: each statement commits on its own, so no
transaction stays open between statements, e.g. while the answer model is called. A
`with conn.transaction():` block is still one transaction (`hnsw.ef_search` is set inside one).
Any statement running past DB_STATEMENT_TIMEOUT_MS is cancelled with `QueryCanceled`, a
`psycopg.OperationalError`, which the routes report as a 503. `/ready` opens its own (`health.py`).
"""

import psycopg
from psycopg.rows import TupleRow

from orgknow.settings import Settings


def api_connection(settings: Settings) -> psycopg.Connection[TupleRow]:
    """A new autocommit connection with the statement timeout, waiting at most
    DB_CONNECT_TIMEOUT_S to connect. The caller closes it (`with`)."""
    return psycopg.connect(
        settings.database_url,
        connect_timeout=settings.db_connect_timeout_s,
        autocommit=True,
        options=f"-c statement_timeout={settings.db_statement_timeout_ms}",
    )
