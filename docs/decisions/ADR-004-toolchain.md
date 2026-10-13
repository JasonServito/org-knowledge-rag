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
- **`httpx2`** (dev only): the HTTP client behind FastAPI's `TestClient`, which the API tests use. Starlette's `TestClient` prefers `httpx2` and deprecates the `httpx` fallback (Starlette PR #3291).

## Amendment 2026-09-27

S01-T8 makes the README quickstart work from a fresh clone. Added with the developer's approval:

- **`pre-commit`** (dev only): the hook runner already chosen in the table above, now pinned in `uv.lock` so `uv run pre-commit install` works right after `uv sync`. Before this, it had to be installed globally, and a fresh clone would fail at that step. Rejected: a global `uv tool install pre-commit` prerequisite, because it's one more machine-level step and leaves the version unpinned.

## Amendment 2026-09-29

S02-T2 (`spikes/fetch.py`) reads `config/corpus_manifest.yaml` and writes `config/corpus_manifest.lock.yaml`. Added with the developer's approval:

- **PyYAML** (dev only for now): parses the manifest and writes the lock file. Only `yaml.safe_load` and `yaml.safe_dump` are allowed. The full loader can build arbitrary Python objects from YAML tags, so it is never used. PyYAML is already in `uv.lock` as a transitive dependency of pre-commit. It is named explicitly so the project doesn't depend on another tool's dependency tree. It moves to the runtime dependencies in S04, when ingestion reads the manifest from `src/`. Rejected: **ruamel.yaml**, whose selling point is round-trip editing that keeps comments, which we don't need, and whose API is less familiar; a **TOML manifest** read with the standard library's `tomllib`, which needs no dependency, but the corpus itself is YAML (doc front matter, `kep.yaml`), so a YAML parser is needed anyway.

## Amendment 2026-10-04

The S03-R1 sitting decided ADR-005 and the releases seed (S03-T5). Added with the developer's approval:

- **`btree_gist`** (a Postgres contrib extension, shipped with Postgres and in the pinned image as version 1.8): enabled by migration `0002`. The "no overlapping validity windows" exclusion constraint needs it to compare `document_id` with `=` inside a GiST index (ADR-005 D2). Rejected: checking overlaps in Python, which any other writer would skip.
- **PyYAML moves to the runtime dependencies in S03-T5,** one slice earlier than the 2026-09-29 amendment planned. The releases seed is the first `src/` code that reads the manifest. Still `yaml.safe_load` only.

## Amendment 2026-10-06

ADR-006 (decided in the S04-R2 sitting) picks the generation client and the tracing SDK. Added with the developer's approval:

- **`anthropic`** (runtime): the official Python SDK, used for `messages.parse` structured outputs (ADR-006 D2). It adds 4 packages. Rejected: raw HTTP via `urllib`, which would hand-maintain schema conversion, retries and error types.
- **`httpx2` moves to the runtime dependencies:** `anthropic` 1.x is built on it. It was dev-only (the 2026-09-26 amendment, for FastAPI's `TestClient`).
- **`langfuse`** (runtime): the Langfuse Python SDK v4, which confirms the Tracing row above (ADR-006 D3). It adds 17 packages, including the OpenTelemetry SDK, protobuf and `httpx`. Rejected: OTLP JSON posted with `urllib` (our own trace builder, replaced by S11's LangGraph integration anyway) and the legacy ingestion API (sunset 2026-11-16).

## Amendment 2026-10-09

ADR-008 (decided in the S08-R1 sitting) picks the reranker and its runtime. Added with the developer's approval:

- **`transformers`** (runtime): loads the pinned `BAAI/bge-reranker-base` and its tokenizer, and runs it as a sequence classifier (ADR-008 D2). Rejected: `sentence-transformers` (one more package on top of the same two) and ONNX Runtime (scores differ from the measured ones by up to 0.29).
- **`torch`** (runtime), **from the PyTorch CPU package index**, pinned in `pyproject.toml` (`[[tool.uv.index]]`, `explicit = true`, plus a `[tool.uv.sources]` entry). The default PyPI wheel on Linux pulls ~2–3 GB of CUDA libraries; the CPU wheel is ~740 MB installed. There's no GPU on the laptop or in S15's plan.
- **macOS now needs Apple Silicon** (arm64, macOS 14 or later), narrowing the Dev environment row above. PyTorch publishes no Intel Mac wheel, so `uv sync` fails on Intel Macs. Linux and WSL2, the platforms used (and CI), are unaffected.

## Amendment 2026-10-12

S12-T2 serves `POST /query` over HTTP (product spec must-have 10). Decided in the S12-R1 sitting; added with the developer's approval:

- **`uvicorn`** (runtime, 0.54.0, pinned in `uv.lock`): the ASGI server that runs the FastAPI app (`make serve`: `uv run uvicorn --factory orgknow.api.app:create_app --host 127.0.0.1 --port 8000`). FastAPI's own docs use it. It adds 1 package; its dependencies, `click` and `h11`, were already in the lock. Rejected: no server, `TestClient` only, which can't serve a request.
