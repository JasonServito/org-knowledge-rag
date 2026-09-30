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

### S02-T3a: Versions `[core]`

- **Goal:** per release, count the in-scope files and the distinct content versions after normalization and hashing (ADR-002 D2). Add a `head` row for the date-scoped sources.
- **Done when:** the report has the per-release and per-source tables, and the hand checks match: one blog post against `git log --first-parent`, and one release's file count against `git ls-tree`.

### S02-T3b: Tokens, chunks, cost `[core]`

- **Goal:** estimate tokens and chunks as an upper bound and a lower bound:
  - upper bound: every new version is embedded in full
  - lower bound: only unique heading sections are embedded, as a chunk-level content-hash cache would see them

  Then estimate the embedding cost and the vector storage.
- **Done when:** the report has the cost table, citing the Voyage pricing page and date.

#### T3 notes (decided at plan review, 2026-09-30)

- **Split:** the plan estimated about 290 lines. The drafts came to 381 code lines (+30%), so T3 was split into T3a (versions) and T3b (tokens, chunks, cost). The T3b code is kept from the draft and re-applied on the T3b branch. T3a as shipped: 311 code lines in `measure.py` plus 52 in tests (363), against the split estimate of about 310 (+17%). The extra came from following blog moves and parsing front-matter variants, both found in the data.
- **Run:** `uv run python spikes/measure.py [--dry-run]`, with the same `CORPUS_CACHE_DIR` rule as T2. `--dry-run` prints the blob counts and stops before downloading.
- **Tests:** the module has no import-time side effects (no env reads, git or exit), so `tests/unit/test_spike_measure.py` runs in CI without a cache. Replace those tests in S04.
- **Download:**
  - Blob ids come from local trees (`git ls-tree`, `git log --raw`). `fetch.py` now also allows `ls-tree` and `log`.
  - The contents are fetched with `git fetch --stdin`, 1,000 ids per request. It's the same request git's own lazy fetch makes, but batched.
  - A batch whose blobs are all present is skipped without contacting the remote, so re-runs download nothing.
  - One `git cat-file --batch` per repo reads the contents under `protocol.allow=never`, so a missing blob fails loudly.
- **Version rule:** a new version when the normalized hash differs from the same document's previous version. A→B→A is three versions. The `raw blob versions` column compares blob ids instead, to show what normalization saves.
- **Normalization (spike version of ADR-002 D2):**
  - Parse the YAML front matter and drop the manifest's strip keys for that source, ignoring case. The script refuses a strip list that contains a `never_strip` key.
  - Sort the remaining keys.
  - Remove link targets (`[text](url)` becomes `[text]`).
  - Collapse whitespace.
  - The parse tolerates a byte-order mark, CRLF line endings and blank lines before the opening `---`. All three occur in real blog posts.
- **Rows:**
  - Releases 1.20–1.37 are the locked snapshots.
  - `head` holds the date-scoped changes after 1.37's release date, up to the lock's default-branch heads.
  - A blog commit goes to the first release whose cutoff is at or after the commit. The cutoff is the lock's rule: committer time (UTC) <= the release date at 23:59:59Z.
- **Blog:**
  - One entry per first-parent commit (`--first-parent --diff-merges=first-parent --raw`), `*.md` only.
  - Scope: the latest version's front-matter `date` is on or after 1.20's release date, and it isn't `draft: true`.
  - Moves are followed with git rename detection. That needs file contents, so the history is listed twice: without renames to find the blobs, then with renames after the download.
- **KEPs:** `README.md` and other `.md` files are the documents. `kep.yaml` and PRR files are counted as metadata versions and aren't embedded (ADR-003 D1).
- **Identity:** the file path, except that blog moves are followed. Docs renames are T4's subject.
- **T3b estimation rules (agreed):**
  - Tokens ≈ characters ÷ 4. This likely underestimates code and YAML, which have more tokens per character.
  - Chunks: split at headings, at most 512 tokens per chunk, plus a 40-token header per chunk. Add 256 and 1024 as sensitivity rows.
  - Lower bound: from unique section hashes.
  - Vector storage: chunks × dimension × 4 bytes, at voyage-4's default of 1024 dimensions (docs.voyageai.com/docs/embeddings, updated 2026-08-10). The voyage-4 family also supports 256, 512 and 2048, so add storage rows at 512 and 256 dimensions.
- **For S04:** the chunk header should contain only fields that are fixed when the version is created. Mutable fields (`valid_until`, tier, flags) go in DB columns, so closing a validity window doesn't force a re-embed.

### S02-T4: Rename check `[core]`

- **Goal:** run `git diff --find-renames` between adjacent release branches for the in-scope paths, and sample 10 detected renames.
- **Done when:** the report gives precision on the sample, lists unmatched add/delete pairs, and recommends a similarity threshold.

#### T4 notes (added at T3a review, 2026-09-30)

- **Blog identity across the year-folder move:** verify that front-matter blog ids (`blog:<date>-<slug>`, ADR-002 D4) stay the same across website PR #53902's move: no collisions and no missing slugs. T1's key inventory found `slug` in 411 of 413 in-range posts at the head, so the fallback for a missing slug matters. If the ids hold, S05 uses front-matter identity for the blog, and rename detection is for docs only.

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

#### T6 notes (added at T3a review, 2026-09-30)

- **Feature-gate share of embeddable versions, per release** (from the T3a data; embeddable means every version except `kep.yaml` and PRR metadata; computed with a scratch script, because `measure.py` doesn't print the per-source split by release):
  - 1.20–1.28: 1–2% each
  - 1.29: 318 of 432 (74%), the split into one file per gate
  - 1.30: 54 of 141 (38%)
  - 1.31: 69 of 356 (19%)
  - 1.32: 371 of 451 (82%), the file renames
  - 1.33: 85 of 159 (53%)
  - 1.34: 71 of 236 (30%)
  - 1.35: 58 of 145 (40%)
  - 1.36: 68 of 213 (32%)
  - 1.37: 62 of 213 (29%)
  - head: 0 of 36
  - overall: 1,169 of 3,281 (36%)

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
