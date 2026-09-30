# Organizational Knowledge & Decision Intelligence RAG

A retrieval-augmented generation system that treats **time, source authority, and conflicting information** as first-class data rather than leaving them for the LLM to guess at.

It's evaluated on the public Kubernetes project: KEPs, versioned docs, release notes, and governance documents. The system answers four kinds of question, each with citations:

- what's true **now**
- what was true **before**
- **how** something changed
- **why** it changed

It refuses when the public record doesn't contain the answer.

> **Status:** pre-development. Foundation slice (S01) in progress. See [`docs/backlog.md`](docs/backlog.md).

## Why this is harder than "chat with your docs"

Organizational knowledge changes over time. Sources differ in authority, and documents contradict each other. For example, a KEP's metadata can claim a feature is GA before the release notes say it shipped. This project models versions, authority and conflicts explicitly, and measures every retrieval technique against a fixed, human-verified golden set.

## Quickstart

### Prerequisites

- **Windows:** WSL2 with Ubuntu. Run every command below in the Ubuntu shell, not in PowerShell. Native Windows is not supported (ADR-004).
- **Docker Desktop** as the only Docker engine, with WSL integration enabled for the Ubuntu distro (Docker Desktop → Settings → Resources → WSL integration). Don't also install Docker Engine inside Ubuntu.
- **make:** `sudo apt install make` (or `sudo apt install build-essential`).
- **uv:** `curl -LsSf https://astral.sh/uv/install.sh | sh`. uv also manages Python: `uv sync` installs Python 3.12 (from `.python-version`) if it's missing, so there's no separate Python install.
- **gh** (GitHub CLI): optional. Only needed to open PRs or watch CI from the terminal.

### Run it

```bash
git clone https://github.com/JasonServito/org-knowledge-rag.git
cd org-knowledge-rag
cp .env.example .env        # local settings; the defaults match compose.yaml
uv sync                     # Python 3.12 + all dependencies, exactly as pinned in uv.lock
make up                     # start Postgres + pgvector and wait until it's healthy
make migrate                # apply Alembic migrations (safe to re-run)
make check                  # format check, lint, mypy --strict, unit tests
make test-int               # integration tests against the local database
uv run pre-commit install   # run ruff on every commit
```

Postgres listens on host port **5433** (not the default 5432), bound to localhost, so it doesn't clash with another Postgres on your machine. `make down` stops it; the data is kept in a named Docker volume.

## Development environment

This is the setup the project is built and verified on:

- **WSL2 Ubuntu** on Windows. The repo lives in the Linux filesystem (e.g. `~/code/`), not under `/mnt/c/`.
- **Docker Desktop** provides the Docker engine to WSL.
- **uv-managed Python 3.12.** No system Python is used.
- **Claude Code Desktop**, running in a WSL session on this repo. See [`docs/ai-workflow.md`](docs/ai-workflow.md).

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/product-spec.md`](docs/product-spec.md) | Phase 1 scope, non-goals, acceptance criteria |
| [`docs/architecture.md`](docs/architecture.md) | What the code does today |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records |
| [`docs/backlog.md`](docs/backlog.md) | Ordered slices and tasks |
| [`docs/ai-workflow.md`](docs/ai-workflow.md) | How this project is built with AI assistance |
| [`CLAUDE.md`](CLAUDE.md) | Rules for the coding agent |
| [`docs/learning/`](docs/learning/) | Slice briefs and glossary |
| [`docs/research/`](docs/research/) | Corpus selection research |

## Data, licensing and attribution

- Kubernetes documentation is licensed CC BY 4.0. KEPs and code are Apache-2.0. Every answer cites its source URL and release.
- The corpus is **not** redistributed in this repository. Only ingestion code and source manifests are committed.
- This is an independent project. It is **not affiliated with or endorsed by** the Kubernetes project or the CNCF.
- Code license: [MIT](LICENSE). It covers the code in this repository, not the Kubernetes corpus.
