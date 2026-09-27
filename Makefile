# Single entry point for local work and CI. CI calls these targets instead of copying commands.
.PHONY: fmt check test-int up down

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

# Tests marked `integration` (everything under tests/integration/). Needs the database.
test-int:
	uv run pytest -m integration

# Start local Postgres and block until its healthcheck passes.
up:
	docker compose up -d --wait

# Stop the container. The named volume (the data) is kept.
down:
	docker compose down
