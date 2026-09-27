# Architecture

This page describes only what exists in the code **today** (end of S01, repo foundation). It is updated as slices land. The planned pipeline (ingestion → retrieval → generation → eval) is described in `CLAUDE.md` and `docs/product-spec.md`; none of it is built yet.

## Overview

```
  environment variables / .env
               │
               ▼
      Settings (settings.py)
        │                  │
        ▼                  ▼
  FastAPI app          Alembic (db/migrations/env.py)
  (api/app.py)           │  URL gets the +psycopg driver name (db/url.py)
  /health  /ready        │  SQLAlchemy engine → psycopg
             │           │
  is_reachable           │
  (db/health.py)         │
  psycopg                │
             ▼           ▼
   Postgres 18 + pgvector 0.8.1
   (Docker Compose, localhost:5433)
```

## Components

| Path | What it does |
|---|---|
| `src/orgknow/settings.py` | `Settings` (pydantic-settings) reads `DATABASE_URL` (required, plain `postgresql://` form) and `DB_CONNECT_TIMEOUT_S` (default 2) from the environment, falling back to `.env`. It is built inside factories, never at import time. |
| `src/orgknow/api/app.py` | `create_app(settings=None)` builds the FastAPI app. `GET /health` is liveness: always 200, never touches the database. `GET /ready` is readiness: 200 if the database answers, otherwise 503. |
| `src/orgknow/db/health.py` | `is_reachable()` opens a fresh psycopg connection with a timeout and runs `SELECT 1`. |
| `src/orgknow/db/url.py` | `with_psycopg_driver()` rewrites `postgresql://` to `postgresql+psycopg://`, the form SQLAlchemy needs. Only Alembic uses it. |
| `src/orgknow/db/migrations/` | Alembic environment and hand-written migrations (no autogenerate, no offline mode). `0001` enables the `vector` extension. There are no domain tables yet (S03). |

There is no server entry point yet (no ASGI server dependency). The app runs only inside tests, through FastAPI's `TestClient`.

## Database

`compose.yaml` runs one service: the pinned `pgvector/pgvector:0.8.1-pg18` image (ADR-004), published on `127.0.0.1:5433`. Data lives in the named volume `pgdata`, so it survives `make down`. A `pg_isready` healthcheck over TCP lets `make up` block until the database accepts connections.

## Tests

| Directory | Needs | Covers |
|---|---|---|
| `tests/unit/` | nothing (no network, no DB) | settings loading, URL rewriting, package import |
| `tests/integration/` | `make up` + `make migrate` | the `vector` extension exists; `/health` and `/ready` return 200 with the DB up, and `/ready` returns 503 with it unreachable |

`tests/integration/conftest.py` marks every test in that directory `integration`, so `make check` excludes them and `make test-int` selects only them.

## Verification loop

| Where | What runs |
|---|---|
| Every commit | pre-commit: `ruff check --fix` and `ruff format` |
| `make check` | ruff format check, ruff lint, `mypy --strict` on `src/`, unit tests |
| `make test-int` | integration tests against the local database |
| CI (`.github/workflows/ci.yml`) | `check` job: `make check`. `integration` job: the same pgvector image as a service container, `make migrate` twice (the second run must be a no-op), then `make test-int`. |

CI calls the same Make targets as local development, and `UV_LOCKED=1` makes it fail if `uv.lock` is out of date.
