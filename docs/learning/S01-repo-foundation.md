# Learning note: S01 Repo foundation

*Written by me, in my own words. The AI may critique it but doesn't write it.*

## In my own words (5–8 sentences)

What we built, how it works end to end, and why it matters to the project's thesis.

## Decisions and trade-offs

| Decision | Alternative rejected | Why | What it cost us |
|---|---|---|---|
| uv for the environment and dependencies, with `uv.lock` committed (ADR-004) | | | |
| ruff for lint + format, `mypy --strict` on `src/` (ADR-004) | | | |
| Local DB is the pinned `pgvector/pgvector:0.8.1-pg18` image, pinned by tag rather than digest (ADR-004) | | | |
| Compose publishes Postgres on `127.0.0.1:5433`, not 5432 | | | |
| Alembic with hand-written migrations (no autogenerate); `0001` only runs `CREATE EXTENSION IF NOT EXISTS vector` | | | |
| psycopg 3 as the driver; SQLAlchemy used only inside Alembic's `env.py` (ADR-004 amendment 2026-09-26) | | | |
| `Settings()` built inside factories, never at import time; unit tests use `Settings(_env_file=None)` | | | |
| `/health` (liveness) never touches the DB; `/ready` (readiness) pings it and returns 503 on failure | | | |
| Integration tests are marked by directory in `conftest.py` and excluded from `make check` | | | |
| CI calls the same Make targets as local work, with `UV_LOCKED=1`, and runs `make migrate` twice | | | |
| pre-commit runs ruff only, and is pinned in the dev dependency group (ADR-004 amendment 2026-09-27) | | | |
| WSL2 Ubuntu on Windows; native Windows unsupported (ADR-004) | | | |
| MIT license for the code | | | |

## Concepts I now understand

Link to glossary terms; add a sentence on anything subtle.

## Interview Q&A

Generate the questions with `/slice-retro`, then answer them myself, then ask the chat assistant to grade the answers.

1. **Q:** What's the difference between `/health` and `/ready`, and why must `/health` not check the database? [`src/orgknow/api/app.py`, `tests/integration/test_api.py`]
   **A:**
2. **Q:** Why pin the pgvector image by tag instead of using `latest` or a digest, and why Postgres 18 specifically? [ADR-004, note on the DB pin]
   **A:**
3. **Q:** What does it mean that `make migrate` is idempotent, how do you prove it, and why does it matter? [`0001_enable_vector_extension.py`, `.github/workflows/ci.yml`]
   **A:**
4. **Q:** Why is `Settings()` built inside `create_app` instead of at import time, and how do unit tests keep a developer's `.env` out? [`src/orgknow/api/app.py`, `CLAUDE.md` Code conventions]
   **A:**
5. **Q:** Why does CI call the Make targets instead of its own commands, and what does `UV_LOCKED=1` catch? [`.github/workflows/ci.yml`, ADR-004 Consequences]
   **A:**

## How I'd draw it on a whiteboard

Boxes and arrows, or a Mermaid diagram.

## Numbers I should remember

Metrics, sizes, costs, latencies from this slice.

## Still fuzzy (follow up in chat)

-
