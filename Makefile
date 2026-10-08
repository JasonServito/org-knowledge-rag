# Single entry point for local work and CI. CI calls these targets instead of copying commands.
.PHONY: fmt check test-int up down migrate seed ingest ingest-report reset-corpus embed \
	eval-check eval-sections

# Integration tests use their own database in the same container, so data ingested into the dev
# database never collides with test rows (S04-R1 decision 1). CI overrides it with its service DB.
TEST_DATABASE_URL ?= postgresql://orgknow:orgknow@localhost:5433/orgknow_test

# Apply ruff's safe lint fixes (including import sorting), then format.
fmt:
	uv run ruff check --fix .
	uv run ruff format .

# The gate before any task is done: format check, lint, strict types, unit tests.
check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest -m "not integration"

# Tests marked `integration` (everything under tests/integration/), against the test database.
# Migrates it first. Needs `make up`.
test-int:
	DATABASE_URL=$(TEST_DATABASE_URL) uv run alembic upgrade head
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -m integration

# Start local Postgres, block until its healthcheck passes, then create the test database if
# it's missing (the image creates only `orgknow`, and only on a fresh volume).
up:
	docker compose up -d --wait
	docker compose exec -T db psql -U orgknow -d orgknow -tAc \
		"SELECT 1 FROM pg_database WHERE datname = 'orgknow_test'" | grep -q 1 \
		|| docker compose exec -T db createdb -U orgknow orgknow_test

# Stop the container. The named volume (the data) is kept.
down:
	docker compose down

# Apply all pending Alembic migrations. Safe to re-run: applied revisions are skipped.
migrate:
	uv run alembic upgrade head

# Load the releases from the corpus manifest into the database. Safe to re-run: it upserts.
seed:
	uv run python -m orgknow.ingestion.seed

# Read the scope's files (INGEST_SCOPE, default full) at the locked SHAs and store their versions,
# then chunk every version that has no chunks yet. Free and local; safe to re-run (a re-run adds
# 0 versions and 0 chunks). Needs `make up`, `make migrate`, `make seed`: it only reads `releases`,
# and stops before reading git if a manifest release is missing there or has other dates.
# It ends with the ingestion report: this run's counts, skipped and failed files, then the
# database part (see ingest-report).
ingest:
	uv run python -m orgknow.ingestion.ingest

# Print the database part of the ingestion report, without reading git: counts per source type
# and per release, the chunk id range, and the fingerprint of every stored value except generated
# ids. Two databases holding the same values print the same report. Read-only. Needs `make up`.
ingest-report:
	uv run python -m orgknow.ingestion.report

# Empty the DEV database's corpus: documents, aliases, versions and chunks, with ids restarting at
# 1 (S05-R1 decision 2). `releases` and `embeddings` are kept: vectors are a cache keyed by content
# hash. Then run `make ingest` to rebuild. `make test-int` uses its own database, untouched here.
reset-corpus:
	docker compose exec -T db psql -U orgknow -d orgknow -c \
		"TRUNCATE documents, document_aliases, document_versions, chunks RESTART IDENTITY CASCADE"

# Embed every chunk text that has no vector for EMBEDDING_MODEL yet (one vector per unique text),
# after deleting vectors no chunk uses. PAID: calls the Voyage API (needs VOYAGE_API_KEY), and
# refuses to start above EMBED_MAX_TOKENS_PER_RUN estimated tokens. Safe to re-run: a re-run
# makes 0 requests. Needs `make ingest`.
embed:
	uv run python -m orgknow.embeddings.embed

# Validate the golden set (EVAL_GOLDEN_PATH, default eval/golden_set/v0.yaml), then check every
# label against the dev database: one line per label with the distinct chunk texts it matches,
# then a total. Fails if the file is invalid or a label matches nothing. Read-only; needs `make up`.
eval-check:
	uv run python -m orgknow.eval check

# List a document's sections as golden-set labels write them, each with its distinct text count:
# one line per heading path in any version, first appearance first; `""` is the intro. Read-only.
# Example: make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp
eval-sections:
	uv run python -m orgknow.eval sections "$(DOC)"
