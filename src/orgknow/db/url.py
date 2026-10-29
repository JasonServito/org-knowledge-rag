"""Database URL handling shared by the app and Alembic."""

_PLAIN_SCHEME = "postgresql://"
_SQLALCHEMY_PSYCOPG_SCHEME = "postgresql+psycopg://"


def with_psycopg_driver(database_url: str) -> str:
    """Return `database_url` with SQLAlchemy's psycopg (v3) driver name, for Alembic's engine.

    Settings keeps a plain libpq URL that psycopg and psql accept as-is. SQLAlchemy reads a
    bare postgresql:// as "use psycopg2", which isn't installed, so the driver must be named.
    """
    if not database_url.startswith(_PLAIN_SCHEME):
        # Don't echo the URL: it contains the password.
        raise ValueError(f"DATABASE_URL must start with {_PLAIN_SCHEME}")
    return _SQLALCHEMY_PSYCOPG_SCHEME + database_url.removeprefix(_PLAIN_SCHEME)
