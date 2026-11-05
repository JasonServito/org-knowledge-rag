# ADR-014: Deployment topology (one EC2 host, RDS, no inbound ports)

- **Status:** Accepted (S15-R1 design review, 2026-10-15)
- **Date:** 2026-10-15
- **Blueprint/spec refs:** §8.2, §20, §23, §27, §32 gap #6; ADR-004 (the RDS recheck), ADR-005 (the connection trigger), ADR-008 (the instance revisit), ADR-013 (no SQS; the worker needs a supervisor)
- **Evidence:** the S15-R1 design review's cost table and probes

## Context

- The target is ≤ US$50/month always on (blueprint §27). Fixed costs (RDS db.t4g.micro and 20 GB, a 20 GB server disk, 1 public IPv4, ECR, CloudWatch) come to ~US$20; the server gets the rest.
- The reranker (ADR-008) needs ~1.6 GiB of RAM; on 2 laptop CPUs it took 11.5 s p50 and 15.4 s p95 per question (`docs/evaluation.md`). The projected answer p95 on 2 CPUs is 22–24 s, against the spec's 23 s ceiling, which S15 records but doesn't gate on (S15 slice doc).
- The API has no authentication. `POST /query` costs ~US$0.03 in paid calls; `POST /ingestion-jobs` starts a rebuild. S15 has no UI; S17 builds one.
- The database is 431 MB (119 MB as a compressed dump). Re-embedding the corpus would mean 5.69 M estimated tokens, above the 2 M per-run cap.
- The corpus cache (396 MB) is a set of blobless partial clones. With git's https disabled, a no-op ingest needed no network and kept the fingerprint (design review probe). Inside a container whose user doesn't own the cache, `git` refuses it ("dubious ownership"; design review probe).
- There is 1 worker and 1 API process, sharing 1 database (ADR-013).

## Decision

### D1. No inbound ports; the API is reached through a Session Manager tunnel

- The server's security group has no inbound rules. The author reaches the API with AWS Systems Manager Session Manager port forwarding, which needs their AWS login; a shell uses Session Manager too (no SSH keys).
- The API container's port is published on the server's own `127.0.0.1` only.
- Public exposure is decided in S17. The S15 security review designs its controls now (HTTPS, an API key, a per-key spending cap, rate limits on the 2 POST routes), marked Proposed.

### D2. One t3a.medium server, local reranker, CPU credits in standard mode

- t3a.medium (AMD x86, 2 vCPU, 4 GiB): the image tested on the laptop is the one that runs. The type is one Terraform variable.
- CPU credits in **standard** mode: out of credits, the server slows down to its baseline; it never bills extra.
- The first deploy (S15-T6) measures the retrieval eval inside the deployed container. A retrieve p95 above 15 s (a projected answer p95 above 23 s) goes to the next design review, with t4g.medium (ARM) and ADR-008's hosted fallback as the levers.

### D3. An own VPC: the server in a public subnet, the database in private subnets

- 1 public subnet holds the server, with a public IPv4 for outbound calls only (Anthropic, Voyage, Langfuse, ECR, SSM); no NAT gateway.
- 2 private subnets in 2 availability zones hold RDS (its subnet group needs 2 zones even for a single-zone database). Their route table has no route to the internet.
- RDS has no public address; its security group admits port 5432 from the server's security group only.
- Terraform tests pin "no public address", "no internet route from the private subnets" and "no inbound rule on the server".

### D4. One image, two containers; Docker is the supervisor

- One image holds the code, the reranker's weights (downloaded at build at the pinned revision; offline at runtime) and the files the retrieval eval reads. It runs as a non-root user.
- 2 containers from it: the API (uvicorn) and the worker (`python -m orgknow.ingestion.worker`), each with restart policy `unless-stopped`. This is the supervisor ADR-013's 2026-10-14 amendment asks for: a worker that exits on a lost connection is restarted, and resumes its job.
- A deploy script on the server (written by the boot script) fetches the configuration, pulls an image tag from ECR, and (re)starts both containers. S16 calls the same script.
- `git` in the image trusts the mounted cache's directory and may use only local transports (`GIT_ALLOW_PROTOCOL=file`): a missing file fails the ingest instead of fetching from GitHub.

### D5. The cloud database is loaded from a dump; the corpus cache lives in S3

- RDS is loaded once from a `pg_dump` of the laptop's database, through S3. The ingestion fingerprint on RDS must equal the laptop's.
- The corpus cache goes to S3 as one archive; the deploy script unpacks it onto the server, mounted read-only into the worker. A job then runs as on the laptop (a no-op at the current lock).
- Nothing is re-embedded in the cloud.

