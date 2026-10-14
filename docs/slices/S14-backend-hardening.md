# S14: Backend hardening + async ingestion

- **Status:** 🟨
- **Blueprint stage:** 10 (Backend hardening + async ingestion)
- **Started:** 2026-10-13
- **Finished:**

## Outcome

Every API response carries a request ID that also appears in one-line JSON logs, with one error shape and explicit timeouts and bounded retries on every external call (R1). `POST /ingestion-jobs` queues a job that `make worker` runs to completion with per-step progress; a duplicate delivery or a killed worker leaves the same ingestion fingerprint (R2).

## Why now

- Blueprint §21, §22, §26 and §29: the backend practices and the async ingestion path come before AWS (S15), which deploys them as they are.
- Blueprint gap #7: interface contracts come before major backend work.
- It retires 2 known risks before a second writer exists: the R3 identifier race and concurrent `make embed` runs (Proposed additions, "Make R3 race-free… (S14 at the latest)").

## Exit checks

- [ ] `docs/interfaces.md` gives each endpoint's input, output and errors, the one error shape, and each dependency's timeout, retry and failure policy.
- [ ] A response to any endpoint carries `X-Request-ID`, and the API's log lines for that request are JSON carrying the same ID.
- [ ] Anthropic, Voyage and GitHub calls use timeouts and retry counts from settings; tests show the retries are bounded.
- [ ] API tests cover temporal and authority modes (S12-R1 input).
- [ ] *(R2)* `POST /ingestion-jobs` → `make worker` → the job reaches `succeeded` with per-step progress in `GET /ingestion-jobs/{id}`.
- [ ] *(R2)* A duplicate delivery and a worker killed mid-job each end with the same fingerprint as a clean run.
- [ ] *(R2)* Two writers can't store the same identifier (R3) or embed the same texts twice.
- [ ] Phase 1 retrieval unchanged: `make eval-retrieval` (free) prints S13's numbers exactly.
- [ ] `make check` and `make test-int` green.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| `docs/interfaces.md` | API versioning (blueprint §21: "only if it becomes useful") |
| Request IDs, JSON logs, one error handler | A log platform; CloudWatch (S15) |
| Timeouts and bounded retries from settings | Circuit breakers; fallback models |
| A database connection pool for the API (if decided) | Async (`async def`) database access |
| API tests for temporal and authority modes | Retrieval or scoring changes |
| *(R2)* A job table, a local queue shaped like SQS, a worker, the job endpoints | Real SQS, S3 and EC2 (S15) |
| *(R2)* A single-writer guarantee for ingest and embed (R3) | Refreshing the corpus lock (K2: a proposed addition) |
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

### S14-T4: Job table, local queue, single-writer lock `[core]`

- **Goal:** a job record in Postgres and a queue that behaves like SQS (at-least-once delivery, visibility timeout).
- **Done when:** decided in the S14-R2 sitting (ADR-013).
- **Notes / pointers:** blueprint §22 ("Track partial failure and job progress in PostgreSQL"); the R3 race item; PR #30's report snapshot; PR #48's chain-read snapshot.
- **Deps:** T1–T3.

### S14-T5: The worker (`make worker`) `[core]`

- **Goal:** run a job's steps (ingest, lifecycle, embed, chains) idempotently, with progress, surviving duplicate delivery and crashes.
- **Done when:** decided in the S14-R2 sitting.
- **Deps:** T4.

### S14-T6: Job endpoints `[commodity]`

- **Goal:** `POST /ingestion-jobs`, `GET /ingestion-jobs/{id}`; `docs/interfaces.md` gains them.
- **Done when:** decided in the S14-R2 sitting.
- **Deps:** T4, T5.

### S14-T7: Docs and the S14 retro `[commodity]`

- **Goal:** architecture, README, slice brief.
- **Deps:** T6.

## Risks & unknowns

- Changing logging could change the CLI's stderr lines, which tests and the eval read.
- An Anthropic timeout set too short would fail real answers: the slowest saved ask took 29.7 s (658 rows in `eval/results/`, whole ask).
- The pool's size and the reranker: concurrent requests already share 1 reranker.
- *(R2)* The worker's steps take real time (a no-op `make ingest` takes 45 s); embed is paid.

## Decisions expected (ADRs)

- R1: no connection pool; autocommit API connections (ADR-005 amendment 2026-10-13, decided in the S14-R1 sitting).
- R2: ADR-013, async ingestion (job model, queue, idempotency). Deployment topology moves to ADR-014 (S15).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S14-R1: Hardening

- **Status:** PR open (split after T2 on the size alarm: PR 1 T1–T2, PR 2 T3, stacked)
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

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S14-*.md`
