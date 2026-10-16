# S15: AWS deployment

- **Status:** 🟨
- **Blueprint stage:** 11 (AWS portfolio deployment); gap #6 (risk/security/cost review)
- **Started:** 2026-10-14
- **Finished:**

## Outcome

One `terraform apply` from the laptop creates the AWS environment (EC2, RDS, S3, ECR, IAM, CloudWatch, SSM, a budget alarm). The API and the worker run there from one container image and restart after a crash. The deployed API answers a live question with citations, the RDS database's ingestion fingerprint equals the laptop's, the forecast cost is ≤ US$50/month, and one runbook command removes everything.

## Why now

- M2 needs a deployed system (blueprint §23, stage 11). S16 (CI/CD) deploys to it; S17 (Next.js UI) serves from it.
- Blueprint gap #6 (risk, security, cost) is "before public deployment": it comes first.
- It retires 4 open triggers: ADR-004's pgvector and `btree_gist` recheck on RDS, ADR-005's connection-count trigger, ADR-008's instance choice, and ADR-013's missing worker supervisor.

## Exit checks

- [ ] The review covers gap #6's 6 topics (model-API abuse and cost, secrets, prompt/data injection, public exposure, dependencies, AWS cost guardrails), each with a rating, a mitigation and where it lives.
- [ ] ADR-014 (deployment topology) is Accepted.
- [ ] `make image` builds one image; on the laptop, its API answers `/ready` 200, and its worker runs a job to `succeeded` with the fingerprint unchanged.
- [ ] `make tf-check` (format, validate, offline tests) is green.
- [ ] *(T6)* On AWS: `/ready` 200; RDS reports pgvector 0.8.1 and `btree_gist`; the RDS fingerprint equals `sha256:0f0ee078…4165`; one live ask answers with citations and a Langfuse trace; latency, RDS `max_connections` and peak connections are recorded (ADR-005's trigger); the cost forecast is ≤ US$50/month (with no forecast for the new account: one full day's cost × 30.4; PR review, 2026-10-15), read as gross cost, credits and tax left out, with net and tax recorded beside it (S15-R2 sitting, P4).
- [ ] *(T6)* The teardown runbook was run once and left no billable resource.
- [ ] Guard: `make eval-retrieval`'s metric lines and the dev fingerprint are unchanged.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| Risk/security/cost review (gap #6) | SQS (ADR-013 D1) |
| ADR-014: deployment topology | ECS/Fargate, ALB, NAT gateway, Secrets Manager, Route 53/CloudFront (blueprint §23.2) |
| One container image (API and worker) | CI/CD: building and deploying on merge (S16) |
| Terraform: EC2, RDS, S3, ECR, IAM, CloudWatch, SSM, a budget alarm | The Next.js UI and its public exposure (S17) |
| A deploy and teardown runbook | Multi-AZ, autoscaling, a staging environment |
| The first real deploy and its measurements (T6) | Re-embedding the corpus in the cloud |

## Metric to move

n/a (deployment). Guards: Phase 1 retrieval metrics and the ingestion fingerprint stay exactly the same; monthly cost ≤ US$50 (forecast). Recorded, not moved: live answer latency on the deployed instance, against the spec's 23 s p95 ceiling.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S15-T1: Risk, security and cost review `[core]`

- **Goal:** blueprint gap #6 as one doc, written from the sitting's decisions.
- **Done when:** each of the 6 topics has its risks, a rating, the mitigation and where it lives (ADR-014, Terraform, runbook, or parked); S14's security inputs and PR #51's parked 2–3 each have a disposition; the cost table sums to ≤ US$50/month with each price's source.
- **Notes / pointers:** blueprint §20, §23, §26.2, §27, §32 gap #6; the Proposed addition "S15 security review inputs from S14-R1".
- **Deps:** the contract.

### S15-T2: ADR-014, deployment topology `[core]`

- **Goal:** the topology decided in the sitting, committed as Accepted in the contract commit.
- **Done when:** the ADR is in `docs/decisions/` with its index row and `.greptile/files.json` entry.
- **Deps:** none.
- **Done:** decided in the S15-R1 sitting (2026-10-15); committed with the run contract.

### S15-T3: Container image `[commodity]`

- **Goal:** one image that runs the API or the worker, with the reranker's weights inside.
- **Done when:** `make image` builds it; on the laptop, the API container answers `/health` and `/ready` 200 and `GET /decisions/kep:2572`; the worker container runs a job to `succeeded` against the local database with the fingerprint unchanged; a killed worker container is restarted by its restart policy.
- **Notes / pointers:** `git` is needed in the image (`ingestion/git_reader.py`); the corpus cache is mounted; `make serve` binds 127.0.0.1.
- **Deps:** the contract.

### S15-T4: Terraform `[commodity]`

- **Goal:** the AWS environment as code, checked offline.
- **Done when:** `make tf-check` runs `terraform fmt -check`, `validate` and `terraform test` (mock providers, no AWS account) and is green; the tests pin the contract's security and cost rules.
- **Deps:** the contract.

### S15-T5: Deploy and teardown runbook `[commodity]`

- **Goal:** the exact commands for the first deploy, an update, and teardown.
- **Done when:** the runbook covers credentials, `apply`, pushing the image, uploading the corpus, loading the database, starting, checking, and `destroy`; each command matches a T3/T4 target or resource.
- **Deps:** T3, T4.

### S15-T6: First deploy and measurements `[human]`

- **Goal:** the real environment, created with the developer, and the numbers that close the ADR triggers.
- **Done when:** the T6 exit checks above hold, with each number in the slice doc.
- **Notes / pointers:** paid (AWS hours, a few Anthropic asks); needs the developer's AWS login. ADR-004 (pgvector recheck), ADR-005 (connection trigger), ADR-008 (instance).
- **How:** the checklist in run contract S15-R2 (one window covering a full UTC day, evidence E0–E13). It changes no repo file; T7 records its numbers and ticks it.
- **Deps:** T5.

