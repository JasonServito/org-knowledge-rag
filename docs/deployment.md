# Deploy and teardown runbook

The exact commands to create the AWS environment of ADR-014, load it, start it, check it, update it and remove it.
Written in S15-T5 from the `Makefile`, the `Dockerfile`, `infra/` and the names table of the S15 run contract (`docs/slices/S15-aws-deployment.md`).

> **Cost: about US$1.56 a day while the environment exists** (US$47.49 a month ÷ 30.4 days; S15 run contract, `docs/security-review.md` 6.1).
> Billing starts with step 2's `apply` and stops only with [step 9's teardown](#9-teardown).
>
> **The environment exists only in windows** (ADR-014's 2026-10-16 amendment): each is created for a task (S15-T6, maybe a few hours in S16, a week in S18) and ends with step 9. Each sets its own budget in step 2.

## Before you start

- **Where each command runs:** every block is labeled.
  - **Laptop:** WSL Ubuntu, in the repo root.
  - **Server:** a shell on the EC2 server, opened with Session Manager (step 5).
- **Shell variables** (`REPO`, `TAG`, `OUT`, `BUCKET`, `INSTANCE_ID`, `DATABASE_URL`, `JOB`) last only in their terminal. Each step sets the ones it uses.
- **One-time order:** steps 1–7 in order. Later deploys: step 8. The end: step 9.
- **Nothing here has run against AWS yet.** Step 5's data path was rehearsed on the laptop (see "Local rehearsal"); the rest is checked against the code only (see "Not verified").

**AWS words used below:**

| Term | In a few words |
|---|---|
| Root user | The account's first login (the sign-up email): can do anything, billing included |
| IAM role | A named set of AWS permissions that a person or a server takes on |
| MFA | Multi-factor authentication: a code from a phone app on top of the password |
| IAM Identity Center | AWS's login service for people; gives short-lived credentials |
| SSO | Single sign-on: the CLI logs in through Identity Center in the browser, so no keys are stored |
| EC2 instance | A virtual server (here: one t3a.medium, "the server") |
| RDS | AWS's managed Postgres (here: one db.t4g.micro, "the database") |
| S3 bucket | File storage (here: the database dump and the corpus archive) |
| ECR | AWS's container image registry (here: the repository `orgknow`) |
| Session Manager | Opens a shell or a port tunnel to the server through your AWS login, with no open port |
| SSM Parameter Store | AWS's settings store; a `SecureString` value is stored encrypted |
| SNS | AWS's notification service (here: alarm emails) |
| CloudWatch | AWS's logs, metrics and alarms |
| Terraform output | A value `terraform apply` prints and stores, read with `terraform -chdir=infra output -raw <name>` |
| CPU credits | A t3a server's budget for running above 20% CPU; in standard mode, out of credits it slows down to 20% |
| Cost Explorer | The billing console's cost and forecast views |

| # | Step | Runs on | Paid |
|---|---|---|---|
| 1 | Account set-up (once) | Console, laptop | No |
| 2 | Create | Laptop | AWS hours start |
| 3 | Secrets | Laptop | — |
| 4 | Image | Laptop | — |
| 5 | Data | Laptop, then server | — |
| 6 | Start | Server | — |
| 7 | Check (7.6 is T6's measurements) | Laptop, server | One ask: ~US$0.03 |
| 8 | Update | Laptop, server | — |
| 9 | Teardown | Laptop | AWS hours stop |

## 1. Account set-up (once)

The account has only the root login today. This step adds MFA to it and an admin user with MFA, and logs the laptop's CLI in through that user (`docs/security-review.md` 2.7, 4.3).

**Console** (as root; region **US East (N. Virginia)**, `us-east-1`, top right). Button names are AWS's docs' names.

1. **MFA on root:** your account name (top right) → **Security credentials** → **Multi-factor authentication (MFA)** → **Assign MFA device** → **Authenticator app**.
2. **Enable Identity Center:** open the IAM Identity Center console → **Enable**. It creates an AWS Organization with this account as its management account (free).
3. **Add your user:** **Users** → **Add user** (your name and email). Accept the invitation email: set a password and register an MFA device.
4. **Admin rights:** **Permission sets** → **Create permission set** → predefined **AdministratorAccess**.
   - Why admin: Terraform creates an IAM role and policy (`infra/compute.tf`); AWS's suggested `PowerUserAccess` can't.
5. **Assign:** **AWS accounts** → this account → **Assign users or groups** → your user, with AdministratorAccess.
6. **Note the AWS access portal URL** (the Identity Center dashboard). It is the "SSO start URL" below.
7. From now on, use root only for account and billing settings.

Source: [root MFA](https://docs.aws.amazon.com/IAM/latest/UserGuide/enable-virt-mfa-for-root.html); [enable Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/get-set-up-for-idc.html); [Identity Center getting started](https://docs.aws.amazon.com/singlesignon/latest/userguide/getting-started.html).

**Laptop:** the AWS CLI v2 (x86_64).

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
```

```bash
unzip awscliv2.zip
```

```bash
sudo ./aws/install
```

```bash
aws --version
```

Source: [install the AWS CLI, "Command line installer - Linux x86 (64-bit)"](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Then delete `awscliv2.zip` and `aws/`.

**Laptop:** the Session Manager plugin (Ubuntu, x86_64).

```bash
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
```

```bash
sudo dpkg -i session-manager-plugin.deb
```

```bash
session-manager-plugin
```

The last command prints that the plugin is installed. Source: [install the plugin on Ubuntu](https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-debian-and-ubuntu.html).

**Laptop:** log the CLI in through Identity Center.

```bash
aws configure sso
```

Answers:

- SSO session name: `orgknow`; SSO start URL: the portal URL from the console step 6; SSO region: `us-east-1`; registration scopes: Enter (the default).
- Sign in in the browser. With 1 account and 1 permission set, the CLI picks both.
- Default client Region: `us-east-1`; output format: `json`; profile name: `orgknow`.
- In WSL, if the browser sign-in doesn't come back to the CLI, run `aws configure sso --use-device-code` and open the printed URL in Windows.

```bash
aws sso login --profile orgknow
```

```bash
export AWS_PROFILE=orgknow
```

```bash
aws sts get-caller-identity
```

- Expected: your account ID and a role ARN with `AdministratorAccess` in it.
- Run `export AWS_PROFILE=orgknow` in **every new laptop terminal**; when a command says the token expired, run `aws sso login` again.

Source: [configure SSO for the CLI](https://docs.aws.amazon.com/cli/latest/userguide/sso-configure-profile-token.html). Terraform's AWS provider reads the same profile from `AWS_PROFILE`.

## 2. Create

**Laptop:** set the 2 variables with no default, the alert email (`alert_email`) and the Langfuse host (`langfuse_base_url`), and this window's budget (`budget_usd`).

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

Edit `infra/terraform.tfvars`: replace `you@example.com` with your email, and check that `langfuse_base_url` equals your `.env`'s `LANGFUSE_BASE_URL` (the example holds the US host). The file is gitignored.

- **Add the window's budget**, e.g. `budget_usd = 5` for S15-T6 (ADR-014's amendment). It emails at 80% of it, so a forgotten stack is noticed within days. The code's default (50) is the always-on size.
- **Console:** Billing and Cost Management → **Credits**: note any credits, their amount and expiry. They can hide the cost (7.6e).

```bash
terraform -chdir=infra init
```

```bash
terraform -chdir=infra plan
```

- Expected last line: `Plan: 37 to add, 0 to change, 0 to destroy.` (counted from `infra/*.tf`: 34 resource blocks, one of them the 4 key parameters).

```bash
terraform -chdir=infra apply
```

- Read the plan again and type `yes`. RDS is the slowest part (not measured).
- Expected: `Apply complete! Resources: 37 added, 0 changed, 0 destroyed.`, then the 4 outputs.
- **If `apply` fails partway** (e.g. a new account's limit, or Postgres 18 missing in the region: the slice's risks), what it created bills: run [step 9](#9-teardown), and take the error to the next sitting.

```bash
terraform -chdir=infra output
```

**Laptop:** does the budget count credits? `true` means it counts the cost after credits, so it stays silent while credits pay.

```bash
aws budgets describe-budget --account-id "$(aws sts get-caller-identity --query Account --output text)" --budget-name orgknow-monthly --query 'Budget.CostTypes.IncludeCredit'
```

**Email:** AWS sends "AWS Notification - Subscription Confirmation" to the alert email.

- Click **Confirm subscription**: without it, the alarms send nothing (`docs/security-review.md` 6.2).
- The budget's emails need no confirmation.

```bash
aws sns list-subscriptions --query "Subscriptions[?ends_with(TopicArn, ':orgknow-alerts')].SubscriptionArn" --output text
```

- Expected: an ARN. `PendingConfirmation` means the link wasn't clicked yet.

**Laptop:** wait until the server is reachable through Session Manager (it registers a few minutes after boot).

```bash
aws ssm describe-instance-information --query 'InstanceInformationList[].[InstanceId,PingStatus]' --output text
```

- Expected: the `instance_id` output, then `Online`.

Source:

- `infra/terraform.tfvars.example`, `infra/variables.tf` (`alert_email`, `langfuse_base_url`); `infra/outputs.tf`.
- `infra/observability.tf` (`aws_sns_topic.alerts`, `aws_sns_topic_subscription.email`); the names table's SNS topic `orgknow-alerts`.
- `infra/compute.tf` (`AmazonSSMManagedInstanceCore`: what lets Session Manager reach the server).
- Terraform state stays in `infra/` on the laptop, gitignored (ADR-014 D6).

## 3. Secrets

Terraform created the 4 API-key parameters with the placeholder `set-me` and never changes their values after (contract c4). Set the real values now, after step 2 (before it, the names don't exist yet).

**Laptop:** each key is read without echo, so it never appears on screen or in shell history. Paste it, then Enter.

```bash
for NAME in ANTHROPIC_API_KEY VOYAGE_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  read -rsp "$NAME: " VALUE; echo
  aws ssm put-parameter --name "/orgknow/$NAME" --type SecureString --overwrite --value "$VALUE"
done; unset VALUE
```

- Expected: 4 small JSON replies, each with `"Version": 2` (version 1 was Terraform's placeholder).

```bash
aws ssm get-parameters-by-path --path /orgknow --with-decryption --query "Parameters[?Value=='set-me'].Name" --output text
```

- Expected: nothing (no placeholder left). It prints names only, never values.
- `/orgknow/DATABASE_URL`, the 5th parameter, was written by Terraform from the generated password. Don't set it.

Source: the names table's SSM parameters; `infra/ssm.tf` (`aws_ssm_parameter.api_key`, `aws_ssm_parameter.database_url`); ADR-014 D6; `docs/security-review.md` 2.2.

## 4. Image

**Laptop:** build and check the one image, then push it to ECR with the git short SHA as its tag. Commit first, so the tag names what is built: `git status --short` should list no ` M` (changed) file.

```bash
git status --short
```

```bash
make image
```

```bash
make image-check
```

- Expected: `image-check: ok (uid 10001, GIT_ALLOW_PROTOCOL=file, safe.directory *)`.

```bash
TAG=$(git rev-parse --short HEAD)
REPO=$(terraform -chdir=infra output -raw ecr_repository_url)
echo "$REPO:$TAG"
```

```bash
docker tag orgknow:dev "$REPO:$TAG"
```

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${REPO%%/*}"
```

- Expected: `Login Succeeded`. `${REPO%%/*}` is the registry (the URL before its first `/`), as in the deploy script.

```bash
docker push "$REPO:$TAG"
```

- The first push uploads the whole image (2.61 GB on disk).

```bash
aws ecr describe-images --repository-name orgknow --query 'imageDetails[].imageTags' --output text
```

- Expected: your tag. **Note it:** step 6 needs it.

Source:

- `Makefile` (`image`, `image-check`); the `ecr_repository_url` output (`infra/outputs.tf`).
- The names table: local image `orgknow:dev`; ECR repository `orgknow`, tags the git short SHA.
- `infra/boot.sh.tftpl` step 3 (the same ECR login).

## 5. Data

RDS is loaded once from a dump of the laptop's database, through S3; nothing is re-embedded (ADR-014 D5). The corpus cache goes to the same bucket as one archive, which the deploy script unpacks in step 6.

**Laptop:** check the source first. The dump must carry the dev fingerprint.

```bash
make up
```

```bash
make ingest-report | grep Fingerprint
```

- Expected: `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`.

**Laptop:** the 2 files, outside the repo.

```bash
OUT=~/orgknow-upload
mkdir -p "$OUT"
```

```bash
docker compose exec -T db pg_dump -Fc -U orgknow -d orgknow > "$OUT/orgknow.dump"
```

- `-Fc`: Postgres's compressed "custom" format, which `pg_restore` reads. `-T`: no terminal, so the binary output isn't changed.
- Rehearsal: 21 s, 118,993,209 bytes.

```bash
tar czf "$OUT/corpus_cache.tar.gz" -C ~/corpus_cache/org-knowledge-rag .
```

- **The `-C … .` form matters:** the archive holds the cache's contents at its top level (`./kubernetes/`, `./website/`, …).
- The deploy script unpacks it directly into `/srv/orgknow/corpus_cache` (mounted as `/corpus_cache`). An archive with a top-level folder would put the repos one level too deep, and the ingest would fail.
- Rehearsal: 14 s, 396,470,796 bytes.

```bash
BUCKET=$(terraform -chdir=infra output -raw bucket_name)
```

```bash
aws s3 cp "$OUT/orgknow.dump" "s3://$BUCKET/orgknow.dump"
```

```bash
aws s3 cp "$OUT/corpus_cache.tar.gz" "s3://$BUCKET/corpus_cache.tar.gz"
```

```bash
aws s3 ls "s3://$BUCKET/"
```

- Expected: the 2 objects with the sizes above.

**Laptop:** keep both files as a dated backup on the Windows side, where a WSL reset can't take them (S15-R2 sitting, P5). The embeddings cost money to recreate, and the GitHub snapshots are pinned by hash. **The backup is never loaded:** every window makes fresh files in this step, so the cloud matches the current local database.

```bash
BACKUP="/mnt/c/Users/<your Windows user>/orgknow-backups/$(date -u +%F)"
```

```bash
mkdir -p "$BACKUP" && mv "$OUT/orgknow.dump" "$OUT/corpus_cache.tar.gz" "$BACKUP/" && rmdir "$OUT"
```

```bash
(cd "$BACKUP" && sha256sum orgknow.dump corpus_cache.tar.gz | tee SHA256SUMS)
```

- Expected: 2 lines, each a 64-character hash and a file name. Keep the dump's line with the evidence.

**Laptop:** open a shell on the server.

```bash
INSTANCE_ID=$(terraform -chdir=infra output -raw instance_id)
```

```bash
aws ssm start-session --target "$INSTANCE_ID"
```

**Server** (the shell starts as `ssm-user`, outside its home):

```bash
cd ~
```

```bash
cloud-init status
```

- Expected: `status: done` (the boot script finished: Docker installed, the deploy script written). On `error`: `sudo tail -50 /var/log/cloud-init-output.log`.

```bash
BUCKET=orgknow-$(aws sts get-caller-identity --query Account --output text)-us-east-1
```

```bash
aws s3 cp --region us-east-1 "s3://$BUCKET/orgknow.dump" orgknow.dump
```

```bash
DATABASE_URL=$(aws ssm get-parameter --region us-east-1 --name /orgknow/DATABASE_URL --with-decryption --query Parameter.Value --output text)
```

- The value holds the host, port 5432 and the password: never `echo` it. (The `rds_endpoint` output is the host alone; `DATABASE_URL` already holds both.)

```bash
time sudo docker run --rm -v "$HOME/orgknow.dump:/orgknow.dump:ro" pgvector/pgvector:0.8.1-pg18 pg_restore --no-owner --no-privileges --single-transaction -d "$DATABASE_URL" /orgknow.dump; echo "exit $?"
```

- The image is `compose.yaml`'s, so `pg_restore` is the same version (18) as the laptop's `pg_dump`.
- `--no-owner --no-privileges`: every object belongs to the user that restores it (`orgknow`); RDS's master user isn't a full superuser.
- `--single-transaction`: all or nothing. A failed restore leaves the database empty, so the same command can run again.
- Expected: no output, `exit 0`. Rehearsal: 40 s on the laptop; on RDS, unmeasured (the slice's risk: the vector index rebuild on 1 GiB). Record the time.
- A `NOTICE` line is information; an `error:` line means it failed.
- If the session drops mid-restore, the container keeps running: `sudo docker ps` shows it until it ends. Don't start a second restore while it runs.

```bash
sudo docker run --rm pgvector/pgvector:0.8.1-pg18 psql "$DATABASE_URL" -c "SELECT extname, extversion FROM pg_extension ORDER BY extname"
```

- Expected (the laptop's values): `btree_gist 1.8`, `plpgsql 1.0`, `vector 0.8.1`. Record RDS's: ADR-004's recheck (T6). Another pgvector version → the next sitting.

```bash
rm orgknow.dump
```

Stay in this shell for step 6.

Source:

- `compose.yaml`: service `db`, user and database `orgknow`, image `pgvector/pgvector:0.8.1-pg18`.
- `Makefile` (`up`, `ingest-report`); the default `CORPUS_CACHE_DIR`, `~/corpus_cache/org-knowledge-rag` (`src/orgknow/settings.py`).
- The `bucket_name` and `instance_id` outputs (`infra/outputs.tf`).
- The names table: bucket `orgknow-<account id>-us-east-1`; objects `orgknow.dump`, `corpus_cache.tar.gz`; `/orgknow/DATABASE_URL`; RDS port 5432.
- `infra/compute.tf`: the server's role may read the bucket's objects and `/orgknow/*`.
- `infra/boot.sh.tftpl` step 2 (the unpack); ADR-014 D5.

## 6. Start

**Server** (same shell). `<tag>` is step 4's tag, e.g. `dbe2093`.

```bash
sudo /usr/local/bin/orgknow-deploy <tag>
```

- **Use the full path.** Amazon Linux's `sudo` likely searches a short `PATH` (`secure_path`) without `/usr/local/bin`, so `sudo orgknow-deploy` could say "command not found" (not verified).
- What it does (`infra/boot.sh.tftpl`):
  1. writes every `/orgknow/*` parameter into `/etc/orgknow/env` (root only, mode 0600);
  2. on the first deploy only: downloads and unpacks `corpus_cache.tar.gz` (396 MB);
  3. logs in to ECR and pulls the tag;
  4. replaces both containers, each with `--restart unless-stopped`: `orgknow-api` on `127.0.0.1:8000` and `orgknow-worker`.
- Expected at the end: `docker ps` with `orgknow-api` and `orgknow-worker`, both `Up`.
- The API loads the reranker before it answers (14.4 s on the laptop). Give it a minute before step 7.

Source: the names table (deploy script `/usr/local/bin/orgknow-deploy <image-tag>`, container names, env file, API port); `infra/boot.sh.tftpl`; ADR-014 D4; contract c1 (the boot script starts nothing).

## 7. Check

### 7.1 Logs

**Laptop, terminal A (new):** step 5's terminal is now the server shell. Both containers log to CloudWatch, group `/orgknow`, streams `api` and `worker`.

```bash
export AWS_PROFILE=orgknow
aws logs tail /orgknow --since 15m
```

- Expected: the API's start-up lines and the worker's `Worker started: polling every 5 s`.

Source: the names table (log group and streams); `infra/boot.sh.tftpl` (`--log-driver awslogs`); `docs/interfaces.md` ("The worker's logs").

### 7.2 The tunnel

**Laptop, terminal A** (7.1's; keep it open; Ctrl-C closes the tunnel).

- It forwards the laptop's port 8001 to the server's `127.0.0.1:8000`, through Session Manager.
- The server has no open port: this tunnel is the only way in (ADR-014 D1, `docs/security-review.md` 4.1).

```bash
INSTANCE_ID=$(terraform -chdir=infra output -raw instance_id)
```

```bash
aws ssm start-session --target "$INSTANCE_ID" --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["8000"],"localPortNumber":["8001"]}'
```

- Expected: `Port 8001 opened for sessionId …` and `Waiting for connections...`.
- Port 8001, not 8000, so a `make serve` on the laptop can never answer in the server's place.

Source: [port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html#sessions-start-port-forwarding); the names table's API port.

### 7.3 Health and readiness

**Laptop, terminal B.** Set its variables first (7.6 uses them):

```bash
export AWS_PROFILE=orgknow
INSTANCE_ID=$(terraform -chdir=infra output -raw instance_id)
```

```bash
curl -s localhost:8001/health
```

- Expected: `{"status":"ok"}`.

```bash
curl -s -w ' %{http_code}\n' localhost:8001/ready
```

- Expected: `{"status":"ready"} 200` (the API reached RDS). `{"status":"unavailable"} 503`: check `DATABASE_URL` and step 5.

Source: `docs/interfaces.md` (`GET /health`, `GET /ready`).

### 7.4 The fingerprint on RDS

**Server** (the step 5 shell, or a new `aws ssm start-session --target "$INSTANCE_ID"` from a new laptop terminal after 7.3's 2 lines; in a new shell, set `DATABASE_URL` again with step 5's command, for 7.6d):

```bash
sudo docker exec orgknow-api python -m orgknow.ingestion.report | grep Fingerprint
```

- Expected: `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`, the laptop's (the slice's exit check).

Source: `Makefile` (`ingest-report` runs `python -m orgknow.ingestion.report`); the container's env file holds `DATABASE_URL`.

### 7.5 A worker job (free)

This runs the worker once on AWS: it reads the unpacked corpus, so it also checks step 5's archive. At the current lock the job is a no-op (0 new texts, 0 Voyage requests; `docs/interfaces.md`).

**Laptop, terminal B:**

```bash
curl -s -X POST localhost:8001/ingestion-jobs | python3 -c "import json, sys; j = json.load(sys.stdin); print('job', j['id'], j['status'])"
```

```bash
JOB=<the job id>
```

```bash
curl -s localhost:8001/ingestion-jobs/$JOB | python3 -c "import json, sys; j = json.load(sys.stdin); print(j['status'], [s['name'] + ' ' + s['status'] for s in j['steps']]); print(j['steps'][0]['counts']); print(j['steps'][2]['counts'])"
```

- Run it again until the status is `succeeded` (~45 s on the laptop; longer on 2 CPUs).
- Expected: ingest `new_versions` 0, `new_chunks` 0, `fingerprint` the value above; embed `requests` 0.
- `failed`: its `error` line, and `aws logs tail /orgknow --log-stream-names worker --since 15m`.

Source: `docs/interfaces.md` (`POST /ingestion-jobs`, `GET /ingestion-jobs/{job_id}`, "Worker"); ADR-013.

### 7.6 T6's measurements

These are S15-T6's: each number goes in the slice doc. Paid: 7.6c's ask (~US$0.03), and US$0.01 per Cost Explorer CLI request (7.6e).

**a. CPU credits first (laptop, terminal B).**

- A t3a server starts with 0 credits (AWS docs: T3a gets no launch credits) and earns 24 an hour.
- At 0, it runs at 20% per CPU, about 5× slower: that would wrongly trip ADR-014 D2's 15 s rule.

```bash
aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUCreditBalance \
  --dimensions Name=InstanceId,Value="$INSTANCE_ID" --statistics Minimum --period 300 \
  --start-time "$(date -u -d '-30 minutes' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --query 'sort_by(Datapoints, &Timestamp)[-1].Minimum'
```

- Start 7.6b at **30 or more**. The eval needs about 14 credits (36 questions × ~11.5 s × 2 CPUs ÷ 60; 1 credit = 1 CPU for 1 minute). Below 30: wait and check again.
- Record the balance before and after 7.6b.

Source: [standard mode concepts](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode-concepts.html), [the credit table](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html); ADR-014 D2 (standard mode); ADR-014 Context (11.5 s p50 on 2 laptop CPUs).

**b. The retrieval eval in the deployed container (server).** Free: stored vectors and routes, no API call.

```bash
sudo docker exec orgknow-api python -m orgknow.eval retrieval
```

- Expected first 5 metric lines: PR #51's (the slice's "Proof map"), e.g. `Recall@10 0.522  Hit@10 0.972  MRR 0.781  nDCG@10 0.508`.
- **The number to record:** `Retrieve time: p50 … s, p95 … s`. A p95 above **15 s** goes to the next sitting (ADR-014 D2). Laptop rehearsal: p95 6.63 s.
- Time: about 7 minutes on 2 CPUs (36 questions × 11.5 s).
- Memory: the eval loads a second reranker inside the API container. Laptop rehearsal: 1,618 MiB at peak for both, of the server's 4 GiB.

Source: `Makefile` (`eval-retrieval` runs `python -m orgknow.eval retrieval`); contract m15 (the eval's files are in the image); ADR-014 D2.

**c. One live ask (laptop, terminal B). Paid: ~US$0.03** (Anthropic answer and router, Voyage). Check the Anthropic credit first (`CLAUDE.md`, "Anthropic credit").

```bash
curl -s -D /tmp/ask.headers -o /tmp/ask.json -w '%{http_code} in %{time_total} s\n' -X POST localhost:8001/query -H 'Content-Type: application/json' -d '{"question": "What enforces pod security standards in-tree?"}'
```

```bash
python3 -c "import json; a = json.load(open('/tmp/ask.json')); print(a['answer_status'], len(a['evidence']), 'citations, trace_id', a['trace_id'])"
```

- Expected: `200 in … s`, then `answered`, at least 1 citation, and a `trace_id`. Record the time (the spec's ceiling: 23 s p95).

**The request ID, traced into AWS's own logs** (the proof it ran on AWS). The response's `X-Request-ID` header names it (`docs/interfaces.md`, "Request IDs"):

```bash
RID=$(grep -i '^x-request-id:' /tmp/ask.headers | awk '{print $2}' | tr -d '\r'); echo "$RID"
```

```bash
aws logs filter-log-events --log-group-name /orgknow --log-stream-names api --filter-pattern "\"$RID\"" --query 'events[].message' --output text
```

- Expected: the API's JSON log line for `POST /query 200` with `"request_id"` equal to `$RID`. A line can take a few seconds to arrive: run it again if it prints nothing.
- **The trace:** open it in Langfuse (search the `trace_id`). A `trace_id` in the reply alone doesn't prove the trace arrived: the ID is made on the server before the trace is sent (inferred from `pipeline.py`).
- The server's traces go to the host `langfuse_base_url` set in step 2 (the parameter `/orgknow/LANGFUSE_BASE_URL`).

Source: `docs/interfaces.md` (`POST /query`: the request body is its example); ADR-006 (tracing).

**d. Connections (ADR-005's trigger).** Add a connection pool if RDS's `max_connections` is under 2× the peak, or if the connect time is over 5% of a median ask.

**Server:** the limit.

```bash
sudo docker run --rm pgvector/pgvector:0.8.1-pg18 psql "$DATABASE_URL" -Atc "SHOW max_connections"
```

**Server:** open connections now. Run it while 7.5's job runs and right after an ask; the count includes this `psql` (subtract 1).

```bash
sudo docker run --rm pgvector/pgvector:0.8.1-pg18 psql "$DATABASE_URL" -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname = 'orgknow'"
```

**Laptop, terminal B:** the peak over the last 3 hours, from RDS's 1-minute metric.

```bash
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=orgknow --statistics Maximum --period 60 \
  --start-time "$(date -u -d '-3 hours' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --query 'max(Datapoints[].Maximum)'
```

**Server:** the connect time from the API container to RDS (rehearsal on the laptop: 9 ms). Compare it with 5% of 7.6c's ask time.

```bash
sudo docker exec orgknow-api python -c "import os, time, psycopg; t = time.perf_counter(); psycopg.connect(os.environ['DATABASE_URL']).close(); print(f'connect {(time.perf_counter() - t) * 1000:.0f} ms')"
```

Source: ADR-005 ("Revisit trigger (S15)"); the names table (RDS identifier `orgknow`); `infra/observability.tf` (the `AWS/RDS` namespace and `DBInstanceIdentifier` dimension of the storage alarm).

**e. The cost forecast (≤ US$50 a month).**

- **Console:** Billing and Cost Management → **Cost Explorer**. The first visit asks to **Launch Cost Explorer**; this month's data appears after about 24 hours. Set the date range to the month's end to see the forecast.
- **Console:** Billing and Cost Management → **Budgets** → `orgknow-monthly` shows its forecast too.
- **CLI** (laptop, terminal B; each Cost Explorer request costs US$0.01):

```bash
aws ce get-cost-forecast --metric UNBLENDED_COST --granularity MONTHLY --time-period Start=$(date -u +%F),End=$(date -u -d "$(date -u +%Y-%m-01) +1 month" +%F)
```

- **None of these is a monthly figure:** the console's and Budgets' forecasts cover this calendar month, which the environment only partly fills; the CLI's covers only the days left in it.
- The figure to compare with US$50 is a per-day cost × 30.4: the CLI's total ÷ the days left × 30.4, or the daily cost below × 30.4.

- **No forecast?** AWS often gives none to an account with under 1 full billing cycle (this one started 2026-10-14).
- Then use 1 full day's cost × 30.4 (accepted for T6's cost check at the PR review, 2026-10-15).

**The full day's cost: gross, net and tax** (S15-R2 sitting, P4). Read it at least a day after that UTC day ends, even after teardown: a finished day's cost stays readable.

- **Gross** (credits and tax left out): what the design costs. **This is the number × 30.4 that is compared with US$50.**
- **Net:** what you pay after credits. **Tax:** GST/HST, kept apart, as the cost table has no tax either.

```bash
DAY=YYYY-MM-DD
```

- Set it to the whole UTC day the stack ran (S15-T6: day 2).

```bash
aws ce get-cost-and-usage --time-period Start=$DAY,End=$(date -u -d "$DAY +1 day" +%F) --granularity DAILY --metrics UnblendedCost --filter '{"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Tax"]}}}' --group-by Type=DIMENSION,Key=SERVICE --query 'ResultsByTime[0].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]' --output text
```

- Gross, by service: add the lines up for the day's gross cost.

```bash
aws ce get-cost-and-usage --time-period Start=$DAY,End=$(date -u -d "$DAY +1 day" +%F) --granularity DAILY --metrics UnblendedCost --query 'ResultsByTime[0].Total.UnblendedCost.Amount' --output text
```

- Net: every charge, credits included.

```bash
aws ce get-cost-and-usage --time-period Start=$DAY,End=$(date -u -d "$DAY +1 day" +%F) --granularity DAILY --metrics UnblendedCost --filter '{"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Tax"]}}' --query 'ResultsByTime[0].Total.UnblendedCost.Amount' --output text
```

- Tax alone (it may appear only once the month is billed).

Source: [enable Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-enable.html), [forecasts](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-forecast.html), [pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/); the names table (budget `orgknow-monthly`); ADR-014 D7.

## 8. Update

A new version of the code, on the same server and database.

**Laptop** (any terminal, after `export AWS_PROFILE=orgknow`): step 4 again, from the new commit: `make image`, `make image-check`, a new `TAG`, tag, ECR login, push.

**Server:**

```bash
sudo /usr/local/bin/orgknow-deploy <new tag>
```

- It re-reads the parameters, pulls the tag and replaces both containers; the corpus is already unpacked.
- Then 7.2–7.3 (the tunnel, `/health`, `/ready`).
- **A release with a new database migration** isn't covered here: its migration must run before the new containers start, and S16 (CI/CD) designs that step. Until then, don't deploy one.
- **Roll back:** run the deploy script with the previous tag. ECR keeps the last 3 images (m13).
- **A change to the boot script** (`infra/boot.sh.tftpl`, which writes the deploy script): it runs only at the first boot, so the change reaches the server only with a new server. A plain `apply` would only stop and restart the old server ([the provider's docs, `user_data`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance#user_data); not verified).

**Laptop** (a terminal with `AWS_PROFILE` set):

```bash
terraform -chdir=infra apply -replace=aws_instance.server
```

- Then: wait for `Online` (step 2's last check), and run step 6 again. The deploy script downloads and unpacks the corpus again on its own, as on the first deploy. The database is untouched.
- The `instance_id` output changes: re-read it before 7.2.

Source:

- `infra/boot.sh.tftpl`; `infra/compute.tf` (`lifecycle { ignore_changes = [ami] }` and its comment on `-replace`).
- `infra/storage.tf` (`aws_ecr_lifecycle_policy.app`).

## 9. Teardown

**Laptop** (any terminal, after `export AWS_PROFILE=orgknow`): one command removes everything Terraform made: the bucket with its objects (`force_destroy`), the repository with its images (`force_delete`, c5), and the database with no final snapshot (m11).

```bash
terraform -chdir=infra destroy
```

- Read the plan (`37 to destroy`) and type `yes`.
- Expected: `Destroy complete! Resources: 37 destroyed.`

**Laptop** (the same terminal): check that nothing billable is left. Each command should print nothing, unless noted.

```bash
terraform -chdir=infra state list
```

```bash
aws ec2 describe-instances --filters Name=tag:Project,Values=orgknow --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text
```

- Expected: nothing, or only `terminated` lines (AWS lists a terminated server for a while; it doesn't bill).

```bash
aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier' --output text
```

```bash
aws rds describe-db-snapshots --query 'DBSnapshots[].DBSnapshotIdentifier' --output text
```

```bash
aws s3 ls
```

- Expected: no `orgknow-…` bucket.

```bash
aws ec2 describe-addresses --query 'Addresses[].PublicIp' --output text
```

- No unattached address: the server's public IPv4 went with it.

```bash
aws ec2 describe-volumes --query 'Volumes[].[VolumeId,State]' --output text
```

```bash
aws ecr describe-repositories --query 'repositories[].repositoryName' --output text
```

**The next day's cost:** Cost Explorer → daily view, grouped by **Service**: the first whole day after the teardown should be about US$0.

Or by CLI (US$0.01). It reads yesterday's cost: run it 2 days after the teardown day.

```bash
aws ce get-cost-and-usage --time-period Start=$(date -u -d yesterday +%F),End=$(date -u +%F) --granularity DAILY --metrics UnblendedCost --query 'ResultsByTime[0].Total.UnblendedCost.Amount' --output text
```

- What stays, free: the Identity Center user, the root MFA and the laptop's `infra/terraform.tfstate` (gitignored).

Source: ADR-014 D7; contract c5, m11, m13; `infra/storage.tf`, `infra/database.tf`; `infra/versions.tf` (every resource has the tag `Project = orgknow`); `docs/security-review.md` 6.1, 6.6.

## Local rehearsal (S15-T5, 2026-10-15)

Step 5's data path, on the laptop's Postgres, with no AWS. Only the target differed: a scratch database `orgknow_restore_check`, reached on the compose network (`--network orgknow_default`), and no `sudo`.

- **Dump:** step 5's `pg_dump` command → 118,993,209 bytes in 21 s.
- **Restore:** step 5's `pg_restore` command and flags → exit 0, no output, 40 s.
- **Fingerprint:** the restored database's equals the dev database's (`sha256:0f0ee078…4165`), and the whole `ingest-report` output is identical (33 lines).
- **Extensions:** `btree_gist 1.8`, `plpgsql 1.0`, `vector 0.8.1`, as on the dev database.
- **Archive:** step 5's `tar` command → 396,470,796 bytes; top-level entries `./community/`, `./enhancements/`, `./gh/`, `./github/`, `./kubernetes/`, `./sig-release/`, `./website/`. Unpacked the way the deploy script does, the repos land directly under `corpus_cache/`.
- **In the image** (`orgknow:dev`, on the restored database): 7.4's report printed the same fingerprint; 7.6b's eval printed PR #51's metric lines (retrieve p95 6.63 s, peak memory 1,618 MiB with the API); 7.6d's connect: 9 ms; `alembic current`: `0009 (head)`.
- The scratch database and every file were removed after.

## Not verified

Nothing here has run against AWS. In particular:

- Every AWS command and console step (no account access when this was written); the console's button names may differ from AWS's docs.
- `--no-owner --no-privileges --single-transaction` on RDS: the rehearsal ran as a local superuser; RDS's master user is not one. The dump creates the `vector` and `btree_gist` extensions, which RDS allows its master user to create (not checked).
- The RDS restore time, and the pgvector version RDS installs.
- That `sudo` on Amazon Linux 2023 lacks `/usr/local/bin` (step 6), that Session Manager's shell starts outside `ssm-user`'s home (step 5), and that the AWS CLI is preinstalled on the server (the deploy script relies on it).
- That a plain `apply` after a boot-script change only stops and starts the server (step 8).
- That Budgets and Cost Explorer show a forecast for this new account (7.6e).
- The Cost Explorer record types `Credit` and `Tax` (7.6e's filters), and the budget's `CostTypes.IncludeCredit` field (step 2).
