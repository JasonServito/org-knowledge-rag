#!/usr/bin/env bash
# make deploy (S16-T4, ADR-015 D2): deploy this commit to the window's server, from the laptop.
# In order: refuse uncommitted changes to tracked files; `make audit`; `make image` and
# `make image-check`; push the image to ECR, tagged with the commit's short SHA; wait for ECR's
# scan and stop on any CRITICAL finding; run `orgknow-deploy <tag>` on the server through SSM Run
# Command and poll it to the end; there, wait for /ready and print the ingestion fingerprint.
# It uses the developer's own AWS login (AWS_PROFILE, set as the runbook says) and runs in the
# current directory: `make deploy` runs it at the repo root. The runbook's commands stay the
# fallback.
set -euo pipefail
# The AWS CLI prints straight to the terminal, never through a pager that waits for `q` (S16
# decision p3).
export AWS_PAGER=""

die() {
  echo "deploy: $*" >&2
  exit 1
}

# 1. A clean tree, so the tag names what is built. Untracked files don't count (S16 c3).
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --short --untracked-files=no >&2
  die "uncommitted changes to tracked files: commit them first, so the tag names what is built"
fi
TAG=$(git rev-parse --short HEAD)

# 2. The free checks: the Python packages, then the image (ADR-015 D4).
echo "deploy: audit"
make audit
echo "deploy: image $TAG"
make image
make image-check

# 3. The registry and the server, from Terraform's outputs. With no stack, `terraform output -raw`
#    exits 0 and prints a "No outputs found" warning on stdout, so check what each value looks like.
REPO=$(terraform -chdir=infra output -raw ecr_repository_url 2>/dev/null || true)
INSTANCE_ID=$(terraform -chdir=infra output -raw instance_id 2>/dev/null || true)
if [[ "$REPO" != *.dkr.ecr.*.amazonaws.com/* || "$INSTANCE_ID" != i-* ]]; then
  die "no ecr_repository_url or instance_id in Terraform's outputs: is a window open?"
fi
# The URL is <account>.dkr.ecr.<region>.amazonaws.com/<name>: the stack's own region.
REGISTRY=${REPO%%/*}
REPO_NAME=${REPO#*/}
REGION=$(echo "$REGISTRY" | cut -d. -f4)

# 4. Push the image (runbook step 4). The laptop logs in to the registry as the runbook does.
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker tag orgknow:dev "$REPO:$TAG"
docker push "$REPO:$TAG"
echo "deploy: pushed $REPO:$TAG"

# 5. ECR's scan of the OS packages (ADR-015 D4, S16 c10): stop on any CRITICAL finding; HIGH and
#    below are printed only. No CRITICAL key in the counts means 0 (the CLI prints None).
scan() {
  aws ecr describe-image-scan-findings --region "$REGION" --repository-name "$REPO_NAME" \
    --image-id imageTag="$TAG" --query "$1" --output "$2"
}
# Seconds after the push the scan may not exist yet, and AWS's waiter fails on that at once
# (ScanNotFoundException, seen in S16-T6): first wait up to 60 s for the scan to exist. Each wait
# prints a line, so a quiet terminal isn't mistaken for a hang (S18-R1 c3).
for n in $(seq 12); do
  scan imageScanStatus.status text >/dev/null 2>&1 && break
  echo "deploy: waiting for ECR's scan of $TAG to start ($n of 12)"
  sleep 5
done
echo "deploy: waiting for ECR's scan of $TAG to complete"
aws ecr wait image-scan-complete --region "$REGION" --repository-name "$REPO_NAME" \
  --image-id imageTag="$TAG" || die "ECR's scan of $TAG did not complete"
echo "deploy: ECR scan: $(scan imageScanFindings.findingSeverityCounts json | tr -d ' \n')"
CRITICAL=$(scan imageScanFindings.findingSeverityCounts.CRITICAL text)
if [ "$CRITICAL" != None ] && [ "$CRITICAL" != 0 ]; then
  scan "imageScanFindings.findings[?severity=='CRITICAL'].[name,uri]" text >&2
  die "ECR found $CRITICAL CRITICAL findings in $REPO:$TAG: not deploying"
fi

# 6. Deploy on the server (runbook steps 6, 7.3 and 7.4), as root, through Run Command. It runs
#    these lines as one shell script whose result is the last line's exit code, so `set -e` stops
#    it at the first failure. The API listens on the server's 127.0.0.1:8000 only (ADR-014 D1):
#    /ready is retried there for up to 120 s (24 tries, 5 s apart; the reranker loads in ~14 s).
SERVER_COMMANDS=(
  'set -e'
  "/usr/local/bin/orgknow-deploy $TAG"
  'for i in $(seq 24); do'
  '  code=$(curl -s -o /dev/null -w "%{http_code}" localhost:8000/ready || true)'
  '  [ "$code" = 200 ] && break'
  '  sleep 5'
  'done'
  'echo "/ready: $code"'
  '[ "$code" = 200 ]'
  'docker exec orgknow-api python -m orgknow.ingestion.report | grep Fingerprint'
)
PARAMETERS=$(python3 -c 'import json, sys; print(json.dumps({"commands": sys.argv[1:]}))' \
  "${SERVER_COMMANDS[@]}")
COMMAND_ID=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --comment "orgknow-deploy $TAG" \
  --parameters "$PARAMETERS" --query Command.CommandId --output text)
echo "deploy: server: command $COMMAND_ID sent; polling every 10 s, up to 20 min"

invocation() {
  aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" --query "$1" --output text
}
# Our own loop: AWS's waiter gives up after ~100 s (S16 c5). Right after send-command the
# invocation may not exist yet: that is "keep polling", not a failure.
STATUS=Pending
for _ in $(seq 120); do
  sleep 10
  if ! STATUS=$(invocation Status 2>&1); then
    case "$STATUS" in
      *InvocationDoesNotExist*) STATUS=Pending ;;
      *) die "$STATUS" ;;
    esac
  fi
  case "$STATUS" in
    Pending | InProgress | Delayed) ;;
    *) break ;;
  esac
done

echo "deploy: server: $STATUS"
invocation StandardOutputContent
invocation StandardErrorContent >&2
case "$STATUS" in
  Success) ;;
  Pending | InProgress | Delayed)
    die "the server's deploy is still $STATUS after 20 min (command $COMMAND_ID)"
    ;;
  *) die "the server's deploy ended with $STATUS" ;;
esac
echo "deploy: done: $REPO:$TAG. Compare the fingerprint with the laptop's (make ingest-report)."
