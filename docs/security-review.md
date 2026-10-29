# Risk, security and cost review

Blueprint gap #6 for the S15 deployment: each risk, how bad it is, what limits it, and where that control lives. Written in S15-T1 from the S15-R1 design review's decisions (ADR-014 and the run plan).

- **Scope:** the AWS deployment as ADR-014 describes it: 1 server, 1 database, **no inbound ports** (D1). S17 opens it to the public; its controls are designed here (section 7), marked Proposed.
- **Result:** 37 risks in the 6 topics: 1 high, 5 medium, 31 low. The high one is the root-only AWS account, closed by the runbook's first step.
- **Abuse and exposure are not "n/a":** both are low today only because nothing can reach the API; in S17 they become high until section 7's controls exist.
- **Carried items:** 6 from S14 and PR #51, all low; none is must-fix with no inbound ports, so no code changes. All 6 go to S17's design review (section 8).
- **Cost:** US$47.49 a month in the design review's table, at most US$47.69 with the 2 alarms it left out: under the US$50 cap.
- **1 gap closed in the run:** teardown would stop on a repository that still holds images (6.6); the run added `force_delete` to it (plan c5).

## How to read the tables

- **Rating:** for S15 as built, counting the controls in ADR-014, Terraform, the image, the runbook and today's code. Proposed controls don't count yet.
  - **High:** costly (money, a secret, the whole account) and nothing in S15 stops it yet.
  - **Medium:** possible, with limited damage; or the control only alerts.
  - **Low:** needs the author's AWS login first, or the damage is small (a log line, public data, cents).
