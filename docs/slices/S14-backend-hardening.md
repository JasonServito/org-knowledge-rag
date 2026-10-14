# S14: Backend hardening + async ingestion

- **Status:** ✅
- **Blueprint stage:** 10 (Backend hardening + async ingestion)
- **Started:** 2026-10-13
- **Finished:** 2026-10-14

## Outcome

Every API response carries a request ID that also appears in one-line JSON logs, with one error shape and explicit timeouts and bounded retries on every external call (R1). `POST /ingestion-jobs` queues a job that `make worker` runs to completion with per-step progress; the same job run twice or a killed worker leaves the same ingestion fingerprint (R2).

## Why now

- Blueprint §21, §22, §26 and §29: the backend practices and the async ingestion path come before AWS (S15), which deploys them as they are.
- Blueprint gap #7: interface contracts come before major backend work.
- It retires 2 known risks before a second writer exists: the R3 identifier race and concurrent `make embed` runs (Proposed additions, "Make R3 race-free… (S14 at the latest)").

## Exit checks

- [x] `docs/interfaces.md` gives each endpoint's input, output and errors, the one error shape, and each dependency's timeout, retry and failure policy.
- [x] A response to any endpoint carries `X-Request-ID`, and the API's log lines for that request are JSON carrying the same ID.
- [x] Anthropic, Voyage and GitHub calls use timeouts and retry counts from settings; tests show the retries are bounded.
- [x] API tests cover temporal and authority modes (S12-R1 input).
- [x] *(R2)* `POST /ingestion-jobs` → `make worker` → the job reaches `succeeded` with per-step progress in `GET /ingestion-jobs/{id}`.
- [x] *(R2)* The same job run twice and a worker killed mid-job each end with the same fingerprint (and the same embedding, lifecycle and chain-step counts) as a clean run.
- [x] *(R2)* Two writers can't store the same identifier (R3) or embed the same texts twice.
- [x] Phase 1 retrieval unchanged: `make eval-retrieval` (free) prints S13's numbers exactly.
- [x] `make check` and `make test-int` green.
- [x] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| `docs/interfaces.md` | API versioning (blueprint §21: "only if it becomes useful") |
| Request IDs, JSON logs, one error handler | A log platform; CloudWatch (S15) |
| Timeouts and bounded retries from settings | Circuit breakers; fallback models |
| A database connection pool for the API (if decided) | Async (`async def`) database access |
| API tests for temporal and authority modes | Retrieval or scoring changes |
| *(R2)* A job table that is also the queue (ADR-013), a worker, the job endpoints | SQS (ADR-013 D1: not needed); S3 and EC2 (S15) |
| *(R2)* A single-writer guarantee for every corpus writer (R3) | Refreshing the corpus lock (K2: a proposed addition) |
| | Auth, rate limits, cost protection on public endpoints (S15's security review) |

## Metric to move

n/a (backend). Guard: Phase 1 retrieval metrics and the ingestion fingerprint stay exactly the same.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S14-T1: Interface contracts (`docs/interfaces.md`) `[commodity]`

- **Goal:** one document a reader can trust for every endpoint and dependency.
- **Done when:** each endpoint (`/health`, `/ready`, `POST /query`, `GET /decisions/{canonical_id}`) has its input, output, status codes and error bodies; the error shape is defined once; each dependency (Postgres, Voyage, Anthropic, GitHub, Langfuse) has its timeout, retries and what the caller sees on failure. Every statement matches the code or a test (pinned in the run contract). R2 adds the job endpoints.
- **Notes / pointers:** blueprint §21 and gap #7; `api/app.py`; `pipeline.ASK_ERRORS`.
- **Deps:** none.

### S14-T2: Request IDs, JSON logs, one error handler `[commodity]`

- **Goal:** follow one request through the logs; every error looks the same.
- **Done when:** every response carries `X-Request-ID` (the caller's, if valid, else a new one); the API logs one JSON line per request (ID, method, path, status, duration) plus its warnings and errors with the same ID; every error response uses the one shape, including validation errors and unexpected exceptions (no traceback or secret in the body); the CLI's stderr output is unchanged.
- **Notes / pointers:** blueprint §21 and §26.2; standard library `logging` (no new dependency unless decided).
- **Deps:** T1 (the error shape).

### S14-T3: Timeouts, retries, connection pool, API mode tests `[commodity]`

- **Goal:** no external call can hang a request or retry forever.
- **Done when:** Anthropic, Voyage and GitHub timeouts and retry counts come from settings (with today's values or the sitting's); tests prove the retries stop; the API uses a pool if decided; API tests cover temporal and authority modes with fakes.
- **Notes / pointers:** `embeddings/voyage.py` (`TIMEOUT_S`, `RETRY_DELAYS_S`), `ingestion/github.py` (`TIMEOUT_S`), the Anthropic SDK's defaults (10 minutes, 2 retries); ADR-005 ("connection pooling… would be a new dependency then"); PR #45 parked 8, PR #46 parked 2.
- **Deps:** T2 (retries log with the request ID).

### S14-T4: Job table, corpus-writer lock, snapshot reads `[core]`

- **Goal:** a job record in Postgres that is also the queue, and one lock every corpus writer takes (ADR-013 D1, D3, D4, D6).
- **Done when:** the `ingestion_jobs` migration with the one-active-job rule; the writer lock taken by all 6 writers; the report and chain reads each in one snapshot (pinned in the S14-R2 contract).
- **Notes / pointers:** blueprint §22 ("Track partial failure and job progress in PostgreSQL"); the R3 race item; PR #30's report snapshot; PR #48's chain-read snapshot.
- **Deps:** T1–T3.

### S14-T5: The worker (`make worker`) `[core]`

- **Goal:** run a job's steps (ingest, lifecycle, embed, chains) idempotently, with progress, surviving a repeated run and crashes.
- **Done when:** `make worker` runs a job's 4 steps in order with per-step progress; an error fails the job at once; a killed worker's job is resumed at its first unfinished step, up to 3 attempts; the scope guard (ADR-013 D2, D5; pinned in the S14-R2 contract).
- **Deps:** T4.

### S14-T6: Job endpoints `[commodity]`

- **Goal:** `POST /ingestion-jobs`, `GET /ingestion-jobs/{id}`; `docs/interfaces.md` gains them.
- **Done when:** POST answers 202 with a new job or 200 with the active one; GET returns the job with its steps, 404 or 422; `docs/interfaces.md` documents both (ADR-013 D4; pinned in the S14-R2 contract).
- **Deps:** T4, T5.

### S14-T7: Docs and the S14 retro `[commodity]`

- **Goal:** architecture, README, slice brief; the doc fixes kept in the S14-R2 sitting (K1, K2).
- **Deps:** T6.

## Risks & unknowns

- Changing logging could change the CLI's stderr lines, which tests and the eval read.
- An Anthropic timeout set too short would fail real answers: the slowest saved ask took 29.7 s (658 rows in `eval/results/`, whole ask).
- The pool's size and the reranker: concurrent requests already share 1 reranker.
- *(R2)* The worker's steps take real time (a no-op `make ingest` takes 45 s); embed is paid.

## Decisions expected (ADRs)

- R1: no connection pool; autocommit API connections (ADR-005 amendment 2026-10-13, decided in the S14-R1 sitting).
- R2: ADR-013, async ingestion (Accepted in the S14-R2 sitting, 2026-10-14): the jobs table is the queue, no SQS; a fixed 4-step job; one corpus-writer lock; one active job; errors fail, crashes resume; one table. Deployment topology moves to ADR-014 (S15).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S14-R1: Hardening

- **Status:** merged (PRs #49 and #50, 2026-10-14; split after T2 on the size alarm)
- **Tasks:** T1, T2, T3.
- **Goal (plain words):** write down every endpoint's contract and one error format; give every request an ID that shows up in its response, its errors and its JSON log lines; and put a timeout and a retry limit on every external call, with no database transaction left open during the LLM call.

#### Sitting evidence (2026-10-13)

Probe scripts were run in the sitting's scratchpad (not committed); each result below is copied from its output.

- **No-op `make ingest`:** 45 s; fingerprint `sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165` (unchanged).
- **The guard baseline** (`HF_HUB_OFFLINE=1 make eval-retrieval`, authority mode, golden v0), equal to S13's row:
  ```
  Recall@10 0.522  Hit@10 0.972  MRR 0.781  nDCG@10 0.508
  Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
  Authority selection 0.889 (8 of 9 CURRENT questions)  CURRENT MRR 0.733
  Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
  Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date
  ```
- **Retrieval SQL time** (`RETRIEVAL_MODE=hybrid make eval-retrieval`, no reranker): p50 0.11 s, p95 0.25 s.
- **Ask latency** (658 saved rows in `eval/results/*/questions.jsonl`, whole ask): p50 8.7 s, p95 14.9 s, max 29.7 s.
- **DB connect** (local, connect + `SELECT 1`, 20 tries): p50 10.8 ms, max 18.5 ms; `max_connections` 100.
- **Middleware probes** (FastAPI 0.141.1, Starlette 1.7.0, anyio 4.15.1):
  - a context variable set in a pure ASGI middleware reaches a plain `def` endpoint (thread pool): yes;
  - an unhandled exception returns plain-text `Internal Server Error` with **no** `X-Request-ID`, because Starlette's error middleware sits outside user middleware;
  - when the middleware itself catches the exception (response not yet started) and sends the 500, the header and JSON body are present, with `TestClient(raise_server_exceptions=True)` and `False`.
- **Idle transaction** (`create_app` in dense mode, a fake embedder named like the stored vectors, a generator that sleeps 4 s; `pg_stat_activity` read at 2.5 s): `('orgknow', 'idle in transaction', 0:00:01.98…, 'SELECT gate, release, stage…')`.
- **Devil's advocate (decision 2):** argued for a pool: the risk is connection count on a small RDS instance (~80–110 by AWS's formula, unmeasured), not speed; the idle transaction (then confirmed); a pool's cap suits 1 shared reranker; interview risk. Led to autocommit and the S15 trigger in ADR-005's amendment.

#### Decisions (made in the sitting, 2026-10-13)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | Triage of S13-R1's 31 parked items: K1 into S14 (GitHub timeout → T3; a non-connection database error's bare 500 → T2; the chain read during `make chains` → R2's T4); K2 lock refresh, K3 chain rules v1, K4 S13 cleanup, K5 docs fixes, K6 GitHub texts in CURRENT questions → Proposed additions; D1–D4 dropped (intended, harmless, or already fixed) | Keep all; drop all | K1 fits S14; K2–K6 are real but outside it |
| Slice | The S14 slice doc approved | — | — |
| Run shape | 2 runs: R1 = T1–T3; R2 = T4–T7 with its own sitting (ADR-013 async ingestion; deployment topology becomes ADR-014) | 1 run with merged tasks and 2 stacked PRs | The 5-task cap; S13's estimate was 3× low; decide async after seeing R1 |
| 1 | **One error envelope** `{"error": {"code", "message", "request_id"}}` for every error response. Codes: `invalid_request` 422, `not_found` 404, `upstream_failed` 502, `database_unavailable` 503, `internal` 500 | FastAPI's `{"detail"}` (no stable code; validation errors a list); RFC 9457 problem details (more fields than one client needs) | A fixed code list S17's UI can switch on; no client reads errors yet |
| 2 | **No connection pool; API connections are autocommit with a statement timeout** (ADR-005 amendment 2026-10-13, with the S15 trigger) | `psycopg_pool` (max 8, 2 s wait → 503; a new dependency); no change | Connecting is ~0.1% of an ask; autocommit fixes the confirmed idle transaction; the connection count can only be measured on RDS |
| Plan | The verification plan and PR plan below; no paid calls | — | — |

**Claude's calls** (reversible; confirmed at the read-back):
- a. **Logs:** a standard-library JSON formatter (no new dependency), set up only by `make serve`'s uvicorn log config (`--log-config`), with uvicorn's access log off. Library code never configures logging; the CLI and make targets are unchanged. R2's worker reuses the formatter.
- b. **Request ID:** the caller's `X-Request-ID` when it is 1–64 characters of `A-Z a-z 0-9 . _ -`, else a new random hex ID. One pure ASGI middleware sets it, writes the request's log line, and turns an unhandled exception into the `internal` 500 (the probe's design).
- c. **Timeouts:** generation 90 s, router 30 s, Anthropic retries 2 (the SDK's default), Voyage 60 s and 3 retries (today's values), GitHub 30 s and 0 retries (a manual command), DB statement 10 s.
- d. **Status codes:** every upstream failure (`ASK_ERRORS`) stays a 502 `upstream_failed`; a cancelled statement is a database error: 503 `database_unavailable`.
- e. **Validation errors:** `message` names the field and the problem; the input is never echoed.
- f. **`/query`'s log line** carries the Langfuse `trace_id` when tracing is on; the pipeline is unchanged.
- g. **One `db/` helper** opens API connections (autocommit, connect timeout, statement timeout), used by `/query` and `/decisions`; `/ready` keeps its own fresh ping.
- h. **The guard baseline** is the sitting's `make eval-retrieval` output above.

#### Pinned: T1 (`docs/interfaces.md`)

- **Per endpoint** (`GET /health`, `GET /ready`, `POST /query`, `GET /decisions/{canonical_id}`), one `###` heading written as `METHOD /path`: purpose, request (body or path parameter), the 200 body (field list, pointing to the Pydantic model), every other status with its code and when it happens, cost (paid or free), idempotency (all 4 are safe to retry; `/query` is paid per call).
- **The error envelope:** the shape, the 5 codes with their statuses and one example each, and the rule that `message` never carries a traceback, a secret, a database URL or the caller's input.
- **Request IDs:** the header rule (Claude's call b), where the ID appears (response header, error body, every log line of the request).
- **Logs:** one JSON object per line; the fields of the per-request line (`ts`, `level`, `logger`, `message`, `request_id`, `method`, `path`, `status`, `duration_ms`, and `trace_id` on `/query` when present); other lines carry `ts`, `level`, `logger`, `message`, `request_id` (when inside a request), and `exc_info` text for errors.
- **Dependencies table:** Postgres, Voyage, Anthropic (answer, router), GitHub, Langfuse: the setting names and default values for timeout and retries, which errors retry, and what the API caller sees when it fails (status and code). Langfuse: the SDK's own background export; a Langfuse failure never fails a request.
- **The worst case per `/query`:** written out from the settings (e.g. the answer call's 90 s × 3 tries), as a known limit, not a promise.
- **A unit test** (`tests/unit/test_interfaces_doc.py`): every route of `create_app(Settings(_env_file=None, database_url=…))` except FastAPI's own (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`) has a `### METHOD /path` heading, and every such heading is a route; the doc's error-code list equals the code's.
- R2 adds the job endpoints.

#### Pinned: T2 (request IDs, JSON logs, errors)

- **Files:** `src/orgknow/logs.py` (the JSON formatter and the request-ID context variable, usable by R2's worker), `src/orgknow/api/middleware.py` (the ASGI middleware), `src/orgknow/api/errors.py` (the envelope model, the code list, the exception handlers), `config/logging.json` (uvicorn's `--log-config`), `api/app.py` (wiring; `HTTPException` raises replaced by the envelope), Makefile `serve` (`--log-config config/logging.json --no-access-log`).
- **The middleware** (pure ASGI, not `BaseHTTPMiddleware`): read or create the ID; set the context variable; add `X-Request-ID` to the response start; after the response, log one INFO line with the per-request fields; on an unhandled exception before the response starts, log it at ERROR with its traceback and send the `internal` 500 envelope with the header; reset the context variable in `finally`.
- **The formatter:** `json.dumps` of the fields above, one line, `ensure_ascii=False`; `request_id` read from the context variable when set; extra fields passed with `extra=`.
- **Handlers:** `RequestValidationError` → 422 `invalid_request` with `message` = `"<loc joined by .>: <msg>"` of the first error (never the `input`); 404 for an unknown path → `not_found` too (Starlette's `HTTPException`); the app's own errors raise one exception type carrying the status, code and message.
- **Tests** (`tests/unit/test_api_errors.py`, `tests/unit/test_logs.py`, `tests/integration/test_api.py`): the proof map rows. Unit tests build the app with fakes and no database where the route allows (a test-only route raising `RuntimeError("secret-xyz")` or `psycopg.errors.UndefinedTable` is added to the app inside the test).

#### Pinned: T3 (timeouts, retries, autocommit, mode tests)

- **Settings** (with `.env.example` lines): `GENERATION_TIMEOUT_S=90`, `ROUTER_TIMEOUT_S=30`, `ANTHROPIC_MAX_RETRIES=2`, `VOYAGE_TIMEOUT_S=60`, `VOYAGE_MAX_RETRIES=3`, `GITHUB_TIMEOUT_S=30`, `DB_STATEMENT_TIMEOUT_MS=10000`; each with bounds (`ge=1`; retries `ge=0`).
- **Anthropic:** the client is built with `max_retries=ANTHROPIC_MAX_RETRIES` (CLI and API); the generator's and router's calls pass `timeout=` their setting. The stale "10-minute timeout and 2 retries" docstrings change.
- **Voyage:** `VoyageEmbedder` takes the timeout and retry count; the delays stay 1 s, 2 s, 4 s… (doubling) for as many retries as set. `TIMEOUT_S` and `RETRY_DELAYS_S` constants go.
- **GitHub:** `github_client` takes the timeout from settings; `TIMEOUT_S` goes; no retries.
- **DB helper** in `src/orgknow/db/` (e.g. `connect.py`): `api_connection(settings)` → `psycopg.connect(url, connect_timeout=…, autocommit=True, options="-c statement_timeout=<ms>")`; `/query` and `/decisions` use it; a `psycopg.OperationalError` (which includes `QueryCanceled`) → 503 `database_unavailable`.
- **Tests:** the proof map rows; the idle-transaction test is the sitting probe as an integration test (a generator that blocks on a `threading.Event` instead of sleeping, so the test doesn't depend on timing: read `pg_stat_activity` while it blocks, then release it).

#### Handoffs between tasks

- T1 → T2: the error envelope, the 5 codes, the log fields and the request-ID rule, as written in `docs/interfaces.md`. T2 implements exactly those; the doc test passes from T1 on.
- T2 → T3: `logs.py`'s context variable, so the Voyage retry warning (and any log line inside a request) carries the request ID; the envelope's `database_unavailable` and `upstream_failed` paths, which T3's timeouts reach.
- T3 → R2: every timeout and retry count is a setting; the `db/` connection helper; the worker will reuse `logs.py`.

#### Edge cases

- An unhandled exception after the response has started (streaming): re-raise (no endpoint streams today).
- A caller's `X-Request-ID` of 65 characters, with a newline, a space or non-ASCII: replaced, never logged as given.
- `/health` and `/ready` get request IDs and log lines too.
- `TestClient` without `with` (no lifespan): the middleware still works.
- An empty or whitespace question: 422 `invalid_request` (the existing pattern rule).
- A statement timeout inside `/decisions`: 503, as a connection failure.
- The CLI: no JSON logs, the same stderr lines; `logging.basicConfig` in `ingest` and `embed` unchanged.
- Langfuse unset: no `trace_id` field (not `null`).

#### Files in scope

`docs/interfaces.md` (new); `src/orgknow/logs.py`, `src/orgknow/api/middleware.py`, `src/orgknow/api/errors.py`, `src/orgknow/db/connect.py` (new); `src/orgknow/api/app.py`, `src/orgknow/settings.py`, `.env.example`, `src/orgknow/generation/generator.py`, `src/orgknow/retrieval/router.py`, `src/orgknow/embeddings/voyage.py`, `src/orgknow/embeddings/embed.py`, `src/orgknow/ingestion/github.py`, `src/orgknow/cli.py`, `src/orgknow/pipeline.py` (docstring only, if its error notes change); `config/logging.json` (new); `Makefile` (`serve`); tests under `tests/unit/` and `tests/integration/`; `docs/backlog.md` (ticks); `docs/architecture.md` (one paragraph on request IDs, errors and timeouts, with a pointer to `docs/interfaces.md`).

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T1 | Every endpoint documented | `test_interfaces_doc.py`: routes ↔ `###` headings | The 4 routes in `api/app.py` |
| T1 | The 5 codes in the doc and the code | Same test | Decision 1 |
| T1 | Each dependency's timeout and retries | The doc names each setting; the reviewer checks each value against `settings.py` | Claude's call c |
| T2 | `X-Request-ID` on 200, 404, 422, 500, 502, 503, equal to the body's `request_id` | One API test per status | Decision 1 |
| T2 | A valid caller ID echoed; invalid ones (65 characters, newline, space) replaced | Unit tests on hand-written inputs | Claude's call b |
| T2 | One JSON line per request with the pinned fields | A test parses the captured line | T1's pinned fields |
| T2 | A log line inside a request carries its ID | A fake that logs a warning | — |
| T2 | A 500 never shows the exception text; the log has the traceback and ID | A route raising `RuntimeError("secret-xyz")`: no `secret-xyz` in the body; code `internal` | The sitting probe |
| T2 | A non-connection database error → the `internal` 500 (K1) | A route raising `psycopg.errors.UndefinedTable` | K1 |
| T2 | The CLI's stderr unchanged | `tests/integration/test_cli.py` and the CLI unit tests pass unmodified (`git diff --stat` shows them untouched); building the app adds no root log handler | Step 3 row 3 |
| T3 | The 7 settings and defaults | Unit test of `Settings(_env_file=None, …)` | Claude's call c |
| T3 | Anthropic calls use them | A fake client records `timeout` and the client's `max_retries` | The settings |
| T3 | Voyage retries stop | Always-503 fake, `VOYAGE_MAX_RETRIES=1`: exactly 2 calls, then the error | Hand count |
| T3 | API connections: autocommit and the statement timeout | Integration: `SHOW statement_timeout` = `10s`; at 200 ms, `SELECT pg_sleep(0.5)` → 503 `database_unavailable` | Decision 2; Postgres's `10s` display |
| T3 | No idle transaction during generation | Integration: the API's connection is `idle`, never `idle in transaction`, while the generator blocks | The sitting probe (`idle in transaction` before) |
| T3 | Temporal and authority modes over the API | Integration with `FakeRouter` and `FakeReranker`: 200; the router called once; the reranker called; a `RouterError` → 502 `upstream_failed` | S12-R1 input |

#### Break-it rules

- T2: remove the middleware's exception catch → the 500 test fails (no header, no envelope).
- T2: remove the request-ID check → the injection test fails.
- T3: turn autocommit off → the idle-transaction test fails.
- T3: let the Voyage loop retry once more → the 2-call test fails.

#### Real-data demo

`make serve` (authority mode; the keys must be set, but no paid call is made), then:

```bash
curl -si http://127.0.0.1:8000/health
curl -si http://127.0.0.1:8000/ready
curl -si http://127.0.0.1:8000/decisions/kep:2572 | head -5
curl -si http://127.0.0.1:8000/decisions/kep:9999
curl -si -X POST http://127.0.0.1:8000/query -H 'content-type: application/json' -d '{"question": " "}'
```

Show each response's `X-Request-ID` beside its JSON log line. Stop the server by PID (memory: not `pkill -f uvicorn` in the same call).

#### Bundle-level check

1. `make check` and `make test-int` (Postgres checked at run start).
2. `HF_HUB_OFFLINE=1 make eval-retrieval` prints the baseline's metric lines above exactly (the timing line may differ).
3. `make ingest-report` prints `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`.

#### PR plan

- 1 PR. Estimate ~1,000–1,200 reviewable lines; if the size alarm fires when the PR opens, split after T2 (contract and logs │ timeouts), as stacked PRs.
- Greptile: 1 trigger (20/50 → 21/50; 22/50 if split).

#### Paid calls allowed

None. Every test uses fakes; the demo calls free endpoints only. No Anthropic credit needed.

### Run S14-R2: Async ingestion

- **Status:** PR open
- **Tasks:** T4, T5, T6, T7 (T7 ends with the S14 retro as the run's last commit).
- **Goal (plain words):** a POST records a rebuild job; `make worker` runs it (ingest → lifecycle → embed → chains) with per-step progress in the job's row; only one corpus writer can run at a time; a killed worker's job is resumed, and a repeated or resumed job leaves the same data.

#### Sitting evidence (2026-10-14)

Probe scripts were run in the sitting's scratchpad (not committed), on a scratch database `orgknow_r2probe` (migrated, seeded, the dev database's `embeddings` table copied in: 21,762 rows, 51 s). Each result below is copied from its output.

- **Fresh full ingest** (empty corpus): 74 s (`TIME make ingest : 73.678719547 s rc=0`); `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165` (the dev database's).
- **Then embed and chains:** `Model voyage-4-large: 0 texts had no vector`, `Requests: 0`, `Orphan vectors deleted: 0` (0.33 s); `kep:2572: 6 steps stored, 6 found, 0 missing`, `kep:3015: 6 steps stored, 5 found, 1 missing (decision: no_link)` (0.42 s). Stored: 21,762 embeddings, 3,295 lifecycle rows.
- **A no-op re-run:** `New documents: 0. New versions: 0. Closed versions: 0. Unchanged documents: 1173.` `New chunks: 0.` `Failed: 0`, the same fingerprint.
- **Killed ingest** (SIGKILL to the Python process; corpus emptied first):
  ```
  == killed at 40s; stored after kill:
  1173|2887|10387|3295            (documents|versions|chunks|lifecycle rows)
  New chunks: 38096.  Failed: 0 documents or versions.
  Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165
  == killed at 60s; stored after kill:
  1173|2887|40129|3295
  New chunks: 8354.  Failed: 0 documents or versions.
  Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165
  ```
- **A first, flawed kill probe** sent SIGKILL to `uv run`'s PID: its Python child kept running, and the re-run overlapped it (2 writers at once). Kill the Python process, never the `make`/`uv` wrapper.
- **The lock:** a subprocess held `pg_advisory_lock(1414)`; `try-lock while held: False`; after SIGKILL to the holder, `try-lock after SIGKILL: True after 0.000 s`.
- **The full corpus's tokens:** 21,762 distinct texts, 5,690,119 estimated tokens (characters / 4), above `EMBED_MAX_TOKENS_PER_RUN` (2,000,000): a lost vector cache makes embed refuse, not pay.
- **The one-active-job rule:** a unique index on `((true))` where status is queued or running: a second queued insert with `ON CONFLICT DO NOTHING` gives `INSERT 0 0`; a `succeeded` row inserts.
- **Writers** (modules that write the corpus tables): `ingestion/ingest.py`, `ingestion/lifecycle.py`, `ingestion/seed.py`, `embeddings/embed.py`, `provenance/build.py`, and the new worker.
- **Devil's advocates** (one per decision 1–6's topic): changed decision 1 (from an SQS-shaped message table to the jobs table as the queue), decision 5 (from "retry every error 3 times" to "errors fail, crashes resume") and decision 6 (from a steps table to a JSON list); added decision 2's 2 guards (embed's orphan deletion), decision 3's "the lock lives on the writer's only connection", and decision 4's database-enforced rule (2 POSTs at once).

#### Decisions (made in the sitting, 2026-10-14)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | Triage of S14-R1's 15 parked items and 3 questions: K1 (PR #49 parked 6) and K2 (PR #50 parked 8) → T7's docs pass; K3–K6 (PR #49 parked 1–4, question 3; PR #50 parked 3–4) → one Proposed addition, "S15 security review inputs"; D1–D7 (PR #49 parked 5, 7; PR #50 parked 1, 2, 5, 6, 7) dropped. PR #49 questions 1 (a 405 keeps FastAPI's body) and 2 (`/ready`'s probe body) accepted | — | K1–K2 fit T7; K3–K6 matter once the API is public (S15) |
| Run shape | **1 run, 1 PR** for T4–T7, even if the size alarm fires (the developer's call for this run) | 2 stacked PRs on the size alarm | The developer's choice |
| 1 | **The jobs table is the queue; no SQS** (ADR-013 D1). The worker holds the writer lock and takes the oldest queued-or-running job; a running job found under the lock was orphaned by a dead worker. SQS leaves S15's plan | An SQS-shaped message table behind an interface; ElasticMQ + boto3 | 1 worker, 1 job type, 1 shared database; one source of truth; a dead worker noticed at once (0.000 s) |
| 2 | **A fixed job:** ingest → lifecycle → embed → chains, no request input. Guards: the worker refuses `INGEST_SCOPE` other than `full`; embed runs only after ingest succeeded in the same job (ADR-013 D2) | No embed in the job; caller-chosen steps | 0 texts at the current lock; the cap bounds surprises; the guards stop embed's orphan deletion from wiping the cache |
| 3 | **One corpus-writer lock** taken by all 6 writers, on the writer's only connection; CLI writers exit 1 when it's held; the worker retries on its next poll (ADR-013 D3) | Locks inside the 2 identifier functions only; one identifiers table | One mechanism for R3, double-paid embeds and dead-worker detection; no table change |
| 4 | **One active job:** a repeated POST returns it (202 new, 200 existing), enforced by the database (ADR-013 D4) | 409 with a 6th code; always create; queue one more while running | Safe to click twice; no new code; 2 POSTs at once make 1 job |
| 5 | **Errors fail the job at once; a crash is resumed** at the first unfinished step, at most 3 attempts (ADR-013 D5) | Retry every error 3 times; a permanent/temporary split | Ingest's errors are deterministic; the kill probes show resume is safe |
| 6 | **One table**, the 4 steps as a JSON list in the job row (ADR-013 D6) | A separate steps table | Every read is one job by ID; no cross-job query |
| Plan | The verification plan and PR plan below; no paid calls | — | — |

**Claude's calls** (reversible; confirmed at the read-back):
- a. **The lock:** one fixed key in `db/`; a CLI writer that can't get it exits 1 with `Another corpus writer is running (make ingest, lifecycle, embed, chains, seed or make worker); try again when it finishes.` `make reset-corpus` (raw `psql`) is outside it; the docs say so.
- b. **The worker loop:** every `WORKER_POLL_S` (5 s): try the lock; with it, take the oldest queued-or-running job, run it, release the lock; with no job, release the lock and sleep. A hand-run writer can run while the worker is idle.
- c. **Attempts:** counted when a run or resume starts; a job found at `WORKER_MAX_ATTEMPTS` (3) is marked failed (`gave up after 3 attempts`) without running.
- d. **Steps and counts:** ingest (documents stored, new documents, new versions, closed versions, new chunks, failures, **fingerprint**), lifecycle (rows), embed (texts, requests, embedded, tokens, orphans deleted), chains (per seed: found, missing). Any ingest failure fails the step.
- e. **The worker's connection:** one plain autocommit connection with the connect timeout and no statement timeout; the lock and every step use it.
- f. **Start-up checks:** `INGEST_SCOPE` must be `full`; `VOYAGE_API_KEY` must be set; otherwise exit 1 with a message, before connecting.
- g. **Logs:** the worker configures logging from `config/logging.json` (the same JSON formatter as `make serve`); while a job runs, `logs.request_id` is set to the job's `request_id` and its lines carry `job_id` (`extra=`).
- h. **The job's error text:** known errors give their own message (releases mismatch, a missing GitHub snapshot, the embed cap, ingest failures: their count and the first one); anything else gives `internal error; see the worker log (job <id>)`, with the traceback logged.
- i. **POST and GET:** POST inserts in one transaction (`ON CONFLICT DO NOTHING`); if refused, it reads the active job (if that job ended in between, it inserts again, at most 2 tries). GET: 404 `not_found` for an unknown ID, 422 `invalid_request` for a non-integer.
- j. **R1's carried item (K1 of S13-R1):** `make ingest-report`'s reads and `stored_decision`'s 2 reads each run in one read-only REPEATABLE READ transaction.
- k. **New settings:** `WORKER_POLL_S=5` (`ge=1`), `WORKER_MAX_ATTEMPTS=3` (`ge=1`), with `.env.example` lines.
- l. **Docs in the contract commit:** ADR-013 (Accepted) and its index row; the backlog's S14 outcome and T4 title, S15's Terraform list (no SQS), the ADR queue row, the "S15 security review inputs" Proposed addition; this slice doc's outcome, exit checks, scope, T4–T7 and R1's status.

#### Pinned: T4 (job table, writer lock, snapshot reads)

- **Migration `0009_ingestion_jobs`:** `ingestion_jobs`:
  - `id` bigint identity primary key; `status` text not null default `queued`, check in (`queued`, `running`, `succeeded`, `failed`);
  - `created_at` timestamptz not null default `now()`; `started_at`, `finished_at` timestamptz null; `attempts` integer not null default 0 (check ≥ 0);
  - `error` text null; `request_id` text null; `steps` jsonb not null.
  - The unique index `ingestion_jobs_one_active` on `((true))` where status in (`queued`, `running`).
  - The migration test covers upgrade and downgrade, like the earlier ones.
- **`db/models.py`:** `JobStep` (`name`, `status` ∈ pending/running/succeeded/failed, `started_at`, `finished_at`, `counts: dict[str, int | str]`, `error`) and `IngestionJob` (the columns, `steps: list[JobStep]`). The API returns `IngestionJob` as is.
- **`db/jobs.py`** (the only SQL for jobs): create a job with the 4 steps pending (or return None when the rule refuses it), read a job by ID, read the active job, save a job's status, times, attempts, error and steps.
- **`db/writer_lock.py`:** the fixed key; `try_writer_lock(conn) -> bool`; `release_writer_lock(conn)`; a context manager that raises `WriterBusy` when it's held elsewhere. A session lock (`pg_try_advisory_lock`), never a transaction lock.
- **The 5 CLI writers** (`ingest`, `lifecycle`, `seed`, `embed`, `provenance.build`): take the lock right after connecting, on that connection, before any read or write; `WriterBusy` → exit 1 with call a's message. `ingest.main`'s own lifecycle rebuild runs under the same hold.
- **Snapshot reads** (call j): `report.main` and `stored_decision`.

#### Pinned: T5 (the worker)

- **`ingestion/worker.py`**, run by `make worker` (`uv run python -m orgknow.ingestion.worker`).
- **Steps:** a list of `(name, function)` where a function takes the connection and returns its counts (call d), built by `main` from settings; tests pass their own list. The real steps call the existing functions (`ingest`, `rebuild_lifecycle`, `embed_missing` with a `VoyageEmbedder` from settings, the chain builder's per-seed store), not the `main`s.
- **`run_once(conn, steps, max_attempts) -> int | None`:** try the lock (none → None); read the active job (none → release, None); if attempts ≥ max → failed, `gave up after N attempts`; else attempts + 1, status running, `started_at` if unset; run each step from the first not `succeeded` (a step left `running` restarts from its beginning), saving the step's status and times before and after; on an error: the step and the job `failed` with call h's text, later steps stay `pending`; all done → `succeeded`, `finished_at`. Release the lock; return the job ID.
- **`main`:** call f's checks, logging (call g), connect (call e), then `run_once` every `WORKER_POLL_S` until Ctrl-C. A Ctrl-C mid-job is a crash (resumed on the next start).
- **Embed after a failed ingest is impossible by construction** (steps stop at the first failure); a test pins it.

#### Pinned: T6 (job endpoints)

- `POST /ingestion-jobs`: no body (an unexpected body is ignored); 202 with `IngestionJob` when created, 200 with the active job otherwise; the job's `request_id` is the request's. Uses `api_connection`; 503 `database_unavailable` as the other routes.
- `GET /ingestion-jobs/{job_id}`: 200 `IngestionJob`; 404 `not_found` (`no ingestion job with this id`); 422 for a non-integer; 503 as the other routes.
- **`docs/interfaces.md`:** both in the endpoint table and as `### POST /ingestion-jobs` and `### GET /ingestion-jobs/{job_id}` (purpose, request, bodies, statuses, cost: free at the current lock, embed paid only for new texts and capped; retry: POST safe to repeat, it returns the active job); a "Worker" section: the lock, the loop, steps, statuses, attempts, the error text, the worker's log fields; the dependencies table gains the worker's database connection.

#### Pinned: T7 (docs and retro)

- `docs/architecture.md`: the jobs path and the writer lock, and the module table's missing modules (K2); the README's run commands (`make worker`, the 2 endpoints); K1's doc nits in `docs/interfaces.md`; the comment K2 names.
- The S14 retro (`/slice-retro`) as the run's last commit: slice brief `docs/learning/S14-backend-hardening.md`, backlog ticks and slice status.

#### Handoffs between tasks

- T4 → T5: `db/jobs.py`, `IngestionJob`/`JobStep`, the lock functions; every CLI writer already takes the lock, so the worker's hold excludes them.
- T5 → T6: `run_once` turns a created job into a finished one; T6 only creates and reads jobs (it never takes the writer lock).
- T6 → T7: the endpoints' doc sections; the demo's outputs feed the retro's numbers.

#### Edge cases

- A POST while the worker runs the active job: 200 with it (decision 4).
- The worker started while a CLI writer holds the lock: it waits (polls) and logs one INFO line per poll at most every 60 s, not every 5 s.
- A job left `running` by a crash, with `attempts` = 3: failed without running (call c).
- A killed worker mid-step: that step restarts from its beginning (every step is safe to re-run; the kill probes).
- `ingest` reports failures → the ingest step fails; lifecycle, embed and chains don't run.
- The embed cap refuses (`RunTooLarge`) → the embed step fails with its message; chains don't run.
- Ctrl-C while idle: exits 0, holding nothing.
- `make reset-corpus` while the worker runs: not prevented (raw `psql`; documented).
- GET of a job ID beyond bigint (e.g. 20 digits): 422 or 404, never 500.
- `make test-int`'s database gains the new table through the existing migration fixture.

#### Files in scope

`src/orgknow/db/migrations/versions/0009_ingestion_jobs.py`, `src/orgknow/db/jobs.py`, `src/orgknow/db/writer_lock.py`, `src/orgknow/ingestion/worker.py` (new); `src/orgknow/db/models.py`, `src/orgknow/db/decisions.py` (snapshot), `src/orgknow/ingestion/report.py` (snapshot), `src/orgknow/ingestion/ingest.py`, `src/orgknow/ingestion/lifecycle.py`, `src/orgknow/ingestion/seed.py`, `src/orgknow/embeddings/embed.py`, `src/orgknow/provenance/build.py` (the lock), `src/orgknow/api/app.py` (routes), `src/orgknow/settings.py`, `.env.example`, `Makefile` (`worker`); tests under `tests/unit/` and `tests/integration/`; `docs/interfaces.md`, `docs/architecture.md`, `README.md`, `docs/backlog.md`, this slice doc, `docs/learning/S14-backend-hardening.md` (T7).

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T4 | The table and the one-active-job rule | Integration: a second queued job is refused (create returns None); a succeeded one then allows a new one | Decision 4; the sitting's index check |
| T4 | All 6 writers take the lock | Integration: the test holds the lock; each of the 5 CLI `main`s exits 1 with call a's message (the worker: T5's row) | The sitting's writer list |
| T4 | The lock is freed when its holder dies | Integration: a subprocess holds it, is SIGKILLed; the test's try-lock succeeds | The sitting probe |
| T4 | Snapshot reads | Integration: inside each, `SHOW transaction_isolation` = `repeatable read` and `transaction_read_only` = `on` (read through a test hook or a spy on the connection) | Call j |
| T5 | 4 steps in order, each recorded | Integration, fake steps: `succeeded`, attempts 1, 4 steps `succeeded` with their counts and times | Decision 6 |
| T5 | An error fails at once | A raising fake step 2: job `failed`, step 2 `failed` with its text, steps 3–4 `pending` and never called | Decision 5 |
| T5 | A killed worker is resumed | A subprocess worker whose step 2 blocks; SIGKILL once step 2 reads `running`; `run_once` in the test: step 1 not called again, step 2 rerun, `succeeded`, attempts 2 | Decision 5 |
| T5 | The attempt limit | A `running` job at attempts 3: `failed`, `gave up after 3 attempts`, no step called | Call c |
| T5 | The worker excludes CLI writers and vice versa | `run_once` while the test holds the lock → None, job untouched | Decision 3 |
| T5 | The scope guard and the key check | `main` with `INGEST_SCOPE=s04`, then with no key: exit 1 with the messages | Decision 2, call f |
| T5 | Unknown errors hide their text | A fake step raising `RuntimeError("secret-xyz")`: the job's error is call h's text, without `secret-xyz` | Call h |
| T6 | POST 202 then 200, same ID; GET 200 | Integration API tests | Decision 4 |
| T6 | 2 POSTs at once make 1 job | Integration: 2 threads POST; 1 row; one 202 and one 200 | Decision 4 |
| T6 | GET 404 and 422 | API tests | Call i |
| T6 | The doc lists both routes | `test_interfaces_doc.py` (unchanged) | — |

#### Break-it rules

- T4: remove the lock from one CLI writer → its lock test fails.
- T5: resume from the first step instead of the first unfinished one → the resume test fails.
- T6: drop the one-active-job index from the migration → the 2-POST test fails.

#### Real-data demo

On the scratch database `orgknow_r2probe` (never the dev database), free: `EMBED_MAX_TOKENS_PER_RUN=1` makes any paid request refuse.

```bash
export DATABASE_URL=postgresql://orgknow:orgknow@localhost:5433/orgknow_r2probe EMBED_MAX_TOKENS_PER_RUN=1 HF_HUB_OFFLINE=1
make migrate
docker compose exec -T db psql -U orgknow -d orgknow_r2probe -c "TRUNCATE documents, document_aliases, document_versions, chunks RESTART IDENTITY CASCADE"
make serve &                                   # stop it by PID at the end
.venv/bin/python -m orgknow.ingestion.worker & # the Python PID itself, not make/uv
curl -si -X POST http://127.0.0.1:8000/ingestion-jobs   # 202
curl -si -X POST http://127.0.0.1:8000/ingestion-jobs   # 200, the same id
# while the ingest step runs: `make ingest` exits 1 with the writer-lock message
# at ~40 s: kill -9 <worker Python PID>; start the worker again
curl -s http://127.0.0.1:8000/ingestion-jobs/<id>       # succeeded, attempts 2
curl -si -X POST http://127.0.0.1:8000/ingestion-jobs   # 202, a new job: the repeated run
```

Expected (from the sitting's probe, not the code): both jobs `succeeded`; the ingest step's fingerprint `sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165` both times; the second job's ingest counts 0 new versions and 0 new chunks; embed 0 requests; chains `kep:2572` 6 found and `kep:3015` 5 found, 1 missing; afterwards 21,762 embeddings, 3,295 lifecycle rows, 2 decisions and 12 chain-step rows. Show the worker's JSON lines with the job's `request_id` equal to the POST's `X-Request-ID`.

#### Bundle-level check

1. `make migrate` on the dev database; `make check` and `make test-int` (Postgres checked at run start).
2. `HF_HUB_OFFLINE=1 make eval-retrieval` prints S14-R1's baseline metric lines exactly (the timing line may differ).
3. `make ingest-report` on the dev database prints `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`.

#### PR plan

- **1 PR** for T4–T7 (decision "Run shape"): the size alarm doesn't split it; the brief records files and reviewable lines. Estimate ~1,400–1,800 reviewable lines.
- Greptile: 1 trigger (22/50 → 23/50).

#### Paid calls allowed

None. Every test uses fakes; the demo's embed sends 0 texts, capped at 1 estimated token. No Anthropic credit needed.

## Retro

- **Shipped (with numbers):**
  - **S14-R1** (T1–T3; PRs #49 and #50, merged 2026-10-14, split after T2 on the size alarm): `docs/interfaces.md` (4 routes, 1 error envelope, 5 codes); a request ID on every response and in its JSON log lines; 7 timeout and retry settings; autocommit API connections (the sitting's `idle in transaction` now reads `idle`); temporal and authority modes tested over the API.
  - **S14-R2** (T4–T7; 1 PR, the developer's call), ~1,980 reviewable lines in 30 files (1,033 of them tests), against an estimate of 1,400–1,800:
    - **T4:** migration `0009` (`ingestion_jobs`, the one-active-job index); the corpus-writer lock in the 5 CLI writers (each exits 1 while it's held); `make ingest-report` and `stored_decision` each read in one snapshot.
    - **T5:** `make worker`: 4 steps with progress in the job's row; an error fails the job; a killed worker's job resumes at its first unfinished step, at most 3 attempts.
    - **T6:** `POST /ingestion-jobs` (202 new, 200 active) and `GET /ingestion-jobs/{job_id}` (200, 404, 422, 503); the "Worker" section of `docs/interfaces.md`.
    - **T7:** `docs/architecture.md` (the jobs path, the lock, every module in the table), the README, S14-R1's 2 kept doc items.
  - **The demo** (scratch database, corpus emptied): the worker killed 43.5 s into ingest (21,278 chunks stored) and restarted → the job `succeeded` at attempt 2 with fingerprint `sha256:0f0ee078…4165`; a repeated job: 0 new versions, 0 new chunks, 0 embed requests. Afterwards 21,762 embeddings, 3,295 lifecycle rows, 2 decisions and 12 chain-step rows: the sitting's clean run.
  - **Guard:** `make eval-retrieval`'s 5 metric lines equal S14-R1's baseline exactly; the dev database's fingerprint is unchanged after migration `0009`.
  - **Tests:** 1,130 unit (1,061 at S13's close), 251 integration (214).
  - **Reviews (R2):** 0 must-fix in T4 and T5; 3 in T6 (2 false doc lines, the backlog tick) and 3 in T7 (3 false doc statements). All fixed.
  - **Paid:** none in S14. Greptile 22/50 before R2's PR.
- **Surprises:**
  - **The worker's own log lines were dropped** in its first real run: under `python -m` a module's `__name__` is `__main__`, outside the `orgknow` logger the config sets to INFO. No test caught it; the logger is now named.
  - **Job ids have gaps:** a refused `ON CONFLICT DO NOTHING` insert still uses an identity value (the demo's jobs are 3 and 5).
  - **A 20-digit job id is a 404, not a 500:** psycopg sends an int beyond bigint as `numeric`, which matches no row. Path ids also accept `1.0`, `+1` and `1_000` (pydantic's lax mode).
  - **`make` exits 2 when its recipe exits 1,** so the docs say a refused writer "stops", not "exits 1".
  - **The worker's no-op ingest took ~19 s** in T5's run, against 45 s for `make ingest` in the sitting (cause not measured).
- **What didn't work / negative results:**
  - **5 of R2's 6 must-fix items were false doc statements** (T6, T7), all found by reviewers, none by tests.
  - **ADR-013's Consequences don't match the code on a passing glitch:** they say a Postgres restart fails the job; the code exits the worker, and the next start resumes the job (1 attempt used). `docs/interfaces.md` describes the code; the ADR's wording is the developer's call.
  - **Nothing restarts a stopped worker** (a lost connection ends it, idle or mid-job): S15's deployment needs a supervisor.
  - **Not exercised:** a lost connection mid-job or while idle; Ctrl-C mid-job with the real steps; the once-per-60-s "waiting" line.
- **Do differently next slice:**
  - In a docs task, have the builder list each new sentence beside the code line it rests on: R2's reviewers found 5 false statements, S13's T6 found 6.
  - Run each new command's real entry point once before review: only the real `python -m` run found the dropped log lines.
  - Keep estimating with tests included: R2's came to ~1,980 lines, ~10% above its estimate's top (1,400–1,800); S13's was 3× low.
- **Slice brief:** `docs/learning/S14-backend-hardening.md`
- **PR #51 review answers (the developer, 2026-10-14):**
  - **Chain errors are shown as written** (changes call h). The chain builder's 4 messages share one error type, `ChainError` (a `ValueError`, so `make chains` is unchanged), which the worker adds to the errors a job shows as written; `docs/interfaces.md` ("Worker") lists them. Why: each is a fixed sentence naming only a seed, an id, a section or the command to run. Rejected: only ``<seed> is not stored: run `make ingest` `` (option A: the other 3 stay "internal error"); showing every `ValueError` (any library's text could reach the API).
  - The other 2 answers (a lost connection stops the worker; giving up also fails the step left running) are ADR-013's amendment 2026-10-14.
