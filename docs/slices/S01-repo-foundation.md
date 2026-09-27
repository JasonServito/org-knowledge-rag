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

- **Goal:** uv project; package `orgknow` under `src/`; `pyproject.toml` with ruff, mypy strict and pytest config; `.gitignore` (including `.env` and the corpus cache); `.gitattributes` with `* text=auto eol=lf`; `.python-version` pinned to 3.12; `.env.example`.
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

- **Goal:** README quickstart verified from a fresh clone, including the WSL2 prerequisite; `LICENSE` chosen (MIT or Apache-2.0; this covers your code, not the corpus); `docs/architecture.md` stub describing the current state; `docs/learning/S01-repo-foundation.md`.
- **Done when:** someone else could clone the repo and run it.

## Risks & unknowns

- Docker on your machine (resources, ARM vs. x86 image availability). Check this early in T4.
- Scope creep into "production" logging or config. That belongs to S14.

## Decisions expected

ADR-004 (accept).

## Retro (fill in at the end)

- **Shipped:**
  - All 8 tasks, in 4 PRs: #1 (T1), #2 (T2), #3 (T3–T7 batched; 427 added lines excluding the lockfile and docs), #4 (T8).
  - A `make` interface (`fmt`, `check`, `test-int`, `up`, `down`, `migrate`) that CI calls unchanged.
  - Compose Postgres 18 + pgvector 0.8.1 on `127.0.0.1:5433`.
  - Alembic with one migration (`0001`, the `vector` extension). CI runs it twice to prove idempotency.
  - A FastAPI factory with `/health` and `/ready`.
  - CI `check` and `integration` jobs. The `protect-main` ruleset requires both, with the branch up to date.
  - MIT license, a README quickstart, and `docs/architecture.md`.
  - ADR-004 Accepted, with two dated amendments: 2026-09-26 (psycopg, SQLAlchemy inside Alembic only, httpx2) and 2026-09-27 (pre-commit).
  - Numbers: 7 unit + 3 integration tests; 262 lines of Python in `src/` + `tests/`; `make check` about 1.5–2.3 s (target ≤ 1 min); CI `check` 19–21 s and `integration` 24–28 s; 4 runtime + 5 dev direct dependencies; no paid API calls.
- **Surprises:**
  - Two verification steps could pass for the wrong reason:
    - **The README's clone defaulted to `main`.** `git clone` checks out the default branch, so following the quickstart word for word before merging tests `main`, not the PR under review. The quickstart was verified on an explicit clone of `s01-t8-close`.
    - **A global pre-commit masked a missing dev dependency.** `uv run pre-commit install` succeeded because `uv run` falls back to `PATH`, where a global `uv tool install pre-commit` lived. pre-commit wasn't a project dependency, so a fresh machine would have failed. Fixed by pinning it in the dev group (ADR-004 amendment 2026-09-27), then verified with the global install removed: `uv sync` installed it from the lockfile.
  - Smaller findings, recorded as code comments:
    - The Postgres 18 image keeps data under `/var/lib/postgresql/<major>/`, so the volume mounts the parent directory.
    - The healthcheck must use TCP, because during first-start init Postgres listens only on the socket.
    - SQLAlchemy reads a bare `postgresql://` URL as psycopg2, so Alembic needs the `+psycopg` driver name.
    - Starlette's `TestClient` prefers `httpx2`.
- **Do differently:**
  - Verify a quickstart from a state that can't borrow from the machine: clone the branch under review explicitly (`git clone --branch <branch>`), and remove global tools that the project should provide.
  - When a check passes, ask what else could have made it pass before counting it as evidence.
- **Learning note:** [`docs/learning/S01-repo-foundation.md`](../learning/S01-repo-foundation.md). The AI drafted it at the developer's request and the developer reviewed it, as its header states.
