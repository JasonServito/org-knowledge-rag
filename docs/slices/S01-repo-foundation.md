# S01: Repo foundation

- **Status:** 🟨
- **Blueprint stage:** 1
- **Started:**
- **Finished:**

## Outcome

A fresh clone runs `make up && make migrate && make check && make test-int` green, locally and in GitHub Actions.

## Why now

Every later slice depends on a fast, trustworthy verification loop. Setting it up now is cheap; retrofitting quality gates onto a grown codebase is not.

## Exit checks

- [ ] Fresh clone + README quickstart works end to end, on your machine.
- [ ] `make check` ≤ 1 min; `make test-int` green.
- [ ] CI `check` and `integration` jobs green on a PR.
- [ ] `/ready` returns 200 with the DB up and 503 with it down.
- [ ] ADR-004 Accepted; code license chosen; learning note S01 written.

## Scope

| In | Out (explicitly) |
|---|---|
| Toolchain per ADR-004, Makefile, Compose Postgres + pgvector, Alembic with the `vector` extension, FastAPI `/health` + `/ready`, CI, README quickstart | Domain tables (S03), ingestion (S04), logging framework/request IDs (S14), Dockerfile for the app (S15), Langfuse (S04) |

## Metric to move

n/a (foundation).

## Tasks

### S01-T1: Accept ADR-004 `[human]`

- **Goal:** confirm or amend the toolchain before any code exists.
- **Done when:** ADR-004 is Accepted, with the pgvector image tag and Postgres major version pinned.
- **Notes:** check which Postgres major versions RDS supports with pgvector, and match it locally.

### S01-T2: Project scaffold `[commodity]`

- **Goal:** uv project; package `orgknow` under `src/`; `pyproject.toml` with ruff, mypy strict and pytest config; `.gitignore` (including `.env` and the corpus cache); `.env.example`.
- **Done when:** `uv run pytest` passes one smoke test, and `uv run mypy src` is clean.
- **Notes:** the package name `orgknow` is a placeholder. Rename it now or never.

### S01-T3: Makefile + pre-commit `[commodity]`

- **Goal:** targets `fmt`, `check`, `test-int`, `up`, `down`, `migrate`. `check` = ruff format check + ruff lint + mypy + unit tests.
- **Done when:** `make check` is green and fast.
- **Notes:** CI must call these targets, not copy the commands.

### S01-T4: Local Postgres `[commodity]`

- **Goal:** Compose service with the pinned pgvector image, a healthcheck, and a named volume. `settings.py` reads `DATABASE_URL`.
- **Done when:** `make up` waits for healthy.

### S01-T5: Alembic + migration 0001 `[commodity]`

- **Goal:** Alembic configured from settings; `0001` runs `CREATE EXTENSION IF NOT EXISTS vector`.
- **Done when:** `make migrate` is idempotent, and an integration test asserts the extension exists.
- **Learn:** what a migration is, why it's versioned, and upgrade vs. downgrade.

### S01-T6: FastAPI skeleton `[commodity]`

- **Goal:** app factory; `GET /health` (process alive); `GET /ready` (DB reachable).
- **Done when:** integration tests cover 200 and 503.
- **Learn:** liveness vs. readiness, and why load balancers and orchestrators treat them differently.

### S01-T7: CI `[commodity]`

- **Goal:** a GitHub Actions workflow with a `check` job, and an `integration` job using a pgvector service container.
- **Done when:** both jobs are green on a PR, and uv's cache makes reruns fast.

### S01-T8: Docs + license `[human]`

- **Goal:** README quickstart verified from a fresh clone; `LICENSE` chosen (MIT or Apache-2.0; this covers your code, not the corpus); `docs/architecture.md` stub describing the current state; `docs/learning/S01-repo-foundation.md`.
- **Done when:** someone else could clone the repo and run it.

## Risks & unknowns

- Docker on your machine (resources, ARM vs. x86 image availability). Check this early in T4.
- Scope creep into "production" logging or config. That belongs to S14.

## Decisions expected

ADR-004 (accept).

## Retro (fill in at the end)

- **Shipped:**
- **Surprises:**
- **Do differently:**
- **Learning note:**
