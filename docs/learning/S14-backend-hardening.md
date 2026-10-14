# Slice brief: S14 Backend hardening + async ingestion

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → **Ingest** → **Store** → Chunk → **Embed** → Retrieve → **Answer**, plus `Supporting: deployment`.
- The API (Answer) gains one error shape, request IDs, JSON logs and a timeout on every external call.
- Ingest, Store and Embed don't change what they store: a worker now runs them as one job, and one lock keeps any 2 writers apart.

## What was built

- **Interface contracts (`docs/interfaces.md`):** every endpoint's input, output and errors; one error envelope with 5 codes; each dependency's timeout, retries and what the caller sees when it fails. A test keeps the routes and the doc in step.
- **Request IDs and JSON logs:** every response carries `X-Request-ID` (a short label for one request), and every log line of that request carries the same ID, so one failing request can be followed through the logs.
- **Limits on every external call:** Anthropic, Voyage, GitHub and database timeouts and retry counts come from settings; API connections commit each statement on their own (autocommit), so no transaction stays open while the model answers.
- **Async ingestion (ADR-013):** `POST /ingestion-jobs` records a job; `make worker` runs it (ingest → lifecycle → embed → chains) with each step's progress in the job's row; `GET /ingestion-jobs/{id}` shows it.
- **Safe to repeat and to crash:** one corpus-writer lock lets only 1 writer run at a time; a killed worker's job resumes at its first unfinished step; a repeated or resumed job leaves the same fingerprint (one hash of every stored value).

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| One error envelope, 5 fixed codes (R1 decision 1) | FastAPI's `{"detail"}`; RFC 9457 problem details | A fixed code list S17's UI can switch on | 2 exceptions remain: `/ready`'s 503 and a 405 |
| No connection pool; autocommit API connections (R1 decision 2) | `psycopg_pool` (a new dependency) | Connecting is 10.8 ms at p50 against an 8.7 s ask; autocommit fixed the idle transaction | The connection count is unmeasured until RDS (S15) |
| Timeouts from settings: answer 90 s, router 30 s, Voyage 60 s (R1 call c) | The Anthropic SDK's 10-minute default | The slowest saved ask took 29.7 s | Worst case per `/query`: 612 s of network waits |
| The jobs table is the queue; no SQS (ADR-013 D1) | An SQS-shaped message table; ElasticMQ + boto3 | 1 worker, 1 database; a dead worker's lock frees in 0.000 s | Revisit with a second worker host |
| A fixed 4-step job with no input (D2) | The caller picks steps or scope | A narrow scope plus embed's orphan deletion would wipe the vector cache | Every job re-runs ingest (a 45 s no-op) |
| One corpus-writer lock for all 6 writers (D3) | Locks in the 2 identifier functions; one identifiers table | One mechanism for the R3 race, double-paid embeds and dead-worker detection | `make reset-corpus` (raw `psql`) is outside it |
| At most 1 active job; a repeated POST returns it (D4) | 409 on a repeat; always create a job | Safe to click twice; the database enforces it, so 2 POSTs at once make 1 job | Job ids have gaps |
| Errors fail the job; crashes resume, at most 3 attempts (D5) | Retry every error 3 times | Ingest's errors are deterministic; kill probes at 40 s and 60 s gave the same fingerprint | The operator POSTs again after a failure |
| The 4 steps as a JSON list in the job's row (D6) | A separate steps table | Every read is one job by its id | No cross-job query on steps |

## Likely interview questions

1. **Q: Why is your queue a Postgres table instead of SQS?**
   - 1 worker, 1 job type, 1 database the API and the worker share: the job row is the one source of truth.
   - A crashed worker is noticed at once (its lock frees when its connection dies), not after a visibility timeout; revisit with a second worker host.
2. **Q: How do you know a crash mid-job leaves the same data?**
   - Every step is safe to re-run: in the sitting, `make ingest` killed at 40 s and at 60 s, then re-run, gave the same fingerprint.
   - Demo: the worker was killed 43.5 s into ingest; the restarted worker resumed the job at attempt 2 and ended with the same fingerprint and counts as a clean run.
3. **Q: How do you stop two writers from racing?**
   - A Postgres session advisory lock with one key, taken by all 6 writers on their only connection; a test holds it and each CLI writer exits 1.
   - Follow-up, "why a session lock, not a transaction lock?": writers commit in many small transactions, and a session lock spans them all.
4. **Q: How would you trace one failing request?**
   - Its `X-Request-ID` is in the response, the error body and every JSON log line; the worker's lines carry the ID of the POST that created the job.
   - A caller's ID is kept only if it is 1–64 safe characters, so a newline can't forge a log line.
5. **Q: Why no connection pool?**
   - Measured first: a connection takes 10.8 ms at p50, about 0.1% of an 8.7 s ask.
   - The real problem was a transaction left open for ~2 s during the answer call; autocommit fixed it. A pool is revisited on RDS, where the connection count matters.

## Numbers to remember

- **Ingest:** a fresh full ingest takes 74 s and a no-op 45 s (`make ingest`, the sitting); the worker's no-op ingest took ~19 s in T5's run.
- **The kill demo:** killed 43.5 s into ingest; resumed at attempt 2; fingerprint `sha256:0f0ee078…4165` both times.
- **After 2 jobs:** 21,762 embeddings, 3,295 lifecycle rows, 2 decisions, 12 chain-step rows; the repeated job: 0 new chunks, 0 embed requests.
- **Lock release after SIGKILL:** 0.000 s.
- **Embed cap:** the full corpus is 5.69 M estimated tokens, above the 2 M per-run cap, so a lost vector cache refuses rather than pays.
- **Latency:** ask p50 8.7 s, p95 14.9 s, max 29.7 s; database connect p50 10.8 ms.
- **Tests:** 1,130 unit (1,061 at S13's close), 251 integration (214).
- **Paid:** US$0 in S14.
