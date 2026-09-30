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
