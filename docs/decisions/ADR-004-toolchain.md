# ADR-004: Development toolchain

- **Status:** Accepted
- **Date:** 2026-09-26
- **Blueprint refs:** §9, §23.3, §26; readiness gaps #9, #10

## Context

The agent needs a fixed, boring toolchain so it doesn't pick tools per task. The choices should be:

- fast, so `make check` finishes in about a minute
- widely used, so they are easy to explain in interviews
- consistent with the AWS target: RDS PostgreSQL with pgvector

## Decision

| Concern | Choice | Why | Main alternative rejected |
|---|---|---|---|
| Python | 3.12 (blueprint: 3.11+) | Current, well supported by the libraries | 3.13: possible library lag, little benefit here |
| Env/deps | **uv** (lockfile committed) | Fast, one tool for venv + lock + run | Poetry: slower, and a second tool to learn |
| Lint/format | **ruff** (lint + format) | One fast tool replaces flake8, isort and black | Separate tools: more config, slower |
| Types | **mypy `--strict`** on `src/` | Most widely known; strict mode catches contract drift early | pyright: faster, but less common in Python backend interviews |
| Tests | **pytest** with `tests/unit` and `tests/integration` (marker-separated) | Standard | — |
| Config | **pydantic-settings** + `.env` (gitignored), `.env.example` committed | Typed config; maps to SSM Parameter Store later | Hand-rolled `os.environ` parsing |
| DB (local) | Docker Compose, **pinned** `pgvector/pgvector:0.8.1-pg18` image (Postgres 18, pgvector 0.8.1) | Matches RDS PostgreSQL 18, which ships pgvector 0.8.1 (AWS's RDS PostgreSQL 18 announcement), so local and cloud stay the same | Floating `latest` tag: non-reproducible |
| Dev environment | macOS/Linux, or **WSL2 (Ubuntu)** on Windows. Native Windows is unsupported. | Parity with CI (`ubuntu-latest`) and EC2; one Makefile and one shell | Native Windows: needs cross-platform Make recipes; CRLF line-ending issues |
| Migrations | **Alembic** | Standard; versioned schema; runs in CI | Hand-written SQL files: no ordering or downgrade discipline |
| API | FastAPI (blueprint) | — | — |
| Task runner | **make** | Available everywhere, readable by agents and in CI | just / nox: an extra install |
| Hooks | pre-commit (ruff only) | Fast; heavier checks run in `make check` and CI | Running mypy/tests in hooks: too slow per commit |
| CI | GitHub Actions: a `check` job, plus an `integration` job with a pgvector service container | Same commands locally and in CI | — |
| Tracing | Langfuse **Cloud** (free tier) | Self-hosted Langfuse needs extra infrastructure that doesn't fit locally or on the cheap EC2 box. Final confirmation in ADR-006. | Self-hosting in Compose |

**Note on the DB pin:** we pin by tag, not by digest, so that rebuilt images pick up Postgres minor (patch) releases. The cost: a tag can be moved to a newer image, so two pulls are not guaranteed to be byte-identical; the recorded digest shows exactly which image was tested. Tested locally: PostgreSQL 18.2, digest `sha256:508c5290cda481d4f5f846446a26e9c1b804766828a394a5861de1b348a18b4c`. Recheck the pgvector version on the real RDS instance in S15.

Deliberately **not** chosen yet: the data-access library (ADR-005), the LLM/embedding clients beyond Voyage (ADR-006), and the reranker (ADR-008).

## Consequences

- `make check` is the single local and CI gate. CI calls the Make targets rather than duplicating commands.
- Adding any tool outside this table requires amending this ADR.
- Pinned values: image `pgvector/pgvector:0.8.1-pg18`; Postgres major version 18; Python 3.12.

## Amendment 2026-09-26

S01-T5 and S01-T6 need libraries that the table above implies but doesn't name. Added with the developer's approval:

- **`psycopg[binary]`** (psycopg 3, runtime): the Postgres driver, used by Alembic and by the `/ready` database ping. The `binary` extra bundles libpq, so no system package is needed. Rejected: psycopg2, the older driver, now in maintenance mode.
- **SQLAlchemy** (transitive, via Alembic): imported only in `src/orgknow/db/migrations/env.py`, because Alembic runs migrations through a SQLAlchemy engine. This is **not** a data-access decision; ADR-005 makes that choice in S03.
