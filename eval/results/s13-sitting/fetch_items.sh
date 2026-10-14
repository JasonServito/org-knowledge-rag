#!/usr/bin/env bash
# S13-R1 sitting: fetch the chains' GitHub items (release cadence: 3; the held-out KEP-3015: 2) as raw API JSON.
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
# The held-out chain's 2 items (KEP-3015; added after the draw).
gh api repos/kubernetes/enhancements/issues/3015 > issue-3015.json
gh api "repos/kubernetes/enhancements/issues/3015/comments?per_page=100" --paginate > issue-3015-comments.json
gh api repos/kubernetes/enhancements/pulls/3010 > pr-3010.json
gh api "repos/kubernetes/enhancements/issues/3010/comments?per_page=100" --paginate > pr-3010-comments.json
gh api "repos/kubernetes/enhancements/pulls/3010/reviews?per_page=100" --paginate > pr-3010-reviews.json
