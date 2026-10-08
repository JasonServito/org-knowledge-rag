# Architecture

This page describes only what exists in the code **today** (S05-R1). S03 added the domain tables, the functions that write and read them, and the releases seed. S04-R1 added the indexing path: `make ingest` stores versions and chunks for the S04 scope, and `make embed` stores one vector per distinct chunk text. S04-R2 added the answer path: `orgknow ask` embeds the question, finds the nearest chunk texts with an HNSW index, asks Claude for a structured answer that cites chunk ids, rejects any citation that wasn't retrieved, and prints the answer as JSON, with one Langfuse trace per ask. S05-R1 widened `make ingest` to the `full` scope: the docs pages of 3 SIGs, the website release records and the feature gates at every release 1.20 → 1.37, with a moved page or renamed gate kept as one document (later URLs and names become aliases), and `make reset-corpus` to rebuild from empty. There is no lexical search, rerank or authority scoring yet. It is updated as slices land. The planned pipeline (ingestion → retrieval → generation → eval) is described in `CLAUDE.md` and `docs/product-spec.md`.

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
  → renames (chains, aliases)           → VoyageEmbedder (urllib) → Voyage API
  → normalize/hash → history            → one vector per (content_hash, model)
  → plan_changes → versions
  → chunker → chunks
  ◄── partial clones (CORPUS_CACHE_DIR)
```

The answer path, `orgknow ask "<question>"` (`cli.py`):

```
  question
     │
     ▼
  retrieve (retrieval/dense.py) ── VoyageEmbedder, input_type "query" ──► Voyage API
     │  search (db/retrieval.py): the RETRIEVAL_TOP_K (10) nearest texts by cosine distance,
     │  through the HNSW index; each text once, with every release window it was valid in
     ▼
  answer (generation/generator.py) ── AnthropicGenerator, messages.parse ──► Anthropic API
     │  prompt (generation/prompt.py): one evidence block per hit
     │  validate (generation/validate.py): reject any cited id that wasn't retrieved;
     │  fill each citation in from its hit (title, section, windows, GitHub URL)
     ▼
  answer JSON on stdout; "tracing off" and errors on stderr

  Langfuse (only in cli.py, only with both keys): one trace per ask, named `ask`,
  with retrieve, generate and validate under it; flushed before the command exits
