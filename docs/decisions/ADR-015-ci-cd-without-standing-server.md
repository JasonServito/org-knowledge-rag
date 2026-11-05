# ADR-015: CI/CD with no standing server (CI checks every PR; `make deploy` from the laptop)

- **Status:** Accepted (S16-R1 design review, 2026-10-31)
- **Date:** 2026-10-31
- **Blueprint/spec refs:** §23 stage 12; ADR-014 (D1, D4, D6, the 2026-10-16 amendment); security review 5.5
- **Evidence:** the S16-R1 design review's probes and 2 devil's advocates (the S16-R1 plan)

## Context

- The AWS environment exists only in windows (ADR-014's amendment): about 3 in the project's life. `terraform destroy` deletes the image registry too, so between windows there is nothing to deploy to.
- There is one operator. A window's day 1 took ~2 hands-on hours (S15-T6); runbook steps 4 and 6 are ~10 typed commands plus a server shell.
- The server has no inbound ports (ADR-014 D1); AWS can run a command on it through Systems Manager (Run Command), which its role already allows.
- The runbook can't ship a release with a migration (`docs/deployment.md` step 8).
- `make eval-smoke` makes 13 paid Anthropic calls (~US$0.40) against the full 431 MB database; CI's database is empty.
- On 2026-10-31, `pip-audit` on the locked runtime packages found 17 known vulnerabilities in 4 packages, all published 2026-10-20 to 10-28, all with fixes; `torch` (from PyTorch's CPU index) can't be audited. ECR's free basic scan checks OS packages only; Python packages need Amazon Inspector (paid).
- In March 2026, `aquasecurity/trivy-action`'s tags were hijacked to steal CI secrets (CVE-2026-33634).

## Decision

### D1. CI checks every PR, free

- New CI jobs: the image (`make image`, `make image-check`), Terraform (`make tf-check`), and the dependency audit (`make audit`).
- `image` and `tf-check` become required checks; `audit` doesn't: new advisories appear over time, not with code changes, so it warns without blocking unrelated PRs.
- CI holds no AWS login and no secrets.

### D2. `make deploy` from the laptop deploys a commit inside a window

- In order: refuse uncommitted changes to tracked files; `make audit`; `make image` and `make image-check`; tag the image with the commit's short SHA and push it to ECR; wait for ECR's scan and stop on any CRITICAL finding; run `orgknow-deploy <tag>` on the server through SSM Run Command, polled until it ends; on the server, retry `/ready` until 200 and print the ingestion fingerprint.
- It uses the developer's own AWS login (`aws sso login`); the registry and the server come from Terraform's outputs.
- The manual runbook commands stay as the fallback.

### D3. The deploy script migrates before it starts the new version

- `orgknow-deploy <tag>`: pull the image; stop the old containers; run `alembic upgrade head` in a one-off container from the new image; then start the API and the worker. A failed migration starts nothing; recovery is the same script with the previous tag.
- The server reaches ECR through the Amazon ECR credential helper (Amazon Linux 2023's `amazon-ecr-credential-helper`), so no login token is written to disk.

### D4. The scan: Python packages before the build, OS packages after the push

- `pip-audit` (a dev dependency, pinned in `uv.lock`) audits the exported runtime lock. It stops on any known vulnerability: it reports no severity, and a fixed version is a lock bump away. An advisory that can't be fixed is accepted on the Makefile's audit line with a one-line reason.
- `make audit` runs before each window's `terraform apply` (free, ~7 s), so a new advisory is fixed in a PR before the window, not during it.
- After the push, ECR's basic scan gates on CRITICAL OS findings only: the Debian base often carries findings with no fix yet.

### D5. No eval in CI or at deploy

- After a deploy: `/ready` 200 and the fingerprint (the runbook compares it with the laptop's). The image is the one CI checked and the data is the same, so retrieval and answers can change only with code, which the laptop's evals cover before merging.
- The paid smoke eval stays a manual laptop command, run when asked.

## Alternatives considered

| Option | Why not |
|---|---|
| A GitHub Actions deploy workflow with OIDC (keyless AWS login) | A new path into AWS that can run any command as root on the server (and so read every API key); each workflow fix during a paid window needs a PR and a merge to `main`; the same 1 step per deploy as `make deploy` |
| Deploy on every merge | No standing server or registry between windows (ADR-014's amendment) |
| Keep the manual runbook only | ~10 commands per deploy; the stage's build/push/deploy not done |
| ECR's basic scan only | OS packages only: it passes today with 17 known Python vulnerabilities |
| Trivy on the image in CI | One tool with severities, but a downloaded binary whose distribution was hijacked in March 2026; its coverage of `torch`'s `+cpu` build is unknown |
| Amazon Inspector in each window | Paid, window-only, and an account-wide switch that `destroy` doesn't remove |
| A retrieval or paid smoke eval at each deploy | ~13 min on the server (78 s per question) or ~US$0.40 per deploy, for an image and data already checked |
| An eval on a small made-up database in CI | Its numbers mean nothing |

## Consequences

- One command per deploy; a fix mid-window is an edit and a rerun. The build runs on the laptop, from a clean tree, tagged with its commit.
- **New tools:** `pip-audit` (dev dependency); `amazon-ecr-credential-helper` on the server; `hashicorp/setup-terraform` in CI.
- **Gaps, recorded:** `torch` is unaudited; the uv binary in the image is in neither scan; HIGH OS findings are printed, not gated.
- A deploy's migration means a short outage: the old containers stop first. Fine for one operator; not zero-downtime.
- The base-image digests have no refresh trigger; the audit's red result is the lock's.
- **Revisit triggers:** a second operator, or 5 or more deploys planned per window (→ a GitHub Actions workflow with OIDC); unfixable advisories piling up on the audit line (→ a scanner with severities); a public API in S17 (→ reconsider Inspector); a cloud-only change that could move answers, such as another instance type or a hosted reranker (→ the retrieval eval in that window).
