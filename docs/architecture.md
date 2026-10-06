# Architecture

This page describes only what exists in the code **today** (S04-R1, indexing path). S03 added the domain tables, the functions that write and read them, and the releases seed. S04-R1 added the indexing path: `make ingest` stores versions and chunks for the S04 scope, and `make embed` stores one vector per distinct chunk text. Nothing reads the vectors yet: dense retrieval is S04-T5. It is updated as slices land. The planned pipeline (ingestion → retrieval → generation → eval) is described in `CLAUDE.md` and `docs/product-spec.md`.

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
  psycopg               │  (db/releases.py)         │  0003: embeddings keyed by chunk text
        │               │  psycopg                  │
        ▼               ▼                           ▼
   Postgres 18 + pgvector 0.8.1 + btree_gist
   (Docker Compose, localhost:5433; dev DB `orgknow`, test DB `orgknow_test`)
        ▲
        │  psycopg, hand-written SQL (ADR-005)
  data-access functions (db/documents.py, db/versions.py, db/chunks.py)
        ▲                                   ▲
        │                                   │
  make ingest (ingestion/ingest.py)     make embed (embeddings/embed.py)
  manifest scope + lock → git_reader    chunk texts with no vector → batches
  → normalize/hash → history            → VoyageEmbedder (urllib) → Voyage API
  → plan_changes → versions             → one vector per (content_hash, model)
  → chunker → chunks
  ◄── partial clones (CORPUS_CACHE_DIR)
