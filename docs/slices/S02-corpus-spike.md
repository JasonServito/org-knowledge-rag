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
  - Tokens ≈ characters ÷ 4, counted on the body only (the front matter isn't embedded). This likely underestimates code and YAML, which have more tokens per character.
  - Chunks: split at headings, at most 512 tokens per chunk, plus a 40-token header per chunk. Add 256 and 1024 as sensitivity rows.
  - Lower bound: unique (document, section hash) pairs, because the header holds `canonical_id`, so identical text in two documents is two cache entries. The global section-hash dedup is printed as a one-line floor. (Changed at T3b plan review, 2026-09-30; the T3a notes said "unique section hashes".)
  - Vector storage: chunks × dimension × 4 bytes, at voyage-4's default of 1024 dimensions (docs.voyageai.com/docs/embeddings, updated 2026-08-10). The voyage-4 family also supports 256, 512 and 2048, so add storage rows at 512 and 256 dimensions.
- **For S04:** the chunk header holds only fields that are stable across all versions of a document: `source_type`, `canonical_id`/title, and the heading path. `valid_from`/`valid_until`, tier and flags go in DB columns, because any per-version field in the embedded text defeats the content-hash cache. (Corrected at T3b plan review, 2026-09-30.)

### S02-T4a: Renames `[core]`

- **Goal:** run `git diff --find-renames` between adjacent release branches for the in-scope paths. Grade every detected rename with an oracle (a census), and hand-read a sample.
- **Done when:** the report gives precision on the census and the sample, lists the unmatched add/delete pairs with their classes, and recommends a similarity threshold.

#### T4a notes (decided at plan review, 2026-09-30)

- **Split:**
  - The plan estimated about 260 code lines for T4. The draft, with the blog check, came to about 440 non-blank lines: 335 in the spike and 103 in tests.
  - The blog check's first result was also bigger than expected. So T4 was split into T4a (renames) and T4b (blog identity).
  - T4a as shipped: 267 non-blank lines in `renames.py` plus 83 in tests (350). The overrun comes from the oracle grading asked for at plan review: the census, the threshold deltas, the split section, and the moved-vs-removed classes.
- **Run:** `uv run python spikes/renames.py`, with the same `CORPUS_CACHE_DIR` rule as T2. `fetch.py`'s git helper now also allows `diff`, which is read-only and runs with the network blocked.
- **Census plus sample:**
  - Every detected rename is graded. Docs pages and release records use the redirect file or Hugo `aliases`; feature gates use the front-matter `title`.
  - Read by hand: every title mismatch, all docs renames, and 6 inexact gate renames (seed 4). The 6 are extra qualitative checks.
- **Threshold table:** for each threshold, it shows the wrong pairings added as well as the real renames gained. One run at a 10% floor gives every row. This was checked against separate runs at 50, 60 and 90%.
- **Delete classes:** a redirect counts as a move only if its target was added in the same release. Otherwise the delete is "removed, redirected to an older page".
- **The 1.28→1.29 feature-gate change** is reported on its own: it's a split, not a rename.
- **Tests:** `tests/unit/test_spike_renames.py` needs no git and no cache. Replace it in S04/S05.

### S02-T4b: Blog identity `[core]`

- **Goal:** check whether front-matter blog ids (`blog:<date>-<slug>`, ADR-002 D4) hold across versions, and across website PR #53902's year-folder move:
  1. Break down the id changes by cause (date, slug, missing date) and by whether they happen before or after publication.
  2. Score two identity rules by how many post histories each keeps together:
     - the latest version's date and slug, applied backwards through the path history
     - the Hugo URL from the site's permalink config, with Hugo's slug-or-title fallback. Read the config; don't assume it.
  3. Check whether pre-publication versions explain most of the changes.
- **Done when:** the report has the breakdown and both rules' scores, plus a note for T6: should a blog version's `valid_from` be the publication date rather than the commit date?
- **Size:** aim for about 150 lines.

#### T4b notes

- **From T3a review (2026-09-30):** verify that the ids stay the same across website PR #53902's move: no collisions and no missing slugs. T1's key inventory found `slug` in 411 of 413 in-range posts at the head, so the fallback for a missing slug matters. If the ids hold, S05 uses front-matter identity for the blog, and rename detection is for docs only.
- **From the T4a draft (2026-09-30):**
  - **136 of the 417 in-scope posts change id between versions.** Causes include date edits, slug edits, and early versions with no date.
  - **No collisions.** No id is shared by two posts.
  - **4 in-scope posts have no `slug`:** the 1.21–1.24 release interviews.
  - **The path is a poor fallback.** The path's slug matches the front-matter slug in only 177 of 413 posts. Hugo's `:slug` token falls back to the title; check that against the config.

#### T4b notes (decided at plan review, 2026-09-30)

- **Size:**
  - The plan estimated about 230 lines: 160 in the spike, 60 in tests, 10 in the `measure.py` refactor.
  - As shipped: 315 non-blank lines in `blog_identity.py`, 172 in tests, and +22/−10 in `measure.py`. That's about 500, +117% over the estimate.
  - That's over CLAUDE.md's ~300-line cap with no split proposed before going over. The PR review flagged it.
  - The overrun comes from three places:
    - Hugo fidelity that the data turned out to need: `url:` front matter with tokens, the filename date and slug, the title fallback, and dates that keep their own offset.
    - The checks added at plan review: the publication phases, old-URL coverage, and the move table.
    - The review fixes: the per-post logic moved out of `main()` into tested functions, and a test for `score`.
- **Run:** `uv run python spikes/blog_identity.py`, with the same `CORPUS_CACHE_DIR` rule as T2. It reuses T3a's post histories through `measure.blog_log`, which was split out of `blog_docs`. `measure.py`'s output is byte-identical before and after the split.
- **Publication, as agreed:** the first moment Hugo would render the post: the live version isn't a draft and its date has passed (`buildFuture` is off, `timeZone` is UTC). It's an approximation, because the site builds on merge.
- **The site config is read:** every `config.toml`/`hugo.toml` on `main` since 1.20's date must give the same blog permalink and date order, or the spike refuses to run. All 69 versions do.
- **Caveat:** table J's ground truth is T3a's rename-followed histories (git similarity), not an independent source. One known miss: the kubescape post, renamed at 41% similarity.
- **Tests:** `tests/unit/test_spike_blog_identity.py`, written first. It needs no git and no cache. Replace it in S04/S05.
- **Results:** report §5. 137 of 417 posts change front-matter id, 144 of the 150 changes before publication. No collisions. Over published commits, the Hugo URL keeps 413 of 416 histories whole, and all 349 measured in-scope moves by PR #53902 keep it.

### S02-T5: Format checks `[core]`

Each answered yes/no with an example:

- the actual latest release and branch
- does the feature-gates reference page give a stage per version?
- do blog posts have front-matter dates, and are in-place edits visible in git history?
- CHANGELOG patch-section heading structure
- the `kep.yaml` status/stage values found, including typos

**Done when:** all are answered in the report.

#### T5 notes (decided at plan review, 2026-09-30)

- **Split before starting:**
  - The plan estimated about 300 lines for all five checks: 220 in the spike, 80 in tests. That's at CLAUDE.md's cap, and T3a, T4a and T4b came in 17–117% over their estimates.
  - So T5 is split up front:
    - **T5a:** feature gates, plus the latest-release hand check
    - **T5b:** CHANGELOG, `kep.yaml` and blog
- **T5a, latest release:** a hand check, no code. It uses three local signals:
  - the website's `release-1.R` branch list
  - `hugo.toml` on `main`
  - the `# v1.37.*` headings in `CHANGELOG-1.37.md`

  Optionally add `gh api repos/kubernetes/kubernetes/releases/latest`. Don't download `CHANGELOG-1.38.md`: it's outside the manifest.
- **T5a, feature gates:** "reliable" means the two formats **agree**, not just that each is well-formed.
  - Per release: the format, the gate count, the stage values, and the gates whose ranges have a gap, an overlap, or an unparseable version.
  - Agreement: for gates in both the 1.28 tables and the 1.37 files, compare the 1.28 table's stage at 1.28 with the stage the 1.37 `stages:` ranges give for 1.28. Report agreements and disagreements, with examples.
  - Count the gates that exist only in the pre-1.29 tables.
  - Examples come from in-scope gates: `PodSecurity` (KEP-2579) and the KEP-2799 service-account token gates.
- **T5b scope:**
  - **CHANGELOG:** keep the version-heading uniqueness check. Drop the newest-first and "since" pointer checks.
  - **CHANGELOG immutability:** sample it for one file with read-only `gh api`. Fetch two historical versions and compare the sections they share. Don't change T2's depth-1 clone.
  - **Blog:** no live fetch of the `------` post.
  - **`kep.yaml`:** case and whitespace variants normalize, but an out-of-vocabulary value is reported, not mapped.

#### T5a notes (as shipped)

- **Size:** 188 non-blank lines in `formats.py` and 115 in tests, 303 in total. The split estimated about 150 for T5a (+102%), and the total is right at the ~300 cap. The overrun comes from:
  - the agreement check and the test list that were widened at plan review
  - two parser fixes the data needed:
    - `-` as well as an empty cell means an open Until (591 cells)
    - a stage range can end and restart at a patch release (`1.35.3` → `1.35.4`)
- **Added beyond the plan:**
  - Besides the stage at 1.28, the spike compares the stage at every minor release 1.0–1.28.
  - Reason: 141 of the 293 shared gates have no stage at 1.28 in either format, so "same at 1.28" says nothing about them.
- **Stage vocabulary:** `GA` = `stable` is the only synonym, applied before comparing. Every other value is reported as written.
- **Run:** `uv run python spikes/formats.py`, with the same `CORPUS_CACHE_DIR` rule as T2. It reuses T3a's `ls_tree`, `prefetch` and `read_blobs`, so nothing new downloads.
- **Tests:** `tests/unit/test_spike_formats.py`, written first. It needs no git and no cache. Replace it in S04/S05.
- **Results** (report §6):
  - 1.37 is the latest release, on website `main`.
  - Every gate has stage ranges in every release.
  - The 1.28 tables and the 1.37 files match at every minor release for 287 of 293 gates.
  - 0–3% of gates per release have ranges that leave a stage undefined or ambiguous.
  - Later files rewrite earlier history for 2 gates (`EventedPLEG`, `DynamicResourceAllocation`).

#### T5b notes (decided at plan review, 2026-10-01)

- **CHANGELOG comparison:** pair sections by heading, never by position, because the files are newest first and each release is prepended. Report duplicate headings rather than comparing them.
- **Immutability sample:** `CHANGELOG-1.28.md`, with three comparisons:
  - after v1.28.0 → after v1.28.15
  - after v1.28.0 → the locked head
  - after v1.28.15 → the locked head

  The two historical versions come through read-only `gh api` at pinned SHAs. The report says "one sampled file, not exhaustive".
- **KEP metadata:**
  - Classify `stage` against both the KEP template (alpha/beta/stable) and ADR-003 D5's `lifecycle_stage`, in two columns.
  - Include the 25 single-file KEPs, whose metadata is front matter.
  - Count milestone values that YAML reads as non-strings (an unquoted `1.30` is the float `1.3`; `yes`/`on` are booleans). Show the traced KEPs' raw `latest-milestone` too.
- **Blog:** no update-note regex. Cite T4b's 508 versions in 272 posts, and hand-check one post. Keep the head's date-format list.

#### T5b notes (as shipped)

- **Size:** 283 non-blank lines in `source_formats.py` (247 without docstrings and comments) and 117 in tests, 400 in total. That's 388 at the PR, plus the 2 tests asked for at PR review. The plan estimated about 290 (+38%), over the ~300 cap and past the ~330 point at which the plan said it would stop and propose a split. That wasn't proposed before going over. At PR review the developer chose not to split, and asked for the miss to be recorded here, in the PR body and in the retro. The overrun comes from:
  - the plan-review additions: the second stage vocabulary, the single-file KEPs, the milestone type check, duplicate headings, and their tests
  - a parser fix the data needed: a stray closing fence in a list item (below)
- **Stray fence:** a release note in `CHANGELOG-1.22.md` and one in `CHANGELOG-1.36.md` end with the PR template's closing fence, with no opening one. Toggling on every fence hid 6 sections, and a `grep -c '^# v'` hand count caught it. The spike now ends an indented fence at the next line in column 0, as CommonMark ends a fence with its list item. T3b's `split_sections` still toggles (backlog, S04-T3).
- **Run:** `uv run python spikes/source_formats.py`, with the same `CORPUS_CACHE_DIR` rule as T2. The two `gh api` files are saved under `$CORPUS_CACHE_DIR/gh/`, so a re-run is offline. T2's depth-1 clone isn't touched.
- **Tests:** `tests/unit/test_spike_source_formats.py`, written first. The level-2 split test and the link-target test were added at PR review. It needs no git, cache or network. Replace it in S04/S05.
- **PR review fixes (2026-10-01):**
  - The template vocabulary now includes `deprecated|disabled|removed`, which the template's comment allows for deprecation KEPs.
  - T3b was recounted for `CHANGELOG-1.22.md` and `CHANGELOG-1.36.md` (report §7, table P).
  - The "For T6" items are now questions.
  - Wording fixes: "at least 3" sections, the label claim, the commit description, and the cache-size scope.
- **Results** (report §7):
  - Every CHANGELOG has one unique, parseable `# v1.R.x` section per release: 371 sections in 18 files.
  - In the sample, at least 3 of the 23 sections in `CHANGELOG-1.28.md` changed after they were written. One change is a factual correction 13 months later (PR #125502). That contradicts ADR-002 D1's assumption that sections never change (a T6 question).
  - KEP `status` is always in vocabulary. For `stage`: `GA` (KEP-1611, 7 snapshots) is outside both vocabularies; `disabled` (KEP-4004) is valid under the template but missing from ADR-003 D5; and 76 versions have no stage.
  - No milestone value parses as a non-string.
  - All 412 in-scope blog posts at the head have a front-matter date. PyYAML returns 8 of them, whose offsets have no colon, as strings.

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

#### T6 notes (added at T4a review, 2026-09-30)

- **Docs `canonical_id` = the Hugo URL, not the file path.**
  - ADR-002 D4 currently says `docs:<path under content/en/docs>`.
  - A move into a page bundle keeps the URL: `feature-gates.md` became `feature-gates/index.md` at 1.29, at the same URL, and git can't pair the two (report §4, section H).
  - Redirects then become URL → URL aliases.
- **Declared signals first, similarity as the fallback.**
  - Use redirects, Hugo aliases and the gate title before git similarity.
  - Similarity found only 4 of the 6 docs renames the redirects declare, and it paired two different gates at 40%.
  - A redirect counts as a rename only when its target was added in the same release (report §4, table G).

#### T6 notes (added at T4b review, 2026-09-30)

- **URL identity applies only to rendered pages.**
  - The per-gate files have `_build: render: false`, so they have no URL (report §4, section H), and feature gates keep gate-name identity.
  - The general rule: the URL for rendered pages (docs pages, website release records, blog posts); a declared key for embedded or structured sources (gate name, KEP number, CHANGELOG `1.R`).
- **Identity and content change are separate.** The v1.20 release notes kept their URL identity through the redirect alias (`/docs/setup/release/notes/` → `/releases/notes/`), but became a 13-line pointer to the CHANGELOG. That's one document with a drastic new version, which is correct (report §4, table G).
- **Blog `canonical_id`: the evidence for the URL** (report §5, table J):
  - Over published commits, the Hugo URL keeps 413 of 416 histories whole. All 349 measured in-scope moves by PR #53902 keep it. 2 more weren't measured: they lost their `.md` extension.
  - That it needs no rename following is an inference: the URL never changes across a move, and no URL is shared by two posts. The spike didn't test grouping by URL directly, and its histories come from git (report §5, J).
  - ADR-002 D4's `blog:<date>-<slug>` splits 10, and has no id for the 4 interviews with no `slug`.
  - "Latest date and slug, applied backwards" needs git rename following, and its id differs between publication and the head for 6 posts (5 real).
  - The 3 URL changes after publication: 1 redirect, 1 alias, and 1 with neither (`ingress-nginx-retirement`).
  - That last URL may never have been served. That holds only if builds run on merge, which wasn't checked against the Netlify config or logs. So declared signals cover 2 of 3, too few to call them complete for the blog.
- **A blog version's `valid_from` = max(commit time, publication time).**
  - 317 of the 416 versions live at publication were merged ahead of their date: median 2.6 days, maximum 28.5. With commit time, they'd claim to be public early.
  - **This amends ADR-002 D3.** D3 says `valid_from_date` is "the date of the commit that introduced the change".
  - **Release rows:** D3 derives the release window from `valid_from_date`, and T3a assigned blog versions to rows by commit time. Under this rule, 25 of the 317 move to a later release row.
  - For versions committed after publication, the rule gives the commit time.
- **Question for T6: exclude never-public versions?**
  - 213 versions, in 168 posts, were superseded before publication.
  - 1 more is the kubescape fragment, which was never published.
  - None of these were ever public.
  - Excluding them removes 214 of T3a's 1,138 blog versions (19%), which is 6.5% of the 3,281 embeddable versions.
  - Report §2's per-release counts and §3's cost estimate would both drop. The token effect wasn't computed.

#### T6 notes (added at T5b review, 2026-10-01)

- **`disabled` → ADR-003 D5's claimed-stage vocabulary.**
  - The KEP template allows `deprecated|disabled|removed` for deprecation KEPs, and the enhancements validator accepts all three. So `disabled` is valid, not a typo; ADR-003 D5 just lacks it.
  - T6: add it to the claimed vocabulary (direction at T5b review). Report §7, table R.
- **T3b's CHANGELOG counts were low for 2 files** because of the stray fence (report §7, table P).
  - Recounted with the corrected rule: at 512 tokens, the upper bound gains 96 chunks (55,821 → 55,917, +0.17%) and 3,853 embedded tokens (+$0.0002 at voyage-4); the lower bound gains 72 chunks (+0.27%).
  - The other 16 CHANGELOGs are unchanged.
  - §3's tables weren't edited. The effect on the budget is negligible.

#### T6 notes (as decided, 2026-10-01)

- **How:** each open question was walked through with its options and tradeoffs, and the developer chose the recommended option every time.
- **Result:** ADR-002 and ADR-003 are Accepted. Each ends with a "Changes from the S02 spike" table.
- **Report:** §8 records the validation answers, the 12 decisions, what the spike didn't validate, and what's handed to S03, S04/S05 and S09.
- **Budget:** up to $5 one-off for the Stage 1 embeddings. The estimate ($0.42 realistic, $1.66 worst case) fits.

## Risks & unknowns

- Repo size and clone time. Use partial clones and path filters.
- The path allowlists may miss relevant docs. Note gaps; don't expand scope.

## Decisions expected

ADR-002 and ADR-003 (accept or amend).

## Retro (fill in at the end)

- **Shipped:**
- **Surprises:**
- **Do differently:** core tasks broke the size cap twice without stopping at the promised point (T4b, T5b).
- **Slice brief:**