- **Where it lives:**
  - `D1`–`D7`: ADR-014's decisions.
  - `TF`: a Terraform resource S15-T4 writes (the plan's "Pinned: T4"), named by its type.
  - `Image`: the container image, S15-T3 (the plan's "Pinned: T3").
  - `Runbook N`: step N of `docs/deployment.md`, S15-T5 (the plan's "Pinned: T5").
  - `In place`: code or a process that exists today.
  - `Accepted`: no further control; the rating says why.
  - `Proposed (S16)` / `Proposed (S17)`: a Proposed addition in the backlog, for that slice's design review.
- **Sources** are in brackets. `m7`, `c3`: the plan's calls. `design review`: the plan's "Design-review evidence". Code paths are under `src/orgknow/`. Commands are in section 10.

**Terms used below:**

- **Security group:** the AWS firewall around the server or the database: which traffic may come in and go out.
- **Session Manager:** an AWS service that opens a shell or a port tunnel to the server through the AWS login, with no open port.
- **SSM Parameter Store:** AWS's store for settings; a `SecureString` value is stored encrypted.
- **Prompt injection:** text in the model's input that tries to give the model instructions.
- **IMDS:** the instance metadata service, where code on the server gets the server role's AWS credentials.
- **Supply-chain attack:** an attack through a dependency (a package, an image) rather than through your own code.

## 1. Model-API abuse and cost

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 1.1 | Anyone who reaches `POST /query` spends money: ~US$0.03 per ask [ADR-014 Context; `docs/evaluation.md`: US$0.028–0.038 per question across runs] | Low: reaching it needs the author's AWS login [D1]. **S17: high** until section 7 exists | No inbound rule; the API listens on the server's `127.0.0.1:8000` only [D1, m4]. S17: an API key, a per-key spending cap, rate limits | D1; TF server security group (0 ingress, tested); Proposed (S17) |
| 1.2 | One ask costs more than usual: the answer's output is capped at 16,000 tokens (≤ US$0.32 per try at US$20/M), the router's at 4,096 (≤ US$0.08) [`settings.py:132`, `:137`, `:146`, `:149`]; the question has no length cap [`api/app.py:43`] | Low: 1 user [D1]; ≤ US$0.40 of output per try | Output caps in place. S17: a question length cap | In place; Proposed (S17) |
| 1.3 | `POST /ingestion-jobs` starts a rebuild: Voyage spend, and 2 CPUs shared with asks | Low: embed refuses above 2,000,000 estimated tokens, before sending [`settings.py:72`]; 1 active job at most [ADR-013 D4]; a no-op job sends 0 requests [PR #51's demo] | Caps in place. S17: the admin key only, 1 per hour | In place; Proposed (S17) |
| 1.4 | Spend outside AWS: Anthropic and Voyage bill apart from the AWS budget [D7 covers AWS only] | Medium: a leaked key or a loop spends until someone notices | Anthropic: the prepaid balance is the ceiling (2.6). Voyage: no ceiling known (not verified) | In place (a project rule) |

## 2. Secret handling

The secrets: 4 API keys (Anthropic, Voyage, Langfuse's 2) and the database password inside `DATABASE_URL` [names table].

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 2.1 | A secret ends up in the image or in git | Low: tested | `.dockerignore` is an allowlist and never sends `.env`; `make image-check` fails if `/app/.env` exists [Pinned T3; break-it rule 1]. Terraform code holds only the placeholder `set-me` [c4] | Image (T3); TF `aws_ssm_parameter` (c4) |
| 2.2 | Secrets at rest in AWS | Low: stored encrypted; reading them needs the server's role or the author's AWS login [m7, D6] | Encrypted `SecureString` parameters under `/orgknow/<ENV_VAR>`; the author sets the API keys with the CLI [m7, D6] | TF `aws_ssm_parameter` ×5; Runbook 3 |
| 2.3 | Secrets on the server: the env file `/etc/orgknow/env` and the containers' environment [names table] | Low: a shell needs the author's AWS login [D1] | Root-only file (mode 0600), written by the deploy script [Pinned T4]; no SSH keys [D1] | TF boot script (the deploy script) |
| 2.4 | Terraform's state file holds the database password in plain text [D6; S15 "Risks"], and likely the 4 API keys after any refresh that follows runbook step 3: the provider stores a `SecureString`'s value in state [AWS provider docs, `ssm_parameter`], and c4's `ignore_changes` stops updates, not reads (inferred; section 9) | Low: the same keys already sit in the laptop's `.env`; the password is useless outside the VPC [D3] | Local and gitignored before any `apply` [m8; Pinned T4 `.gitignore`]. S17: write-only values (`value_wo`, Terraform ≥ 1.11 [provider docs]) keep them out of state | D6; `.gitignore` (T4); Proposed (S17) |
| 2.5 | A secret leaks into a log line or an error message | Low: keys print masked, and no error message carries a key or the database URL | API keys are `SecretStr`, printed as `**********` [`settings.py:57`, `:151`, `:158-159`]; settings errors hide their input [`settings.py:16`]; database errors never show the URL [`api/app.py:150-153`]; Voyage's error never holds its key [`embeddings/voyage.py:95-96`] | In place |
| 2.6 | A stolen Anthropic key | Medium: it can spend the whole balance | The prepaid balance is a hard ceiling: at 0, calls fail with "credit balance is too low" [Anthropic's prepaid billing], while auto-reload stays off (not verified) | In place (a project rule) |
| 2.7 | The AWS account has only the root login [design review]: root can do anything, billing included | **High until runbook step 1:** 1 stolen password = the whole account | MFA on root; an IAM Identity Center admin user; the CLI through `aws sso login` (short-lived credentials, no stored keys) [Pinned T5, step 1] | Runbook 1 |
| 2.8 | The server role's credentials are taken through IMDS (e.g. by a forged request) | Low: the role holds what the containers already have | IMDSv2 required [m12]; the role pulls 1 repository, reads 1 bucket, writes 1 log group, and reads `/orgknow/*` by path; the managed Session Manager policy can also read any parameter by name, and this account has no others [D6] | TF `aws_instance` (`metadata_options`); TF IAM inline policy |
| 2.9 | `sslmode=require` encrypts the database link but doesn't check the server's certificate [m11; libpq docs, "SSL Mode Descriptions"] | Low: the link never leaves the VPC [D3] | Private subnets; the database admits only the server [D3] | D3 |

## 3. Prompt and data injection

- **Where untrusted text enters:**
  - the question, written by whoever calls `POST /query` [`api/app.py:43`];
  - GitHub comments (tier 7, `discussion` texts): anyone with a GitHub account writes them, and they reach the answer prompt as evidence like any other text [`generation/prompt.py:97`, `:118-130`].
- **Size:** 5 GitHub threads, 210 of 48,483 stored texts (dev database; section 10).

**What limits the damage** (each checked in the code):

| Limiter | What it stops | Code |
|---|---|---|
| Structured output | The reply must be the answer schema's JSON; anything else is an error, never shown | `generation/generator.py:62-80`; `generation/schema.py:19-30` |
| No tools | Neither model call passes `tools`: the model can't fetch, write or run anything; its only output is the JSON | `generator.py:62-72`; `retrieval/router.py:89-97`; 0 `tools=` in `src/` |
| Citation validation | An id outside this question's retrieved texts rejects the whole answer, which becomes `insufficient_evidence` | `generation/validate.py:24-40`; `generator.py:147-148` |
| Provenance from the database | The model returns ids only; each citation's link, title and tier come from the stored text, so injected text can't forge a link or a tier | `schema.py:3-4`, `:22`; `validate.py:43-71` |
| Conflicts checked by code | A model-listed pair naming a text not retrieved is dropped; the kind, resolution and winner come from code | `generation/conflicts.py:200-241` |
| The router sees only the question | Evidence never reaches the router, so it can't change the mode or the release window | `router.py:93` |
| Pinned snapshots | A thread's file must match the sha256 in the lock: a new comment enters only when the author re-fetches and re-pins | `ingestion/github.py:181-186` |
| No secrets in the prompt | The prompt holds the system text, public corpus texts and the question only | `prompt.py:18-35`, `:118-130` |

**What doesn't limit it**, and the risks left:

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 3.1 | An injected comment steers the answer's wording: `answer` and a kept conflict's `summary` are free text [`schema.py:21`; `conflicts.py:236`]. It can state a false claim citing the injected text itself, which passes: validation checks ids, not support [`validate.py:24-40`] | Medium: 210 texts, pinned, but any answer can use them, and the reader sees a real citation | The limiters above; each citation shows its tier, so a tier-7 source is visible [`validate.py:66`]. S17: the prompt says evidence is data, not instructions; today it explains tiers 1–6, not 7 [`prompt.py:21-23`; backlog, "GitHub texts in CURRENT questions"]. A prompt change: measure it on golden set v1 | In place; Proposed (S17) |
| 3.2 | The question carries instructions (direct injection) | Low: only the asker sees the result; no tools, no secrets, no other user's data in the prompt | The limiters above | In place |
| 3.3 | S17's UI shows model text as HTML (a script or a link in `answer`) | Low: S15 returns JSON through a tunnel [D1]. S17: medium | S17: the UI shows `answer` and conflict summaries as plain text | Proposed (S17) |
| 3.4 | SQL injection | Low: no SQL text is built from input; values go as parameters | All SQL is in `db/` [a project convention] with values passed as parameters, e.g. `db/retrieval.py:64-66`; 0 SQL strings built with f-strings in `db/` | In place |
| 3.5 | Log injection: a request ID with a line break forges a log line | Low: a caller's ID is dropped unless it has only safe characters | An ID is kept only if it matches `[A-Za-z0-9._-]{1,64}` [`api/middleware.py:26`]; logs are 1 JSON object per line [`docs/interfaces.md`, "Logs"] | In place |

## 4. Public endpoint exposure

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 4.1 | The API has no authentication [ADR-014 Context] | Low: 0 inbound rules; reached only through a Session Manager tunnel with the AWS login [D1]. **S17: high** | The S17 design (section 7) | D1; TF server security group (tested); Runbook 7; Proposed (S17) |
| 4.2 | The database is reachable from the internet | Low: 3 locks, each tested | No public address; private subnets with no internet route; port 5432 from the server's group only [D3] | TF `aws_db_instance` (`publicly_accessible = false`); private route table; database security group |
| 4.3 | Someone opens a shell on the server | Low: no port and no key to attack; a shell needs the AWS login [D1] | No SSH keys, no port 22; Session Manager needs the AWS login, with MFA after runbook step 1 [D1] | D1; TF role (`AmazonSSMManagedInstanceCore`); Runbook 1 |
| 4.4 | The server's public IPv4 is scanned | Low: nothing answers | The address is for outbound calls only [D3]; 0 inbound rules [D1] | TF server security group |
| 4.5 | The bucket (database dump, corpus) is made public | Low: all 4 blocks on, tested; its contents come from the public corpus | All 4 public-access blocks on; encrypted [m13] | TF `aws_s3_bucket_public_access_block` (tested) |
| 4.6 | **c2:** the app connects as the RDS master user, so a bug or an injection could drop tables or create roles [c2; ADR-014 Consequences] | Low: SQL is parameterized (3.4); only the server reaches the database [D3]; the data reloads from the dump [D5]. S17: medium | S17: a least-privilege role for the app; the master user only for migrations and restore | D3; Proposed (S17) |
| 4.7 | **c3:** the server's group allows all outbound traffic, so a compromised container could send its secrets anywhere [c3] | Low: reaching a container needs the AWS login first [D1] | S17: allow only TCP 443 out, plus 5432 to the database's group (c3's destinations are HTTPS or the database: not verified for the Amazon Linux repos). Filtering by domain needs a proxy: more moving parts | Proposed (S17) |

## 5. Dependency risk

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 5.1 | A Python package is changed or swapped (supply-chain attack) | Low: every download has its sha256 pinned in the lock | `uv.lock` pins 90 of 91 packages with sha256 hashes; the 91st is this project [section 10]. The image installs exactly the lock (`uv sync --frozen --no-dev`) [Pinned T3]; torch comes only from the PyTorch CPU index [`pyproject.toml:62-70`] | In place; Image (T3) |
| 5.2 | A base image changes under its tag | Low: a digest names exact bytes, so a changed image can't match it | `python:3.12-slim` and `ghcr.io/astral-sh/uv` pinned by digest [Pinned T3] | Image (T3) |
| 5.3 | The reranker's model changes, or runs code when loaded | Low: a fixed revision, no network at runtime, no pickle | A fixed revision [`settings.py:106-107`]; downloaded at build, offline at runtime [m3]; weights read from safetensors only, not pickle [`retrieval/cross_encoder.py:29-30`] | Image (T3); In place |
| 5.4 | A Terraform provider changes | Low: versions pinned, with their hashes in the committed lock file | `hashicorp/aws` and `hashicorp/random` pinned to minor versions; the lock file with their hashes committed [m8; Pinned T4] | TF `versions.tf`; `.terraform.lock.hcl` |
| 5.5 | Known vulnerabilities in the image's packages: pins freeze old versions | Low: nothing reaches the server [D1]. S17: medium | ECR scans each pushed image [m13], but it only reports, and no step reads it. S16: fail the pipeline on critical findings; refresh the lock and digests monthly | TF `aws_ecr_repository` (scan on push); Proposed (S16) |
| 5.6 | Unpinned parts: the Amazon Linux image ("latest", from AWS's public parameter) [m12]; Docker from `dnf` [Pinned T4]; the restore image `pgvector/pgvector:0.8.1-pg18`, by tag [Pinned T5, step 5] | Low: official sources; the restore runs once, by hand | The restore image's tag matches the laptop's [`compose.yaml:6`] | Accepted |

## 6. AWS cost guardrails

Prices: `us-east-1` [m1], on demand, 730 hours a month. Each was checked in the design review (2026-10-14/15) [design review]; not re-checked here.

| Item | Price | Per month (US$) | Source |
|---|---|---|---|
| EC2 t3a.medium (2 vCPU, 4 GiB) | US$0.0376/h | 27.45 | https://instances.vantage.sh/aws/ec2/t3a.medium |
| EBS gp3, 20 GB | US$0.08/GB-month | 1.60 | https://aws.amazon.com/ebs/pricing/ (the design review used secondary sources) |
| Public IPv4, 1 | US$0.005/h | 3.65 | https://aws.amazon.com/vpc/pricing/ (the public IPv4 charge, since 2024-02-01) |
| RDS db.t4g.micro, single-AZ | US$0.016/h | 11.68 | https://instances.vantage.sh/aws/rds/db.t4g.micro |
| RDS gp3, 20 GB | US$0.115/GB-month | 2.30 | https://aws.amazon.com/rds/postgresql/pricing/ (the design review used secondary sources) |
| ECR, ~3 GB | US$0.10/GB-month | 0.30 | https://aws.amazon.com/ecr/pricing/; size estimated (3 images kept [m13]) |
| CloudWatch Logs, ~1 GB | US$0.50/GB ingested | ~0.50 | https://aws.amazon.com/cloudwatch/pricing/; volume estimated |
| S3, ~0.6 GB | US$0.023/GB-month | 0.01 | https://aws.amazon.com/s3/pricing/; the 119 MB dump and the corpus archive (396 MB before compression) [design review] |
| SSM standard parameters, Budgets (first 2), SNS email, VPC, IAM | — | 0 | The design review; https://aws.amazon.com/systems-manager/pricing/, https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/, https://aws.amazon.com/sns/pricing/ |
| **Total (the design review's table)** | | **47.49** | The plan |
| Left out of the design review's table: 2 CloudWatch alarms [D7] | US$0.10 per alarm metric-month | ≤ 0.20 | https://aws.amazon.com/cloudwatch/pricing/ (not checked in the design review) |
| **Total with the alarms** | | **≤ 47.69** | US$2.31 under the US$50 cap [blueprint §27] |

- **For comparison** [design review]: t3.medium (US$0.0416/h) → ~US$50.40, over the cap; t4g.medium (US$0.0336/h) → ~US$44.56.
- **Not AWS:** Anthropic, ~US$0.03 per ask (1.1), bounded by the prepaid balance (2.6); Voyage, a few tokens per ask.

| # | Risk | Rating | Mitigation | Where it lives |
|---|---|---|---|---|
| 6.1 | A forgotten environment bills every hour: ~US$1.56 a day (47.49 / 30.4) | Medium: US$2.51 under the cap [ADR-014 Consequences] | A US$50 budget emails at 80% actual and 100% forecast [m10]; teardown is 1 command [D7], with checks after [Pinned T5, step 9] | TF `aws_budgets_budget` (tested); Runbook 9 |
| 6.2 | A budget alert doesn't stop anything | Medium: it only emails | Confirm the alerts' email subscription at create [Pinned T5, step 2]; the variable costs are small by design (6.3–6.5) | Runbook 2 |
| 6.3 | CPU credits bill extra: T3a launches in unlimited mode by default [AWS EC2 docs, "Unlimited mode concepts"] | Low: tested | Standard mode: out of credits, the server slows down and never bills extra [D2] | TF `aws_instance` (`credit_specification`, tested) |
| 6.4 | Storage grows: images, logs, the database | Low: each store has a limit or an alarm (3 images, 14 days, 2 GB free) | ECR keeps the last 3 images [m13]; logs kept 14 days [m9]; RDS has 20 GB, with an alarm under 2 GB free [m11, D7] | TF `aws_ecr_lifecycle_policy`, `aws_cloudwatch_log_group`, `aws_cloudwatch_metric_alarm` |
| 6.5 | A costly service or a bigger server is added by mistake | Low: none of them is in the Terraform code; the default type is tested [D7, D2] | Not used: NAT gateway, load balancer, ECS/Fargate, Secrets Manager, SQS, Route 53/CloudFront [D7]; `instance_type` defaults to t3a.medium (tested) [D2] | D7; TF variables |
| 6.6 | Teardown leaves a billable resource. RDS (no final snapshot, no deletion protection) [m11] and the bucket (`force_destroy`) [m13] are covered. The ECR repository needs `force_delete`: by default the provider refuses to delete a repository that holds images [AWS provider docs, `ecr_repository`] | Low: without it, `destroy` stops with an error and ~US$0.30 a month keeps billing | `force_delete = true` on the repository [c5]; Runbook 9's checks after `destroy` | TF `aws_ecr_repository`; Runbook 9 |

## 7. S17's exposure controls (Proposed)

Decision 1 of the S15-R1 design review: S15 has no inbound ports, and S17 builds these before anything is public [D1; blueprint §26.2: "basic rate/cost protections for AI endpoints if exposed publicly"]. Values are starting points; S17's design review decides.

| Control | Design | Why |
|---|---|---|
| HTTPS | Either only the UI is public, and its server calls the API on the server itself; or a TLS proxy (e.g. Caddy with Let's Encrypt) opens TCP 443 in front of `127.0.0.1:8000` [ADR-014 Alternatives] | A key sent over plain HTTP can be read on the way [ADR-014 Alternatives] |
| An API key | Every route but `/health` and `/ready` needs an `X-API-Key` header; 2 keys, `ui` and `admin`, stored in SSM under `/orgknow/` [D6] | Blocks anonymous paid calls (1.1) |
| A per-key spending cap | Each ask's cost = its reported token usage × the price settings [`settings.py:136-149`], added to the key's daily total; over US$2 a day → 429 | ~65 asks a day at US$0.031; at most ~US$60 a month per key. The `ui` key is shared by every visitor, so its cap is the site's |
| Rate limit: `POST /query` | 6 per minute per key, 1 at a time | Concurrent asks share 1 reranker [`api/app.py:62`] on 2 CPUs [D2] |
| Rate limit: `POST /ingestion-jobs` | The `admin` key only; 1 per hour | 1 active job at most already [ADR-013 D4]; a rebuild shares the CPUs with asks (1.3) |
| A question length cap | At most 2,000 characters, else 422 | No cap today [`api/app.py:43`]; bounds input tokens (1.2) |
| Where the counters live | In the API's memory (there is 1 API process [ADR-014 Context]) or in a table (survives restarts) | S17's design review decides |
| Model text as plain text | The UI never renders `answer` or a summary as HTML | 3.3 |
| The carried items | A fixed 502 text, with the cause in the log; a deadline per ask | Section 8 |

## 8. Carried items

Each is rated for a deployment with no inbound ports [m16]. **Must-fix: none**, so no code changes in S15. Each needs a public API (or a misconfiguration) to matter, so all 6 go to S17's design review.

| # | Item [source] | What the code does | Rating | Disposition |
|---|---|---|---|---|
| 8.1 | Logs: the reranker's library writes plain-text lines; a failed traced ask's log line has no `trace_id`; a 502 or 503 logs no cause [S15 security review inputs (1); PR #49 deferred items 1, 3, 4] | `trace_id` is set only on success [`api/app.py:154-156`]; the `ApiError` handler logs nothing [`api/errors.py:54-55`]; plain-text library lines [`docs/interfaces.md`, "Logs"] | Low: harder debugging, no secret; the cause is in the 502's body and the Langfuse trace [`pipeline.py:222`] | Proposed (S17), with 8.3 |
| 8.2 | Anthropic's `retry-after` has no cap [(2); PR #49 deferred 2] | SDK 1.11.0 waits as long as the header says, up to 4,294,967 s [`anthropic/_base_client.py:834-839`] | Low: 1 user; a stalled ask holds 1 request. S17: medium (stalled requests pile up) | Proposed (S17): a deadline per ask |
| 8.3 | Provider text in a 502; any `RuntimeError` or `ValueError` is a 502; a validation message can include the input [(3); PR #49 question 3] | The 502 message is the error's one line [`api/app.py:148-149`; `pipeline.py:325-327`]; Voyage's reason, up to 500 characters [`voyage.py:115-116`]; `ASK_ERRORS` lists both base types [`pipeline.py:51-59`] | Low: only the author sees it; never a key [`voyage.py:95-96`] | Proposed (S17): a fixed 502 text, the cause in the log |
| 8.4 | `VOYAGE_MAX_RETRIES` has no upper bound and its wait doubles without a cap; the connection helper's `options` replaces any `options` in `DATABASE_URL` [(4); PR #50 deferred 3, 4] | No upper bound [`settings.py:63`]; `2**retries` [`voyage.py:117`]; `options=` [`db/connect.py:19-24`] | Low: the deployment sets neither. Retries stay 3 (waits 1 + 2 + 4 s) [`docs/interfaces.md`, "Worst case"]; `DATABASE_URL` ends `?sslmode=require`, with no `options` [Pinned T4], and `sslmode` is a different key | Proposed (S17) |
| 8.5 | A file path in a job's error [PR #51 deferred 3] | A missing snapshot's error names its path [`ingestion/github.py:178-180`]; it is a known error, shown in the job [`worker.py:78`, `:199-201`], which `GET /ingestion-jobs/{job_id}` returns [`api/app.py:207-221`] | Low: in the container the path is `/corpus_cache/github/<repo>/<kind>/<number>.json` [names table; `ingestion/manifest.py:179-181`]: no user name, no secret | Proposed (S17): name the item only |
| 8.6 | The misleading "step failed" line [PR #51, deferred "Behavior"] | A connection lost mid-step logs `Job <id>: step <name> failed` [`worker.py:202-204`]; saving the job then fails [`worker.py:207`] and the worker exits; the job stays `running` and is resumed [`docs/interfaces.md`, "A lost database connection"] | Low: a log line only; the job's row is right, and Docker restarts the worker [D4] | Proposed (S17) |

## 9. Not verified

- The prices: checked in the design review, not re-checked in this run; the alarm price (6, last rows) was not checked in the design review.
- That auto-reload is off in the Anthropic console (2.6), and whether Voyage's account has a spending limit (1.4).
- That a Terraform refresh writes the real API keys into state (2.4): the provider's docs say a stored value is in state; the refresh behavior is inferred.
- That every outbound destination in c3 uses HTTPS (4.7).
- Every `TF`, `Image` and `Runbook` location: this review was written before T3–T5, so each points at the plan's pinned text, not at built code.

## 10. Commands to reproduce

Run from the repo root.

```bash
# 5 GitHub threads, 210 of 48,483 stored texts (section 3); needs `make up`
docker compose exec -T db psql -U orgknow -d orgknow -At -c "select d.source_type, count(distinct d.id), count(c.id) from documents d join document_versions v on v.document_id = d.id join chunks c on c.document_version_id = v.id group by 1 order by 1;"
# 91 locked packages; only the project itself has no hashes (5.1)
python3 -c "import tomllib; p = tomllib.load(open('uv.lock', 'rb'))['package']; h = lambda x: [a.get('hash') for a in x.get('wheels', []) + [x.get('sdist', {})] if a]; print(len(p), 'packages; without hashes:', [x['name'] for x in p if not h(x) or not all(h(x))])"
# No model call passes tools (section 3): prints 0
grep -rn 'tools=' src/ | wc -l
# No SQL built with f-strings in db/ (3.4): prints 0
grep -rnE 'execute\(f|f"""' src/orgknow/db/ | wc -l
# The SDK's retry-after wait (8.2)
sed -n 834,839p .venv/lib/python3.12/site-packages/anthropic/_base_client.py
```
