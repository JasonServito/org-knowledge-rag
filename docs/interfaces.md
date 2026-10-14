# Interfaces

The API's contract: each endpoint's input, output and errors, the one error shape, request IDs, the log format, each external dependency's timeout and retries, and the ingestion worker that runs the jobs the API queues.

- It describes the API and the worker as run S14-R2 leaves them.
- Every statement matches the code or a test. `tests/unit/test_interfaces_doc.py` checks that each route has a `###` heading below, each `###` heading is a route, and the error-code table equals the code's list.
- `make serve` runs the API on `http://127.0.0.1:8000`. There is no auth and no rate limit (S15's security review).

| Endpoint | Does | Cost | Statuses |
|---|---|---|---|
| `GET /health` | Liveness: the process answers HTTP | Free | 200 |
| `GET /ready` | Readiness: Postgres is reachable | Free | 200, 503 |
| `POST /query` | Answers a question with citations | Paid | 200, 422, 502, 503, 500 |
| `GET /decisions/{canonical_id}` | A seed KEP's stored decision chain | Free | 200, 404, 503, 500 |
| `POST /ingestion-jobs` | Queues a rebuild of the corpus for the worker, or returns the job already queued or running | Free (the job's embed step pays only for new texts, capped) | 202, 200, 503, 500 |
| `GET /ingestion-jobs/{job_id}` | One ingestion job, with each step's progress | Free | 200, 404, 422, 503, 500 |

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

- **Purpose:** readiness. Can this process serve real traffic? It opens a new Postgres connection (waiting at most `DB_CONNECT_TIMEOUT_S`, 2 s, per address tried; see Dependencies) and runs `SELECT 1`. It checks only Postgres, not Voyage or Anthropic.
- **Request:** no parameters.
- **200:** `{"status": "ready"}`.
- **503:** `{"status": "unavailable"}`, on any database error (can't connect in time, refused, `SELECT 1` failed).
  - This body is a probe answer, not the error envelope: it has no `error` object and no `request_id`. The `X-Request-ID` header is still set.
- **Cost:** free (one short database connection).
- **Retry:** safe (writes nothing).

### POST /query

- **Purpose:** answer one question through the same pipeline as `orgknow ask` (`pipeline.answer_question`): route (temporal and authority modes), retrieve, find rule-found conflicts, answer, validate citations.
- **Request:** a JSON object with one field (the `Query` model in `api/app.py`). Other fields are ignored.
  - `question`: a string, at least 1 character, at least one of them not whitespace (a space, tab, line break or any other Unicode whitespace).
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
  - **422 `invalid_request`:** the body isn't JSON or isn't an object, `question` is missing or not a string, or it is empty or only whitespace. No connection is opened and no paid call is made.
  - **502 `upstream_failed`:** the ask failed upstream (`pipeline.ASK_ERRORS`): Voyage or Anthropic (answer or router) failed after its retries, or the model gave no usable answer or route (a refusal, a cut-off, output off the schema). Any `RuntimeError` or `ValueError` raised during the ask is reported the same way, because `ASK_ERRORS` lists those 2 base types.
  - **503 `database_unavailable`:** no connection within `DB_CONNECT_TIMEOUT_S`, the connection failed mid-request, or a statement ran past `DB_STATEMENT_TIMEOUT_MS` (psycopg's `OperationalError`, which includes a cancelled statement). No paid call is made when the connection can't be opened.
  - **500 `internal`:** anything else, including a database error that isn't a connection failure (e.g. a missing table).
- **Cost:** paid, per call: 1 Voyage embedding request and 1 Anthropic answer call, plus 1 Anthropic router call in temporal and authority modes (authority is the default). With nothing retrieved, the answer call is skipped. Each retry (see Dependencies) is another request.
- **Retry:** safe: it writes nothing to the database. Each retry pays again, and the model may word the answer differently. With tracing on, each call leaves its own trace.

### GET /decisions/{canonical_id}

- **Purpose:** read the stored decision chain of one seed KEP, as `orgknow chain` prints it (`load_chain`). Read-only: it never builds a chain (`make chains` does).
- **Request:** the path parameter `canonical_id`, a seed KEP's id, e.g. `kep:2572`. Any text without a `/` is looked up; a `/` inside the id matches no route (404), and a trailing `/` redirects (307) to the id without it.
- **200:** the `Chain` model (`provenance/chain.py`):
  - `seed`, `title`, `built_at` (ISO 8601, in the database session's time zone: UTC by the database's default, `Etc/UTC`, not enforced by the code).
  - `steps`: in step order (`problem`, `discussion`, `proposal`, `decision`, `implementation`, `current_docs`), each a `ChainStep`: `step`, `occurred_at`, `chunk_id`, `canonical_id`, `heading_path`, `source_type`, `source_url`, `tier`, `found_by`, `via_chunk_id`, `via_canonical_id`, `via_heading_path`, `missing_reason`. A missing step has only `step` and `missing_reason`; the rest are `null`.
- **Other statuses:**
  - **404 `not_found`:** no chain is stored for this id. The message doesn't repeat the id (see Errors).
  - **503 `database_unavailable`:** as `POST /query`, including a statement past `DB_STATEMENT_TIMEOUT_MS`.
  - **500 `internal`:** anything else (e.g. a missing table or manifest file).
- **Cost:** free.
- **Retry:** safe (writes nothing).

### POST /ingestion-jobs

- **Purpose:** queue a rebuild of the corpus: one job that the worker (`make worker`, see Worker) runs: ingest → lifecycle → embed → chains, at the corpus lock and manifest the worker is configured with (ADR-013 D2). The API only records the job: it never runs a step or takes the corpus-writer lock.
- **Request:** no parameters and no body. A body sent anyway is never read, so it is ignored, whatever it holds.
- **202:** a new job: the `IngestionJob` model (`db/models.py`):
  - `id`: the job's id, an integer, for `GET /ingestion-jobs/{job_id}`. Ids grow but can skip numbers: each refused insert uses one up (e.g. a POST answered 200).
  - `status`: `queued`, `running`, `succeeded` or `failed` (see Worker). A new job is `queued`.
  - `created_at`, `started_at`, `finished_at`: ISO 8601 times, or `null` until set, in the database session's time zone as `built_at` above (UTC by default, not enforced). `started_at` is the first attempt's start, kept when the job is resumed.
  - `attempts`: the runs and resumes started; 0 for a new job.
  - `error`: a failed job's one-line reason, else `null` (see Worker, "The job's error text").
  - `request_id`: the `X-Request-ID` of the POST that created the job.
  - `steps`: the 4 steps in order (`ingest`, `lifecycle`, `embed`, `chains`), each a `JobStep`: `name`; `status`, one of `pending`, `running`, `succeeded`, `failed`; `started_at`; `finished_at`; `counts`, an object of numbers and strings, `{}` until the step succeeds (see Worker, "Steps"); `error`.
- **200:** a job is already queued or running: that job, the same body as its `GET`. No job is created, and the job's `request_id` stays its creating POST's.
- **Other statuses:**
  - **503 `database_unavailable`:** as `POST /query`.
  - **500 `internal`:** anything else (e.g. a missing table). Also, practically never: the insert was refused because a job was active, that job ended before it could be read, and the same happened on the second try (at most 2 tries). POST again.
- **Cost:** free for the request (one short database connection). The job is free at the current corpus lock: its embed step sends only texts that have no vector yet (0 at the current lock), and `EMBED_MAX_TOKENS_PER_RUN` (2,000,000 estimated tokens) caps it: above the cap the step fails before any request.
- **Retry:** safe to repeat: while a job is queued or running, a POST returns it (200) and creates nothing, and 2 POSTs at the same instant make 1 job (the database allows one active job). Once the job has finished, a POST creates a new one: a whole rebuild again (a no-op ingest takes ~45 s).

### GET /ingestion-jobs/{job_id}

- **Purpose:** read one ingestion job and its steps' progress. The worker saves the job's row when each step starts and ends, so a running job shows the step it is on. Read-only.
- **Request:** the path parameter `job_id`, an integer, e.g. `/ingestion-jobs/1`. Pydantic's lax parsing also reads `1.0`, `+1` and `1_000` as integers.
- **200:** the `IngestionJob` model, as in `POST /ingestion-jobs`. The ingest step's `counts` include the stored corpus's `fingerprint`, as `make ingest-report` prints it.
- **Other statuses:**
  - **404 `not_found`:** no job has this id, including a negative id or one beyond Postgres's bigint range (e.g. 20 digits). The message doesn't repeat the id.
  - **422 `invalid_request`:** `job_id` isn't an integer (e.g. `abc`, `1.5`) or is too long to parse. No connection is opened.
  - **503 `database_unavailable`:** as `POST /query`.
  - **500 `internal`:** anything else (e.g. a missing table).
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
| `invalid_request` | 422 | The request fails validation (`POST /query`'s body, `GET /ingestion-jobs/{job_id}`'s id) | `body.question: Field required` |
| `not_found` | 404 | No stored chain for the id, no ingestion job with the id, or no route for the path | `no stored decision chain for this canonical_id; chains are built by make chains` |
| `upstream_failed` | 502 | Voyage or Anthropic failed after its retries, or the model gave no usable answer or route | `no usable answer from the model (stop reason: refusal)` |
| `database_unavailable` | 503 | Postgres can't be reached in time, the connection fails, or a statement runs past its timeout | `database unavailable` |
| `internal` | 500 | Anything unexpected, including a database error that isn't a connection failure | `internal error` |

**Message rules:**

- `message` never carries a traceback, a secret, a database URL or the caller's input. The traceback goes to the log, under the same request ID.
- `invalid_request`: `"<location joined by .>: <problem>"` of the first validation error only, e.g. `body.question: String should match pattern '\S'`. The value sent is never echoed.
- `not_found`: for a missing chain, the text in the table; for a missing job, `no ingestion job with this id` (neither repeats the id); for an unknown path, `Not Found`.
- `upstream_failed`: the failure's one line, the same text `orgknow ask` prints after `error: ` (`pipeline.one_line`). For an HTTP error it includes the provider's own reason (Voyage's: its first 500 characters).
- `database_unavailable` and `internal`: the fixed texts in the table.

## Request IDs

- **The rule:** a request's `X-Request-ID` header is used as given when it is 1 to 64 characters, each one of `A-Z a-z 0-9 . _ -` (the whole value matches `[A-Za-z0-9._-]{1,64}`).
- Otherwise (missing, empty, 65+ characters, or any other character such as a space, a newline or non-ASCII), the API makes a new random ID: 32 lowercase hex characters. A rejected value is never logged.
- **Where the ID appears:**
  - the response's `X-Request-ID` header, on every response: every status, every endpoint, unknown paths, and a 500;
  - the error body's `request_id`;
  - for a `POST /ingestion-jobs` that creates a job (202): the job's `request_id`, and the worker's log lines while it runs that job (see Worker);
  - every log line written while the request runs: its per-request line, warnings (e.g. a Voyage retry), and the error line of an unexpected failure.

## Logs

- **`make serve` and `make worker`** set this up: `make serve` through uvicorn's log config (`--log-config config/logging.json --no-access-log`), the worker from the same file (see Worker). Library code never configures logging. The CLI and the other make targets are unchanged: their stderr lines stay plain text.
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
- **Not JSON:** 2 lines the pipeline prints to stderr, shared with the CLI: `tracing off: …` once at startup when the Langfuse keys are unset, and the route line of each ask in temporal and authority modes. Also anything a library writes to stderr itself: the reranker's library (transformers) sets up its own plain-text log handler when it loads, and prints a progress bar while loading the model at startup. Langfuse's and Anthropic's warnings are JSON.

## Dependencies

Each external call has a timeout and a retry limit from the settings (environment variables, defaults shown). Nothing retries forever.

| Dependency | Called by | Timeout | Retries | Retried on | The API caller sees |
|---|---|---|---|---|---|
| Postgres | `/ready`, `/query`, `/decisions`, `/ingestion-jobs` | Connect: `DB_CONNECT_TIMEOUT_S=2` (s). Each statement: `DB_STATEMENT_TIMEOUT_MS=10000` (all but `/ready`) | 0 | — | 503 `database_unavailable` (`/ready`: 503 `{"status": "unavailable"}`). Another database error: 500 `internal` |
| Postgres, the worker's connection | `make worker`, not the API | Connect: `DB_CONNECT_TIMEOUT_S=2`. No statement timeout: a step's statements may run long | 0 | — | Never an API error. A connection that fails at start, or is lost later, stops the worker (see Worker) |
| Voyage (question embedding) | `/query` | `VOYAGE_TIMEOUT_S=60` | `VOYAGE_MAX_RETRIES=3`, after 1 s, 2 s, 4 s (doubling) | HTTP 429 and 5xx only. Not a timeout or a failed connection | 502 `upstream_failed` |
| Anthropic, answer | `/query` | `GENERATION_TIMEOUT_S=90` | `ANTHROPIC_MAX_RETRIES=2`, after ~0.5 s, then ~1 s | The SDK's rule: no connection, a timeout, HTTP 408, 409, 429, 5xx; an error response's `x-should-retry` header, when `true` or `false`, decides first, whatever the status | 502 `upstream_failed` |
| Anthropic, router | `/query` in temporal and authority modes | `ROUTER_TIMEOUT_S=30` | `ANTHROPIC_MAX_RETRIES=2`, as above | As above | 502 `upstream_failed` |
| GitHub | Not the API: only `make fetch-github`, a manual command | `GITHUB_TIMEOUT_S=30` | 0 | — | Never called by the API. The command stops with `Nothing written: <item>: <error>` and writes nothing |
| Langfuse | `/query` when both Langfuse keys are set | The SDK's 5 s per export (its own `LANGFUSE_TIMEOUT` variable, not a `Settings` field) | The SDK's exporter's own, within that 5 s | — | Never an error. The SDK exports traces in the background; a failed export loses the trace, never the answer |

Notes:

- `DB_CONNECT_TIMEOUT_S`: libpq treats values below 2 as 2 (psycopg follows its rule). It applies to each address tried: psycopg resolves the host name and tries each of its addresses in turn, each with the full timeout, so a host name with 2 addresses can wait up to 4 s.
- Anthropic: not retried are other 4xx errors (e.g. a wrong key: 401), unless the response's `x-should-retry` header is `true`, and a refusal or cut-off answer, which is a normal reply. The SDK waits ~0.5 s then ~1 s between tries (with jitter), or as long as a `retry-after` header says.
- Voyage: any other HTTP error fails at once. A Voyage retry writes one WARNING log line.
- The worker's embed step calls Voyage with the same timeout and retries. A Voyage failure there fails the step and the job (see Worker, "The job's error text"); the API never sees it.
- Startup checks only that `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are set. A wrong key shows up as a 502 on `/query`.
- At shutdown, the API waits for Langfuse's queued traces (`flush`).
- The reranker isn't a network call: it runs in-process on CPU (loaded once at startup), with no timeout.

## Worst case per POST /query

A known limit, not a promise: authority mode (the default), every step failing at its limit with the default settings.

| Step | Limit |
|---|---|
| Connect to Postgres | 2 s per address tried |
| Route (router call) | 3 tries × 30 s + at most 1.5 s of waits = 91.5 s |
| Embed the question (Voyage) | 4 tries × 60 s + 1 + 2 + 4 s of waits = 247 s |
| Answer (Anthropic) | 3 tries × 90 s + at most 1.5 s of waits = 271.5 s |
| **Network steps in total** | **612 s (~10 minutes)** |
| Each SQL statement | 10 s (an ask runs several; their sum has no cap) |
| Rerank | No limit (local CPU) |

Why it isn't a hard bound:

- A timeout bounds each wait on the network (connecting, or the gap between bytes received), not a whole try. A reply that trickles in can take longer.
- When Anthropic sends a `retry-after` header (e.g. with a 429), the SDK waits that long instead; SDK 1.11.0 sets no upper cap.
- The SQL statements and the reranker add to the 612 s, and so does each extra address of the database's host name (2 s each).

## Worker

`make worker` (`python -m orgknow.ingestion.worker`, ADR-013) runs the jobs `POST /ingestion-jobs` creates. The `ingestion_jobs` table is its queue: at most one job is queued or running at a time.

- **Start-up checks**, before connecting: `INGEST_SCOPE` must be `full`, and `VOYAGE_API_KEY` must be set. Otherwise it exits 1 with a one-line message.
- **Its connection:** one autocommit connection (connect timeout `DB_CONNECT_TIMEOUT_S`, no statement timeout). The lock and every step use it.

**The corpus-writer lock**

- One Postgres session advisory lock with one fixed key (`db/writer_lock.py`), taken by every corpus writer before it reads or writes: `make ingest`, `make lifecycle`, `make embed`, `make chains`, `make seed` and the worker.
- It is per database: writers on 2 different databases don't exclude each other.
- A CLI writer that can't get it exits 1 with `Another corpus writer is running (make ingest, lifecycle, embed, chains, seed or make worker); try again when it finishes.` Run through `make`, `make` then reports the failure with its own exit code, 2.
- Postgres frees the lock when its holder's connection ends, however the process dies.
- `make reset-corpus` runs raw `psql`, outside the lock: nothing stops it while a job runs.

**The loop**

- Each poll, the worker tries the lock, without waiting:
  - **got it, a job is queued or running:** it runs that job to its end, releases the lock, and polls again at once;
  - **got it, no job:** it releases the lock and sleeps `WORKER_POLL_S` (5 s);
  - **another writer holds it:** it sleeps `WORKER_POLL_S` and tries again, logging `Another corpus writer holds the lock; waiting for it` at most once per 60 s.
- So between jobs the worker holds nothing, and a hand-run writer can run; while a job runs, a hand-run writer exits 1.

**Steps**

Each step calls the function its `make` target calls (not the target's whole command). Its status, times and counts are saved in the job's row when it starts and when it ends.

| Step | Does | `counts` when it succeeds |
|---|---|---|
| `ingest` | `make ingest`'s store and chunk, without its lifecycle rebuild; then the stored corpus's fingerprint | `documents_stored`, `new_documents`, `new_versions`, `closed_versions`, `new_chunks`, `failures` (always 0: any failure fails the step), `fingerprint` (`sha256:…`, as `make ingest-report` prints it) |
| `lifecycle` | `make lifecycle`: rebuild the observed lifecycle | `rows` |
| `embed` | `make embed`: delete vectors no chunk uses, then embed every text with no vector. Above `EMBED_MAX_TOKENS_PER_RUN` (estimated) it fails first, deleting and sending nothing | `texts`, `requests`, `embedded`, `tokens` (Voyage's count: what was billed), `orphans_deleted` |
| `chains` | `make chains`: rebuild each manifest seed's decision chain | per seed, `<seed>_found` and `<seed>_missing`, e.g. `kep:2572_found` |

A resumed job's counts are those of the attempt that ran the step: e.g. `new_chunks` counts only the chunks the resumed ingest added.

**Statuses and attempts**

- **A job:** `queued` (created) → `running` (an attempt started) → `succeeded` (all 4 steps succeeded) or `failed`.
- **A step:** `pending` → `running` → `succeeded` or `failed`.
- **An error fails the job at once:** the step and the job become `failed`, with the same one-line `error` and a `finished_at`. Later steps stay `pending` and never run, so embed never runs after a failed ingest. Nothing retries it: POST again.
- **A crash is resumed:** a worker that dies mid-job (killed, stopped with Ctrl-C, or its connection lost) leaves the job `running`. The next worker to hold the lock resumes it at its first step that hasn't succeeded; a step left `running` starts again from its beginning (each step is safe to re-run).
- **Attempts:** `attempts` goes up by 1 each time a run or resume starts. A job found with `attempts` already at `WORKER_MAX_ATTEMPTS` (3) or more is marked `failed` without running, with the error `gave up after <attempts> attempts`; a step left `running` is marked `failed` with the same text.

**The job's error text**

- **Known errors** give their own one line:
  - the releases table doesn't match the manifest (`ReleasesMismatch`; its text starts "run `make seed` first.");
  - a GitHub snapshot is missing or isn't the one the lock pins (`GithubSnapshotError`; its text can name the cached file's path);
  - the embed cap (`RunTooLarge`: `<N> texts to embed come to <T> estimated tokens, above EMBED_MAX_TOKENS_PER_RUN (<cap>). …`);
  - ingest failures (`<N> ingest failures; the first: <failure>`).
- **Any other error:** `internal error; see the worker log (job <id>)`. The traceback is in the worker's log, on an ERROR line with `exc_info`. The job is readable over the API, so an unknown error's text stays out of it.

**A lost database connection**

- **At start:** a connection that fails stops the worker (Python's traceback on stderr, exit code 1).
- **Mid-job:** saving the job fails, and the worker process exits (an uncaught `psycopg.OperationalError`: Python's traceback on stderr, exit code 1). The job stays `running`; the next worker start resumes it, using 1 attempt.
- **While idle:** the next poll fails the same way, and the worker exits.
- Nothing restarts it: in deployment the worker needs a supervisor that restarts it (S15).
- **Ctrl-C:** the worker logs `Worker stopped (Ctrl-C)` and exits 0, holding nothing. A job it was running stays `running`, resumed at the next start.

**The worker's logs**

- It sets up logging from `config/logging.json`, the same JSON formatter as `make serve` (see Logs): one JSON object per line on stderr, with `ts`, `level`, `logger` and `message`.
- While a job runs, every line carries the job's `request_id`: the `X-Request-ID` of the POST that created it. So one ID follows a job from its POST to its last step.
- The worker's own lines (logger `orgknow.ingestion.worker`) about a job also carry `job_id`; a step's success line also carries its `counts`. Lines from the steps' own code carry `request_id` but no `job_id`.
- Its lines: `Worker started: polling every 5 s`; `Job <id>: attempt <n> started`; `Job <id>: step <name> started`; `Job <id>: step <name> succeeded`; `Job <id> succeeded`; at ERROR, `Job <id>: step <name> failed: <text>` for a known error, `Job <id>: step <name> failed` with `exc_info` for any other, and `Job <id>: gave up after <n> attempts`; the busy line above; `Worker stopped (Ctrl-C)`.
