# ADR-005: Data access approach

- **Status:** Accepted (2026-10-04, decided in the S03-R1 design review)
- **Date:** 2026-10-04
- **Blueprint/spec refs:** §13; readiness gap #3; ADR-002 (the rules to enforce); ADR-004 (toolchain)

## Context

- S04 starts writing documents, versions, chunks and vectors, and S04–S09 add retrieval queries. Retrieval SQL is core code, so it must stay easy to read and explain.
- psycopg 3 is already the runtime driver (ADR-004 amendment 2026-09-26). SQLAlchemy is installed only because Alembic needs it, and is imported only in the migrations' `env.py`.
- The features this project leans on are Postgres-specific: pgvector distance operators, HNSW indexes, full-text search (S07), range types and exclusion constraints.
- ADR-002's rules (no overlapping windows, one current version, unique identity) must hold whichever code path writes the data.

## Decision

### D1. psycopg 3 with hand-written SQL

- All SQL lives in `src/orgknow/db/`. Each data-access function takes a `psycopg.Connection`. The caller owns the transaction.
- Inputs and outputs are Pydantic models.
- Prefer one fixed, readable query per use case over a query assembled from pieces. Use `psycopg.sql` composition only where a piece genuinely varies, never f-strings.
- Vectors are sent as a text literal cast to `vector` (`'[0.1,…]'::vector`), so the pgvector Python package isn't needed yet.

### D2. Rules are enforced by the database wherever SQL can express them

- Use `UNIQUE`, foreign keys, `CHECK`, and an `EXCLUDE` constraint for "date windows of one document never overlap". The exclusion constraint compares `document_id` with `=`, which in a GiST index needs the **`btree_gist`** extension. It ships with Postgres as a contrib module. Migration `0002` enables it.
- Two open-ended windows overlap, so the same constraint also enforces "at most one current version per document".
- Python checks only the rules the database can't express: a rule that spans two tables, a value the write function must compute itself, or an update allowed only from one state. `docs/domain-model.md` lists each rule and where it is enforced.
- Every rule has an integration test that breaks it on purpose and asserts the exact error.

**Checked on 2026-10-04,** against the pinned image, in rolled-back transactions:
- `btree_gist` 1.8 is available.
- The exclusion constraint rejects a second open window.
- Two real blog edits 5 minutes apart (the v1.30 release post, 2024-04-19) are stored.
- Inserting a new version before closing the old one is rejected.

## Alternatives considered

| Option | Why not |
|---|---|
| SQLAlchemy Core | It builds optional filters cleanly. But it's a second layer to learn and explain, and the Postgres-specific parts need dialect operators anyway. It stays the fallback if S09 needs many combined query variants (Consequences) |
| SQLAlchemy ORM | It hides the SQL that is this project's core logic |
| Rules checked in Python only | Any other writer (a script, a future worker in S14) skips them; check-then-insert can race |
| Unique/FK/check in the DB, overlap checked in Python ("A-lite") | Safe only while there's one writer. A bug quietly stores overlapping windows, which give wrong "as of v1.24" answers with no error |
| Triggers | Logic hidden in the database; the hardest option to test and explain |

## Consequences

- The SQL that runs is the SQL in the repo. It can be read, explained and pasted into `psql`.
- **mypy doesn't check SQL strings.** psycopg types its queries as `LiteralString`, but mypy 2.3.1 accepts an f-string query (tested 2026-10-04). Reviewers check for string-built SQL by hand.
- **Revisit in the S09 design review:** if the query modes and ablation stages need more than about 4 query variants that must be combined, compare against SQLAlchemy Core then. Switching means rewriting `src/orgknow/db/` queries; callers keep their function signatures.
- Errors arrive as psycopg exceptions (`UniqueViolation`, `CheckViolation`, `ExclusionViolation`, …). Superseding a version must close the old one before inserting the new one, in one transaction.
- `btree_gist` is recorded in ADR-004 (amendment 2026-10-04). It must be checked on the RDS instance in S15.
- Connection pooling isn't needed until the API serves queries (S12). It would be a new dependency then.

## Amendment 2026-10-13 (S14-R1 design review)

Consequences' "Connection pooling … would be a new dependency then" is decided: **no pool for now.** Decided in the S14-R1 design review (decision 2), after a devil's advocate argued for a pool.

- **API connections are autocommit, with a statement timeout** (`DB_STATEMENT_TIMEOUT_MS`, 10 s), opened per request by one helper in `db/`. `/ready` keeps its own fresh-connection ping.
- **Why autocommit:** `/query` held an open transaction during the LLM call. The design review probe (a slow fake generator against the dev database) saw the connection `idle in transaction` during generation. Autocommit removes it, and read consistency doesn't change: under READ COMMITTED each statement already took its own snapshot.
- **Why no pool:** a local connect + `SELECT 1` takes p50 10.8 ms (20 tries), and a full ask p50 8.7 s, p95 14.9 s, max 29.7 s (658 saved eval rows), so connecting is ~0.1% of a request. One uvicorn process runs plain `def` endpoints on 40 threads, so it opens at most ~40 connections.
- **Revisit trigger (S15):** measure RDS's `max_connections` and the peak open connections (API + worker). Add `psycopg_pool` (a bounded pool with a short wait mapped to 503) if the limit is under 2× the peak, or if the EC2 → RDS connect time is over 5% of a median ask.

| Option | Why not |
|---|---|
| `psycopg_pool`, at most 8 connections, a 2 s wait then 503 | A new dependency for a cost that is ~0.1% of a request today. The connection count, its real argument, can only be measured on RDS (the trigger above) |
| No change (non-autocommit connections) | The idle transaction was confirmed |
