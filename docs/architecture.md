# Architecture

This page describes only what exists in the code **today** (end of S03, domain model). S03 added the domain tables, the functions that write and read them, and the releases seed. Nothing calls the data-access functions yet: S04 ingestion is their first caller. It is updated as slices land. The planned pipeline (ingestion → retrieval → generation → eval) is described in `CLAUDE.md` and `docs/product-spec.md`.

## Overview

```
  environment variables / .env
               │
               ▼
      Settings (settings.py)
        │                 │                         │
        ▼                 ▼                         ▼
  FastAPI app         make seed                 Alembic (db/migrations/env.py)
  (api/app.py)        (ingestion/seed.py)         │  URL gets the +psycopg driver name (db/url.py)
  /health  /ready       │  load_releases            │  SQLAlchemy engine → psycopg
        │               │  (ingestion/manifest.py)  │  0001: vector extension
  is_reachable          │  ◄── config/corpus_manifest.yaml
  (db/health.py)        │  upsert_releases          │  0002: domain tables + rules
  psycopg               │  (db/releases.py)         │
        │               │  psycopg                  │
        ▼               ▼                           ▼
   Postgres 18 + pgvector 0.8.1 + btree_gist
   (Docker Compose, localhost:5433)
        ▲
        │  psycopg, hand-written SQL (ADR-005)
  data-access functions (db/documents.py, db/versions.py, db/chunks.py)
  first caller: S04 ingestion; today only the integration tests
```

## Components