### D6. Secrets in SSM Parameter Store; Terraform state on the laptop

- Each secret is an encrypted (`SecureString`) SSM parameter named `/orgknow/<ENV_VAR>`. Terraform creates each name; the author sets the API keys' values with the CLI; Terraform writes `DATABASE_URL` from a generated password (letters and digits; `sslmode=require`).
- The deploy script writes them to a root-only env file that `docker run` reads. No secret is in the image, the Terraform code or git.
- The server's IAM role reads `/orgknow/*` (the deploy script fetches by that path), pulls only its ECR repository, reads only its bucket, and writes only its log group. The AWS-managed Session Manager policy it also holds (`AmazonSSMManagedInstanceCore`) can read any parameter by name; this account holds no other parameters of its own (reworded at the PR review, 2026-10-15).
- Terraform state stays on the laptop, gitignored (it holds the database password). Providers are pinned in the committed lock file.

### D7. Cost guardrails

- An AWS budget of US$50/month emails at 80% actual and 100% forecast. 2 CloudWatch alarms (the server's status check, the database's free storage under 2 GB) email through one SNS topic.
- Not used: NAT gateway, load balancer, ECS/Fargate, Secrets Manager, SQS (ADR-013 D1), Route 53/CloudFront (blueprint §23.2).
- Teardown is `terraform destroy`: no final database snapshot (the data reloads from the dump), and the bucket is emptied with it.

## Alternatives considered

| Option | Why not |
|---|---|
| Public HTTP with an API key and an IP allowlist | The key travels in clear text; home IPs change; only the author needs access before S17 |
| HTTPS through a proxy (Caddy, Let's Encrypt) with a key and a spending cap, now | S17's work done before there is a UI; ~3× the work |
| t3.medium (Intel) | ~US$50.40/month in total, over the cap |
| t4g.medium (ARM) | US$3/month cheaper, but the image would be built under emulation and can't be tested on the laptop; kept as a lever |
| Voyage's hosted reranker on a smaller server | Changes every retrieval metric (an ADR-008 change and a paid re-eval); kept as ADR-008's fallback |
| The account's default VPC | One lock instead of two (all its subnets route to the internet); some accounts have deleted it |
| Re-ingest and re-embed in the cloud | 5.69 M tokens, above the 2 M cap, and paid; the dump gives the same fingerprint for free |
| Docker Compose or systemd units on the server | Compose isn't installed on Amazon Linux 2023; Docker's restart policy is enough for 2 containers |
| Terraform state in S3 with locking | One operator; S16 deploys the app, not the infrastructure |
| Secrets Manager | US$0.40/secret/month for rotation features we don't use (blueprint §23.2) |

## Consequences

- Only the author can use the deployment until S17 opens it. A demo needs the AWS CLI, the Session Manager plugin and their login.
- The cost estimate is ~US$47.49/month (S15 run plan), US$2.51 under the cap: one forgotten extra resource can break it, so the budget alarm and the teardown runbook matter.
- **New tools:** Terraform (≥ 1.14) with the `hashicorp/aws` and `hashicorp/random` providers, pinned in `infra/.terraform.lock.hcl`; the Python and uv base images, pinned by digest.
- The first deploy (S15-T6) must close 3 open checks: ADR-004's pgvector 0.8.1 and `btree_gist` on RDS; ADR-005's trigger (RDS `max_connections` against 2× the peak, and the connect time); ADR-008's instance revisit (D2's 15 s rule).
- The app connects as the RDS master user (one database user). The S15 security review rates it.
- **Revisit triggers:** a public UI (S17: D1); D2's 15 s rule; a second worker host (ADR-013 D1: SQS returns); a second operator or CI applying Terraform (remote state).

## Amendment 2026-10-16 (S15-R2 design review): the deployment exists only in windows

Decided in the S15-R2 design review, after a devil's advocate. Context: US$47.49/month is a lot for a system with no inbound ports (D1): nobody else can reach the deployment before S17.

