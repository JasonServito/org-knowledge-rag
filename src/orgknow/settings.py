"""Configuration read from environment variables, falling back to a local `.env` file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Plain libpq form, e.g. postgresql://user:password@host:port/dbname. No default: a
    # missing value should fail at startup, not silently point at some database.
    database_url: str
    # How long /ready waits for a new DB connection. libpq treats values below 2 as 2.
    db_connect_timeout_s: int = 2
