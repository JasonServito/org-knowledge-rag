# S02: Corpus spike

- **Status:** 🟨
- **Blueprint stage:** pre-Stage 2 (validates ADR-002 and ADR-003)
- **Started:** 2026-09-27
- **Finished:**

## Outcome

Measured numbers for the Stage 1 subset, with ADR-002 and ADR-003 accepted, or amended on evidence.

## Why now

The schema (S03) depends on how many versions, renames and status mismatches actually exist. Writing migrations before measuring would mean designing on guesses.

## Exit checks

- [ ] `docs/research/corpus-spike-report.md` has: SHAs, per-release counts, distinct versions after dedup, token/chunk estimates, embedding cost estimate, rename findings, format findings.
- [ ] The embedding cost estimate for the Stage 1 subset is acceptable to you.
- [ ] ADR-002 and ADR-003 are Accepted (amendments noted).
- [ ] Slice brief S02 written.

## Scope

| In | Out (explicitly) |
|---|---|
| Manifest v0, throwaway scripts in `spikes/`, measurements, a written report | Any code in `src/`; DB writes; embedding API calls (estimate only); GitHub issues/PRs |

**Spike rule:** spike code is disposable. It lives in `spikes/`, is excluded from `mypy --strict`, and is never imported by `src/`. Anything reusable gets **rewritten** properly in S03/S04.

## Metric to move

n/a. The outputs are measurements.

## Tasks

### S02-T1: Manifest v0 `[core]`

- **Goal:** `config/corpus_manifest.yaml` containing:
  - repos and branches
  - the release range (v1.20 → latest)
  - SIG → docs path allowlists (Release, Auth, Network)
  - KEPs 2572 / 2579 / 2799 / 4858, plus the SIG KEP directories in scope
  - blog, CHANGELOG and governance sources
  - the ADR-002 normalization field list
- **Done when:** you've reviewed the path allowlists against the actual website tree.

### S02-T2: Fetch script `[commodity]`

- **Goal:** `spikes/fetch.py` makes partial clones (`--filter=blob:none`) into `CORPUS_CACHE_DIR`, which is outside the repo and gitignored, and records the repo SHAs and release branch heads.
- **Done when:** the SHAs are listed in the report.

#### T2 notes (decided at plan review, 2026-09-29/30)

- **Dependency:** PyYAML in the dev group, `safe_load`/`safe_dump` only (ADR-004 amendment 2026-09-29). It moves to runtime in S04.
- **Run:** `uv run python spikes/fetch.py [--relock]`. The script reads `CORPUS_CACHE_DIR` from the environment directly, not through `Settings`, so there are no `src/` changes. `uv run` doesn't load `.env`, so export the variable in your shell. `.env.example` has a commented placeholder.
- **Guardrails:**
  - Refuse if `CORPUS_CACHE_DIR` is unset, or if its `expanduser().resolve()` path is inside the repo (`is_relative_to`). Tested unset, inside-repo, a `..` path and a `~` path.
  - Git data is written only under the cache. The only repo file written is the lock.
  - Print every git command before running it.
  - Clone if missing, else fetch. No `--prune`, so fetch never deletes refs.
  - The git helper runs only `clone`, `fetch`, `rev-parse`, `rev-list` and `cat-file`, so it can't push or delete.
- **Clones:** all use `--filter=blob:none --no-checkout`: commits and directory listings only, no file contents.
  - kubernetes adds `--depth 1 --single-branch`. CHANGELOG is read from `master` and needs no history (ADR-002 D1).
  - website takes all branches with full history, because the `release-1.R` branches are the per-release docs.
  - enhancements, community and sig-release take their default branch only, with full history.
- **Local reads never touch the network.** Git 2.43 has no `--no-lazy-fetch` (added in 2.44). In a partial clone, reading a missing object would quietly download it. So the read-only commands run with `-c protocol.allow=never`, which makes a missing object an error. Tested: `cat-file -e` on a missing commit fails with `transport 'https' not allowed`.
- **Lock file:** `config/corpus_manifest.lock.yaml` is the **single record of corpus SHAs**. The report lists only the default-branch heads, the fetch date, and the lock file's path and commit.
  - Lock missing: resolve the SHAs and write the lock.
  - Lock present: fetch, check every locked SHA exists locally, and leave the lock unchanged.
  - `--relock`: re-resolve the SHAs and overwrite the lock.
  - With a lock present, kubernetes fetches its locked SHA (`git fetch --depth 1 origin <sha>`), not `master`, so a fresh cache can rebuild the locked state. Only `--relock` fetches `master`. On a fresh cache, the clone itself gets `master`'s tip first, because git 2.43 has no `clone --revision`.
  - GitHub allows fetch-by-SHA. Tested on a `master` commit 30 behind the tip: 1.6 MB, and the commit was present afterwards.
- **Lock contents:**
  - the default-branch head of each repo
  - the website SHA per release: branch `release-1.R`, or `main` for the latest release, 1.37
  - the default-branch SHA at each release date, for enhancements, community and sig-release
- **Release-date cutoff rule** (also written in the lock): the last first-parent commit on the default branch with committer date `<= YYYY-MM-DDT23:59:59Z` (UTC) on the release date. End of day, so same-day merges count. Tested: git reads the `Z` suffix as UTC.
- **The script asserts the 4 traced KEPs exist** at the locked enhancements head. It checks the directory listing, so no file contents are downloaded.
- **Known limit:** fresh-cache reproduction from an existing lock is verified for kubernetes only in T2; full check in S05 (AC8).
- **For T3:** the clones hold no file contents yet. Reading files one at a time makes git fetch each one separately (a "lazy fetch"), which is slow, and `protocol.allow=never` blocks those fetches anyway. T3 should batch-prefetch the in-scope files first.

### S02-T3: Measurement `[core]`

- **Goal:** per release, count the in-scope files and the distinct content versions after normalization and hashing (ADR-002 D2), and estimate tokens and chunks.
- **Done when:** there's a table in the report, plus an embedding cost estimate using current Voyage pricing. Cite the pricing page and date.

### S02-T4: Rename check `[core]`

- **Goal:** run `git diff --find-renames` between adjacent release branches for the in-scope paths, and sample 10 detected renames.
- **Done when:** the report gives precision on the sample, lists unmatched add/delete pairs, and recommends a similarity threshold.

### S02-T5: Format checks `[core]`

Each answered yes/no with an example:

- the actual latest release and branch
- does the feature-gates reference page give a stage per version?
- do blog posts have front-matter dates, and are in-place edits visible in git history?
- CHANGELOG patch-section heading structure
- the `kep.yaml` status/stage values found, including typos

**Done when:** all are answered in the report.

### S02-T6: Decide `[human]`

- **Goal:** write the report's conclusion, amend the ADRs, and set them to Accepted.
- **Done when:** the ADR index is updated.

## Risks & unknowns

- Repo size and clone time. Use partial clones and path filters.
- The path allowlists may miss relevant docs. Note gaps; don't expand scope.

## Decisions expected

ADR-002 and ADR-003 (accept or amend).

## Retro (fill in at the end)

- **Shipped:**
- **Surprises:**
- **Do differently:**
- **Slice brief:**
