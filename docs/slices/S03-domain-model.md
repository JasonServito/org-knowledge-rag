# S03: Domain model + migrations

- **Status:** 🟨
- **Blueprint stage:** pre-Stage 2 (readiness gap #3: the domain model)
- **Started:** 2026-10-04
- **Finished:**

## Outcome

A migrated Postgres schema that encodes the ADR-002/003 rules. Every rule in `docs/domain-model.md` is rejected by the database, or by tested code, when broken. The `releases` table is seeded from the manifest.

## Why now

S04 ingestion needs a place to write documents, versions, chunks and vectors. S02 measured the corpus, so the schema can be designed on real numbers instead of guesses. Fixing a schema is cheapest now, before any data or callers exist.

## Exit checks

- [ ] `docs/domain-model.md` approved by the developer (S03-T2).
- [ ] ADR-005 Accepted (S03-T1).
- [ ] Migration `0002` round-trips: `alembic downgrade 0001` then `alembic upgrade head`, with no errors and no domain tables left after the downgrade.
- [ ] `make test-int` has at least one test per rule in the domain model, each asserting the exact database error (or the code check) for a deliberate violation.
- [ ] `make seed` run twice leaves 18 `releases` rows (1.20–1.37) and changes nothing the second time.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| Tables: `releases`, `documents`, `document_aliases`, `document_versions`, `chunks`, `embeddings` | `search_vector` column + GIN index (S07) |
| Database constraints for the domain-model rules | `observed_lifecycle` (S09); relationships/decisions tables (S13) |
| Data-access functions that write these tables, with integration tests | HNSW vector index (S04-T5); retrieval queries (S04-T5+) |
| Releases seed from `config/corpus_manifest.yaml` | Ingestion, window derivation, idempotent re-ingest (S04-T2) |
| | Chunker and chunk-header contents (S04-T3); embedding provider and cache (S04-T4) |

## Metric to move

n/a (foundation).

## Tasks

These mirror `docs/backlog.md`; details live here.

### S03-T1: ADR-005, data access approach `[human]`

- **Goal:** decide how application code talks to Postgres, and where the domain-model rules are enforced.
- **Done when:** ADR-005 is Accepted. Decided in the S03-R1 sitting and committed with the run contract.

### S03-T2: `docs/domain-model.md` `[core]`

- **Goal:** entities, keys, constraints and validity-window rules, precise enough to write migration `0002` from.
- **Done when:** the developer has approved it. Drafted and approved in the S03-R1 sitting, and committed with the run contract.
- **Questions handed over by the spike** (report §8): one vector per chunk or per content hash; the CHANGELOG's release window; aliases hold both old URLs and old gate names.

### S03-T3: Migration `0002` `[core]`

- **Goal:** create the tables and constraints in `docs/domain-model.md`.
- **Done when:** it migrates up and down cleanly.
- **Deps:** T2.

### S03-T4: Data-access layer `[core]`

- **Goal:** the write functions S04 ingestion will call, in `src/orgknow/db/`.
- **Done when:** integration tests prove every rule in the domain model (for example, an overlapping window is rejected).
- **Deps:** T3.

### S03-T5: Seed the `releases` table `[commodity]`

- **Goal:** load version, release date and end of life from the manifest.
- **Done when:** re-running the seed is idempotent.
- **Deps:** T3.

## Risks & unknowns

- **The schema is designed before its first caller (S04-T2).** Mitigation: only the columns ADR-002 names plus the minimum to store chunks and vectors; S04 adds columns by migration if it needs them.
- **Two clocks can drift apart.** The database can't check that a version's date window matches its release window (a CHECK can't read the `releases` table). Ingestion derives one from the other (S04-T2) and tests it there.
- **Chunk-header contents are undecided (S04-T3).** They decide how many chunks share identical text, which affects the embedding-storage choice.

## Decisions expected (ADRs)

- ADR-005: data access approach (S03-T1).
- Domain-model decisions, recorded in `docs/domain-model.md`.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S03-R1: domain model storage

- **Status:** running
- **Branch:** `s03-r1-domain-model`
- **Tasks, in this order:** S03-T3 (migration `0002`) → S03-T5 (seed `releases`) → S03-T4 (data-access layer). T1 and T2 were completed in the sitting (ADR-005 Accepted; `docs/domain-model.md` approved).
- **Closes the slice:** yes. `/slice-retro` is the run's last commit, unless a task parks; then no retro.
- **Goal (plain words):** build the Store stage's tables and rules exactly as `docs/domain-model.md` says. Load the 18 releases from the manifest. Add the write functions S04 ingestion will call. Prove every rule with a test that breaks it on purpose.

#### Decisions (made in the sitting, 2026-10-04)

| # | Choice | Rejected | Why |
|---|---|---|---|
| 1 | psycopg 3 + hand-written SQL in `src/orgknow/db/` only; functions take a `psycopg.Connection`; the caller owns the transaction; Pydantic models at the boundary (ADR-005 D1) | SQLAlchemy Core; ORM | SQL stays visible and explainable; Postgres-specific features as-is. Revisit at S09 |
| 2 | Rules enforced by DB constraints wherever SQL can express them, including `EXCLUDE … tstzrange … WITH &&` with `btree_gist`; Python only for R3, R10, R13 (ADR-005 D2) | Python-only checks; "A-lite"; triggers | The DB refuses bad rows from any writer; one constraint gives both R8 and R9 |
| 3 | Release windows inclusive `[from, until]` as minor numbers; date windows half-open `[from, until)` as `timestamptz`; CHANGELOG-1.R = `[R, R]`; no-overlap on date windows only | Both half-open (needs a "1.38"); both inclusive with `date` | Every release bound is a real release (FK); same-day edits fit |
| 4 | `releases` keyed by `minor smallint` with a `version` display column; `bigint` identity ids elsewhere; aliases keyed by `alias`; embeddings keyed by `(chunk_id, model)` | Text release key (`'1.9' < '1.20'` is false); `canonical_id` as PK | Integer comparisons; short, uniform ids for citations |
| 5 | One vector per chunk per model, `vector(1024)`, deleted with its chunk | One vector per unique text hash | Under the spec's per-version header fields it saves nothing. Revisit trigger recorded for the S04 sitting |
| 6 | PyYAML moves dev → runtime in T5 (ADR-004 amendment 2026-10-04); `make seed` upserts (insert new, update dates of existing), never deletes, and validates the list first | Insert-only; seeding in a migration | 4 end-of-life dates (1.34–1.37) are planned and will change |
| 7 | Domain model approved, including its 11 proposals (prefix CHECK, R7, R10, hash formats, hash computed in code, EOL required, 6 source types, single `text` column, cascades, derived `version_status`, 2 read functions) | — | See `docs/domain-model.md` |

**Claude's calls (overrulable):**
- T5 runs before T4, so T4's tests reuse the seed.
- CI gets a down → up migration round trip.
- The manifest path comes from settings.
- Module layout inside `db/` and `ingestion/`.
- Tests run in a `force_rollback` transaction.

#### Handoffs between tasks

- **T3 → T5, T4:** the tables and named constraints of `docs/domain-model.md`, with the exact failure per rule (its "Failure" column).
- **T5 → T4:**
  - `Release` model + `load_releases(path)` (manifest → list) + `upsert_releases(conn, releases)`.
  - T4's test fixture seeds the real releases inside its rolled-back transaction.
- **T4 → S04:** the 10 functions in the domain model's "Data-access functions" table, with those names and behaviours.

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **Test isolation:**
  - Every integration test that writes uses a `conn` fixture: `psycopg.connect(...)` + `conn.transaction(force_rollback=True)`.
  - Expected violations run inside a nested `with conn.transaction():` (a savepoint) under `pytest.raises`.
  - No test may assume empty tables. The dev DB may already hold seeded releases.
- **CI never runs `make seed`.** Tests seed what they need inside their own transaction.
- **Superseding is close-then-insert.**
  - Insert-before-close must raise `ExclusionViolation` (tested).
  - Touching windows (`old.until == new.from`) are allowed.
- **Allowed, and tested as allowed:**
  - a gap (removed then re-added)
  - content A → B → A
  - two blog versions sharing release 30
  - two CHANGELOG versions sharing `[R, R]`
- **Timestamps:** naive datetimes are rejected by the Pydantic models (`AwareDatetime`), before reaching SQL.
- **`chunks.content_hash`:** computed inside `add_chunks` as SHA-256 of the UTF-8 `text`; never a parameter. Postgres can't generate it (`convert_to` isn't immutable; checked).
- **Vectors:** sent as a `'[…]'::vector` text literal. A wrong length raises `DataException` ("expected 1024 dimensions").
- **Manifest:**
  - YAML dates load as `date` objects; the key is `end_of_life` (column `end_of_life_date`).
  - Versions must be `1.N`, contiguous from `releases.first` to `releases.latest`; dates strictly ascending; end of life after release.
- **No SQL built with f-strings or `+`.** mypy doesn't catch it (tested). The reviewer checks by hand.
- **Migration `0002`:**
  - Raw SQL via `op.execute`, like `0001`.
  - `CREATE EXTENSION IF NOT EXISTS btree_gist`.
  - The downgrade drops tables in reverse dependency order, then `DROP EXTENSION IF EXISTS btree_gist`. It never touches `vector`.

#### Files in scope

- **T3:**
  - `src/orgknow/db/migrations/versions/0002_domain_tables.py`
  - `tests/integration/test_migrations.py`
  - `.github/workflows/ci.yml` (round-trip step: `uv run alembic downgrade 0001` then `make migrate`, before `make test-int`)
- **T5:**
  - `pyproject.toml`, `uv.lock` (PyYAML to runtime)
  - `src/orgknow/settings.py` (`corpus_manifest_path`, default `config/corpus_manifest.yaml`)
  - `src/orgknow/ingestion/__init__.py`
  - the manifest loader and seed entry point in `src/orgknow/ingestion/`
  - `src/orgknow/db/models.py`, `src/orgknow/db/releases.py`
  - `Makefile` (`seed` target)
  - `.env.example` (only if a new variable needs documenting)
  - `tests/unit/` (loader), `tests/integration/` (upsert), `tests/integration/conftest.py`
- **T4:**
  - `src/orgknow/db/models.py`
  - new `src/orgknow/db/` modules for documents/aliases, versions, chunks/embeddings
  - `tests/integration/conftest.py`
  - `tests/integration/` rule and window tests
  - `tests/unit/` (model validation)
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Retro:** `docs/learning/S03-*.md`, `docs/architecture.md`, `docs/backlog.md` (status flip), this slice doc's Retro section.
- **Out of scope:**
  - HNSW and `content_hash` indexes
  - retrieval queries
  - a `current_version` read
  - window derivation and re-ingest logic (S04)
  - any change to `config/corpus_manifest.yaml`

#### Proof map

| Task | Done when | Proof | Source of expected values |
|---|---|---|---|
| T3 | Migrates up | `make migrate` shows `0001 -> 0002`; a second `make migrate` is a no-op | Alembic output |
| T3 | Migrates down cleanly | `uv run alembic downgrade 0001` → no domain tables, no `btree_gist`, `vector` still installed (show the `psql` output) → `make migrate` again succeeds | Domain model's table list |
| T3 | Schema present | Integration test: the 6 tables and `btree_gist` exist | Domain model's table list |
| T3 | Stays verified | CI round-trip step green | CI log |
| T5 | Loads the manifest | Unit test: 18 releases, minor 20 → 37; 1.24 = 2022-05-03 with end of life 2023-07-28; 1.34 end of life 2026-10-27 | `config/corpus_manifest.yaml`, read by hand in the sitting |
| T5 | Rejects a bad list | Unit tests with small inline YAML: 1.25 missing; dates not ascending; end of life before release; a version not shaped `1.N` | Hand-written inputs |
| T5 | Idempotent | Integration test: upsert twice → 18 rows, identical contents; a changed end-of-life date updates in place (still 18 rows); upserting a shorter list deletes nothing | Manifest |
| T4 | R1–R15 each hold | One integration test per rule: break it, assert the exact error | Domain model's "Failure" column |
| T4 | Allowed cases stay allowed | Gap; A → B → A; touching windows; shared release 30; shared CHANGELOG `[R, R]` | ADR-002 D2/D3 + domain model |
| T4 | Release-window edges (inclusive) | **PSP page** (real): versions `[20,20]`, `[21,22]`, `[23,23]`, `[24,24]`, `[25, open]`, with alias `web:/docs/concepts/security/pod-security-policy/` on canonical `web:/docs/concepts/policy/pod-security-policy/` (URL form as the redirect file writes it; the URL normalization rule itself is S04's). `versions_at_release(22)` → v2 only; `versions_at_release(23)` → v3 only | Corpus trace in the sitting: blob changes at 1.20, 1.21, 1.23, 1.24, 1.25; redirect at 1.23 (`static/_redirects` line 162) |
| T4 | Date-window edges (half-open) | PSP date windows from release dates at 00:00 UTC: `version_at_time(2021-12-07T00:00Z)` → v3 (1.23's release date); one microsecond earlier → v2. **v1.30 release post** (real): v1 `[2024-04-19T14:56:34Z, 2024-04-19T15:01:40Z)`, v2 from 15:01:40Z; `version_at_time(14:58Z)` → v1; `version_at_time(15:01:40Z)` → v2; `versions_at_release(30)` → both | Manifest release dates; website `main` first-parent commit times read in the sitting |
| T4 | Hash computed (R13) | `add_chunks` with text `abc` stores `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` | FIPS 180-2 SHA-256 test vector |
| T4 | Supersede order | Insert before close → `ExclusionViolation`; close then insert → OK | Domain model, "Superseding a version" |
| T4 | Naive timestamps rejected | Unit test: a timezone-less datetime raises `ValidationError` | Domain model, data-access section |

#### Break-it rules

- **T3:** delete one table's `DROP` from the downgrade → `alembic downgrade 0001 && make migrate` fails with "already exists" → restore → `git diff` clean.
- **T5:**
  1. Replace the upsert with a plain `INSERT` → the idempotency test fails with `UniqueViolation`.
  2. Remove the contiguity check → the "1.25 missing" test fails.
- **T4:**
  1. **Most important.** Remove the `EXCLUDE` constraint from `0002`, then `alembic downgrade 0001 && make migrate` → the R8 and R9 tests fail. Restore, re-migrate, `git diff` clean.
  2. Remove the alias-vs-canonical check from `add_alias` → the R3 test fails.
  3. Drop the "only an open window" condition from `close_version` → the R10 test fails.

#### Real-data demos

- **T3:** `uv run alembic downgrade 0001 && make migrate`, then `docker compose exec -T db psql -U orgknow -d orgknow -c '\dt'` (output excerpt).
- **T5:**
  - `make seed`, then `docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT count(*), min(version), max(version), md5(string_agg(r::text, ',' ORDER BY minor)) FROM releases r"`
  - then `make seed` and the same query again: 18 rows, 1.20, 1.37, identical checksums.
- **T4:** `uv run pytest tests/integration -k psp -v` (output excerpt).

#### Bundle-level check

1. `make check`
2. `uv run alembic downgrade 0001 && make migrate`
3. `make seed`, the T5 checksum query, `make seed`, the query again (identical)
4. `make test-int`
5. `git status --short` is clean after every break-it restore

#### PR plan

- **1 PR.** If the size alarm trips (more than ~30 files or ~800 reviewable lines), split after T5:
  - PR 1, `s03-r1a-domain-model`: contract, migration, seed
  - PR 2: data access + rule tests, stacked on PR 1
- Greptile once per PR.

**Paid calls allowed:** none.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S03-*.md`
