# Deploy and teardown runbook

The exact commands to create the AWS environment of ADR-014, load it, start it, check it, update it and remove it.
Written in S15-T5 from the `Makefile`, the `Dockerfile`, `infra/` and the names table of the S15 run plan.

S16-T5 moved steps 2, 4, 6 and 8 to `make audit` and `make deploy` (ADR-015); the manual commands stay as the fallback.

> **Cost: about US$1.56 a day while the environment exists** (US$47.49 a month ÷ 30.4 days; S15 run plan, `docs/security-review.md` 6.1).
> Billing starts with step 2's `apply` and stops only with [step 9's teardown](#9-teardown).
>
> **The environment exists only in windows** (ADR-014's 2026-10-16 amendment): each is created for a task (S15-T6, maybe a few hours in S16, up to 2 days in S18: the 2026-11-02 amendment) and ends with step 9. Each sets its own budget in step 2.

## Before you start

- **Where each command runs:** every block is labeled.
  - **Laptop:** WSL Ubuntu, in the repo root.
  - **Server:** a shell on the EC2 server, opened with Session Manager (step 5).
- **Shell variables** (`REPO`, `TAG`, `OUT`, `BUCKET`, `INSTANCE_ID`, `DATABASE_URL`, `JOB`) last only in their terminal. Each step sets the ones it uses.
- **One-time order:** steps 1–7 in order. **The data (step 5) comes before `make deploy` (step 6):** step 6 says why. Later deploys: step 8. Showing the system: [demo hours](#demo-hours-4-cores-s18). The end: step 9.
- **Run against AWS twice:** S15-T6 (2026-10-27/28, steps 1–7 and 9) and S16-T6 (2026-11-01, steps 2, 3, 5, 6, 8 and 9 with `make deploy`). Their outputs are in [`deployment-evidence.md`](deployment-evidence.md); what is still unchecked is under "Not verified".
- **Tip:** step 4's `make image` and step 5's dump and archive need no AWS. Doing them before step 2's `apply` shortens the paid window.
  - With the build cached, `make deploy`'s audit, build and image check took 9.5 s (S16-T4).

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
| 4 | Image (pushed by step 6's `make deploy`) | Laptop | — |
| 5 | Data | Laptop, then server | — |
| 6 | Start: `make deploy` | Laptop (fallback: server) | — |
| 7 | Check (7.6 is T6's measurements) | Laptop, server | One ask: ~US$0.03 |
| 8 | Update: `make deploy` | Laptop (roll back: server) | — |
| — | Demo hours: 4 cores, then back | Laptop, server | ~US$0.23 an hour, not ~US$0.04 |
| 9 | Teardown | Laptop | AWS hours stop |

## 1. Account set-up (once)

The account has only the root login today. This step adds MFA to it and an admin user with MFA, and logs the laptop's CLI in through that user (`docs/security-review.md` 2.7, 4.3).

**Console** (as root; region **US East (N. Virginia)**, `us-east-1`, top right). Button names are AWS's docs' names.

1. **MFA on root:** your account name (top right) → **Security credentials** → **Multi-factor authentication (MFA)** → **Assign MFA device** → **Authenticator app**.
2. **Enable Identity Center:** first check the region (top right) says **N. Virginia**: the instance's region can't be changed later. Open the IAM Identity Center console → **Enable**. It creates an AWS Organization with this account as its management account (free).
   - Choose **Single-Region instance**. The default, Multi-Region, creates a customer-managed KMS key (about US$1/month) that Terraform doesn't manage, so it outlives every teardown. Its settings should show an AWS owned key.
3. **Add your user:** **Users** → **Add user** (your name and email). Accept the invitation email: set a password and register an MFA device.
4. **Admin rights:** **Permission sets** → **Create permission set** → predefined **AdministratorAccess**.
   - Why admin: Terraform creates an IAM role and policy (`infra/compute.tf`); AWS's suggested `PowerUserAccess` can't.
5. **Assign:** **AWS accounts** → this account → **Assign users or groups** → your user, with AdministratorAccess.
6. **Note the AWS access portal URL** (the Identity Center dashboard). It is the "SSO start URL" below. Of the endpoints listed, use the **IPv4-only** one (`https://d-….awsapps.com/start`).
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
- **Every MFA code rejected:** check the phone's clock. The codes are made from the time, so a phone set by hand fails them all. Turn on its network-provided time and time zone (S16-T6: a phone set an hour back, to match Windows, after Alberta stayed on UTC−6 on 2026-11-01).

Source: [configure SSO for the CLI](https://docs.aws.amazon.com/cli/latest/userguide/sso-configure-profile-token.html). Terraform's AWS provider reads the same profile from `AWS_PROFILE`.

## 2. Create

**Laptop:** first, audit the locked Python packages for known vulnerabilities (ADR-015 D4). Free (~7 s), no AWS: a new advisory is fixed in a PR before the window, not during it.

```bash
make audit
```

- Expected: `No known vulnerabilities found`, then a `Skip Reason` table with 1 row: `torch Dependency not found on PyPI and could not be audited: torch (2.14.1+cpu)`.
  - `torch` comes from PyTorch's CPU index, so it isn't audited; that is not a failure.
  - 2 `WARNING:pip_audit._cli:` lines about `--no-deps` come first; they are expected.
- **Red** (`Found … known vulnerabilities …`): don't run `apply`. `make deploy` runs the same audit first and stops on it. Fix it in a PR, then pull `main`:
  - a fixed version exists: bump the package, `uv lock --upgrade-package <name>`;
  - no fix: accept it with `--ignore-vuln <ID>` and a one-line reason on the `Makefile`'s `audit` line.

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
- **If `apply` fails partway** (e.g. a new account's limit, or Postgres 18 missing in the region: the slice's risks), what it created bills: run [step 9](#9-teardown), and take the error to the next design review.

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

- `Makefile` (`audit`); ADR-015 D4; S16 c7 (an advisory with no fix), c9 (the bump).
- `infra/terraform.tfvars.example`, `infra/variables.tf` (`alert_email`, `langfuse_base_url`); `infra/outputs.tf`.
- `infra/observability.tf` (`aws_sns_topic.alerts`, `aws_sns_topic_subscription.email`); the names table's SNS topic `orgknow-alerts`.
- `infra/compute.tf` (`AmazonSSMManagedInstanceCore`: what lets Session Manager reach the server).
- Terraform state stays in `infra/` on the laptop, gitignored (ADR-014 D6).

## 3. Secrets

Terraform created the 4 API-key parameters with the placeholder `set-me` and never changes their values after (plan c4). Set the real values now, after step 2 (before it, the names don't exist yet).

**Laptop** (in the repo root): each key is copied from `.env`, so nothing is pasted or printed. A hidden paste went wrong twice in S15-T6 (4 empty values, then one key pasted twice); reading the file can't. The cloud gets the laptop's keys.

```bash
for NAME in ANTHROPIC_API_KEY VOYAGE_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  VALUE=$(grep -E "^$NAME=" .env | cut -d= -f2- | sed -E 's/^"(.*)"$/\1/')
  aws ssm put-parameter --name "/orgknow/$NAME" --type SecureString --overwrite --value "$VALUE" --query Version --output text
done; unset VALUE
```

- Expected: 4 lines, each `2` (version 1 was Terraform's placeholder; re-running the loop in the same window prints `3`). An empty value fails with a `ValidationException` that names no key.
- The `sed` drops double quotes around a value, if `.env` has them (a quoted Langfuse key, for example).

**Laptop:** check each stored key against `.env`. It prints lengths and yes/no, never a value.

```bash
for NAME in ANTHROPIC_API_KEY VOYAGE_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  S=$(aws ssm get-parameter --name "/orgknow/$NAME" --with-decryption --query Parameter.Value --output text)
  E=$(grep -E "^$NAME=" .env | cut -d= -f2- | sed -E 's/^"(.*)"$/\1/')
  echo "$NAME: length ${#S}, equal to .env: $([ "$S" = "$E" ] && echo yes || echo NO)"
done; unset S E
```

- Expected: 4 lines ending `equal to .env: yes`, none with length 0.

```bash
aws ssm get-parameters-by-path --path /orgknow --with-decryption --query "Parameters[?Value=='set-me'].Name" --output text
```

- Expected: nothing (no placeholder left). It prints names only, never values.
- `/orgknow/DATABASE_URL`, the 5th parameter, was written by Terraform from the generated password. Don't set it.

Source: the names table's SSM parameters; `infra/ssm.tf` (`aws_ssm_parameter.api_key`, `aws_ssm_parameter.database_url`); ADR-014 D6; `docs/security-review.md` 2.2.

## 4. Image

**`make deploy` (step 6) builds, checks and pushes the image**, tagged with the commit's short SHA. The manual commands below are the fallback.

- **Don't run `make deploy` yet:** it also migrates the database, so it runs in step 6, after step 5's data (step 6 says why).
- No AWS needed: `make image` now (or before step 2) fills the build cache that `make deploy` reuses.

**Fallback (manual).**

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

- Expected: `Login Succeeded`. `${REPO%%/*}` is the registry (the URL before its first `/`), as in `scripts/deploy.sh`.

```bash
docker push "$REPO:$TAG"
```

- The first push uploads the whole image (2.61 GB on disk).

```bash
aws ecr describe-images --repository-name orgknow --query 'imageDetails[].imageTags' --output text
```

- Expected: your tag. **Note it:** step 6's fallback needs it.
- The fallback has no ECR scan gate (`make deploy` stops on a CRITICAL finding): use it only when `make deploy` can't run.

Source:

- `Makefile` (`deploy`, `image`, `image-check`); the `ecr_repository_url` output (`infra/outputs.tf`).
- The names table: local image `orgknow:dev`; ECR repository `orgknow`, tags the git short SHA.
- `scripts/deploy.sh` steps 1 and 4 (its clean-tree check; the same tag, login and push); ADR-015 D2.

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

**Laptop:** keep both files as a dated backup on the Windows side, where a WSL reset can't take them (S15-R2 design review, P5). The embeddings cost money to recreate, and the GitHub snapshots are pinned by hash. **The backup is never loaded:** every window makes fresh files in this step, so the cloud matches the current local database.

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
sudo docker pull -q pgvector/pgvector:0.8.1-pg18
```

- Pulled first, so the timed restore below measures only the restore.

```bash
time sudo docker run --rm -v "$HOME/orgknow.dump:/orgknow.dump:ro" pgvector/pgvector:0.8.1-pg18 pg_restore --no-owner --no-privileges --single-transaction -d "$DATABASE_URL" /orgknow.dump; echo "exit $?"
```

- The image is `compose.yaml`'s, so `pg_restore` is the same version (18) as the laptop's `pg_dump`.
- `--no-owner --no-privileges`: every object belongs to the user that restores it (`orgknow`); RDS's master user isn't a full superuser.
- `--single-transaction`: all or nothing. A failed restore leaves the database empty, so the same command can run again.
- Expected: no output, `exit 0`. Rehearsal: 40 s on the laptop; on RDS, 1 min 30 s (S15-T6). Record the time.
- A `NOTICE` line is information; an `error:` line means it failed.
- If the session drops mid-restore, the container keeps running: `sudo docker ps` shows it until it ends. Don't start a second restore while it runs.

```bash
sudo docker run --rm pgvector/pgvector:0.8.1-pg18 psql "$DATABASE_URL" -c "SELECT extname, extversion FROM pg_extension ORDER BY extname"
```

- Expected (the laptop's values): `btree_gist 1.8`, `plpgsql 1.0`, `vector 0.8.1`. Record RDS's: ADR-004's recheck (T6). Another pgvector version → the next design review.

```bash
rm orgknow.dump
```

Keep this shell open: step 6's fallback, 7.4 and 7.6 use it.

Source:

- `compose.yaml`: service `db`, user and database `orgknow`, image `pgvector/pgvector:0.8.1-pg18`.
- `Makefile` (`up`, `ingest-report`); the default `CORPUS_CACHE_DIR`, `~/corpus_cache/org-knowledge-rag` (`src/orgknow/settings.py`).
- The `bucket_name` and `instance_id` outputs (`infra/outputs.tf`).
- The names table: bucket `orgknow-<account id>-us-east-1`; objects `orgknow.dump`, `corpus_cache.tar.gz`; `/orgknow/DATABASE_URL`; RDS port 5432.
- `infra/compute.tf`: the server's role may read the bucket's objects and `/orgknow/*`.
- `infra/boot.sh.tftpl` step 2 (the unpack); ADR-014 D5.

## 6. Start

One laptop command does step 4's push, this step's start and the free checks of 7.3–7.4 (ADR-015 D2).

**Step 5 first.** `make deploy` migrates the database before it starts the app.

- Before step 5, the database is empty: the migration would create every table, and step 5's restore (`--single-transaction`) would then fail, as the tables would already exist.
- After step 5, the restored database is at the laptop's newest migration (`0009` today), so the migration has nothing to do.

**Laptop, terminal A (new):** step 5's terminal is now the server shell. `make deploy` needs:

- the AWS login: the `export` below and a live `aws sso login` (step 1);
- Docker running; the window's stack, read from Terraform's outputs in `infra/terraform.tfstate` (step 2);
- the boot script finished on the server, as step 5's `cloud-init status` showed: it writes `orgknow-deploy`;
- every change committed: it refuses changed tracked files.
- **Commit new files too:** untracked files don't stop it, but one under `src/` or `config/` would still be built into the image, under a tag that doesn't contain it.

```bash
export AWS_PROFILE=orgknow
```

```bash
make deploy
```

Expected, in order (`scripts/deploy.sh`):

1. `deploy: audit`, then step 2's audit output.
2. `deploy: image <tag>` (the commit's short SHA), the build, then `image-check: ok (uid 10001, GIT_ALLOW_PROTOCOL=file, safe.directory *)`.
3. `Login Succeeded`, the push, then `deploy: pushed <repo>:<tag>`. The first push uploads the whole image (2.61 GB on disk).
4. `deploy: ECR scan: ` and the scan's counts by severity, as JSON. HIGH and lower are printed only.
5. `deploy: server: command <id> sent; polling every 10 s, up to 20 min`, then, when the server is done, `deploy: server: Success`.
6. The server's output, ending with `docker ps` (`orgknow-api` and `orgknow-worker`, both `Up`), `/ready: 200` and `Fingerprint: sha256:…`.
7. Then the server's stderr: alembic's `INFO` lines. On a window's first deploy there is no `Running upgrade` line.
8. `deploy: done: <repo>:<tag>. Compare the fingerprint with the laptop's (make ingest-report).`

**If it stops**, nothing after that point ran. A fix mid-window is a commit and a rerun (ADR-015).

| It stops with | Meaning | Then |
|---|---|---|
| The changed files, then `deploy: uncommitted changes to tracked files: commit them first, so the tag names what is built` | A tracked file is changed | Commit, then rerun |
| pip-audit's `Found … known vulnerabilities …` | A new advisory | Step 2's fix, in a PR |
| An `image-check:` line other than `ok` | The image breaks 1 of its 4 rules | Fix it in a PR |
| `deploy: no ecr_repository_url or instance_id in Terraform's outputs: is a window open?` | No stack in `infra/terraform.tfstate` | Step 2 |
| An AWS CLI error, alone or after `deploy: ` (e.g. an expired login) | The laptop's AWS login | `aws sso login` (step 1), then rerun |
| `deploy: ECR's scan of <tag> did not complete` | ECR's scan failed or is still running (the script first waits up to 60 s for the scan to exist, then for it to finish: S16-T6), or an AWS error above it | Rerun; if it repeats, read the tag's scan status in the ECR console (repository `orgknow`) |
| Each finding's name and link, then `deploy: ECR found N CRITICAL findings in <repo>:<tag>: not deploying` | A critical finding in the image's OS packages | Nothing was deployed. If Debian has a fix (`docker run --rm --user root orgknow:dev sh -c 'apt-get update -qq && apt-cache policy <package>'` shows a newer `Candidate`), upgrade that package in the `Dockerfile`'s late layer, pinned, as S16-T6 did for `libbrotli1`; or use a newer base-image digest. Commit, then rerun. No fix: take it to the next design review |
| The server's output, then `deploy: the server's deploy ended with Failed` (or `TimedOut`, `Cancelled`) | A server step failed: its output shows which | A failed migration: step 8. `/ready: ` not `200`: 7.1's logs |
| `deploy: the server's deploy is still InProgress after 20 min (command <id>)` | The laptop stopped waiting; the server may still be working | Server: `sudo docker ps`, then 7.3–7.4 |

**Laptop** (terminal A): compare the server's fingerprint with the laptop's database (it needs `make up`, as in step 5).

```bash
make ingest-report | grep Fingerprint
```

- Expected: the server's line exactly: `Fingerprint: sha256:0f0ee07847e8b05fcde7f1491c628618cfb42a555ec5b098f1c2effd52ee4165`.
- Different: stop, and compare the full reports (7.4's command without `| grep Fingerprint`, and `make ingest-report`).

**What it runs on the server**, as root, through SSM Run Command (`scripts/deploy.sh` step 6):

1. `orgknow-deploy <tag>` (`infra/boot.sh.tftpl`):
   1. writes every `/orgknow/*` parameter into `/etc/orgknow/env` (root only, mode 0600);
   2. on the first deploy only: downloads and unpacks `corpus_cache.tar.gz` (396 MB);
   3. pulls the tag; the ECR credential helper gets the registry token, so there's no `docker login` and no token on disk (ADR-015 D3);
   4. removes the old containers, then runs `alembic upgrade head` in a one-off container from the new image; a failure stops it here and starts nothing (step 8);
   5. starts both containers, each with `--restart unless-stopped`: `orgknow-api` on `127.0.0.1:8000` and `orgknow-worker`.
2. `/ready`, retried on the server for up to 120 s (the reranker loads in 14.4 s on the laptop): 7.3's check, without the tunnel.
3. 7.4's fingerprint command.

**Fallback (manual).**

**Server** (step 5's shell). `<tag>` is step 4's fallback tag, e.g. `dbe2093`.

```bash
sudo /usr/local/bin/orgknow-deploy <tag>
```

- **Use the full path.** Amazon Linux's `sudo` likely searches a short `PATH` (`secure_path`) without `/usr/local/bin`, so `sudo orgknow-deploy` could say "command not found" (not verified).
- Expected at the end: `docker ps` with `orgknow-api` and `orgknow-worker`, both `Up`.
- The API loads the reranker before it answers (14.4 s on the laptop). Give it a minute, then 7.3 and 7.4.

Source:

- `Makefile` (`deploy`); `scripts/deploy.sh` (its steps and messages); ADR-015 D2, D3; S16 c1–c5.
- The names table (deploy script `/usr/local/bin/orgknow-deploy <image-tag>`, container names, env file, API port); `infra/boot.sh.tftpl`; ADR-014 D4; plan c1 (the boot script starts nothing).

## 7. Check

### 7.1 Logs

**Laptop, terminal A** (step 6's). Both containers log to CloudWatch, group `/orgknow`, streams `api` and `worker`.

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
- Session Manager ends a session after 20 idle minutes (the tunnel and the server shell alike): when `curl` can't connect or the shell stops answering, run the command again.

Source: [port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html#sessions-start-port-forwarding); the names table's API port.

### 7.3 Health and readiness

`make deploy` already checked `/ready` on the server (`/ready: 200`). These go through the tunnel, as a client's request would; after step 6's fallback, they are the first check.

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

After `make deploy`, this is done: it printed the fingerprint, and step 6 compared it. After step 6's fallback, run it.

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

- Start 7.6b at **30 or more**. In S15-T6 the eval kept 1 vCPU busy for ~40 minutes, and the balance fell from ~27 to 9.6 while still earning (1 credit = 1 vCPU for 1 minute). Below 30: wait and check again.
- Record the balance before and after 7.6b.

Source: [standard mode concepts](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode-concepts.html), [the credit table](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html); ADR-014 D2 (standard mode); ADR-014 Context (11.5 s p50 on 2 laptop CPUs).

**b. The retrieval eval in the deployed container (server).** Free: stored vectors and routes, no API call.

```bash
sudo docker exec orgknow-api python -m orgknow.eval retrieval
```

- Expected first 5 metric lines: PR #51's (the slice's "Proof map"), e.g. `Recall@10 0.522  Hit@10 0.972  MRR 0.781  nDCG@10 0.508`.
- **The number to record:** `Retrieve time: p50 … s, p95 … s`. A p95 above **15 s** goes to the next design review (ADR-014 D2). Laptop rehearsal: p95 6.63 s.
- Time: about 40 minutes in S15-T6 (retrieve p50 57.8 s; `deployment-evidence.md`). It prints nothing until the end.
- Memory: the eval loads a second reranker inside the API container. Laptop rehearsal: 1,618 MiB at peak for both, of the server's 4 GiB.

Source: `Makefile` (`eval-retrieval` runs `python -m orgknow.eval retrieval`); plan m15 (the eval's files are in the image); ADR-014 D2.

**c. One live ask (laptop, terminal B). Paid: ~US$0.03** (Anthropic answer and router, Voyage). Check the Anthropic prepaid balance first.

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

**The full day's cost: gross, net and tax** (S15-R2 design review, P4). Read it at least a day after that UTC day ends, even after teardown: a finished day's cost stays readable.

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

**Laptop** (any terminal, after `export AWS_PROFILE=orgknow`), at the new commit, everything committed:

```bash
make deploy
```

- Expected: step 6's output and its fingerprint check. Then 7.2–7.3 (the tunnel, `/health`).
- It re-reads the parameters, pulls the tag, migrates and replaces both containers; the corpus is already unpacked.
- **Fallback:** step 4's fallback from the new commit, then on the server:

```bash
sudo /usr/local/bin/orgknow-deploy <new tag>
```

**A release with a new database migration** deploys the same way: the old containers stop, the new image's `alembic upgrade head` runs, then the new containers start.

- A short outage: the API is down from the stop until the new API is ready (ADR-015 Consequences).
- **Only after CI:** deploy a migration once its downgrade is written and CI's migration round trip is green (the `integration` job: down to `0001`, then up).
- **A failed migration starts nothing:** the API stays down until a fixed deploy or a rollback. Alembic's error is in the server's stderr, in `make deploy`'s output.
- All pending migrations run in one transaction (none of today's 9 opts out of it), so a failed migration changes nothing.

**Roll back** to the previous tag: ECR keeps the last 3 images (m13).

- **The new release had no migration, or its migration failed:** on the server, deploy the previous tag.

```bash
sudo /usr/local/bin/orgknow-deploy <previous tag>
```

- **Its migration succeeded:** the previous image doesn't know the new revision. Its `alembic upgrade head` stops with `Can't locate revision identified by '<new revision>'`, and nothing starts.
- So, on the server: stop the new containers, read the previous revision from the previous image, undo the migration with the **new** image, then deploy the previous tag.
- **Not verified on a server** ("Not verified"). A laptop drill comes with the first slice that adds a migration (S16 decision p2).

```bash
sudo docker rm -f orgknow-api orgknow-worker
```

- First, so no running job or request holds a lock the downgrade needs, and the new code never runs on the old schema.

```bash
sudo docker run --rm <repo>:<previous tag> alembic heads
```

- Expected: one line, e.g. `0009 (head)`. That number is `<previous revision>`. It reads only the image's migration files: no database, no env file.

```bash
sudo docker run --rm --env-file /etc/orgknow/env <repo>:<new tag> alembic downgrade <previous revision>
```

```bash
sudo /usr/local/bin/orgknow-deploy <previous tag>
```

- `<repo>:<new tag>` and `<repo>:<previous tag>`: both images are on the server, as `sudo docker images` lists them.
- CI proves each downgrade undoes its upgrade, on its own database (`.github/workflows/ci.yml`, "Migration round trip").

**A change to the boot script** (`infra/boot.sh.tftpl`, which writes the deploy script): it runs only at the first boot, so the change reaches the server only with a new server. A plain `apply` would only stop and restart the old server ([the provider's docs, `user_data`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance#user_data); not verified).

**Laptop** (a terminal with `AWS_PROFILE` set):

```bash
terraform -chdir=infra apply -replace=aws_instance.server
```

- Then: wait for `Online` (step 2's last check) and for the boot script (step 5's `cloud-init status`, in a new server shell), and run step 6 again. The deploy script downloads and unpacks the corpus again on its own, as on the first deploy. The database is untouched.
- The `instance_id` output changes: re-read it before 7.2 (`make deploy` reads it itself).

Source:

- `Makefile` (`deploy`); `scripts/deploy.sh`; ADR-015 D2, D3; S16 c1 (no automatic downgrade).
- `infra/boot.sh.tftpl` (`orgknow-deploy` step 4, the migration); `src/orgknow/db/migrations/env.py` (one transaction for the whole upgrade); `.github/workflows/ci.yml` (`integration`, "Migration round trip").
- `infra/compute.tf` (`lifecycle { ignore_changes = [ami] }` and its comment on `-replace`).
- `infra/storage.tf` (`aws_ecr_lifecycle_policy.app`).

## Demo hours: 4 cores (S18)

For the hours a window shows the system (S18's video, an interview's screen share), the server runs as c7a.xlarge: 4 physical cores, 8 GiB, ~US$0.23 an hour against ~US$0.04 (ADR-014's 2026-11-02 amendment).

- **Why:** on t3a.medium, a question's retrieval took p50 57.83 s and p95 78.04 s (S15-T6), over ADR-014 D2's 15 s line.
- **Only the server's type changes**, then changes back: same image, same pipeline, same scores.

**a. Before the window (free; laptop, after `export AWS_PROFILE=orgknow`).** Is the type offered in the server's zone (`us-east-1a`: `${var.region}a` in `infra/network.tf`)?

```bash
aws ec2 describe-instance-type-offerings --location-type availability-zone --filters Name=location,Values=us-east-1a Name=instance-type,Values=c7a.xlarge,c7a.2xlarge --query 'InstanceTypeOfferings[].InstanceType' --output text
```

- Expected: `c7a.xlarge` (and `c7a.2xlarge`, d's fallback). No `c7a.xlarge`: no demo hours this window; take it to the next design review.

The account's limit on running vCPUs of the standard types (A, C, D, H, I, M, R, T, Z):

```bash
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --query 'Quota.Value' --output text
```

- c7a.xlarge needs 4; the c7a.2xlarge fallback needs 8. A new account's limit is often 5. Record it.

**b. Resize (laptop).** Add one line to `infra/terraform.tfvars` (`instance_type` is ADR-014 D2's "one Terraform variable"):

```hcl
instance_type = "c7a.xlarge"
```

```bash
terraform -chdir=infra plan
```

- Expected: `Plan: 0 to add, 1 to change, 0 to destroy.`: `aws_instance.server` updated in-place, `instance_type` from `"t3a.medium"` to `"c7a.xlarge"`.
- **`must be replaced` or `1 to destroy`: stop.** A new server loses the unpacked corpus and the env file (step 8's boot-script note).
- The `credit_specification` (D2's standard credits) is for T types only. The provider is expected to skip it on c7a with a warning: the devil's advocate read that in its source, not in the pinned version (6.68.0). This plan is the first check.

```bash
terraform -chdir=infra apply
```

- Expected: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` The provider stops the server, changes its type and starts it: 52 s in S18-T4.
- The server shell and the tunnel (7.2) drop with the stop. Wait for `Online` (step 2's last check).

**c. Both containers back (laptop, then server).** Nothing is redeployed:

- Docker starts at boot, and both containers are `--restart unless-stopped` (`infra/boot.sh.tftpl`).
- The corpus cache (`/srv/orgknow/corpus_cache`) and the env file (`/etc/orgknow/env`) are on the root disk, which a stop keeps.

**Laptop:** open a new shell on the server.

```bash
INSTANCE_ID=$(terraform -chdir=infra output -raw instance_id)
```

```bash
aws ssm start-session --target "$INSTANCE_ID"
```

**Server:**

```bash
sudo docker ps --format '{{.Names}} {{.Status}}'
```

- Expected: `orgknow-api Up …` and `orgknow-worker Up …`. Give the API a minute to load the reranker, then 7.2–7.3 (the tunnel, `/ready`).

**d. Measure first (server), before any demo.** Torch's thread count in the API container:

```bash
sudo docker exec orgknow-api python -c "import torch; print('torch threads', torch.get_num_threads())"
```

- Expected: `torch threads 4` (torch's default is one per physical core; each c7a vCPU is a core). Record it.

The retrieve time, with 7.6b's command (what `make eval-retrieval` runs). Free: stored vectors and routes.

```bash
sudo docker exec orgknow-api python -m orgknow.eval retrieval
```

- Expected metric line: `Recall@10 0.522  Hit@10 0.972  MRR 0.781  nDCG@10 0.508`.
- **Record** `Retrieve time: p50 … s, p95 … s`. The laptop's 4 cores gave p95 10.61 s in 4 min 50 s, an optimistic bound (`docs/evaluation.md`, "Reranker timing and S15 sizing"). It prints nothing until the end.
- **p95 at or under 15 s:** demo on c7a.xlarge.
- **Over 15 s:** c7a.2xlarge (8 cores, 16 GiB, about twice the hourly price) if a's limit is 8 or more: b–d again with `instance_type = "c7a.2xlarge"`. Under 8: demo on c7a.xlarge and state the measured p95 as a known limit (d2).

**e. Resize back (laptop), when the demo hours end, and before any break over 1 hour** (S18 t3). In S18-T4 it was missed overnight: ~17.6 hours more on c7a.xlarge (~US$0.205 an hour on the bill, against ~US$0.038), ~US$2.95 extra of a US$4.89 window. Delete the `instance_type` line from `infra/terraform.tfvars` (the default is t3a.medium), then:

```bash
terraform -chdir=infra apply
```

- Expected: `0 added, 1 changed, 0 destroyed`, in place, `"c7a.xlarge"` to `"t3a.medium"`. Then c's container check again.
- Then `terraform -chdir=infra plan`: expected `No changes.` A `cpu_credits` change back to `"standard"`: apply it (D2).
- While the file says c7a, `make tf-check` fails its `instance_and_credits` run: the test pins the default type (offline, with `-var instance_type=c7a.xlarge`: `10 passed, 1 failed`).
- Step 9 also ends demo hours: it destroys the server whatever its type.

Source: ADR-014 D2 and its 2026-11-02 amendment; the S18 slice doc (d2; the devil's advocate's checks); `infra/variables.tf` (`instance_type`); `infra/compute.tf` (`credit_specification`, `ignore_changes = [ami]`); `infra/network.tf` (the zone); `infra/boot.sh.tftpl` (Docker at boot, the restart policy, the cache path); `infra/tests/rules.tftest.hcl` (`instance_and_credits`).

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

- Right after the delete, it may still list the database's automatic daily snapshots (`rds:orgknow-…`). AWS removes them within a minute (S15-T6): run it again.

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
- **Then delete the window's `infra/terraform.tfvars`** (step 2 makes a fresh one each window). While it sets `budget_usd` to anything but 50, `make tf-check`'s budget test fails, because `terraform test` reads that file too (S15-T7).

Source: ADR-014 D7; plan c5, m11, m13; `infra/storage.tf`, `infra/database.tf`; `infra/versions.tf` (every resource has the tag `Project = orgknow`); `docs/security-review.md` 6.1, 6.6.

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

S15-T6 ran steps 1–7 and 9 against AWS (`deployment-evidence.md`), before S15-T7's fixes. It confirmed: the console steps, with the fixes above; the restore flags on RDS (as its master user, the dump created `vector` and `btree_gist`); the restore time and RDS's pgvector version; the AWS CLI on the server; `/usr/local/bin/orgknow-deploy` by its full path; the Cost Explorer filters and the budget's `IncludeCredit` field. Still unchecked:

- That plain `sudo orgknow-deploy` fails on Amazon Linux 2023 (step 6 uses the full path, which worked), and that Session Manager's shell starts outside `ssm-user`'s home (step 5's `cd ~` ran either way).
- That a plain `apply` after a boot-script change only stops and starts the server (step 8 hasn't run).
- That Budgets and Cost Explorer show a forecast for this account (7.6e used 1 day's cost × 30.4 instead).
- Tax in 7.6e's third command: 0 so far; it may appear only when the month is billed.

S16-T5 rewrote steps 2, 4, 6 and 8 with no AWS:

- `make audit` ran (step 2's output, 2026-11-01).
- `make deploy` ran only up to its no-stack stop (S16-T4): `image-check: ok`, then the "is a window open?" line; 9.5 s with a warm build cache.

S16-T6 ran steps 2, 3, 5, 6, 8 and 9 against AWS (`deployment-evidence.md`, "Window 2"). It confirmed: `make deploy` against a stack (the login and push, both gates and the scan counts' format, Run Command and the 10 s polling, `/ready: 200` and the fingerprint); step 8's update, replacing running containers; the ECR credential helper (no `docker login` on the server; `/root/.ecr` holds only `log/`); `terraform destroy`'s own last line (`Destroy complete! Resources: 37 destroyed.`); step 3's two `.env` loops and step 9's `terraform.tfvars` delete. It found 2 problems, fixed then: the scan wait (`scripts/deploy.sh`) and a CRITICAL OS finding (`Dockerfile`).

Still unchecked:

- A deploy whose migration changes the database: none yet (the first deploy's is a no-op).
- Step 8's rollback after a migration that succeeded. The `Can't locate revision` stop was reproduced in a scratch Alembic project; the stop, `alembic heads` in the previous image (run once on the laptop, in today's image: `0009 (head)`), the downgrade with the new image, then the previous tag, have run together nowhere. The drill is a backlog Proposed addition (S16 decision p2).

S18-T4 ran steps 2, 3, 5, 6, [demo hours](#demo-hours-4-cores-s18) and 9 against AWS (`deployment-evidence.md`, "Window 3"). It confirmed: both commands of a; the in-place resize and its plan, with no credit line on c7a (provider 6.68.0); both containers back after each start; the resize back (3 min 1 s) and its `No changes.`; the scan wait for a scan that doesn't exist yet (7 "waiting … to start" lines).
