# ADR-013: Async ingestion (job model, queue, idempotency)

- **Status:** Accepted (S14-R2 sitting, 2026-10-14)
- **Date:** 2026-10-14
- **Blueprint/spec refs:** §8.2, §22, §29 stage 10; ADR-002 (R3), ADR-005 (data access and its 2026-10-13 amendment)
- **Evidence:** the S14 slice doc's run contract (S14-R2, "Sitting evidence")

## Context

- Ingestion takes minutes and shouldn't hold an HTTP request open (blueprint §22). Today it is 4 hand-run commands: `make ingest`, `make lifecycle` (also run inside ingest), `make embed`, `make chains`.
- Each command is already safe to re-run (a re-run adds 0 versions, 0 chunks, 0 requests), and commits in small transactions (per document, per version's chunks, per embed batch, per chain).
- Sitting measurements on a scratch database:
  - a fresh full ingest takes 74 s, a no-op re-run 45 s; embed (0 texts at the current lock) and chains under 0.5 s each;
  - `make ingest` killed with SIGKILL at 40 s and at 60 s, then re-run: the same fingerprint as a clean run both times;
  - a Postgres session advisory lock is freed 0.000 s after its holder is SIGKILLed.
- There is 1 worker, 1 kind of job, and 1 Postgres instance that the API and the worker both use (S15: one EC2 instance and RDS).
- 6 modules write the corpus: ingest, lifecycle, embed, chains, seed, and the worker. R3 (an identifier resolves to exactly one document) is a check-then-insert across 2 tables, so 2 concurrent writers can break it (Proposed additions, "Make R3 race-free"). The sitting's first kill probe ran 2 ingests at once by accident.
- Embed is the only paid step. It first deletes vectors no chunk uses ("orphans"). The full corpus is 5.69 M estimated tokens, above the 2 M per-run cap (`EMBED_MAX_TOKENS_PER_RUN`).
- `POST` has no auth until S15's security review.

## Decision

### D1. The jobs table is the queue; no SQS

- The worker takes the writer lock (D3), then picks the oldest job that is `queued` or `running`. A `running` job found while the worker holds the lock is one whose worker died: it is resumed (D5).
- No separate message table, no queue interface, no visibility timeout.
- This replaces blueprint §22's SQS and the backlog's "local queue shaped like SQS". S15's Terraform has no SQS.
- **Revisit trigger:** a second worker host, or the API and the worker no longer sharing a database. Then SQS carries the job ID as a wake-up nudge, and the table stays the source of truth (a duplicate nudge is harmless, since the worker re-reads the table).

### D2. A job is a fixed recipe with no request input

- Steps, in order: ingest → lifecycle → embed → chains, at the corpus lock and manifest the worker is configured with. The request body is empty.
- Guards against embed's orphan deletion:
  - the worker refuses to start unless `INGEST_SCOPE` is `full`;
  - embed runs only after ingest succeeded in the same job.
- Embed keeps its per-run token cap. At the current lock a job sends 0 texts.

### D3. One corpus-writer lock

- One Postgres session advisory lock (one fixed key), taken at start by every corpus writer (ingest, lifecycle, embed, chains, seed, the worker), and held to the end.
- The lock lives on the writer's **only** connection, so a dropped connection stops the writes too.
- A CLI writer that can't get it exits 1 ("another corpus writer is running"). The worker tries again on its next poll, and releases the lock between jobs, so a hand-run command can run while the worker is idle.
- This closes the R3 race and double-paid embeds while every writer goes through this codebase. A direct `psql` edit (e.g. `make reset-corpus`) is outside it.

### D4. At most one active job; a repeated POST returns it

- The database allows at most one job that is `queued` or `running` (a unique rule on active jobs), so 2 POSTs at the same instant make 1 job.
- `POST /ingestion-jobs` answers 202 with a new job, or 200 with the active one (the same body as `GET /ingestion-jobs/{id}`). No new error code.

### D5. An error fails the job; a crash is resumed

- An error in a step marks the step and the job `failed` with a one-line reason; later steps stay `pending`; nothing retries it. Per-document ingest failures fail the ingest step.
- A crash (the worker dies) leaves the job `running`. The next worker to hold the lock resumes it at the first step that hasn't succeeded.
- Attempts are counted when a run or resume starts. A job found already at `WORKER_MAX_ATTEMPTS` (3) is marked `failed` without running.
- Voyage keeps its own bounded retries (S14-R1).

### D6. One table; the steps are a list in the job row

- `ingestion_jobs`: id, status (`queued`, `running`, `succeeded`, `failed`), created, started and finished times, attempts, a one-line error, the creating request's ID, and `steps`: a JSON list of the 4 steps, each with its status, start and finish times, counts and error.
- Every read is one job by its ID; no query crosses jobs' steps.

## Alternatives considered

| Option | Why not |
|---|---|
| An SQS-shaped message table behind a queue interface | A second source of truth that can disagree with the job; a dead worker noticed only after the visibility timeout; an interface with 1 implementation; real SQS can't insert the job and send the message in one transaction anyway |
| ElasticMQ + boto3 (real SQS API locally) | A new service and dependency, and AWS work before S15 |
| No embed in the job (manual `make embed`) | Two halves to remember on every lock refresh; the guards cover the deletion risk |
| The caller picks steps or scope | More input to validate; a narrow scope plus embed is what wipes the vector cache |
| Locks inside the 2 identifier functions only | 2 mechanisms; doesn't cover whole runs or dead-worker detection |
| One identifiers table with a single UNIQUE | Changes ADR-002/005's tables and every query on them; only needed for writers outside this codebase |
| 409 on a repeated POST; always create; queue one more while running | An error for a normal case; floods of 45 s no-ops; the input can't change mid-run |
| Retry every error 3 times; split permanent and temporary errors | Ingest's errors are deterministic (pinned commits, cached files); no passing error has been seen |
| A separate steps table | A join and 4 rows per job for a cross-job query no one runs |

## Consequences

- `make worker` runs jobs; `GET /ingestion-jobs/{id}` shows each step's progress, with the fingerprint in the ingest step's counts.
- Crash recovery is immediate (the lock), not after a timeout. Idempotency rests on each step being safe to re-run, which the kill probes measured.
- Every corpus writer must take the lock; a test lists them. A new writer added later must too.
- A passing glitch (e.g. Postgres restarting) fails the job; the operator POSTs again.
- S15 deploys the worker beside the API on one host, with no SQS.
- **Revisit triggers:** D1's (a second worker host or no shared database); D5's (a logged error that a later attempt fixed); D6's (a planned report across jobs' steps).