- **Windows, not always on.** The environment is created only when a task needs it: S15-T6 (one full UTC day, for the measured cost), possibly a few hours in S16 to prove its deploy step, and ~7 days in S18. Each window ends with `terraform destroy` and the runbook's step-9 checks; nothing runs between windows.
- **The sizing rule stays.** "≤ US$50/month always on" (Context) is how the design is sized, not how long it runs.
- **A budget per window.** Each window sets `budget_usd` in the local `terraform.tfvars` to fit it (S15-T6: US$5), so a forgotten stack emails within days, not after ~26 days at 80% of US$50 (D7). The code's default stays 50.
- **S16 inherits it.** With no standing server, S16's design review decides how its deploy step works (a backlog Proposed addition).
- **Revisit trigger.** A window that takes over 2 hands-on hours (S15-T6 logs them) or fails in a new way: the next design review reconsiders keeping the stack and stopping the server and database between uses.
- **Rejected:** always on for months (~US$47/month for a system only the author can reach); keeping the stack but stopping it between uses (~US$5/month, but a stopped RDS instance restarts itself after 7 days and bills until noticed); keeping T6's stack up through S16–S17.

## Amendment 2026-11-02 (S18-R1 design review): demo hours on 4 physical cores

Decided in the S18-R1 design review (decision d2), after a devil's advocate. Context: D2's 15 s rule fired in S15-T6 (retrieve p50 57.83 s, p95 78.04 s on t3a.medium; ADR-008's 2026-10-30 amendment). On the laptop pinned to one physical core, 2 torch threads were 1.55× faster than 1, with identical metrics; the server's core was 2.57× slower than the laptop's at 1 thread, so 2 threads project to ~37 s p50 and ~50 s p95 there (the S18-R1 design review's measurement).

- **t3a.medium stays the sized default.** The ≤ US$50/month always-on sizing rule (Context) and D2's type are unchanged; so is the Terraform code.
- **Demo hours on c7a.xlarge.** For the hours a window shows the system (S18's video, an interview's screen share), the window's server is resized in place to c7a.xlarge (AMD, 4 vCPU = 4 physical cores, 8 GiB) by setting `instance_type` in the local `terraform.tfvars` and applying (stop, resize, start; Docker brings both containers back), and resized back afterwards. ~US$0.23 per hour in us-east-1, against ~US$0.04 for t3a.medium.
- **Checks.** Before the window (free): c7a.xlarge is offered in the server's zone (`${var.region}a`), and the account's vCPU limit allows it. First in demo hours: torch's thread count in the API container and the retrieve p95 (`make eval-retrieval` in the container). A retrieve p95 over 15 s: c7a.2xlarge if the vCPU limit allows, else a stated limit.
- **Rejected:** 2 torch threads on t3a.medium (answers ~45–60 s); Voyage's hosted reranker (its scores need the authority weights re-fitted on a fresh golden set: a scoring change in the final slice; future work, ADR-008); c7a.xlarge for a whole ~7-day window (~US$39, 2.6× the US$15 plan); c7a.large (2 cores; forecast retrieve p95 ~14–21 s, at the 15 s line).
- **Revisit trigger:** an always-on deployment (the hosted reranker, once golden set v1 can re-check the authority weights), or demo hours that miss 15 s on c7a.2xlarge.

## Amendment 2026-11-02 (S18-T4 design review): S18's window lasts up to 2 days

Decided at S18-T4's start (decision t3), after a devil's advocate; the S18-R1 design review left the length open (call c9). Context: the 2026-10-16 amendment planned ~7 days in S18 before `make deploy` existed. Window 2 (S16-T6) went from nothing to a running deploy in 1 h 2 min of stack time, and nothing on the runbook's "Not verified" list needs 7 days.

- **Up to 2 days, not ~7.** Create, load, deploy, demo hours and the video on day 1. The stack stays up overnight, on t3a.medium, only for a re-take. `terraform destroy` runs as soon as the developer accepts the video, by a clock-time deadline set on day 1, and at the latest at the end of day 2. ~US$0.70 if it ends the same day, at most ~US$4.
- **Guards** (the devil's advocate's): `budget_usd = 6`, so the 80% email fires at US$4.80, above the plan (AWS's forecast alerts need ~5 weeks of history, which this account doesn't have yet); free checks the day before (a no-cache `make image`, the vCPU limit, the zone's offering); a laptop rehearsal of the demo questions first; back to t3a.medium before any break over 1 hour; the video checked for IDs and IP addresses before `destroy`.
- **Wording:** the README and the resume name the window's real length, not "one week".
- **Rejected:** one day, destroyed the same day (a re-take then needs a new window and a fresh image build, which can hit ECR's CRITICAL gate or break the `libbrotli1` pin); ~7 days (~US$12, 3× this plan's ceiling, for nothing measurable).
- **Revisit trigger:** an interview booked inside the window's dates (keep the stack up for it, on t3a.medium).
