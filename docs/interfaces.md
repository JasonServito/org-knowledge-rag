# Interfaces

The API's contract: each endpoint's input, output and errors, the one error shape, request IDs, the log format, and each external dependency's timeout and retries.

- It describes the API as run S14-R1 leaves it. S14-R2 adds the ingestion job endpoints.
- Every statement matches the code or a test. `tests/unit/test_interfaces_doc.py` checks that each route has a `###` heading below, each `###` heading is a route, and the error-code table equals the code's list.
- `make serve` runs the API on `http://127.0.0.1:8000`. There is no auth and no rate limit (S15's security review).

| Endpoint | Does | Cost | Statuses |
|---|---|---|---|
| `GET /health` | Liveness: the process answers HTTP | Free | 200 |
| `GET /ready` | Readiness: Postgres is reachable | Free | 200, 503 |
| `POST /query` | Answers a question with citations | Paid | 200, 422, 502, 503, 500 |
| `GET /decisions/{canonical_id}` | A seed KEP's stored decision chain | Free | 200, 404, 503, 500 |

## Endpoints

Every response carries an `X-Request-ID` header (see Request IDs). Any endpoint answers an unexpected failure with a 500 `internal` (see Errors).

### GET /health

- **Purpose:** liveness. The process is up and answering HTTP. It never touches the database.
- **Request:** no parameters.
- **200:** `{"status": "ok"}`, always.
- **Other statuses:** none.
- **Cost:** free.
- **Retry:** safe (reads nothing, writes nothing).

### GET /ready

- **Purpose:** readiness. Can this process serve real traffic? It opens a new Postgres connection (waiting at most `DB_CONNECT_TIMEOUT_S`, 2 s) and runs `SELECT 1`. It checks only Postgres, not Voyage or Anthropic.
- **Request:** no parameters.
- **200:** `{"status": "ready"}`.
- **503:** `{"status": "unavailable"}`, on any database error (can't connect in time, refused, `SELECT 1` failed).
  - This body is a probe answer, not the error envelope: it has no `error` object and no `request_id`. The `X-Request-ID` header is still set.
- **Cost:** free (one short database connection).
- **Retry:** safe (writes nothing).

### POST /query

- **Purpose:** answer one question through the same pipeline as `orgknow ask` (`pipeline.answer_question`): route (temporal and authority modes), retrieve, find rule-found conflicts, answer, validate citations.
- **Request:** a JSON object with one field (the `Query` model in `api/app.py`). Other fields are ignored.
  - `question`: a string, at least 1 character, at least one of them not a space.
  - Example: `{"question": "What enforces pod security standards in-tree?"}`
- **200:** the `Answer` model (`generation/schema.py`), the JSON `orgknow ask` prints:
  - `question`: the question as sent.
  - `answer_status`: `answered` or `insufficient_evidence`. Insufficient evidence is a 200, not an error.
  - `answer`: the answer text; `""` when nothing was retrieved or the citations were rejected.
  - `evidence`: the citations, each an `Evidence`: `chunk_id`, `document`, `title`, `section`, `source_type`, `release_windows`, `claimed_status`, `claimed_stage`, `tier`, `superseded_proposal`, `effective_stage`, `stage_confidence`, `source_url`.
  - `conflicts`: each a `Conflict` (`generation/conflicts.py`): `kind`, `found_by`, `chunk_ids`, `documents`, `summary`, `resolution`, `prevails`.
  - `insufficient_evidence_reason`: a string, or `null` when answered.
  - `model`: the answer model's name.
  - `trace_id`: the Langfuse trace's ID, or `null` when tracing is off.
- **Other statuses:**
  - **422 `invalid_request`:** the body isn't JSON or isn't an object, `question` is missing or not a string, or it is empty or only spaces. No connection is opened and no paid call is made.
  - **502 `upstream_failed`:** the ask failed upstream (`pipeline.ASK_ERRORS`): Voyage or Anthropic (answer or router) failed after its retries, or the model gave no usable answer or route (a refusal, a cut-off, output off the schema). Any `RuntimeError` or `ValueError` raised during the ask is reported the same way, because `ASK_ERRORS` lists those 2 base types.
  - **503 `database_unavailable`:** no connection within `DB_CONNECT_TIMEOUT_S`, the connection failed mid-request, or a statement ran past `DB_STATEMENT_TIMEOUT_MS` (psycopg's `OperationalError`, which includes a cancelled statement). No paid call is made when the connection can't be opened.
  - **500 `internal`:** anything else, including a database error that isn't a connection failure (e.g. a missing table).
- **Cost:** paid, per call: 1 Voyage embedding request and 1 Anthropic answer call, plus 1 Anthropic router call in temporal and authority modes (authority is the default). With nothing retrieved, the answer call is skipped. Each retry (see Dependencies) is another request.
- **Retry:** safe: it writes nothing to the database. Each retry pays again, and the model may word the answer differently. With tracing on, each call leaves its own trace.

### GET /decisions/{canonical_id}

- **Purpose:** read the stored decision chain of one seed KEP, as `orgknow chain` prints it (`load_chain`). Read-only: it never builds a chain (`make chains` does).
- **Request:** the path parameter `canonical_id`, a seed KEP's id, e.g. `kep:2572`. Any text without a `/` is looked up; a `/` inside the id matches no route (404), and a trailing `/` redirects (307) to the id without it.
- **200:** the `Chain` model (`provenance/chain.py`):
  - `seed`, `title`, `built_at` (ISO 8601, UTC).
  - `steps`: in step order (`problem`, `discussion`, `proposal`, `decision`, `implementation`, `current_docs`), each a `ChainStep`: `step`, `occurred_at`, `chunk_id`, `canonical_id`, `heading_path`, `source_type`, `source_url`, `tier`, `found_by`, `via_chunk_id`, `via_canonical_id`, `via_heading_path`, `missing_reason`. A missing step has only `step` and `missing_reason`; the rest are `null`.
- **Other statuses:**
  - **404 `not_found`:** no chain is stored for this id. The message doesn't repeat the id (see Errors).
  - **503 `database_unavailable`:** as `POST /query`, including a statement past `DB_STATEMENT_TIMEOUT_MS`.
  - **500 `internal`:** anything else (e.g. a missing table or manifest file).
- **Cost:** free.
- **Retry:** safe (writes nothing).

## Errors

Every error response from the API uses one envelope, with 2 exceptions:

- `/ready`'s 503 probe answer above.
- A 405, when a route is called with the wrong method (e.g. `GET /query`): FastAPI's own `{"detail": "Method Not Allowed"}`. None of the 5 codes fits it, and no client sends it. The `X-Request-ID` header is still set.

```json
{"error": {"code": "not_found", "message": "no stored decision chain for this canonical_id; chains are built by make chains", "request_id": "0b9f6c2e8d0a4f6b9c1d2e3f4a5b6c7d"}}
```

- `code`: one of the 5 codes below. A client switches on the code, never on the message.
- `message`: one line for a human.
- `request_id`: the same value as the response's `X-Request-ID` header.

The codes (`ERROR_CODES` in `src/orgknow/api/errors.py`). Each code has exactly one status.

| Code | Status | When | Example `message` |
|---|---|---|---|
| `invalid_request` | 422 | The request fails validation (`POST /query`'s body) | `body.question: Field required` |
| `not_found` | 404 | No stored chain for the id, or no route for the path | `no stored decision chain for this canonical_id; chains are built by make chains` |
| `upstream_failed` | 502 | Voyage or Anthropic failed after its retries, or the model gave no usable answer or route | `no usable answer from the model (stop reason: refusal)` |
| `database_unavailable` | 503 | Postgres can't be reached in time, the connection fails, or a statement runs past its timeout | `database unavailable` |
| `internal` | 500 | Anything unexpected, including a database error that isn't a connection failure | `internal error` |

**Message rules:**

- `message` never carries a traceback, a secret, a database URL or the caller's input. The traceback goes to the log, under the same request ID.
- `invalid_request`: `"<location joined by .>: <problem>"` of the first validation error only, e.g. `body.question: String should match pattern '\S'`. The value sent is never echoed.
- `not_found`: for a missing chain, the text in the table (no id); for an unknown path, `Not Found`.
- `upstream_failed`: the failure's one line, the same text `orgknow ask` prints after `error: ` (`pipeline.one_line`). For an HTTP error it includes the provider's own reason (Voyage's: its first 500 characters).
- `database_unavailable` and `internal`: the fixed texts in the table.

## Request IDs

- **The rule:** a request's `X-Request-ID` header is used as given when it is 1 to 64 characters, each one of `A-Z a-z 0-9 . _ -` (the whole value matches `[A-Za-z0-9._-]{1,64}`).
- Otherwise (missing, empty, 65+ characters, or any other character such as a space, a newline or non-ASCII), the API makes a new random ID: 32 lowercase hex characters. A rejected value is never logged.
- **Where the ID appears:**
  - the response's `X-Request-ID` header, on every response: every status, every endpoint, unknown paths, and a 500;
  - the error body's `request_id`;
  - every log line written while the request runs: its per-request line, warnings (e.g. a Voyage retry), and the error line of an unexpected failure.

## Logs

- **Only `make serve`** sets this up, through uvicorn's log config (`--log-config config/logging.json --no-access-log`). Library code never configures logging. The CLI and the other make targets are unchanged: their stderr lines stay plain text.
- **Format:** the app's and uvicorn's log lines are JSON, one object per line.
- **One line per request**, at INFO, after its response is sent:

| Field | Value |
|---|---|
| `ts` | When the line was written: ISO 8601 in UTC with milliseconds, e.g. `2026-10-13T22:05:11.250+00:00` |
| `level` | `INFO` |
| `logger` | The logger's name, e.g. `orgknow.api.middleware` |
| `message` | `"<method> <path> <status>"`, e.g. `GET /health 200` |
| `request_id` | The request's ID |
| `method` | The HTTP method, e.g. `POST` |
| `path` | The URL path, without the query string |
| `status` | The response's status, an integer |
| `duration_ms` | Milliseconds from the request's arrival to the end of its response, a number |
| `trace_id` | Only on `POST /query` when its 200 body has a `trace_id` (tracing on): the same value. Otherwise the field is absent, never `null` |

Example:

```json
{"ts": "2026-10-13T22:05:11.250+00:00", "level": "INFO", "logger": "orgknow.api.middleware", "message": "GET /health 200", "request_id": "0b9f6c2e8d0a4f6b9c1d2e3f4a5b6c7d", "method": "GET", "path": "/health", "status": 200, "duration_ms": 1.4}
```

- **Other lines** carry at least `ts`, `level`, `logger` and `message`; `request_id` when written inside a request; and `exc_info`, the traceback as text, when the line records an exception.
- **An unexpected failure** writes one ERROR line with `exc_info`; the request's own line then shows status 500.
- **Not JSON:** 2 lines the pipeline prints to stderr, shared with the CLI: `tracing off: …` once at startup when the Langfuse keys are unset, and the route line of each ask in temporal and authority modes. Also anything a library writes to stderr itself.

## Dependencies

Each external call has a timeout and a retry limit from the settings (environment variables, defaults shown). Nothing retries forever.

| Dependency | Called by | Timeout | Retries | Retried on | The API caller sees |
|---|---|---|---|---|---|
| Postgres | `/ready`, `/query`, `/decisions` | Connect: `DB_CONNECT_TIMEOUT_S=2` (s). Each statement: `DB_STATEMENT_TIMEOUT_MS=10000` (`/query`, `/decisions`; not `/ready`) | 0 | — | 503 `database_unavailable` (`/ready`: 503 `{"status": "unavailable"}`). Another database error: 500 `internal` |
| Voyage (question embedding) | `/query` | `VOYAGE_TIMEOUT_S=60` | `VOYAGE_MAX_RETRIES=3`, after 1 s, 2 s, 4 s (doubling) | HTTP 429 and 5xx only. Not a timeout or a failed connection | 502 `upstream_failed` |
| Anthropic, answer | `/query` | `GENERATION_TIMEOUT_S=90` | `ANTHROPIC_MAX_RETRIES=2`, after ~0.5 s, then ~1 s | The SDK's rule: no connection, a timeout, HTTP 408, 409, 429, 5xx | 502 `upstream_failed` |
| Anthropic, router | `/query` in temporal and authority modes | `ROUTER_TIMEOUT_S=30` | `ANTHROPIC_MAX_RETRIES=2`, as above | As above | 502 `upstream_failed` |
| GitHub | Not the API: only `make fetch-github`, a manual command | `GITHUB_TIMEOUT_S=30` | 0 | — | Never called by the API. The command stops with `Nothing written: <item>: <error>` and writes nothing |
| Langfuse | `/query` when both Langfuse keys are set | The SDK's 5 s per export (its own `LANGFUSE_TIMEOUT` variable, not a `Settings` field) | The SDK's exporter's own, within that 5 s | — | Never an error. The SDK exports traces in the background; a failed export loses the trace, never the answer |

Notes:

- `DB_CONNECT_TIMEOUT_S`: libpq treats values below 2 as 2.
- Anthropic: not retried are other 4xx errors (e.g. a wrong key: 401) and a refusal or cut-off answer, which is a normal reply. The SDK waits ~0.5 s then ~1 s between tries (with jitter), or as long as a `retry-after` header says.
- Voyage: any other HTTP error fails at once. A Voyage retry writes one WARNING log line.
- Startup checks only that `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are set. A wrong key shows up as a 502 on `/query`.
- At shutdown, the API waits for Langfuse's queued traces (`flush`).
- The reranker isn't a network call: it runs in-process on CPU (loaded once at startup), with no timeout.

## Worst case per POST /query

A known limit, not a promise: authority mode (the default), every step failing at its limit with the default settings.

| Step | Limit |
|---|---|
| Connect to Postgres | 2 s |
| Route (router call) | 3 tries × 30 s + at most 1.5 s of waits = 91.5 s |
| Embed the question (Voyage) | 4 tries × 60 s + 1 + 2 + 4 s of waits = 247 s |
| Answer (Anthropic) | 3 tries × 90 s + at most 1.5 s of waits = 271.5 s |
| **Network steps in total** | **612 s (~10 minutes)** |
| Each SQL statement | 10 s (an ask runs several; their sum has no cap) |
| Rerank | No limit (local CPU) |

Why it isn't a hard bound:

- A timeout bounds each wait on the network (connecting, or the gap between bytes received), not a whole try. A reply that trickles in can take longer.
- When Anthropic sends a `retry-after` header (e.g. with a 429), the SDK waits that long instead; SDK 1.11.0 sets no upper cap.
- The SQL statements and the reranker add to the 612 s.