```

## Components

| Path | What it does |
|---|---|
| `src/orgknow/settings.py` | `Settings` (pydantic-settings) reads `DATABASE_URL` (required, plain `postgresql://` form), `DB_CONNECT_TIMEOUT_S`, the corpus paths (`CORPUS_MANIFEST_PATH`, `CORPUS_LOCK_PATH`, `CORPUS_CACHE_DIR`), `INGEST_SCOPE` (default `s04`), `CLAIM_SYNONYMS`, `CHUNK_MAX_TOKENS` (512) and the embedding settings (`VOYAGE_API_KEY`, `VOYAGE_API_URL`, `EMBEDDING_MODEL`, batch and per-run token limits) from the environment, falling back to `.env`. It is built inside factories, never at import time. |
| `src/orgknow/api/app.py` | `create_app(settings=None)` builds the FastAPI app. `GET /health` is liveness: always 200, never touches the database. `GET /ready` is readiness: 200 if the database answers, otherwise 503. |
| `src/orgknow/db/health.py` | `is_reachable()` opens a fresh psycopg connection with a timeout and runs `SELECT 1`. |
| `src/orgknow/db/url.py` | `with_psycopg_driver()` rewrites `postgresql://` to `postgresql+psycopg://`, the form SQLAlchemy needs. Only Alembic uses it. |
| `src/orgknow/db/migrations/` | Alembic environment and hand-written migrations (raw SQL, no autogenerate, no offline mode). `0001` enables `vector`. `0002` enables `btree_gist` and creates the 6 domain tables with 28 named constraints. `0003` re-keys `embeddings` by `(content_hash, model)` and indexes `chunks.content_hash`; its downgrade recreates `0002`'s empty table (vectors are a cache). |
| `src/orgknow/db/models.py` | Pydantic models at the data-access boundary (ADR-005): `Release`, `VersionData` / `NewVersion` / `Version` (timezone-aware datetimes only), `NewChunk` (no hash field), and the read results `VersionToChunk` and `TextToEmbed`. |
| `src/orgknow/db/releases.py` | `upsert_releases`: inserts new releases and updates the dates of existing ones; never deletes. |
| `src/orgknow/db/documents.py` | `create_document`, `add_alias`, `resolve_document`. The two writes check the other table first (rule R3). |
| `src/orgknow/db/versions.py` | `insert_version`, `close_version` (only an open version, R10), `list_versions` (a document's versions, oldest first), and the two reads that hold the window conventions: `versions_at_release` (inclusive) and `version_at_time` (half-open). |
| `src/orgknow/db/chunks.py` | `versions_without_chunks`, `add_chunks` (computes each `content_hash` as SHA-256 of the text, R13), `texts_without_embedding` (distinct texts with no vector for a model: the embedding cache check), `add_embedding` (by `content_hash`; sends the vector as pgvector's text form) and `delete_orphan_embeddings` (vectors whose hash no chunk has). |
| `src/orgknow/ingestion/manifest.py` | `load_releases`: reads the manifest's release list and rejects it unless it is contiguous from `first` to `latest`, with ascending release dates and end of life after release. `load_scope` resolves a named scope (`scopes:` block) to snapshots at the locked SHAs. `load_normalization` reads the strip lists and refuses one that contains a `never_strip` key. |
| `src/orgknow/ingestion/git_reader.py` | Reads files and committer times from the partial clones with the `git` command. Skips symlinks, submodules and non-`.md` files (logged). Fetches missing blobs on demand; a git failure raises `GitError` and stops the run. |
| `src/orgknow/ingestion/normalize.py` | Decodes (BOM, CRLF), splits front matter, and hashes the normalized text (ADR-002 D2): strip-listed front-matter keys removed, link targets dropped, whitespace collapsed. `docs_state` / `kep_state` (README + first YAML document of `kep.yaml`). |
| `src/orgknow/ingestion/identity.py` | Canonical ids (ADR-002 D4): `web:` + docs path (`_index.md` / `index.md` → its folder), `kep:<n>`, and alias ids from front-matter `aliases`. |
| `src/orgknow/ingestion/history.py` | Pure functions from snapshots to versions: `release_history` (docs; a change at release R2 closes the previous version at R2 − 1, dates at release-day 00:00 UTC) and `date_history` (KEPs; a version starts at the last committer time touching its files). `plan_changes` compares derived and stored versions: insert all, nothing, close + insert, or a `HistoryMismatch`. |
| `src/orgknow/ingestion/chunker.py` | A 4-rule line scanner (headings outside fences, indented fences, Hugo `highlight` blocks), sections by heading, packing by whole blocks up to `CHUNK_MAX_TOKENS` (chars ÷ 4), and the fixed chunk header (source, title, document id, heading path). Pure functions. |
| `src/orgknow/ingestion/ingest.py` | `make ingest`: upserts releases, collects each document's snapshots, stores new versions with one transaction per document, then chunks every version that has none. Prints a summary; a mismatch or an unparseable document makes the exit code non-zero while other documents still ingest. |
| `src/orgknow/embeddings/embedder.py` | The `Embedder` protocol (`model`, `embed(texts, input_type)`), reused for query embeddings in S04-R2. |
| `src/orgknow/embeddings/voyage.py` | `VoyageEmbedder`: one POST per batch with `urllib` (no SDK), 1024 dimensions, retries on 429/5xx only; pure `request_body` and `parse_response` (reorders by `index`, refuses wrong lengths). |
| `src/orgknow/embeddings/embed.py` | `make embed`: lists texts with no vector, refuses to start above `EMBED_MAX_TOKENS_PER_RUN`, deletes orphan vectors, then sends batches of at most 128 texts and 60,000 estimated tokens (one transaction per batch). |
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
| `embeddings` | One `vector(1024)` per distinct chunk text per model (key `(content_hash, model)`); the table is the embedding cache | exactly 1024 numbers; well-formed hash; vectors no chunk uses are deleted by `make embed` |

There is no vector index yet (HNSW arrives with dense retrieval, S04-T5).

After `make seed`, `make ingest` and `make embed` on the S04 scope, the dev database holds 44 documents (43 docs pages, KEP-2579), 220 versions, 4,967 chunks with 1,583 distinct texts, and 1,583 `voyage-4-large` vectors.

## Tests

| Directory | Needs | Covers |
|---|---|---|
| `tests/unit/` | nothing (no network, no DB) | settings loading, URL rewriting, package import; the manifest's release-list, scope and strip-list checks; naive datetimes rejected by the models; normalization and hashing, canonical ids, version histories and `plan_changes` (real KEP-2579 snapshots), the git reader on a tiny local repo; the chunker on real corpus excerpts; embedding batching, request and response handling, and the run cap; the spike scripts' pure functions (`test_spike_*.py`) |
| `tests/integration/` | `make up` (`make test-int` migrates the test database) | the extensions and 6 tables exist, and `0003`'s key and index; `/health` and `/ready`; the releases upsert is idempotent; one test per domain-model rule (R1–R15), plus the allowed cases and the window edges on real PSP-page and v1.30-post data; ingestion of real fixture files from a tiny git repo (windows, alias, idempotent re-run, close + insert, mismatch); embedding with a call-counting fake (a second run makes 0 calls; orphan cleanup; the run cap) |

`tests/integration/conftest.py` marks every test in that directory `integration`, so `make check` excludes them and `make test-int` selects only them. Integration tests connect only to `TEST_DATABASE_URL` (the `orgknow_test` database that `make up` creates), so data ingested into the dev database never collides with test rows. The `conn` fixture rolls back every test's writes, and `seeded_releases` loads the 18 releases inside that transaction, so tests work on an empty or a seeded database. `tests/conftest.py` holds the `make_git_repo` fixture (a tiny git repo with controlled committer dates) and the fake embedder. `tests/fixtures/` holds small real corpus files, pinned.

## Verification loop

| Where | What runs |
|---|---|
| Every commit | pre-commit: `ruff check --fix` and `ruff format` |
| `make check` | ruff format check, ruff lint, `mypy --strict` on `src/`, unit tests |
| `make test-int` | migrates the test database, then runs the integration tests against it |
| CI (`.github/workflows/ci.yml`) | `check` job: `make check`. `integration` job: the same pgvector image as a service container, `make migrate` twice (the second run must be a no-op), a round trip down to `0001` and back up, then `make test-int` with `TEST_DATABASE_URL` set to the service database. |

CI calls the same Make targets as local development, and `UV_LOCKED=1` makes it fail if `uv.lock` is out of date. CI never runs `make seed`: tests seed what they need inside their own transaction.
