# ADR-004: Development toolchain

- **Status:** Proposed. Accepting it is task S01-T1.
- **Date:** 2026-09-22
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
| DB (local) | Docker Compose, **pinned** `pgvector/pgvector` image. Pin the Postgres major version to one RDS supports with pgvector. | Local and cloud stay the same | Floating `latest` tag: non-reproducible |
| Migrations | **Alembic** | Standard; versioned schema; runs in CI | Hand-written SQL files: no ordering or downgrade discipline |
| API | FastAPI (blueprint) | — | — |
| Task runner | **make** | Available everywhere, readable by agents and in CI | just / nox: an extra install |
| Hooks | pre-commit (ruff only) | Fast; heavier checks run in `make check` and CI | Running mypy/tests in hooks: too slow per commit |
| CI | GitHub Actions: a `check` job, plus an `integration` job with a pgvector service container | Same commands locally and in CI | — |
| Tracing | Langfuse **Cloud** (free tier) | Self-hosted Langfuse needs extra infrastructure that doesn't fit locally or on the cheap EC2 box. Final confirmation in ADR-006. | Self-hosting in Compose |

Deliberately **not** chosen yet: the data-access library (ADR-005), the LLM/embedding clients beyond Voyage (ADR-006), and the reranker (ADR-008).

## Consequences

- `make check` is the single local and CI gate. CI calls the Make targets rather than duplicating commands.
- Adding any tool outside this table requires amending this ADR.
- Before pinning, check the exact image tag and the Postgres version supported by RDS with pgvector. Record the pinned values here when accepting.