```

## Components

| Path | What it does |
|---|---|
| `src/orgknow/settings.py` | `Settings` (pydantic-settings) reads `DATABASE_URL` (required, plain `postgresql://` form), `DB_CONNECT_TIMEOUT_S`, the corpus paths (`CORPUS_MANIFEST_PATH`, `CORPUS_LOCK_PATH`, `CORPUS_CACHE_DIR`), `INGEST_SCOPE` (default `full`), `CLAIM_SYNONYMS`, `CHUNK_MAX_TOKENS` (512), the embedding settings (`VOYAGE_API_KEY`, `VOYAGE_API_URL`, `EMBEDDING_MODEL`, batch and per-run token limits), `RETRIEVAL_TOP_K` (10, at most 40), the generation settings (`GENERATION_MODEL` `claude-opus-5-5`, `GENERATION_EFFORT` `medium`, `GENERATION_MAX_TOKENS` 16,000, `ANTHROPIC_API_KEY`) and the tracing settings (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`) from the environment, falling back to `.env`. Keys are `SecretStr`. It is built inside factories, never at import time. |
| `src/orgknow/api/app.py` | `create_app(settings=None)` builds the FastAPI app. `GET /health` is liveness: always 200, never touches the database. `GET /ready` is readiness: 200 if the database answers, otherwise 503. |
| `src/orgknow/db/health.py` | `is_reachable()` opens a fresh psycopg connection with a timeout and runs `SELECT 1`. |
| `src/orgknow/db/url.py` | `with_psycopg_driver()` rewrites `postgresql://` to `postgresql+psycopg://`, the form SQLAlchemy needs. Only Alembic uses it. |
| `src/orgknow/db/migrations/` | Alembic environment and hand-written migrations (raw SQL, no autogenerate, no offline mode). `0001` enables `vector`. `0002` enables `btree_gist` and creates the 6 domain tables with 28 named constraints. `0003` re-keys `embeddings` by `(content_hash, model)` and indexes `chunks.content_hash`; its downgrade recreates `0002`'s empty table (vectors are a cache). `0004` adds the HNSW index on `embeddings.embedding` (`vector_cosine_ops`, pgvector's default build settings). |
| `src/orgknow/db/models.py` | Pydantic models at the data-access boundary (ADR-005): `Release`, `VersionData` / `NewVersion` / `Version` (timezone-aware datetimes only), `NewChunk` (no hash field), and the read results `VersionToChunk`, `TextToEmbed` and `Hit` (one retrieved chunk text: its cited chunk, distance, release windows, KEP claims and snapshot). |
| `src/orgknow/db/releases.py` | `upsert_releases`: inserts new releases and updates the dates of existing ones; never deletes. `list_releases`: the stored releases, oldest first (ingest's read-only check). |
| `src/orgknow/db/documents.py` | `create_document`, `add_alias`, `resolve_document`. The two writes check the other table first (rule R3). |
| `src/orgknow/db/versions.py` | `insert_version`, `close_version` (only an open version, R10), `list_versions` (a document's versions, oldest first), and the two reads that hold the window conventions: `versions_at_release` (inclusive) and `version_at_time` (half-open). |
| `src/orgknow/db/chunks.py` | `versions_without_chunks`, `add_chunks` (computes each `content_hash` as SHA-256 of the text, R13), `texts_without_embedding` (distinct texts with no vector for a model: the embedding cache check), `add_embedding` (by `content_hash`; sends the vector as pgvector's text form) and `delete_orphan_embeddings` (vectors whose hash no chunk has). |
| `src/orgknow/ingestion/manifest.py` | `load_releases`: reads the manifest's release list and rejects it unless it is contiguous from `first` to `latest`, with ascending release dates and end of life after release. `load_scope` resolves a named scope (`scopes:` block) to snapshots at the locked SHAs: one release-scoped group per source type (docs pages, release records, feature gates) from its `from_release`, and refuses a scope where two groups would read one file. `load_normalization` reads the strip lists and refuses one that contains a `never_strip` key. |
| `src/orgknow/ingestion/git_reader.py` | Reads files, committer times and git's similarity renames (`git diff -M50%` among given paths) from the partial clones with the `git` command. Skips symlinks, submodules and non-`.md` files (logged). Fetches missing blobs on demand; a git failure raises `GitError` and stops the run. |
| `src/orgknow/ingestion/normalize.py` | Decodes (BOM, CRLF), splits front matter, and hashes the normalized text (ADR-002 D2): strip-listed front-matter keys removed, link targets dropped, whitespace collapsed. `docs_state` / `kep_state` (README + first YAML document of `kep.yaml`). |
| `src/orgknow/ingestion/identity.py` | Canonical ids (ADR-002 D4): `web:` + docs path (`_index.md` / `index.md` → its folder), `gate:` + a gate's front-matter `title`, `kep:<n>`, and alias ids from front-matter `aliases`. |
| `src/orgknow/ingestion/renames.py` | Pure functions that link each release's files to the next release's into chains, one per document: the redirect-file parser, the ordered link rules for web pages (same URL, redirect, `aliases`) and for gate files (same path, same title, `former_titles`), then git similarity ≥ 50% for what's left. Conflicts and links across source types are refused; unmatched adds and deletes are listed. |
| `src/orgknow/ingestion/history.py` | Pure functions from snapshots to versions: `release_history` (docs; a change at release R2 closes the previous version at R2 − 1, dates at release-day 00:00 UTC) and `date_history` (KEPs; a version starts at the last committer time touching its files). `plan_changes` compares derived and stored versions: insert all, nothing, close + insert, or a `HistoryMismatch`. |
| `src/orgknow/ingestion/chunker.py` | A 4-rule line scanner (headings outside fences, indented fences, Hugo `highlight` blocks), sections by heading, packing by whole blocks up to `CHUNK_MAX_TOKENS` (chars ÷ 4), and the fixed chunk header (source, title, document id, heading path). A gate's body starts with its `stages` (and `removed`) as YAML. Pure functions. |
| `src/orgknow/ingestion/ingest.py` | `make ingest`: first checks, read-only, that the `releases` table holds every manifest release with the same dates (`list_releases`), and stops with "run `make seed`" before any git read if not; then reads each release-scoped group at every release, links pages and gate files into chains (separately, each with its own rules and ids), derives one document per chain (refusing two chains with one id), stores new versions and aliases with one transaction per document, then chunks every version that has none. Prints a summary; a mismatch or an unparseable document makes the exit code non-zero while other documents still ingest. |
| `src/orgknow/embeddings/embedder.py` | The `Embedder` protocol (`model`, `embed(texts, input_type)`), reused for query embeddings in S04-R2. |
| `src/orgknow/embeddings/voyage.py` | `VoyageEmbedder`: one POST per batch with `urllib` (no SDK), 1024 dimensions, retries on 429/5xx only; pure `request_body` and `parse_response` (reorders by `index`, refuses wrong lengths). |
| `src/orgknow/embeddings/embed.py` | `make embed`: lists texts with no vector, refuses to start above `EMBED_MAX_TOKENS_PER_RUN`, deletes orphan vectors, then sends batches of at most 128 texts and 60,000 estimated tokens (one transaction per batch). |
| `src/orgknow/ingestion/seed.py` | `make seed`: validates the release list, then upserts it in one transaction. |
| `src/orgknow/db/retrieval.py` | `search`: one fixed query. The `k` texts nearest a question vector among one model's vectors (index-ordered by cosine distance, so HNSW is used; vectors no chunk uses are skipped), then each text expanded to the chunks holding it: the chunk in the newest version is cited, and every version's release window is listed, never merged. Ties are ordered by `content_hash`. |
| `src/orgknow/retrieval/dense.py` | `retrieve`: embeds the question with `input_type="query"`, then calls `search` with `RETRIEVAL_TOP_K`. Its `main()` prints the top hits (a demo). |
| `src/orgknow/generation/schema.py` | The answer models: `ModelAnswer` (what the model returns: status, answer, cited chunk ids, reason), `Evidence` (one filled-in citation), `Answer` (what `ask` prints) and `AnswerTrace` (what the trace records about the model call; never printed). |
| `src/orgknow/generation/prompt.py` | The fixed system prompt and the user message: one evidence block per hit (chunk id, release windows, a KEP's claimed status and stage, the chunk text), then the question. Pure functions. |
| `src/orgknow/generation/generator.py` | `answer`: prompt, one model call, validate, fill in. No hits: `insufficient_evidence` without a call. `AnthropicGenerator` calls `messages.parse` with the answer schema and the effort setting, behind the `Generator` protocol. A refusal, a cut-off or output off the schema raises `GenerationError` with the stop reason. |
| `src/orgknow/generation/validate.py` | The citation validator: an answer citing an id that wasn't retrieved, an `answered` with no citations or an `insufficient_evidence` with no reason becomes `insufficient_evidence` with reason `citation_validation_failed: [...]`. `fill_in` builds each citation from its hit, with a GitHub URL at the snapshot commit. Pure functions. |
| `src/orgknow/cli.py` | `orgknow ask "<question>"` (argparse; the `orgknow` console script). `main` checks the keys and builds the real Voyage, Anthropic and Langfuse clients; `ask` retrieves, answers and prints the JSON. Without both Langfuse keys it prints "tracing off" and builds no Langfuse client. Expected failures (a `GenerationError`, the Anthropic SDK's API errors, the Voyage client's errors) print one stderr line and exit 1; an empty question exits 2. The only caller of Langfuse: the trace holds the question, `retrieve` (k, model, chunk ids and distances), `generate` (model, effort, prompt, output, token usage, stop reason), `validate` (result, rejected ids) and the final JSON, and never the settings or a key. |

Every data-access function takes a `psycopg.Connection` and leaves the transaction to the caller (ADR-005). `src/orgknow/db/` is the only place with SQL, and every query is a fixed string with parameters.

There is no server entry point yet (no ASGI server dependency). The app runs only inside tests, through FastAPI's `TestClient`. The command-line entry point is the `orgknow` console script (`[project.scripts]` in `pyproject.toml`).

Outside `src/`:

| Path | What it does |
|---|---|
| `config/corpus_manifest.yaml` | Defines the Stage 1 corpus: repos, releases 1.20–1.37 with release and end-of-life dates, per-SIG path allowlists, the traced KEPs, and the normalization strip lists (ADR-002 D6). |
| `config/corpus_manifest.lock.yaml` | The single record of the 77 corpus SHAs: each repo's head, the website SHA per release, and the default-branch SHA at each release date. |
| `eval/results/s04/` | S04-T8's seed run: each `orgknow ask` output for seeds #6–#10, a readable top 10 per seed, selected trace fields (usage, retrieved ids), and failure notes with verdicts. S06 defines the real results format. |
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

`embeddings.embedding` has an HNSW index for cosine distance (`0004`). On 20 real queries it returned the same top 10 as an exact scan (200 of 200).

After `make seed`, `make ingest` and `make embed` on the S04 scope, the dev database held 44 documents (43 docs pages, KEP-2579), 220 versions, 4,967 chunks with 1,583 distinct texts, and 1,583 `voyage-4-large` vectors. After `make reset-corpus && make ingest` on the `full` scope (S05-R1), it holds 564 documents (64 docs pages, 8 release records, 491 feature-gate documents, KEP-2579), 1,332 versions, 9 aliases and 10,509 chunks. The 1,583 vectors are kept as a cache; the new texts are embedded in S05-T9.

## Tests

| Directory | Needs | Covers |
|---|---|---|
| `tests/unit/` | nothing (no network, no DB) | settings loading, URL rewriting, package import; the manifest's release-list, scope and strip-list checks; naive datetimes rejected by the models; normalization and hashing, canonical ids, version histories and `plan_changes` (real KEP-2579 snapshots), the git reader on a tiny local repo (including git's similarity score on real gate files); redirect parsing and the link rules of pages and gate files; a document from its chain (ids, aliases, windows); the chunker on real corpus excerpts; embedding batching, request and response handling, and the run cap; the answer step with the fake generator and a mocked Anthropic transport (validator, fill-in, prompt blocks, refusal and cut-off errors, no model call without hits); the spike scripts' pure functions (`test_spike_*.py`) |
| `tests/integration/` | `make up` (`make test-int` migrates the test database) | the extensions and 6 tables exist, `0003`'s key and index, and `0004`'s HNSW index; `/health` and `/ready`; the releases upsert is idempotent and `list_releases` reads it back; one test per domain-model rule (R1–R15), plus the allowed cases and the window edges on real PSP-page and v1.30-post data; ingestion of real fixture files from a tiny git repo (windows, alias, idempotent re-run, close + insert, mismatch, a moved release record, the feature-gate cases and a gate's stored chunk text), and its read-only releases check (a missing or re-dated release stops it before any write or git read); embedding with a call-counting fake (a second run makes 0 calls; orphan cleanup; the run cap); dense retrieval (order and distances, one hit per text with every window, orphan and other-model vectors skipped, ties, `input_type="query"`); `orgknow ask` with the fakes (the printed JSON, "tracing off" with no Langfuse keys and no secret printed, one-line errors with exit 1, an empty question exits 2, a missing API key exits 1) |

`tests/integration/conftest.py` marks every test in that directory `integration`, so `make check` excludes them and `make test-int` selects only them. Integration tests connect only to `TEST_DATABASE_URL` (the `orgknow_test` database that `make up` creates), so data ingested into the dev database never collides with test rows. The `conn` fixture rolls back every test's writes, and `seeded_releases` loads the 18 releases inside that transaction, so tests work on an empty or a seeded database. `tests/conftest.py` holds the `make_git_repo` fixture (a tiny git repo with controlled committer dates), the fake embedder and the fake generator. No test calls Voyage, Anthropic or Langfuse. `tests/fixtures/` holds small real corpus files, pinned.

## Verification loop

| Where | What runs |
|---|---|
| Every commit | pre-commit: `ruff check --fix` and `ruff format` |
| `make check` | ruff format check, ruff lint, `mypy --strict` on `src/`, unit tests |
| `make test-int` | migrates the test database, then runs the integration tests against it |
| CI (`.github/workflows/ci.yml`) | `check` job: `make check`. `integration` job: the same pgvector image as a service container, `make migrate` twice (the second run must be a no-op), a round trip down to `0001` and back up, then `make test-int` with `TEST_DATABASE_URL` set to the service database. |

CI calls the same Make targets as local development, and `UV_LOCKED=1` makes it fail if `uv.lock` is out of date. CI never runs `make seed`: tests seed what they need inside their own transaction.
