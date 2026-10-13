# Single entry point for local work and CI. CI calls these targets instead of copying commands.
.PHONY: fmt check test-int up down migrate seed fetch-github ingest lifecycle ingest-report \
	reset-corpus embed eval-check eval-check-chains eval-sections eval-retrieval eval-conflicts \
	eval-routes eval-smoke eval eval-table eval-resummarize serve

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

# Fetch every decision chain's GitHub items (the manifest's `decision_chains`; S13-T1): REST for
# issues and PRs (the item, its comments, a PR's reviews; never diff-line comments), GraphQL for
# discussions (comments, replies), every list paged. Writes one JSON snapshot per item to
# CORPUS_CACHE_DIR/github/<repo>/<kind>/<number>.json and pins each one's sha256 and fetch time in
# the lock's `github:` section (an unchanged snapshot keeps its pin). Nothing is written unless
# every item was fetched. Free, but needs GITHUB_TOKEN (`gh auth token`) and the network: about
# 10 requests. `make ingest` then reads only the cached snapshots.
fetch-github:
	uv run python -m orgknow.ingestion.github

# Read the scope's files (INGEST_SCOPE, default full) at the locked SHAs and store their versions,
# then chunk every version that has no chunks yet, then rebuild the observed lifecycle (see
# lifecycle). Free and local; safe to re-run (a re-run adds 0 versions and 0 chunks). Needs
# `make up`, `make migrate`, `make seed`: it only reads `releases`, and stops before reading git if
# a manifest release is missing there or has other dates. It ends with the ingestion report: this
# run's counts and the lifecycle line, skipped and failed files, then the database part (see
# ingest-report). The `full` scope also stores each decision chain's GitHub item as a `discussion`
# document from its cached snapshot (see fetch-github); a missing snapshot, or one the lock doesn't
# pin, stops it before any write, naming the item.
ingest:
	uv run python -m orgknow.ingestion.ingest

# Rebuild `observed_lifecycle` (S09-T5, ADR-003 D2): each feature gate's stage at each stored
# release, as that release's own feature-gate reference gives it (to 1.28 the table pages, re-read
# from the website clone; from 1.29 the stored gate files). Replaces every row in one transaction,
# so a re-run stores the same rows; `make ingest` runs the same step after chunking. Prints one
# line: rows, releases, and rows by confidence. Free and local. Needs `make migrate`, `make ingest`.
lifecycle:
	uv run python -m orgknow.ingestion.lifecycle

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

# Check the gold decision chains (EVAL_CHAINS_PATH, default eval/golden_set/chains-v0.yaml;
# ADR-012 D4) against the dev database: one line per `texts` label with the distinct chunk texts
# it matches (ADR-007 D2's section rule; the document by canonical id or alias), then a total.
# Fails, naming each one, if a label matches nothing. Read-only; needs `make up` and `make ingest`.
eval-check-chains:
	uv run python -m orgknow.eval check-chains

# List a document's sections as golden-set labels write them, each with its distinct text count:
# one line per heading path in any version, first appearance first; `""` is the intro. Read-only.
# Example: make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp
eval-sections:
	uv run python -m orgknow.eval sections "$(DOC)"

# Score retrieval alone (S07-R1 decision 5): retrieve in RETRIEVAL_MODE for every answerable golden
# question with its stored vector (EVAL_VECTORS_DIR), then print the mode and Recall@10, Hit@10,
# MRR and nDCG@10, then the stale-result rate and temporal accuracy (S09-T3), then authority
# selection and CURRENT MRR (S09-T7), then in temporal and authority modes the router line (router
# accuracy, windows, plans; S09-T4), then the retrieve time's p50 and p95 and, in rerank, temporal
# and authority modes, the reranker's load time (S08-T4). Temporal and authority modes read each
# question's stored route (EVAL_ROUTES_DIR; a missing one is an error, filled by
# `make eval-routes`). Free: no Voyage or Anthropic call (a missing vector is an error), and it
# writes nothing. The check before a paid `make eval`. Needs `make up`.
# Example: RETRIEVAL_MODE=hybrid make eval-retrieval (the default mode is authority)
eval-retrieval:
	uv run python -m orgknow.eval retrieval