### S15-T7: Docs and the S15 retro `[commodity]`

- **Goal:** T6's numbers and evidence in the repo, the ADR triggers closed, then the S15 retro.
- **Done when:** the "T7 plan" in run contract S15-R2 holds. An interactive task (`/start-task S15-T7`), not a run: it is the only task left that isn't `[human]` (S15-R2 decision 6).
- **Deps:** T6.

## Risks & unknowns

- **Cost:** an always-on instance and database sit near the US$50 line; a forgotten resource bills every hour.
- **Latency on 2 CPUs:** the projected answer p95 is 22–24 s against the 23 s ceiling (`docs/evaluation.md`, "Reranker timing and S15 sizing").
- **A new account's limits:** on-demand vCPU quotas may be low.
- **RDS:** Postgres 18 and the chosen class must exist in the region; the HNSW index rebuild on a 1 GiB instance is unmeasured.
- **Secrets:** Terraform's state file holds the generated database password.

## Decisions expected (ADRs)

- ADR-014: deployment topology (S15-R1 sitting).
- ADR-014 amendment 2026-10-16: the deployment exists only in windows (S15-R2 sitting).

## Run contracts

### Run S15-R1: Review, image and Terraform

- **Status:** PR open (2 PRs, split after T3)
- **Tasks:** T1, T3, T4, T5 (T2, ADR-014, is in this contract's commit). T6 is `[human]`, needs the developer's AWS login and is paid: never in a run.
- **Goal (plain words):** write down every risk of the deployment and where its fix lives; build one container image and prove it on the laptop (the API answers, the worker rebuilds the real corpus with the same fingerprint, the retrieval eval prints the laptop's numbers); describe the whole AWS environment in Terraform, checked offline by tests that pin the security and cost rules; and write the runbook T6 will follow. Nothing in AWS is created.

#### Sitting evidence (2026-10-14/15)

Each result is copied from its output.

- **Tools on the laptop:** `Terraform v1.14.8 on linux_amd64`; `aws: command not found` (no AWS CLI, no credentials); Docker on `x86_64`.
- **Database size:** `431 MB` (`embeddings` 292 MB, `chunks` 126 MB); a compressed dump: `pg_dump -Fc | wc -c` → `118992254` bytes (119 MB). Extensions: `vector 0.8.1`, `btree_gist 1.8`. Local `max_connections`: `100`.
- **Corpus cache:** `396M ~/corpus_cache/org-knowledge-rag`; `community`, `enhancements`, `kubernetes`, `sig-release`, `website` are partial clones (`promisor=true`, `filter=blob:none`); `gh/` and `github/` are plain files.
- **No network needed for a no-op ingest:** `GIT_ALLOW_PROTOCOL=file` blocks lazy fetches (`fatal: transport 'https' not allowed` / `fatal: could not fetch 0080fd68… from promisor remote`); with it, `make ingest` took `real 0m21.603s` and printed `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`. (A first attempt overriding `remote.origin.url` through the environment did not block git: `ls-remote` still reached GitHub. Don't use it as a proof.)
- **Git refuses a cache owned by another user:** `docker run -u 10001 -v <cache>:/c:ro alpine/git:v2.47.2 -C /c/sig-release log -1` → `To add an exception for this directory, call: git config --global --add safe.directory /c/sig-release`, exit 128.
- **torch for ARM exists** in `uv.lock` (`torch-2.14.1+cpu-cp312-cp312-manylinux_2_28_aarch64.whl`); not used (decision 2).
- **Prices** (us-east-1, on demand, 730 h/month), each checked in the sitting:

| Item | Price | Per month | Source |
|---|---|---|---|
| EC2 t3a.medium (2 vCPU, 4 GiB) | US$0.0376/h | 27.45 | instances.vantage.sh/aws/ec2/t3a.medium |
| EBS gp3, 20 GB | US$0.08/GB-month | 1.60 | EBS pricing (secondary sources) |
| Public IPv4, 1 | US$0.005/h | 3.65 | AWS public IPv4 charge (since 2024-02-01) |
| RDS db.t4g.micro, single-AZ | US$0.016/h | 11.68 | instances.vantage.sh/aws/rds/db.t4g.micro |
| RDS gp3, 20 GB | US$0.115/GB-month | 2.30 | RDS pricing (secondary sources) |
| ECR, ~3 GB | US$0.10/GB-month | 0.30 | estimate |
| CloudWatch Logs | US$0.50/GB ingested | ~0.50 | estimate |
| S3, ~0.6 GB | US$0.023/GB-month | 0.01 | estimate |
| SSM standard parameters, Budgets (first 2), SNS email, VPC, IAM | — | 0 | — |
| **Total** | | **47.49** | |

  For comparison: t3.medium (US$0.0416/h) → 50.40 in total; t4g.medium (US$0.0336/h) → 44.56.
- **The AWS account:** created 2026-10-14 on the **Paid Plan** (no Free Plan instance restrictions). Only the root login exists so far.
- **Devil's advocates** (one per decision 1–3): none changed a decision. Decision 1's added the condition that T1 designs the S17 exposure controls (never "n/a"); decision 2's made the instance type a variable, the credit mode explicit (standard), and the T6 measurement with its 15 s rule; decision 3's added the tests that pin "no public address" and "no internet route".

#### Decisions (made in the sitting, 2026-10-15)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | Triage: PR #51 parked 2 (no worker supervisor) → T3; PR #51 parked 3 (a file path in a job's error), the "misleading step failed line" and the 4 "S15 security review inputs" → T1 rates each; "S15: the reranker's 2-CPU numbers" → decision 2; PR #52 parked 1 (ADR index rows) → fixed in this commit; PR #51's 9 and PR #52's 3 doc nits → folded into "Phase 1 text corrections"; PR #51's 7 test nits and "untested" list dropped | — | — |
| Scope | Slice tasks T1–T7; bundle T1, T3, T4, T5; T6 `[human]` with the developer; latency recorded, not gated; the teardown proof in T6 | AWS calls in the run | No credentials; creating resources costs money |
| 1 | **No inbound ports; Session Manager tunnel** (ADR-014 D1). T1 designs S17's public controls (HTTPS, API key, per-key spending cap, rate limits on the 2 POST routes), marked Proposed | HTTP + key + IP allowlist; HTTPS proxy now | Only the developer needs access before S17; abuse risk 0; adding a door later is cheap |
| 2 | **t3a.medium, local reranker, standard credits; measured in T6** (ADR-014 D2); > 15 s retrieve p95 → next sitting | t4g.medium (ARM); Voyage rerank + t3a.small; t3.medium | Same x86 image as the laptop; US$47.49; ARM can't be tested here; Voyage changes every metric |
| 3 | **Own VPC: public subnet for the server, 2 private subnets for RDS**, with tests pinning no public address and no internet route (ADR-014 D3) | The default VPC | Two locks instead of one; no dependency on the default VPC; US$0 |
| PRs | **2 PRs, split after T3:** PR 1 = T1 + T3 (`s15-r1a-review-image`, cut at T3's commit); PR 2 = T4 + T5 (this branch, based on PR 1) | 1 PR | Size alarm (~1,100–1,300 lines); one purpose per PR; the Terraform gets its own review |
| Paid | **None** | — | — |

**Claude's calls** (reversible; confirmed at the read-back):
- m1. Region `us-east-1`.
- m2. RDS is loaded from a dump of the laptop's database through S3, never re-embedded (ADR-014 D5).
- m3. The reranker's weights are downloaded at build (`RERANK_MODEL` at `RERANK_REVISION`) into the image; `HF_HUB_OFFLINE=1` at runtime.
- m4. One image, 2 containers via `docker run`, `--restart unless-stopped`; the API published on `127.0.0.1:8000` only.
- m5. A non-root user; `git config --system --add safe.directory '*'`; `GIT_ALLOW_PROTOCOL=file`.
- m6. The corpus cache as one archive in S3, unpacked by the deploy script, mounted read-only into the worker.
- m7. Secrets in SSM `SecureString` under `/orgknow/<ENV_VAR>`; the developer sets the API keys; Terraform writes `DATABASE_URL`; the password has letters and digits only.
- m8. Local Terraform state, gitignored; providers pinned in the committed lock file.
- m9. Docker's `awslogs` driver → log group `/orgknow`, 14-day retention; 2 alarms → SNS email.
- m10. Budget US$50/month: email at 80% actual, 100% forecast; the email address in a gitignored `terraform.tfvars`.
- m11. RDS: Postgres major 18, `db.t4g.micro`, 20 GB gp3, single-AZ, encrypted, 1-day backups, no final snapshot, no deletion protection, `sslmode=require`.
- m12. Amazon Linux 2023 (latest AMI from AWS's public SSM parameter), 20 GB gp3 encrypted, IMDSv2 required, a least-privilege role.
- m13. 1 ECR repository (scan on push, keep the last 3 images); 1 S3 bucket (all public access blocked, encrypted, `force_destroy`).
- m14. `make image`, `make image-check`, `make tf-check`; `make tf-check` is not part of `make check` (CI gets Terraform in S16).
- m15. The image holds the files `make eval-retrieval` reads (the golden set v0, the conflict set, the stored question vectors and routes).
- m16. T1 rates each S14 input; code is fixed only if rated must-fix for a deployment with no inbound ports (none expected); the rest → Proposed additions for S17.
- m17. Files: `Dockerfile`, `.dockerignore`, `infra/`, `docs/security-review.md`, `docs/deployment.md`; `CLAUDE.md`'s repo map gains `infra/` and the `Dockerfile`.
- m18. One names table (below) that T3, T4 and T5 copy from.

**Details set while writing the contract** (Claude's calls; listed at the hand-off for the developer to see):
- c1. The boot script installs Docker and writes the deploy script, but starts nothing: the first start is the runbook's `orgknow-deploy <tag>`, after the image is pushed, the secrets are set and the database is loaded. On a reboot, Docker's restart policy brings both containers back.
- c2. The app connects as the RDS master user (one database user); T1 rates it.
- c3. The server's security group allows all outbound traffic (Anthropic, Voyage, Langfuse, ECR, SSM, S3, the Amazon Linux repos, RDS); T1 rates it.
- c4. Terraform creates the 4 API-key parameters with the placeholder value `set-me` and ignores later value changes, so the names (and the role's scope) are in code and the real values never are.
- c5. *(Set in the run, from T1's finding 6.6.)* The ECR repository has `force_delete = true`, as the bucket has `force_destroy` (m13): the provider's default (`false`) makes `terraform destroy` stop on a repository that holds images, against D7 and the slice outcome ("one runbook command removes everything"). Confirmed by the developer at the PR review (2026-10-15).

#### Developer's answers at the PR review (2026-10-15, PRs #53 and #54)

| # | Question | Answer | Where |
|---|---|---|---|
| 1 | ADR-014 D6 and review row 2.8 said the server "reads only `/orgknow/*`", but the managed Session Manager policy can read any parameter by name | **Reword** both (rejected: a narrower Session Manager policy); this account holds no other parameters | PR #53 |
| 2 | c5: the registry is deleted with `destroy` even when it holds images | **Keep** | c5 |
| 3 | The laptop's Langfuse region (US) isn't the app's default (EU), and the server's env had no setting for it | **A 6th Terraform parameter** `/orgknow/LANGFUSE_BASE_URL`, a plain String (not a secret), from the variable `langfuse_base_url` with no default (rejected: setting it by hand at T6) | Names table; PR #54 |
| 4 | A new account may get no cost forecast in T6 | **Accept** one full day's cost × 30.4 for the ≤ US$50 check | Exit checks |

#### Names table (T3, T4 and T5 copy from here)

| Thing | Value |
|---|---|
| Local image | `orgknow:dev` (`make image`) |
| ECR repository | `orgknow`; tags are the git short SHA |
| Container names | `orgknow-api`, `orgknow-worker` |
| API command | `uvicorn --factory orgknow.api.app:create_app --host 0.0.0.0 --port 8000 --log-config config/logging.json --no-access-log` |
| API port | container 8000 → server `127.0.0.1:8000` |
| Worker command | `python -m orgknow.ingestion.worker` |
| Image workdir | `/app` |
| Container user | `orgknow`, uid 10001 |
| Model cache in the image | `HF_HOME=/opt/hf`, `HF_HUB_OFFLINE=1` |
| Corpus cache in the container | `/corpus_cache` (`CORPUS_CACHE_DIR=/corpus_cache`), read-only |
| Corpus cache on the server | `/srv/orgknow/corpus_cache` |
| Env file on the server | `/etc/orgknow/env` (root, mode 0600) |
| Deploy script on the server | `/usr/local/bin/orgknow-deploy <image-tag>` |
| SSM parameters (SecureString) | `/orgknow/DATABASE_URL` (Terraform), `/orgknow/ANTHROPIC_API_KEY`, `/orgknow/VOYAGE_API_KEY`, `/orgknow/LANGFUSE_PUBLIC_KEY`, `/orgknow/LANGFUSE_SECRET_KEY` (developer) |
| SSM parameter (String) | `/orgknow/LANGFUSE_BASE_URL` (Terraform, from `langfuse_base_url`; added at the PR review, 2026-10-15) |
| S3 bucket | `orgknow-<account id>-us-east-1` |
| S3 objects | `corpus_cache.tar.gz`, `orgknow.dump` |
| Log group / streams | `/orgknow`; `api`, `worker` |
| RDS | identifier `orgknow`, database `orgknow`, user `orgknow`, port 5432 |
| SNS topic | `orgknow-alerts` |
| Budget | `orgknow-monthly`, US$50 |
| Terraform variables | `region` (`us-east-1`), `instance_type` (`t3a.medium`), `alert_email` (no default), `budget_usd` (50), `langfuse_base_url` (no default; PR review) |
| Terraform outputs | `ecr_repository_url`, `bucket_name`, `instance_id`, `rds_endpoint` |

#### Pinned: T1 (the risk, security and cost review)

- **`docs/security-review.md`**, with one table per topic of blueprint gap #6: model-API abuse and cost; secret handling; prompt and data injection; public endpoint exposure; dependency risk; AWS cost guardrails. Each row: the risk, a rating (high/medium/low, with its reason in one line), the mitigation, and where it lives (an ADR-014 D-number, a Terraform resource, the runbook, or "Proposed (S17)").
- **Must include:**
  - Decision 1's S17 exposure design (HTTPS, an API key, a per-key spending cap, rate limits on `POST /query` and `POST /ingestion-jobs`), marked Proposed; abuse and exposure are never "n/a".
  - Injection: GitHub comments (tier 7) are user-written text that reaches the answer prompt; what limits the damage (structured output, citation validation, no tools the model can call), and what doesn't.
  - Secrets: SSM, the env file, the state file holding the database password, root vs. an admin user with MFA (the account has only root today), the Anthropic prepaid balance as a hard spending ceiling.
  - Dependencies: `uv.lock` pins every Python package with hashes; base images pinned by digest; ECR scan on push; the providers' lock file.
  - The cost table above, with each price's source, and the guardrails (ADR-014 D7).
  - c2 and c3, rated.
- **A disposition for each** of: the 4 "S15 security review inputs from S14-R1" (plain-text library log lines and missing `trace_id`/causes; Anthropic's uncapped `retry-after`; provider text in a 502; unbounded `VOYAGE_MAX_RETRIES` and the replaced `options`), PR #51 parked 3 (a file path in a job's error) and the "misleading step failed line": fixed in this run only if rated must-fix for a deployment with no inbound ports; otherwise a Proposed addition (S17) named in the review.
- **Every claim beside its source** (a contract line, an ADR, a Terraform resource, a price link, a code line); the builder lists them for the reviewer (S14's retro).

#### Pinned: T3 (the container image)

- **`Dockerfile`:** `python:3.12-slim` pinned by digest; uv copied from `ghcr.io/astral-sh/uv` pinned by digest; `git` installed; `uv sync --frozen --no-dev` (the CPU torch index, as in `pyproject.toml`); the reranker's weights fetched at build (m3); the names table's user, workdir, `HF_HOME`, `HF_HUB_OFFLINE=1`, `GIT_ALLOW_PROTOCOL=file`, `CORPUS_CACHE_DIR=/corpus_cache`; `git config --system --add safe.directory '*'`; the default command is the API's. A multi-stage build only if it's needed to keep build tools out.
- **`.dockerignore`:** an allowlist (`*`, then `!` the paths the image needs: `pyproject.toml`, `uv.lock`, `src/`, `config/`, and m15's eval files). `.env` and `.venv` are never sent.
- **Make targets:** `image` (`docker build -t orgknow:dev .`); `image-check` (one `docker run --rm orgknow:dev` that fails unless: no `/app/.env`, `id -u` is not 0, `GIT_ALLOW_PROTOCOL` is `file`, and git's system config lists `safe.directory`).
- **No change under `src/`** is expected. If one is needed (e.g. a path the container can't see), it's the smallest one, named in the brief; anything touching retrieval, generation or ingestion logic → park.

#### Pinned: T4 (Terraform)

- **`infra/`** (one root module; no sub-modules): `versions.tf` (Terraform ≥ 1.14; `hashicorp/aws` and `hashicorp/random` pinned to minor versions), `variables.tf`, `network.tf`, `compute.tf` (the instance, its role and profile, the boot script from a template file), `database.tf`, `storage.tf` (S3, ECR), `observability.tf` (logs, alarms, SNS, the budget), `ssm.tf`, `outputs.tf`, `terraform.tfvars.example`, `tests/*.tftest.hcl`. `.terraform.lock.hcl` committed.
- **`.gitignore`** (in the same commit, before any `apply` can happen): `infra/.terraform/`, `*.tfstate`, `*.tfstate.*`, `infra/terraform.tfvars`.
- **Network:** a VPC `10.0.0.0/16`; public subnet `10.0.1.0/24` (zone a, route `0.0.0.0/0` → internet gateway); private subnets `10.0.11.0/24` (zone a) and `10.0.12.0/24` (zone b) on their own route table with no routes beyond the local one; a DB subnet group of the 2 private subnets.
- **Security groups:** the server's: no ingress, all egress (c3); the database's: ingress TCP 5432 from the server's group only.
- **The instance:** m12; `instance_type` variable; `credit_specification { cpu_credits = "standard" }`; `associate_public_ip_address = true`; `metadata_options { http_tokens = "required" }`; root volume 20 GB gp3 encrypted; the boot script (c1) installs Docker (`dnf`), enables it, writes `/usr/local/bin/orgknow-deploy`.
- **The deploy script** (`orgknow-deploy <tag>`): fetch `/orgknow/*` with decryption into `/etc/orgknow/env` (0600); if `/srv/orgknow/corpus_cache` is missing, download and unpack `corpus_cache.tar.gz`; log in to ECR; pull the tag; remove and re-run both containers with the names table's commands, `--restart unless-stopped`, `--env-file`, `--log-driver awslogs` (group `/orgknow`, streams `api` and `worker`, region), the corpus mount read-only on the worker, the API on `127.0.0.1:8000:8000`.
- **IAM:** the managed `AmazonSSMManagedInstanceCore`; an inline policy: `ssm:GetParametersByPath`/`GetParameters`/`GetParameter` on `parameter/orgknow/*`; `ecr:GetAuthorizationToken` (`*`), `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchCheckLayerAvailability` on the repository; `s3:GetObject` on the bucket's objects and `s3:ListBucket` on the bucket; `logs:CreateLogStream`, `logs:PutLogEvents` on the log group.
- **RDS, S3, ECR, logs, alarms, budget, SSM:** m9–m11, m13, c4, c5, the names table. `DATABASE_URL` = `postgresql://orgknow:<password>@<endpoint>:5432/orgknow?sslmode=require`; `random_password` length 32, `special = false`.
- **`make tf-check`:** `terraform -chdir=infra fmt -check -recursive`, `terraform -chdir=infra init -backend=false -input=false` (downloads the pinned providers), `validate`, `test`. Tests use `mock_provider` (offline, no AWS account) with `command = apply` where computed values are needed, and `override_data` for the AMI lookup and the account ID.

#### Pinned: T5 (the runbook)

- **`docs/deployment.md`**, in order:
  1. **Account set-up (once):** MFA on root; an IAM Identity Center admin user; the AWS CLI and the Session Manager plugin on the laptop; `aws configure sso`, `aws sso login`.
  2. **Create:** `cp infra/terraform.tfvars.example infra/terraform.tfvars` (the alert email); `terraform -chdir=infra init`, `plan`, `apply`; confirm the SNS subscription email.
  3. **Secrets:** `aws ssm put-parameter --overwrite --type SecureString` for each developer-set name.
  4. **Image:** `make image`; tag with the git short SHA; ECR login; push.
  5. **Data:** `pg_dump -Fc` of the laptop database and `tar czf` of the corpus cache; `aws s3 cp` both; on the server (Session Manager shell), `pg_restore` into RDS from the `pgvector/pgvector:0.8.1-pg18` image.
  6. **Start:** `sudo orgknow-deploy <tag>`.
  7. **Check:** the Session Manager port-forward to `127.0.0.1:8000`; `curl` `/health`, `/ready`; the fingerprint on RDS; T6's measurements.
  8. **Update:** push a new tag, `sudo orgknow-deploy <tag>`.
  9. **Teardown:** `terraform -chdir=infra destroy`; what to check after (no running instance, no RDS instance, no bucket, no unattached address, the next day's cost).
- **Every command names its source:** a make target, a Terraform output or resource, or the names table; nothing invented.

#### Handoffs between tasks

- T1 → T3/T4/T5: each mitigation T1 places in T3, T4 or T5 must be in that task's pinned text above; T1 places nothing new in them (a new control → Proposed).
- T3 → T4: the image's commands, user, paths and env names (the names table); T4's deploy script runs exactly the names table's commands.
- T3 + T4 → T5: `make image`, the Terraform outputs and the deploy script.

#### Edge cases

- The container's user doesn't own the mounted cache → git refuses it (sitting probe); the safe-directory line prevents it (break-it 2).
- A file missing from the cache → the ingest step fails with git's error (`GIT_ALLOW_PROTOCOL=file`), never a fetch from GitHub.
- `docker stop`/`docker kill` count as manual stops: the restart policy ignores them. The restart proof uses a lost database connection (below).
- An idle worker may not exit on a lost connection (S14's retro: "not exercised"). If T3's restart proof finds it hanging or not exiting, that's a worker bug: park it (no `src/` change in this run), and record the restart policy as proven only by `docker inspect`'s configured policy.
- The worker's start-up check needs `VOYAGE_API_KEY` set: the local demo uses a dummy value with `EMBED_MAX_TOKENS_PER_RUN=1`, so any paid request refuses.
- The image build downloads ~1.1 GB of model weights and ~800 MB of wheels: slow, but free. A failed download → retry (no-progress rule after 3).
- `terraform init` downloads the AWS provider (~600–700 MB) into `infra/.terraform/` (gitignored).
- Mock providers fill computed attributes with made-up values; a format check on a fake ARN can fail. Use `override_resource`/`override_data` with realistic values; 3 failed attempts → park that test.
- The RDS password must stay URL-safe (`special = false`).
- `.env` exists in the repo root (the developer's real keys): the allowlist `.dockerignore` must never send it.

#### Files in scope

`docs/security-review.md` (T1); `Dockerfile`, `.dockerignore`, `Makefile` (`image`, `image-check`, `tf-check`) (T3, T4); `infra/**` and `.gitignore` (T4); `docs/deployment.md` (T5); `CLAUDE.md`'s repo map (m17); `docs/backlog.md` (ticks, Proposed additions from T1); this slice doc. Nothing under `src/` or `tests/` unless T3's rule above allows it.

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T1 | 6 topics, each risk with a rating, mitigation and location | The reviewer reads it; each location exists in this contract's pinned text or ADR-014 | Blueprint gap #6; this contract |
| T1 | S17 exposure controls designed, marked Proposed | Present; abuse and exposure not "n/a" | Decision 1 |
| T1 | Cost ≤ US$50 with sources | The table | This contract: US$47.49 |
| T1 | A disposition for each of the 6 carried items | One row each | Step 0's list |
| T3 | The image builds | `make image` exits 0; `docker image ls orgknow:dev` size | ~2.5 GB (estimate; recorded, not gated) |
| T3 | No secrets, non-root, git settings | `make image-check` exits 0 | m5, the names table |
| T3 | The API runs | `curl` `/health` → 200; `/ready` → 200; `GET /decisions/kep:2572` → 200 with 6 steps | S13: 6 steps |
| T3 | The worker runs a job | POST `/ingestion-jobs` → the job `succeeded`; ingest counts: 0 new versions, 0 new chunks; embed: 0 requests | S14-R2's demo |
| T3 | The fingerprint is unchanged | The job's ingest step's `fingerprint` | `sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165` (sitting) |
| T3 | Retrieval is unchanged in the container | `python -m orgknow.eval retrieval` in the container → its first 5 lines | PR #51's laptop lines (below) |
| T3 | The worker restarts itself | `docker compose restart db` → the worker exits on the lost connection → `docker inspect -f '{{.RestartCount}}' orgknow-worker` ≥ 1, then a job still runs to `succeeded` | ADR-013's amendment; ADR-014 D4 |
| T4 | Format, validate, tests | `make tf-check` green | — |
| T4 | RDS has no public address | test: `publicly_accessible == false` | Decision 3 |
| T4 | The private subnets have no internet route | test: the private route table has 0 routes to `0.0.0.0/0`, and both private subnets use it | Decision 3 |
| T4 | The server has no inbound rule | test: 0 ingress rules on its group | Decision 1 |
| T4 | The database admits only the server | test: 1 ingress rule, TCP 5432, source = the server's group | Decision 3 |
| T4 | Instance and credits | test: `instance_type == "t3a.medium"` by default; `cpu_credits == "standard"`; `http_tokens == "required"` | Decision 2, m12 |
| T4 | Budget | test: limit 50 USD monthly; notifications ACTUAL > 80% and FORECASTED > 100% to `alert_email` | m10 |
| T4 | Storage locked down | test: S3 public access block all 4 true; RDS `storage_encrypted`; root volume encrypted; log retention 14 | m9, m11–m13 |
| T4 | SSM names | test: the set of parameter names equals the names table's 6 (5 before the PR review) | m18 |
| T5 | Every step has a command, and every command a source | The reviewer checks each against T3's targets, T4's outputs/resources and the names table | This contract |

PR #51's laptop lines (T3's expected values; the 6th line, the retrieve time, differs by machine and is recorded, not compared):

```
Recall@10 0.522  Hit@10 0.972  MRR 0.781  nDCG@10 0.508
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Authority selection 0.889 (8 of 9 CURRENT questions)  CURRENT MRR 0.733
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date
```

#### Break-it rules

- T3: add `!.env` to `.dockerignore`'s allowlist, rebuild → `make image-check` fails. Restore.
- T3: remove the `safe.directory` line, rebuild → the worker's job fails in its ingest step with "dubious ownership". Restore.
- T4: set RDS `publicly_accessible = true` → a test fails. Restore.
- T4: add an ingress rule (e.g. TCP 22 from `0.0.0.0/0`) to the server's group → a test fails. Restore.
- T4: add a `0.0.0.0/0` route to the private route table → a test fails. Restore.
- Each restore is confirmed with `git diff` (empty for that file).

#### Real-data demo (T3; free, laptop)

On the dev database. A no-op job adds 1 row to `ingestion_jobs` and nothing else; `EMBED_MAX_TOKENS_PER_RUN=1` makes any paid request refuse; the Voyage key is a dummy.

```bash
make up && make image && make image-check
NET=orgknow_default; DB=postgresql://orgknow:orgknow@db:5432/orgknow
docker run -d --name orgknow-api --network $NET -p 127.0.0.1:8000:8000 -e DATABASE_URL=$DB \
  -e ANTHROPIC_API_KEY=unused -e VOYAGE_API_KEY=unused orgknow:dev   # the API refuses to start without both keys (T3)
docker run -d --name orgknow-worker --network $NET --restart unless-stopped \
  -e DATABASE_URL=$DB -e VOYAGE_API_KEY=unused -e EMBED_MAX_TOKENS_PER_RUN=1 \
  -v ~/corpus_cache/org-knowledge-rag:/corpus_cache:ro orgknow:dev python -m orgknow.ingestion.worker
curl -s localhost:8000/health; curl -s localhost:8000/ready; curl -s localhost:8000/decisions/kep:2572
curl -s -X POST localhost:8000/ingestion-jobs           # then GET /ingestion-jobs/<id> until succeeded
docker compose restart db; sleep 20; docker inspect -f '{{.RestartCount}}' orgknow-worker
docker run --rm --network $NET -e DATABASE_URL=$DB orgknow:dev python -m orgknow.eval retrieval
docker rm -f orgknow-api orgknow-worker
```

#### Bundle-level check (end of run; free, ~10 min)

- `make check`; `make test-int`; `make tf-check`.
- The T3 demo above, from a fresh `make image`.
- `git diff main --stat -- src/ tests/` is empty (or lists only T3's allowed change).
- `make ingest-report | grep Fingerprint` on the dev database: unchanged.

#### PR plan

- **2 PRs, split after T3.** PR 1 (`s15-r1a-review-image`, cut at T3's commit): the contract, ADR-014, T1, T3. PR 2 (this branch, base PR 1's branch): T4, T5.
- Greptile on both (23/50 → 25/50). No re-review unless must-fix changes behavior.
- **Paid calls allowed:** none. Free downloads only (the base images, the model, the Python wheels, the Terraform providers).

### Run S15-R2: First deploy window (T6) and T7

- **Status:** planned. T6 starts only on the developer's "go".
- **Tasks:** T6 `[human]`, with the developer (paid); then T7 as an interactive task (decision 6). No unattended run: CLAUDE.md's bundle is 2–5 tasks, and T7 is the only one left that isn't `[human]`.
- **Goal (plain words):** create the AWS environment once, for one full UTC day; measure it (the RDS checks, the fingerprint, retrieval speed on 2 CPUs, connections, the real daily cost); capture the evidence as text and a few screenshots; destroy it and prove nothing bills. Then T7 writes it all into the repo and closes S15.

#### Sitting evidence (2026-10-15/16)

- **Input:** a handoff from the developer's planning chat, checked against the repo first (not committed). 14 findings; the ones that changed the plan:
  - S16's "smoke eval in CI" isn't free: `make eval-smoke` makes one paid Anthropic call per question (`Makefile:190`), and it needs the full 431 MB corpus database, which CI doesn't have.
  - The accepted cost check needs one full UTC day of the stack (`docs/deployment.md` 7.6e), so T6 is ~30–36 hours of stack time, not "about a day".
  - E7's commands (the response's request ID, and the same ID in CloudWatch Logs) weren't in the runbook; added in this commit.
  - No OIDC role (OpenID Connect: CI's keyless AWS login) exists in `infra/`; a local "run it yourself" path needs a data load (a published dump, or ~5.69 M paid embedding tokens: ADR-014 Context).
- **Devil's advocate (P1):** its 3 strongest objections were S16's deploy having no standing server, the repeated work and version drift between windows, and a budget alarm sized for always-on (80% of US$50 ≈ 26 days of a forgotten stack). The amendment answers them with S16's own sitting, T6's timing log and a revisit trigger, and a budget per window.
- **The request ID on the laptop** (the image `orgknow:dev`, `GET /health`): the `X-Request-ID` header gave `RID=[f73da06738c7487eb74d748861bfbddb] len=32`, and the container's log had `"message": "GET /health 200", "request_id": "f73da06738c7487eb74d748861bfbddb"`. The runbook's extraction command works on the real header.

#### Decisions (made in the sitting, confirmed 2026-10-16)

| # | Decision | Rejected | Why |
|---|---|---|---|
| P1 | **The deployment exists only in windows** (ADR-014 amendment 2026-10-16): opened when a task needs one (T6; maybe hours in S16; ~7 days in S18), each ended by destroy and step 9's checks; a budget per window; over 2 hands-on hours or a new failure → the next sitting reconsiders stop/start; "≤ US$50/month always on" stays the sizing rule | Always on; stop/start between uses; T6's stack kept through S16–S17 | ~CA$68–74/month with tax for a system only the developer can reach; a stopped RDS restarts itself after 7 days |
| P2 | **T6 now, its window covering one full UTC day** (~30–36 h, ~US$2–2.50 before tax) | Folding T6 into S18 | S16 and S17 get designed on measured numbers; S15 can't close without T6 (exit checks) |
| P3 | **Text-first evidence:** E0–E13 below; raw captures in a local folder outside the repo; T7 commits `docs/deployment-evidence.md` with ≤ 6 redacted screenshots, and S18 adds its window; a search for the account ID must print nothing before any commit; no screen recording until S18 | Screenshots of everything, curated in S18; numbers only | Text is searchable and easy to redact; captures are gone once the stack is destroyed |
| P4 | **Gross and net cost:** read Billing → Credits at the start; the full day's gross cost (credits and tax left out) × 30.4 is compared with US$50, with net and tax recorded; `budget_usd = 5` for T6; if the budget counts credits and the account has them, a Proposed addition makes it count gross before the next window | Fixing the budget before T6; reading only the net bill | Credits would make the bill read ~US$0; a guided 1.5-day window carries little forget risk |
| P5 | **A dated backup of the dump and the corpus archive**, with their sha256, on the Windows side; every window makes fresh files | Deleting them; reloading them in S18 | The embeddings cost money to recreate and the GitHub snapshots are pinned by hash; a stale dump in S18 could miss S16–S17's changes |
| 6 | **T7 is an interactive task** after T6, with the plan below | A 1-task run; folding T7 into S16 | T7's inputs (screenshots, timings, readings) are the developer's; only one slice can be active |

**Claude's calls** (confirmed at the read-back):
- c1. The sitting's outputs ship as one docs-only PR, merged before T6, so the runbook's edits are in place. No Greptile (docs only).
- c2. T6's blocker rule: a problem not fixed the same day → destroy (step 9) first, then park it; the stack never bills overnight while we debug. The same failure after 3 attempts also parks it.
- c3. Screenshots are cropped to the panel when taken, with no account menu, so T7 redacts less.
- c4. Cost Explorer (AWS's billing report page) is opened once before T6's day 1: its data appears ~24 h after the first visit (`docs/deployment.md` 7.6e).
- c5. T6 changes no repo file; T7 records its numbers and ticks it.
- c6. The ADR trigger outcomes go in the ADRs that own them (004, 005, 008), one dated line each, in T7.
- c7. The handoff's errors are corrected in the backlog's Proposed additions (S16's paid smoke eval and its data, no OIDC role yet, the local path's data load).

#### T6 checklist (`[human]`, paid; nothing starts before "go")

Runbook steps are `docs/deployment.md`'s. Evidence goes to a local folder outside the repo.

| When | Runbook step | Evidence |
|---|---|---|
| Before day 1 (free) | This sitting's PR merged; step 1 (MFA on root, an IAM Identity Center admin, the AWS CLI and the Session Manager plugin, `aws sso login`); Cost Explorer opened once; Billing → Credits read; the timing log started | E0 |
| Day 1 | 2: `terraform.tfvars` (`alert_email`, `langfuse_base_url`, `budget_usd = 5`), `plan`, `apply`; the alert email confirmed; whether the budget counts credits | E1, E4 (EC2), E11 |
| | 3: the 4 secrets · 4: the image pushed | E2 |
| | 5: dump, archive, upload; the restore timed; the extensions; the backup and its sha256 | E3, E4 (RDS) |
| | 6: `orgknow-deploy` · 7.1–7.5: logs, tunnel, `/health`, `/ready`, the fingerprint, a free worker job | E5, E6 |
| | 7.6: CPU credits ≥ 30, then the retrieval eval (D2's 15 s rule: record it, change nothing); 1 live question, its request ID found in CloudWatch, its Langfuse trace; `max_connections`, the peak, the connect time | E9, E7, E8 |
| Day 2 | Nothing: the stack runs through the whole UTC day | — |
| Just after UTC midnight ending day 2 | 9: `destroy`, then every check prints nothing | E12 |
| Day 4 (a day after day 2 ends) | 7.6e: day 2's gross by service, net and tax; gross × 30.4 against US$50. Day 3's cost near US$0 | E10, E13 |

**Evidence** (P3; text unless marked as a screenshot):

| # | What | Step |
|---|---|---|
| E0 | Hands-on minutes per runbook step (P1's 2-hour trigger) | All |
| E1 | `apply`'s last lines (`37 added`) | 2 |
| E2 | The pushed tag in the registry | 4 |
| E3 | The restore's time and exit code, the extensions query, the dump's sha256 line | 5 |
| E4 | Screenshots: the server running; the database "Available", "Publicly accessible: No" | 2, 5 |
| E5 | `/health` and `/ready` through the tunnel | 7.3 |
| E6 | The RDS fingerprint line, equal to the laptop's | 7.4 |
| E7 | The live answer (status, time, citations), its `X-Request-ID`, and the matching CloudWatch log line | 7.6c |
| E8 | Screenshot: the question's Langfuse trace | 7.6c |
| E9 | The retrieval eval's 5 metric lines and its retrieve-time line | 7.6b |
| E10 | Day 2's gross cost by service, net, and tax | 7.6e |
| E11 | Screenshot: the budget page; the alert-email confirmation (and any alert received) | 2 |
| E12 | `destroy`'s last line (`37 destroyed`) and step 9's checks printing nothing | 9 |
| E13 | The day after teardown: gross near US$0 | 9 |

- **Redaction** (before anything is committed): the account ID (in the bucket name, the registry URL and every ARN, AWS's resource names), API keys, the alert email, instance and session IDs, the server's IP address. `DATABASE_URL` is never printed.
- **Stop rules:** no AWS command before "go"; c2's blocker rule; a 400 "credit balance is too low" stops the paid steps at once; D2's 15 s rule is recorded, not acted on (the next sitting decides).
- **Paid calls allowed:** Credit at sitting: US$109 (2026-10-15). Anthropic: at most 3 `POST /query` questions (~US$0.03 each). AWS: ~US$2–2.50 before tax for the window, plus Cost Explorer's API at US$0.01 per request (~5 requests).

#### T7 plan (an interactive task after T6; `/start-task S15-T7`)

- **Done when:**
  1. This slice doc records every T6 number (exit checks) and marks each of E0–E13 taken or missed.
  2. `docs/deployment-evidence.md` holds T6's section: the text captures and ≤ 6 redacted screenshots in one image folder; a search of both for the account ID prints nothing.
  3. The ADR-004 (pgvector and `btree_gist` on RDS), ADR-005 (`max_connections` against 2× the peak, the connect time) and ADR-008 (D2's 15 s rule) outcomes are written, one dated line each in their ADR (c6).
  4. A Proposed addition for each thing T6 triggered: the budget counting credits (P4), a window over 2 hands-on hours (P1), a retrieve p95 over 15 s (D2), any blocker.
  5. `docs/deployment.md` gets fixes only, for anything T6 found wrong.
  6. `docs/architecture.md` and the README get one short deployment section each.
  7. The S15 retro (`/slice-retro`) is the PR's last commit: exit checks, the slice brief (interview points: why windows, cost per day vs. per month, what the request-ID trace proves, why no NAT gateway and no inbound ports), S15 ✅ and S16 🟨.
- **Rules:** no code (`src/`, `tests/`, `infra/`), no AWS command (the stack is gone), nothing paid.
- **Files in scope:** this slice doc; `docs/deployment-evidence.md` and its image folder (new); `docs/deployment.md` (fixes); ADR-004, -005, -008 and `docs/decisions/README.md`; `docs/backlog.md`; `docs/architecture.md`; `README.md`; the slice brief and the glossary (the retro).
- **Proof map:** done-when 1 → each exit check carries its number and its E-capture; 2 → the account-ID search prints nothing; 3 → one dated line in each ADR; 4 → the backlog diff; 7 → `/slice-retro`'s exit-check pass. `make check` green.
- **PR:** one, docs only: no Greptile.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S15-aws-deployment.md`
