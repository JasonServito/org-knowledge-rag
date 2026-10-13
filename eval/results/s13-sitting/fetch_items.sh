#!/usr/bin/env bash
# S13-R1 sitting: fetch the release-cadence chain's 3 GitHub items as raw API JSON.
# The output is GitHub text (not CC BY), so it goes to a scratch directory, never the repo.
# Usage: bash eval/results/s13-sitting/fetch_items.sh <scratch dir>   (needs `gh auth login`)
set -euo pipefail
out="$1"; mkdir -p "$out"; cd "$out"
gh api repos/kubernetes/enhancements/issues/2572 > issue-2572.json
gh api "repos/kubernetes/enhancements/issues/2572/comments?per_page=100" > issue-2572-comments.json
gh api repos/kubernetes/enhancements/pulls/2567 > pr-2567.json
gh api "repos/kubernetes/enhancements/issues/2567/comments?per_page=100" > pr-2567-comments.json
gh api "repos/kubernetes/enhancements/pulls/2567/reviews?per_page=100" --paginate > pr-2567-reviews-all.json
gh api graphql -f query='query { repository(owner:"kubernetes", name:"sig-release") { discussion(number:1290) { title createdAt url body comments(first:100) { totalCount nodes { createdAt author { login } body replies(first:50) { totalCount nodes { createdAt author { login } body } } } } } } }' > disc-1290.json