# Check the conflict set (EVAL_CONFLICTS_PATH, default eval/golden_set/conflicts-v0.yaml; ADR-007
# D4): validate it against the golden set, and check every side entry against the dev database (an
# entry matching no stored text is an error). Then retrieve in RETRIEVAL_MODE for every golden
# question and the set's new questions, from their stored vectors and routes, find the rule-found
# conflicts, and print: the set's counts, how many conflicts and seeds search retrieved (reachable),
# and the rule-found conflicts' precision and recall (S10-T6). Free: no Voyage or Anthropic call (a
# missing vector or route is an error, filled by `make eval-routes`), and it writes nothing. Exits 1
# with no conflict file. The free check before a paid `make eval`. Needs `make up`.
# Example: EVAL_CONFLICTS_PATH=tests/fixtures/conflicts/demo-sample.yaml make eval-conflicts
eval-conflicts:
	uv run python -m orgknow.eval conflicts

# Route every golden question (all of them, answerable or not) that has no stored route in
# EVAL_ROUTES_DIR/<ROUTER_MODEL>.json (ADR-009 D3): the router's mode and time scope per question,
# keyed like the question vectors. Then print how many were routed and already stored, the route
# time's p50 and p95, and the cost. PAID: one ROUTER_MODEL call per missing route (needs
# ANTHROPIC_API_KEY then; v0's 43 cost about $0.19 with claude-opus-5-5 at effort low); a re-run
# makes 0. Each route is saved as it arrives, so a failure midway keeps the ones paid for. The file
# records the router prompt's hash: a file made with another prompt is an error. When the conflict
# set (EVAL_CONFLICTS_PATH) exists, its new questions are routed too, and those with no stored
# vector (EVAL_VECTORS_DIR) are embedded in one Voyage request (PAID: needs VOYAGE_API_KEY then; a
# re-run makes 0), so `make eval-conflicts` can retrieve for them.
eval-routes:
	uv run python -m orgknow.eval routes

# Run the golden set's smoke questions (`smoke: true`) end to end: retrieval in RETRIEVAL_MODE with
# each question's stored vector (EVAL_VECTORS_DIR), one answer call, then the metrics and AC1-AC3.
# Writes a results folder (named `<mode>-smoke`, its own table row) under EVAL_RESULTS_DIR (default
# eval/results) and rebuilds the ablation table there. PAID: one Anthropic call per question with
# hits (needs ANTHROPIC_API_KEY), and one Voyage request when a question has no stored vector
# (needs VOYAGE_API_KEY then; a re-run makes 0). A label matching no stored text stops it before
# any paid call; a failed ask is a row, not a crash. In temporal and authority modes it also routes
# each question with no stored route (EVAL_ROUTES_DIR; one ROUTER_MODEL call each, saved as it
# arrives; a re-run makes 0), and retrieves each question with its route.
eval-smoke:
	uv run python -m orgknow.eval run --smoke

# The same for every question of the golden set, plus the conflict set's new questions when it
# exists: their rows go to conflict_questions.jsonl, and the summary scores every row's conflicts
# against the set (S10-T6). PAID: one Anthropic call per question (S04: about $0.02-0.04 each; in
# temporal and authority modes, plus one router call per question with no stored route), so run it
# only when asked.
eval:
	uv run python -m orgknow.eval run

# Rebuild the ablation table (EVAL_RESULTS_DIR/ablation.md) from every results folder: one row per
# pipeline name and golden file. Free and local; `make eval` and `make eval-smoke` end with it.
eval-table:
	uv run python -m orgknow.eval table

# Rebuild the summary.json of every results folder (EVAL_RESULTS_DIR) that has one and a
# questions.jsonl, from its saved rows (S08-T3), keeping its name, golden hash and start time: an
# older folder gains the newer fields (p95 latency, retrieve p95, cost per question at
# GENERATION_PRICE_*). Prints one line per folder and writes only the summaries. Free and local;
# run `make eval-table` after it.
eval-resummarize:
	uv run python -m orgknow.eval resummarize

# Serve the API on http://127.0.0.1:8000 (S12-T2): POST /query answers as `orgknow ask` does, with
# one Langfuse trace per request when both keys are set; FastAPI's /docs page lists the endpoints.
# Startup builds the clients once and, in rerank, temporal and authority modes, loads the reranker;
# a missing ANTHROPIC_API_KEY or VOYAGE_API_KEY stops it. PAID per request, as `orgknow ask`: one
# Voyage call and one Anthropic call, and in temporal and authority modes one router call. Needs
# `make up`. Stop it with Ctrl-C.
serve:
	uv run uvicorn --factory orgknow.api.app:create_app --host 127.0.0.1 --port 8000