| Path | What it does |
|---|---|
| `src/orgknow/settings.py` | `Settings` (pydantic-settings) reads `DATABASE_URL` (required, plain `postgresql://` form), `DB_CONNECT_TIMEOUT_S` (default 2) and `CORPUS_MANIFEST_PATH` (default `config/corpus_manifest.yaml`) from the environment, falling back to `.env`. It is built inside factories, never at import time. |
| `src/orgknow/api/app.py` | `create_app(settings=None)` builds the FastAPI app. `GET /health` is liveness: always 200, never touches the database. `GET /ready` is readiness: 200 if the database answers, otherwise 503. |
| `src/orgknow/db/health.py` | `is_reachable()` opens a fresh psycopg connection with a timeout and runs `SELECT 1`. |
| `src/orgknow/db/url.py` | `with_psycopg_driver()` rewrites `postgresql://` to `postgresql+psycopg://`, the form SQLAlchemy needs. Only Alembic uses it. |
| `src/orgknow/db/migrations/` | Alembic environment and hand-written migrations (raw SQL, no autogenerate, no offline mode). `0001` enables `vector`. `0002` enables `btree_gist` and creates the 6 domain tables with 28 named constraints. |
| `src/orgknow/db/models.py` | Pydantic models at the data-access boundary (ADR-005): `Release`, `NewVersion` / `Version` (timezone-aware datetimes only), `NewChunk` (no hash field). |
| `src/orgknow/db/releases.py` | `upsert_releases`: inserts new releases and updates the dates of existing ones; never deletes. |
| `src/orgknow/db/documents.py` | `create_document`, `add_alias`, `resolve_document`. The two writes check the other table first (rule R3). |
| `src/orgknow/db/versions.py` | `insert_version`, `close_version` (only an open version, R10), and the two reads that hold the window conventions: `versions_at_release` (inclusive) and `version_at_time` (half-open). |
| `src/orgknow/db/chunks.py` | `add_chunks` (computes each `content_hash` as SHA-256 of the text, R13) and `add_embedding` (sends the vector as pgvector's text form). |
| `src/orgknow/ingestion/manifest.py` | `load_releases`: reads the manifest's release list and rejects it unless it is contiguous from `first` to `latest`, with ascending release dates and end of life after release. |
| `src/orgknow/ingestion/seed.py` | `make seed`: validates the release list, then upserts it in one transaction. |

Every data-access function takes a `psycopg.Connection` and leaves the transaction to the caller (ADR-005). `src/orgknow/db/` is the only place with SQL, and every query is a fixed string with parameters.

There is no server entry point yet (no ASGI server dependency). The app runs only inside tests, through FastAPI's `TestClient`.

Outside `src/`:

| Path | What it does |
|---|---|
| `config/corpus_manifest.yaml` | Defines the Stage 1 corpus: repos, releases 1.20–1.37 with release and end-of-life dates, per-SIG path allowlists, the traced KEPs, and the normalization strip lists (ADR-002 D6). |
| `config/corpus_manifest.lock.yaml` | The single record of the 77 corpus SHAs: each repo's head, the website SHA per release, and the default-branch SHA at each release date. |
| `spikes/` | S02's throwaway measurement scripts (`fetch.py`, `measure.py`, `renames.py`, `blog_identity.py`, `formats.py`, `source_formats.py`). They read a partial-clone cache outside the repo (`CORPUS_CACHE_DIR`). They're excluded from `mypy --strict`, never imported by `src/`, and to be rewritten in S04/S05. Results: `docs/research/corpus-spike-report.md`. |

## Database

`compose.yaml` runs one service: the pinned `pgvector/pgvector:0.8.1-pg18` image (ADR-004), published on `127.0.0.1:5433`. Data lives in the named volume `pgdata`, so it survives `make down`. A `pg_isready` healthcheck over TCP lets `make up` block until the database accepts connections.

The schema is specified in `docs/domain-model.md`:

| Table | Holds | Key rules |
|---|---|---|
| `releases` | One row per minor release (key `minor`, 24 = v1.24), seeded from the manifest | version matches minor; end of life after release |
| `documents` | One stable identity per document (`canonical_id`, `source_type`) | unique id with a known prefix; known source type |
| `document_aliases` | Old URLs and gate names pointing at a document | unique; never equal to a `canonical_id` (code check) |
| `document_versions` | One row per content change, with a release window and a date window | date windows of one document never overlap (`EXCLUDE … tstzrange … WITH &&`), so at most one is open |
| `chunks` | The embedded text of each version, by position | unique position per version; deleted with their version |
| `embeddings` | One `vector(1024)` per chunk per model | exactly 1024 numbers; deleted with their chunk |

There is no vector index yet (HNSW arrives with dense retrieval, S04-T5).

## Tests

| Directory | Needs | Covers |
|---|---|---|
| `tests/unit/` | nothing (no network, no DB) | settings loading, URL rewriting, package import; the manifest's release-list checks; naive datetimes rejected by the models; the spike scripts' pure functions (`test_spike_*.py`, replaced with the spikes in S04/S05) |
| `tests/integration/` | `make up` + `make migrate` | the extensions and 6 tables exist; `/health` and `/ready`; the releases upsert is idempotent; one test per domain-model rule (R1–R15), plus the allowed cases and the window edges on real PSP-page and v1.30-post data |

`tests/integration/conftest.py` marks every test in that directory `integration`, so `make check` excludes them and `make test-int` selects only them. Its `conn` fixture rolls back every test's writes, and `seeded_releases` loads the 18 releases inside that transaction, so tests work on an empty or a seeded database.

## Verification loop

| Where | What runs |
|---|---|
| Every commit | pre-commit: `ruff check --fix` and `ruff format` |
| `make check` | ruff format check, ruff lint, `mypy --strict` on `src/`, unit tests |
| `make test-int` | integration tests against the local database |
| CI (`.github/workflows/ci.yml`) | `check` job: `make check`. `integration` job: the same pgvector image as a service container, `make migrate` twice (the second run must be a no-op), a round trip down to `0001` and back up, then `make test-int`. |

CI calls the same Make targets as local development, and `UV_LOCKED=1` makes it fail if `uv.lock` is out of date. CI never runs `make seed`: tests seed what they need inside their own transaction.
