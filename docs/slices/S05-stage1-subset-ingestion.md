# S05: Stage 1 subset ingestion

- **Status:** 🟨
- **Blueprint stage:** Stage 2 (the full manifest; S04 was the narrowed first pass)
- **Started:** 2026-10-07
- **Finished:**

## Outcome

`make ingest` on an empty database stores the whole manifest, and a second run, or a second from-empty ingest, gives identical counts and hashes.

The whole manifest means:
- docs pages of 3 SIGs (Release, Auth, Network) and the website release records, at every release v1.20 → v1.37
- the feature-gates reference
- every KEP in the 3 SIG folders
- the governance docs, blog posts and CHANGELOGs

Every chunk text then has a `voyage-4-large` vector.

## Why now

- **S06 freezes a golden set and runs the dense baseline.** Every later ablation row is compared against that baseline, so the corpus must be complete and fixed before it (AC7).
- **It retires S04's known gaps:**
  - releases 1.20–1.23 need rename handling (the PSP page moved at 1.23)
  - seed #9's "why" lives in a blog post
  - seed #14 cites KEP-1205
  - seed #16 cites the feature-gates reference
- **It tests ADR-002's remaining rules on real data:** renames and aliases, blog identity and publication time, CHANGELOG versions, merge-time dating.

## Exit checks

- [ ] `make ingest` from an empty database, then again: the second run adds 0 documents, versions and chunks.
- [ ] Two from-empty ingests print identical reports, fingerprints included (AC8, first part).
- [ ] Per-source document and version counts match the spike (`docs/research/corpus-spike-report.md`, table B) within an explained tolerance: each difference has a stated cause.
- [ ] The 6 known docs and release-record moves (spike §4 E and G) are one document each, with the later URL as an alias.
- [ ] `make embed` gives every distinct chunk text a `voyage-4-large` vector, and a second run makes 0 requests.
- [ ] `make test-int` is green with the dev database fully ingested and embedded.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| Docs pages, 3 SIGs (manifest `docs_page`), every release 1.20 → 1.37 (18 snapshots) | Non-English docs; SIGs outside the manifest |
| Website release records (`releases/`, `setup/release/` at 1.20, the deprecation guide) | — |
| `CHANGELOG-1.R.md` for 1.20–1.37, from the kubernetes lock head | Reconstructing CHANGELOG text from before the first ingestion (ADR-002 D1) |
| Feature-gates reference: the page (1.20–1.28), then one file per gate (1.29+) | Parsing stage ranges into `observed_lifecycle` and `effective_stage` (S09) |
| Every KEP in the 3 SIG folders (README + `kep.yaml`) at each release date plus `head` (S05 sitting, decision 1) | Production readiness review (PRR) files; the 25 old single-file KEPs stay separate documents (ADR-002, known limit) |
| Governance docs (`community`, `sig-release` paths in the manifest) | SIG annual reports (Proposed additions, deferred) |
| Blog posts dated on or after 1.20's release date, one version per content change on `main` | Never-public versions (ADR-002 D3); drafts |
| Renames and aliases (ADR-002 D4) | Refreshing the lock; keeping past `head` SHAs (moved to S14) |
| Chunker fixes: `{#id}` anchors, HTML tables with a blank line in a cell | LLM chunk enrichment (non-goal); the tiny-section merge experiment (S06) |
| An ingestion report command | Tiers, query modes, conflicts (S09, S10) |
| Embedding the full corpus with `voyage-4-large` (S05 sitting, decision 3) | Embedding-model comparisons (after S06) |

## Metric to move

n/a (foundation). The slice is measured by counts against the spike and by identical re-ingests (AC8). The dense-baseline row is S06's.

## Tasks

These mirror `docs/backlog.md`; details live here. Runs are planned one at a time; the expected split is R1 = T1–T3, R2 = T4–T6, R3 = T7–T9.

### S05-T1: Release-scoped website sources from 1.20 `[core]`

- **Goal:** `make ingest` reads the manifest's release-scoped website sources at every release 1.20 → 1.37.
  - These are the docs pages of all 3 SIGs and the website release records.
  - Documents are still identified by path here; T2 adds renames.
- **Done when:** a re-run adds 0 versions, and the counts are explained against the spike.
- **Notes / pointers:**
  - The dev database is rebuilt from empty, because every docs page's first version moves from 1.24 to 1.20 (domain model, "How windows are derived"). Vectors are a cache keyed by content hash, so they can be kept.
  - The `release_record` strip list applies to the release records.
  - Parked report items go to T8; this task only keeps every skip logged.
  - Parked item 10b (moved here from T4 in the R1 sitting): an id equal to another document's alias gives a misleading "history mismatch". It must give the R3 error. T1 hits it on real data: the 1.37 deprecation-policy page's `aliases` holds the old page's URL.
- **Deps:** S04.

### S05-T2: Renames and aliases `[core]`

- **Goal:** a page that moves stays one document (ADR-002 D4).
  - **Declared signals first:** a redirect at release R+1 from the old URL to a page that is new at R+1, or the new page's front-matter `aliases`.
  - **Fallback:** git similarity of 50% or more between adjacent release snapshots.
  - The `canonical_id` is the first URL; later URLs become aliases. Unmatched adds and deletes are logged per release pair.
- **Done when:** the 6 known moves are one document each.
  - The 6 moves: PSP (1.23), version skew (1.21), topology-aware hints → routing (1.27), deprecation policy (1.37, alias only), `setup/release/_index` → `releases/_index` (1.21), release notes (1.21).
  - The 1.29 `overview.md` removal is not a rename (its redirect points to a page that already existed).
- **Notes / pointers:**
  - The redirect file is `static/_redirects` up to 1.33 and `static/_redirects.base` from 1.34 (spike §4).
  - Skip wildcard and placeholder rules; the first rule for a URL wins.
  - `spikes/renames.py` is the independent reference.
- **Deps:** T1.

### S05-T3: Feature gates `[core]`

- **Goal:** the feature-gates reference at every release.
  - The page (1.20–1.28) and `feature-gates/index.md` (1.29+) are one `web:` document (same URL).
  - Each per-gate file is `gate:<name>`, from its front-matter `title`. The removed-gates page and folder follow the same rules.
  - A gate renamed by file only (343 at 1.32) keeps its document. A renamed title (`APIServingWithRoute` → `APIServingWithRoutine`) is found by git similarity of 50% or more.
- **Done when:** the 1.32 file renames create no new documents, and the 40% pair `PodInfoAPI` → `InPlacePodVerticalScalingMemoryBackedVolumes` stays two documents.
- **Notes / pointers:**
  - A gate's stages sit in its front matter, which the chunker drops. Seed #16 needs "beta since 1.36, on by default". Whether to write the stages into the chunk text is a decision for the R1 sitting.
  - About 490 gate files at 1.37, but only 2% of the corpus tokens (spike §3).
- **Deps:** T1, T2.

### S05-T4: KEPs and governance docs (date-scoped) `[core]`

- **Goal:** every KEP in the 3 SIG folders, and the governance docs, read from the default branch at each release date plus `head`.
  - A version is dated by the time its change was **merged** to the default branch (first-parent), not its commit time.
- **Done when:** a re-run adds 0 versions; KEP-2579's versions start at their merge times; counts are explained against the spike.
- **Notes / pointers:**
  - The 25 old single-file KEPs at 1.20 carry their metadata in front matter.
  - KEP-1205's `kep.yaml` holds two YAML documents; only the first is read.
  - Symlinks are skipped.
  - Governance docs have no front matter, so they need a title rule.
  - Parked edge cases:
    - A KEP deleted and re-created skips the date guard and could stop the run with a database error.
    - No test covers a re-ingest that only closes a version.
    - (The alias-vs-id message moved to T1.)
  - `git log --follow` for governance renames was never tested (spike §8).
- **Deps:** T1.

### S05-T5: Blog posts `[core]`

- **Goal:** one version per first-parent commit on website `main` that changes a post's normalized content (ADR-002 D2, D3).
  - Identity is the Hugo URL at publication; a later URL becomes an alias (ADR-002 D4).
  - `valid_from` = max(commit time, publication time). A version superseded before publication isn't stored.
  - Drafts are excluded; posts are in scope when dated on or after 1.20's release date.
- **Done when:** a re-run adds 0 versions; counts are explained against the spike (416 published posts; 1,138 versions minus 214 never public).
- **Notes / pointers:**
  - Front-matter dates come as `date`, `datetime` or text (8 posts use `+0000`).
  - Front matter that fails to parse is logged with a reason (`------`).
  - Hugo's title-to-slug rule is approximated (spike §5).
  - `spikes/blog_identity.py` is the independent reference.
- **Deps:** T1.

### S05-T6: CHANGELOG `[core]`

- **Goal:** `CHANGELOG-1.R.md` for 1.20–1.37 as `changelog:1.R` (`release_record`).
  - Release window `[R, R]`; the date window starts at the kubernetes lock head (ADR-002 D1, D3).
  - Chunks fall per patch section (heading path starting `v1.R.x`).
  - The generated table of contents and the sha512 download tables are left out of chunks.
- **Done when:**
  - 18 documents and 371 patch sections (spike §7 P).
  - No chunk holds a sha512 row.
  - `close_version` refuses to change a release `until` that is already set.
- **Notes / pointers:** stray closing fences at `CHANGELOG-1.22.md` line 3085 and `CHANGELOG-1.36.md` line 1602 (rule 3 handles them).
- **Deps:** T1.

### S05-T7: Chunker fixes `[core]`

- **Goal:**
  - Strip Hugo `{#id}` anchors from heading paths.
  - Add scanner rule 5: an HTML table with a blank line inside a cell isn't cut.
  - Re-check the scanner against markdown-it on the S05 sources.
  - Added in the R3 sitting: cut oversize lists and pipe tables (decision 1), drop HTML comment blocks (rule 6, decision 2), the "Downloads for" rule on every source (decision 4).
- **Done when:**
  - 0 heading paths contain `{#`.
  - The RBAC page's 30 cut HTML tables are whole: 2 in each of its 15 versions. (Corrected in the R3 sitting: 12 was S04's scope.)
  - The scanner's headings match markdown-it's on every S05 source, or each difference is listed and explained.
- **Notes / pointers:**
  - S05 rebuilds the database from empty, so no re-chunk machinery is needed; vectors are reused by content hash.
  - From the triaged backlog items:
    - **Rule 5:** 12 of 78 HTML tables in the S04 scope (all on the RBAC page) are cut into 24 chunks. Recheck with it: a tab-indented line would close an indented fence under rule 3 (0 cases in S04).
    - **Anchors:** 1,754 of S04's 4,967 chunks have an anchor in `heading_path`. S06 labels relevance by heading path. The parked item suggested keeping the id for citation URL fragments; where it goes is an R3 decision.
  - **Oversize blocks, decided in the R3 sitting (decision 1)** (measured in the R1 sitting with today's chunker; full-corpus numbers in run S05-R3's contract).
    - Lists without blank lines and pipe tables count as one block, and a block is never cut. So they become single chunks far over 512 tokens.
    - The pre-1.29 feature-gates page reaches **11,219 tokens** in one chunk.
    - R1 sources have 33 chunks over 2,000 tokens.
    - A preview of `CHANGELOG-1.30` gives 275 chunks, where 32 over 1,024 tokens hold 51,056 of its 108,825 tokens (47%), mostly release-note lists.
    - Option to weigh: cut an oversize list between items and an oversize pipe table between rows, repeating the header row. Code blocks and HTML tables stay whole.
  - The scanner already matches markdown-it on every R1 source: 1,382 distinct files, 8,239 headings, 0 differences (R1 sitting).
- **Deps:** T1–T6 (so the re-check covers every source).

### S05-T8: Ingestion report `[commodity]`

- **Goal:** `make ingest` ends with a report, and `make ingest-report` prints its database part (R3 sitting, decision 7):
  - documents, versions, chunks and distinct texts, per source type and per release
  - skipped and failed files with reasons (`make ingest` only)
  - a fingerprint over every stored value except generated ids, to compare two ingests (R3 sitting, decision 8; was "`canonical_id`, version hashes and windows")
- **Done when:** two from-empty ingests print identical reports.
- **Notes / pointers:** the parked "clearer failures" items:
  - each failure line carries its snapshot label
  - a skipped file is counted once, not once per snapshot
  - a manifest path absent from every release in range is an error
- **Deps:** T1–T6.

### S05-T9: Embed the full corpus `[commodity]`

- **Goal:** `make embed` over the full corpus with `voyage-4-large`, with the per-run token cap raised to fit (about 5.5–6.5M estimated tokens, inside the free tier). The cap is raised for that one command only (R3 sitting, decision 9).
- **Done when:** every distinct chunk text has a vector, a second run makes 0 requests, and Voyage's token count is recorded against the chars ÷ 4 estimate.
- **Deps:** T7, T8.

## Risks & unknowns

- **Scale:** about 15× S04's documents.
  - The spike already downloaded the blobs, so ingestion should need no network, but run time on 18 releases × 5 repos is unmeasured.
- **The rebuild changes ids:**
  - Chunk ids cited in `eval/results/s04/` stop resolving. They're historical outputs.
  - The PSP page's `canonical_id` becomes its 1.20 URL, with the 1.23+ URL as an alias.
- **Runs came out 2.2× their estimates in S04.** Each run sitting estimates reviewable lines and splits for size there.
- **The scanner was checked on S04 data only.** CHANGELOG list-item headings already differ from CommonMark (2 in `CHANGELOG-1.36`).
- **Untested assumptions:**
  - `git log --follow` for governance docs
  - grouping blog versions by URL without git rename following
  - the blog publication time assumes the site builds on every merge (spike §8)
- **Feature-gate stages live in front matter,** outside the chunk text, unless T3 writes them in.

## Decisions expected (ADRs)

- **Slice sitting (2026-10-07), done:**
  - triage of 13 parked items
  - decision 1: all KEPs in the 3 SIG folders, not 4
  - decision 2: feature gates in S05
  - decision 3: the full embed is S05's last task
- **R1 sitting (2026-10-07), done:** see run S05-R1 below. The full scope is Claude's call; the from-empty reset is decision 2; the rename rules are Claude's calls within ADR-002 D4; feature-gate stages in the chunk text are decision 1.
- **R2 sitting (2026-10-07), done:** see run S05-R2 below. Decisions 1–9; decision 2 amends ADR-002 D4 (devil's advocate run), decisions 1 and 3 add to ADR-002 D3 and D4.
- **R3 sitting (2026-10-07), done:** see run S05-R3 below. Decisions 1–9 and the PR plan; decision 6 changes the ADR README's rule for changed sub-decisions (no ADR changes).
- No new ADR is expected: ADR-002 and ADR-003 already decide the rules. A rule that turns out wrong on real data is an ADR-002 amendment, decided in a sitting (as R2's decisions 1–3 did).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S05-R1: release-scoped website sources

- **Status:** merged (PRs #27, #28)
- **Branch:** `s05-r1-release-scoped`. PR 1's branch `s05-r1a-docs-from-1-20` is cut at T2's last commit.
- **Tasks, in this order:** S05-T1 (from-1.20 loop) → S05-T2 (renames and aliases) → S05-T3 (feature gates).
- **Closes the slice:** no. T4–T9 remain (R2 and R3, each after its own sitting).
- **Goal (plain words):**
  - Ingest the docs pages of all 3 SIGs, the website release records and the feature gates at every release 1.20 → 1.37.
  - A page or gate that moves or is renamed stays one document, with its later URLs or names as aliases.
  - A gate's stages reach its chunk text.
  - The dev database can be rebuilt from empty while keeping its vectors, and a re-run changes nothing.

#### Decisions (made in the sitting, 2026-10-07)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Triage of 13 parked items: 9 folded into S05 tasks (blog front matter, CHANGELOG download tables + TOC, blog date types, R10 freeze, KEP merge time, scanner rule 5, `{#id}` anchors, ingestion edge cases, report failures); the extensionless interviews dropped; past `head` SHAs → S14; the cut-off stop reason → the S06 sitting | Fixing each now | Recorded in `docs/backlog.md`. The 1.23 interview's URL returns 404 on kubernetes.io (Hugo ignores files without an extension) while the 1.22 one renders, so the `*.md` filter is right |
| S2 | S04-R2 question 2: the rule becomes "**secret** keys never appear in stdout, stderr or the trace"; the Langfuse public key may appear | Patching the Langfuse SDK | Langfuse treats the public key as non-secret |
| S3 | All KEPs in the 3 SIG folders (113 at the head) | The 4 traced KEPs (the backlog's wording) | The manifest defines the subset (ADR-002 D6); seed #14 cites KEP-1205; the spike measured all of them |
| S4 | Feature gates are in S05 | Defer to S09 | The corpus must be fixed before the S06 baseline (AC7); seed #16 cites them |
| S5 | The full embed is S05's last task (T9) | The first task of S06 | Chunk texts are final at S05's end, so the corpus is embedded once |
| S6 | Bundle T1 → T2 → T3 | — | All three read the website release branches; T3 reuses T2's chain builder |
| 1 | A `gate:` document's chunk body starts with its `stages` (and `removed`) front matter as YAML (pinned below) | One formatted line; leaving stages out | Lossless, no formatting rules, and it's the file's own text, not enrichment. Seed #16 needs "beta since 1.36, on by default" |
| 2 | `make reset-corpus` empties `documents`, `document_aliases`, `document_versions` and `chunks` (ids restart at 1); `releases` and `embeddings` are kept | Recreating the database; a `psql` line in the README | S05 rebuilds at least 4 times; vectors are a cache keyed by content hash; restarted ids make chunk ids identical across from-empty ingests |
| 3 | Oversize chunks (uncut lists and tables, up to 11,219 tokens) are parked to the R3 sitting (T7), with the numbers in T7's notes | Fixing them in R1 | Not R1's scope; S05 re-chunks from empty before T9 embeds |
| 4 | Parked item 10b (the R3 error message) moves from T4 into T1 | Leaving it in T4 | T1 hits it on real data (the deprecation-policy pair) |
| 5 | The verification plan below | — | — |
| 6 | 2 stacked PRs, split after T2 | Split after T1; 1 PR | A PR 1 ending at T1 would merge a known failure into `main`; ~1,700–2,300 reviewable lines |

No ADR-level decision, so no devil's advocate. The link rules below implement ADR-002 D4 without changing it.

**Claude's calls (overrulable):**
- **Scope:** a `full` entry in the manifest's `scopes:` block (pinned below). `INGEST_SCOPE` defaults to `full`; the `s04` scope stays.
- **Layout:**
  - `src/orgknow/ingestion/renames.py` (new, pure functions): redirect parsing, the link rules, chain building.
  - `git_reader.py`: list similarity renames between two snapshots (`git diff -M50% --name-status -z <a> <b> -- <paths>`); read the redirect file with the existing `read_file`.
  - `identity.py`: `gate_canonical_id(title)`.
  - `chunker.py`: the stages YAML.
  - `ingest.py`: one collector for every release-scoped group.
- **Link rules**, one release pair R → R+1 at a time. A link joins a file present at R and gone at R+1 to a file absent at R and present at R+1. The first rule that links wins, and similarity is read only for files no earlier rule linked.
  - **Web pages** (docs pages, release records, the 2 feature-gate pages):
    1. Same canonical id. This covers page bundles: `feature-gates.md` → `feature-gates/index.md`.
    2. The redirect file at R+1 maps the gone URL to the new URL.
    3. The new page's front-matter `aliases` holds the gone URL.
    4. git similarity ≥ 50%.
  - **Gate files:**
    1. Same path.
    2. Same front-matter `title`.
    3. The new file's `former_titles` holds the gone file's title.
    4. git similarity ≥ 50%.
  - **Refused links:**
    - A gone file claimed by two new files (or the reverse) isn't linked; it's logged as a conflict (0 on real data).
    - A link never crosses source types: an error (0 on real data).
    - A redirect to a URL that existed at R is a removal, not a link.
- **Redirects:**
  - Read `static/_redirects` at R+1, else `static/_redirects.base`.
  - Lines are `<from> <to> [status]`. Comments, and rules whose source contains `*` or `:`, are skipped; the first rule per source wins.
  - URLs are normalized as in `spikes/renames.py`: the `https://kubernetes.io` prefix removed, fragment and query dropped, lowercased, trailing slash added.
- **Ids and aliases:**
  - `canonical_id` = the chain's first URL (`web:`) or first title (`gate:<title>`, case kept).
  - Every later URL or title in the chain becomes an alias. Front-matter `aliases` become aliases, as in S04. `former_titles` never become aliases.
  - An alias equal to the document's own id is skipped, as in S04.
- **Unmatched adds and deletes:** logged at INFO per release pair, with the redirect target if there is one.
- **Two source groups:** a file matched by two groups' paths is an error, before any write.
- **`make reset-corpus`:** `TRUNCATE documents, document_aliases, document_versions, chunks RESTART IDENTITY CASCADE` through `docker compose exec -T db psql -U orgknow -d orgknow`. Dev database only; `make test-int` uses its own database.
- **Stages YAML:** only for `gate:` documents whose metadata has `stages`; read from the version's file at chunk time: the same values as its `metadata`, in the file's key order, because Postgres `jsonb` reorders keys. (Corrected in the R2 sitting; was "built from the version's `metadata`".)
- **Parked 10b:** `store_document` looks a document up by `canonical_id` only (a new read in `db/documents.py`), so an id that is another document's alias reaches `create_document`'s R3 check.
- **Docs:** each task updates `docs/domain-model.md` (windows from 1.20, the link rules, gate identity, a gate's chunk text, the reset).

#### Pinned formats

**Manifest scope** (appended to `scopes:`):

```yaml
  # S05: grows task by task until it is the whole manifest (S05-R1 sitting).
  full:
    docs_page: {sigs: [auth, network, release], from_release: "1.20"}
    release_record: {repos: [website], from_release: "1.20"}  # T6 adds kubernetes (CHANGELOG)
    feature_gate_reference: {from_release: "1.20"}  # added by T3
    kep: {traced: [2579]}  # as in S04 until T4
```

**A gate's chunk text** (decision 1): the header, a blank line, the YAML, a blank line, then the body.

```
Source: feature_gate_reference
Title: StrictIPCIDRValidation
Document: gate:StrictIPCIDRValidation

stages:
- stage: alpha
  defaultValue: false
  fromVersion: '1.33'
  toVersion: '1.35'
- stage: beta
  defaultValue: true
  fromVersion: '1.36'

Use stricter validation for fields containing IP addresses and CIDR values.
…
```

- The YAML is `yaml.safe_dump(..., sort_keys=False)` of `stages`, then `removed` if present, and nothing else.
- Test expectations for it are written by hand, never produced with `yaml.safe_dump`.

**Canonical ids:**
- Web: as in S04 (`docs_canonical_id`), now also for `content/en/releases/…` → `web:/releases/…/`.
- Gate: `gate:` + the front-matter `title` as written (ADR-002 D4).

#### Handoffs between tasks

- **T1 → T2:**
  - Per release-scoped group (source type, repo, paths, strip list): every file's raw content at each of the 18 snapshots.
  - A collector that turns "the chain of files of one document" into a `Document`. In T1 a chain is one path.
  - `make reset-corpus`.
- **T2 → T3:** `renames.py`'s chain builder, which takes a group's per-snapshot listings and its link rules, plus the git similarity reader.
- **T3 → R2/R3:**
  - `gate:` documents with `stages` in `metadata`, for S09.
  - The chain builder, for any later release-scoped source.

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **T1:**
  - 18 website snapshots (1.37 = `main` at the lock head). A page older than 1.20 starts at 20.
  - Manifest paths absent from some releases are logged, e.g. `reference/networking/` before 1.25 and `setup/release/` after 1.20.
  - **Expected T1-only failure:** the deprecation-policy pair, with an R3 error naming the alias. It's gone after T2. T1's demo exits non-zero for this reason only.
  - KEP-2579 still ingests as in S04 (commit-time dates until T4).
  - `make test-int` passes with the dev database rebuilt.
  - Ingest run time at 18 releases is measured and reported.
- **T2:**
  - A redirect to a page that existed at R (`overview.md` → `/docs/concepts/security/`, 1.29) is a removal.
  - A redirect to an out-of-scope page added at R+1 (2 cases): the version closes, and nothing links.
  - A page moved in from out of scope (`ports-and-protocols.md`, 1.25) is a new document.
  - The 1.37 deprecation-policy move adds no version, because only the stripped `aliases` key changed. Its open version keeps `source_path` at the old path and snapshot 1.31.
  - No page is present at both its old and new path in one release (checked: 0).
- **T3:**
  - The feature-gates page and `feature-gates/index.md` share a URL: one document (12 versions). The removed-gates page likewise (5 versions).
  - The 316 gate files new at 1.29 (split out of the tables) are new documents; nothing links them to the page.
  - The title fixed in place (`ServiceAcccount…` → `ServiceAccount…` at 1.35): same path, so one document, whose id keeps the typo.
  - `former_titles: PodHasNetworkCondition` while that gate keeps its own file: no link, no alias, no R3 error.
  - `PodInfoAPI` → `InPlacePodVerticalScalingMemoryBackedVolumes` at 40%: two documents.
  - Stage values can carry trailing spaces (`alpha `). YAML drops a trailing space after an unquoted value, so it is read as `alpha`; a quoted `'alpha '` keeps its space. The code trims nothing. (Corrected in the R2 sitting; was "kept as written".)
  - 233 gate versions have `removed: true`. 242 distinct file contents have a `removed` key (238 true, 4 false); 5 of the true ones hash like the version before them, so they add no version. (Corrected in the R2 sitting; was 242.)
  - 0 duplicate titles at any release (checked). A duplicate is an error, never a silent merge.
- **SQL:** no string-built SQL (ADR-005); the reviewer checks by hand.

#### Files in scope

- **T1:**
  - `config/corpus_manifest.yaml` (the `full` scope only)
  - `src/orgknow/ingestion/manifest.py`, `ingest.py`
  - `src/orgknow/db/documents.py` (the strict lookup)
  - `src/orgknow/settings.py`, `.env.example` (`INGEST_SCOPE` default)
  - `Makefile` (`reset-corpus`), `README.md` (the command list)
  - `docs/domain-model.md`
  - `tests/unit/`, `tests/integration/`, `tests/fixtures/` (small real files, pinned)
- **T2:** `src/orgknow/ingestion/renames.py` (new), `git_reader.py`, `ingest.py`, `identity.py` if needed, `docs/domain-model.md`, tests, fixtures (redirect-file excerpts).
- **T3:** `config/corpus_manifest.yaml` (the `feature_gate_reference` scope entry), `identity.py`, `renames.py`, `chunker.py`, `ingest.py`, `docs/domain-model.md` (gate identity, a gate's chunk text), tests, fixtures (4–5 real gate files), `docs/architecture.md` (at the end of the run).
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Out of scope:**
  - KEPs beyond keeping KEP-2579 as in S04; governance docs, blog, CHANGELOG (R2)
  - chunk-size rules and anchors (T7)
  - `make embed`, and any retrieval or generation change
  - the strip lists and every other manifest block
  - migrations
  - `eval/`

#### Proof map

| Task | Done when / rule | Proof | Source of expected values |
|---|---|---|---|
| T1 | Re-run adds 0 versions (done when) | Integration test on a tiny git repo (ingest twice, count rows) + demo: the second `make ingest` prints 0 new versions | — |
| T1 | Release records use their own strip list | Unit test: a `card`-only change keeps the hash; a body change changes it | Manifest `release_record` strip list |
| T1 | Counts before renames | Demo: release records **11 documents / 55 versions**; docs pages: of **67 paths**, 66 stored + exactly 1 failure, the deprecation-policy pair, with an R3 message | Spike code (`spikes/measure.py`), run in the sitting |
| T1 | Clear R3 error (parked 10b) | Integration test: storing a document whose id is another document's alias raises the R3 error, not `HistoryMismatch` | Hand-written |
| T1 | A file in two groups is refused | Unit test on a hand-built scope | — |
| T1 | Reset | Demo: after `make reset-corpus`, 0 documents, versions and chunks; `releases` and `embeddings` counts unchanged; after `make ingest`, `min(chunks.id)` = 1 | — |
| T2 | **The 6 moves are one document each (done when)** | Unit tests of the chain builder, one per signal (redirect, alias, similarity) + an integration test on a tiny git repo with a move and a redirect file + the demo query | Windows below: git + spike hashes, computed in the sitting |
| T2 | The 6 windows | PSP `[20,20] [21,22] [23,23] [24,24] [25,–]`; topology hints → routing `[21,22] [23,24] [25,25] [26,26] [27,29] [30,–]`; version skew `[20,20] [21,22] [23,23] [24,26] [27,27] [28,–]`; releases index `[20,20] [21,22] [23,29] [30,32] [33,34] [35,–]`; release notes `[20,20] [21,21] [22,–]`; deprecation policy `[20,20] [21,21] [22,22] [23,24] [25,26] [27,28] [29,30] [31,–]` | Same |
| T2 | `canonical_id` = the first URL | Test: the PSP document is `web:/docs/concepts/policy/pod-security-policy/`; `web:/docs/concepts/security/pod-security-policy/` is its alias | ADR-002 D4 |
| T2 | A removal isn't a rename | Test: a redirect to a page that existed at R (`overview.md`, 1.29) links nothing | Spike §4 G |
| T2 | Redirect parsing | Unit tests: `*` and `:x` rules skipped; the first rule wins; full URL, fragment, query, case and trailing slash normalized; `_redirects` read before `_redirects.base` | Spike §4; hand-written lines |
| T2 | Final counts | Demo: **docs pages 64 / 405; release records 8 / 55; 7 web aliases** (6 from chains + `web:/rbac/`); docs pages valid per release 1.20 → 1.37: 29, 30, 35, 36, 42, 48, 51, 50, 52, 52, 53, 54, 55, 57, 57, 58, 60, 60; release records 4 at 1.20, then 8; 0 failures | Spike code + the 6 known moves, in the sitting |
| T3 | **The 1.32 file renames create no new documents (done when)** | Unit tests of the gate rules + demo: **feature gates 491 documents / 868 versions** (pages 2 / 17: main 12, removed 5; gates 489 / 851) | Spike code + git `-M50%`, in the sitting |
| T3 | Title fixed in place | Test: one document `gate:ServiceAcccountNodeAudienceRestriction`, `[33,34] [35,–]`, alias `gate:ServiceAccountNodeAudienceRestriction` | Git, in the sitting |
| T3 | Renamed title found by similarity | Test: `gate:APIServingWithRoute` `[32,32] [33,–]`, alias `gate:APIServingWithRoutine`; a 40% pair stays two documents | Spike §4 E |
| T3 | `former_titles` isn't an alias | Test: `former_titles` naming a gate that keeps its own file gives no link, no alias and no error | Sitting (`PodHasNetworkCondition`) |
| T3 | Stages in the chunk text (decision 1) | Unit test on the real `StrictIPCIDRValidation` file: the exact chunk text pinned above, written by hand | Pinned format |
| Bundle | All three together | After T3: docs pages 64 / 405; release records 8 / 55; feature gates 491 / 868; KEP 1 / 4; **9 aliases** (7 web + 2 gate) | Sum of the rows above |

#### Break-it rules

- **T1:**
  1. **Most important.** Make a re-run always insert (bypass `plan_changes`) → the idempotency test fails.
  2. Apply the docs strip list to release records → the release-record hash test fails.
  3. Look the id up through aliases again → the R3 message test fails.
- **T2:**
  1. **Most important.** Accept a redirect to a page that existed at R → the removal test fails.
  2. Drop the redirect signal → the release-notes test fails (git can't pair it).
  3. Use the latest URL as `canonical_id` → the PSP id test fails.
- **T3:**
  1. **Most important.** Identity by title only (no same-path rule) → the typo test fails (two documents).
  2. Store `former_titles` as aliases → the `former_titles` test fails.
  3. Drop the stages YAML → the `StrictIPCIDRValidation` chunk test fails.
- After every restore, `git status --short` is clean (new files: compare sha256).

#### Real-data demos

- **T1:**
  - `make reset-corpus && time make ingest`, then the counts query, then `make ingest` again:

    ```bash
    docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT d.source_type, count(DISTINCT d.id) AS documents, count(v.id) AS versions FROM documents d JOIN document_versions v ON v.document_id = d.id GROUP BY 1 ORDER BY 1"
    ```

- **T2:**
  - From empty again, then the counts query.
  - The 6 chains: canonical id, aliases, and each version's release window and `source_path`.
  - Docs pages valid per release:

    ```bash
    docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT r.version, count(DISTINCT d.id) FROM releases r JOIN document_versions v ON v.valid_from_release <= r.minor AND (v.valid_until_release IS NULL OR v.valid_until_release >= r.minor) JOIN documents d ON d.id = v.document_id AND d.source_type = 'docs_page' WHERE r.minor BETWEEN 20 AND 37 GROUP BY r.version, r.minor ORDER BY r.minor"
    ```

  - The unmatched adds and deletes from the ingest log.
- **T3:**
  - From empty again, then the counts query.
  - The 3 gate cases (typo, `APIServingWithRoute`, `PodInfoAPI`).
  - The stored chunk text of `gate:StrictIPCIDRValidation`'s current version.

#### Bundle-level check

1. `make check`
2. `make reset-corpus && make ingest`, then `make ingest` again: 0 new documents, versions and chunks; exit 0
3. The counts query: every value in the proof map's Bundle row
4. `make test-int`, with the dev database ingested
5. `git status --short` clean after every break-it restore

#### PR plan

- **2 stacked PRs** (decided in the sitting; estimate ~1,700–2,300 reviewable lines):
  - **PR 1:** `s05-r1a-docs-from-1-20`, cut at T2's last commit: the contract, the backlog update, T1 and T2 ("every docs page from 1.20, one document per page"). Expected above the ~800-line alarm; accepted in the sitting.
  - **PR 2:** `s05-r1-release-scoped`, based on PR 1: T3 ("feature gates").
- Merge rule: retarget PR 2 to `main` before merging PR 1.
- Greptile once per PR (6 → 8 of 50). Record each PR's size in its brief.

**Paid calls allowed:** none. No Voyage and no Anthropic calls, and `make embed` doesn't run. After the reset, `orgknow ask` only finds texts whose vectors were kept; that's expected until T9.

### Run S05-R2: date-scoped sources and CHANGELOG

- **Status:** merged (PR #29)
- **Branch:** `s05-r2-date-scoped`
- **Tasks, in this order:** S05-T4 (KEPs and governance docs) → S05-T5 (blog posts) → S05-T6 (CHANGELOG).
- **Closes the slice:** no. T7–T9 remain (R3, after its own sitting).
- **Goal (plain words):**
  - Ingest every KEP in the 3 SIG folders, the governance docs, the blog posts dated from 1.20, and the 18 CHANGELOGs.
  - A date-scoped version is dated by when its change was merged to the default branch (a blog post's first public version by when it was published).
  - A governance doc that moves stays one document.
  - CHANGELOG chunks hold release notes only: no generated TOC and no download tables.
  - A re-run changes nothing.

#### Decisions (made in the sitting, 2026-10-07)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Triage of R1's 17 parked items and T4's 2 edge cases: P2 (a CHANGELOG snapshot of its own) → T6; P4 (delete `test_spike_renames.py`) → retro; P9 (the absent-path log) → T8; P11 (a wrong docstring), E1 (a re-created KEP), E2 (a close-only re-ingest) → T4; P13 (3 R1 contract lines) corrected in this commit; the other 11 dropped (0 cases on real data, or settled by convention) | Fixing each now | Each dropped item has 0 cases on real data or is a convention already in force |
| S2 | Bundle T4 → T5 → T6 | — | All three depend only on T1; backlog order |
| 1 | A date-scoped version whose start is before 1.20's release date keeps its true `valid_from_date`; its `valid_from_release` is 20, the scope's first release | Clamping the date too; adding releases 1.0–1.19 | The date window is authoritative for date-scoped sources (ADR-002 D3). 67 documents (48 KEPs, 19 governance docs) start before 2020-12-08, the earliest KEP on 2019-06-29 and the earliest governance doc on 2018-12-05; today's code raises on all of them (governance date corrected in the R3 sitting) |
| 2 | **ADR-002 D4 amendment.** Governance moves: R1's chain builder on the date snapshots, with the links same path, then git similarity ≥ 50% between adjacent snapshots. The first path is the id; later paths are aliases | `git log --follow` (the ADR's wording); no rename handling | Finds all 8 real moves (sig-release PR #2984, 1.36 → 1.37, 66–100%); reuses tested code. Devil's advocate run: its concession condition (the per-commit log shows the same 8 pairs and no edit before a move) was checked and holds: the 8 moves, 4 deletes and 2 adds are one commit |
| 3 | The 25 old single-file KEPs (1.20 only) are separate documents with `kep:<sig folder>/<file name>`, e.g. `kep:sig-auth/0014-dynamic-audit-configuration` | `kep:<file name>`; linking to the later folder by title; skipping them | Keeps the S02 known limit; unique by construction; can't be read as a KEP number. Linking by title (24 of 25 match exactly) → Proposed additions |
| 4 | A governance doc's title is the version's first `# ` heading with HTML comments removed, else its repo path. A CHANGELOG's title is `CHANGELOG-1.R` | The path always; titles in the manifest | 152 of 154 governance versions have a `# ` heading, always their first heading; the 2 without: `artifacts.md` (4 versions), `platforms/guide.md` (a "moved" stub) |
| 5 | Blog histories follow git renames in one first-parent log of `_posts/` (the spike's method); the permalink pattern lives in the manifest | Grouping commits by URL; reading `hugo.toml` at ingest | The spike measured this method (785 histories, 417 in scope); all 69 site-config versions since 1.20 have the same permalink |
| 6 | A CHANGELOG version's `valid_from_date` is the kubernetes lock head commit's committer time, 2026-09-30T01:30:57Z | The lock's `fetched_at`; a deeper clone | A git fact, reproducible from the clone; ADR-002 D1/D3 (no history before the first ingestion) |
| 7 | `close_version` refuses to change a release `until` that is already set (ValueError); passing the same value is fine. R10 becomes "A window is closed once. Only an open version can be closed, a release `until` set at insert never changes, and nothing reopens or moves it" | Silently keeping it; a trigger; no change | One SQL condition where R10 already lives; the S03 review finding |
| 8 | CHANGELOG chunks leave out the text before the first heading (the generated TOC) and every section under a `## Downloads for …` heading | Only the sha512 rows; only the rows, keeping the TOC | All 8,397 sha512 rows sit inside those sections (corrected in the R3 sitting; was 8,477); they are 42% of the 7.74M CHANGELOG characters, and the TOC is 3% |
| 9 | The 50% rename threshold stays a named constant that cites ADR-002 D4. Rule: a value an ADR fixes is a constant that cites its ADR; tuning knobs stay in settings | A setting; the manifest | It's an identity rule: changing it changes `canonical_id`s, which needs an ADR, not an env var |
| 10 | The verification plan below | — | — |
| 11 | **1 PR**, an explicit exception to the ~800-line size alarm (estimate ~2,000–2,600 reviewable lines); the run doesn't split it | 2 stacked PRs, split after T4 (recommended) | The developer's call in the sitting |

**Claude's calls (overrulable):**
- **Merge time:** a date-scoped version starts at the committer time, in UTC, of the **last first-parent commit** touching the document's files between the previous snapshot and this one (`git log --first-parent --format=%cI <prev>..<snap> -- <paths>`). For the first snapshot, the range is all of its history. The paths are the document's files at both snapshots, so a move or a KEP slug rename is seen.
- **Front matter** may open with 3 or more dashes, as Hugo renders it (the VAP GA post opens with `------` and renders on kubernetes.io, checked in the sitting). Applies to every source; 0 R1 files change, because none opened that way.
- **Old single-file KEPs:** hashed with the `kep_yaml` strip list; `metadata` is the front matter; `claimed_status` comes from its `status` (24 of 25 have one), and `claimed_stage` is null (none has a `stage`). The chunk title is the front-matter `title`, with no `KEP-<n>:` prefix. The body is chunked without its front matter.
- **Blog scope:** the page date of the version live at publication is on or after 2020-12-08 (00:00 UTC), and the post was ever published. Posts out of scope are counted, not logged one by one.
- **Layout:**
  - `src/orgknow/ingestion/blog.py` (new, pure functions): the Hugo URL, the publication moment, a post's versions.
  - `git_reader.py`: first-parent commit times; the blog log reader.
  - `history.py`: the release clamp, the re-creation guard (E1), the CHANGELOG version.
  - `identity.py`: the old-KEP, governance, blog and CHANGELOG ids.
  - `renames.py`: the date-snapshot link rules (same path, then similarity).
  - `chunker.py`: the governance title; single-file KEP bodies; the CHANGELOG exclusions and title.
  - `db/versions.py`: R10.
  - `ingest.py`: one collector per source.
- **Docs:** each task updates `docs/domain-model.md`. `docs/architecture.md` is updated once, at the end of the run.

#### Pinned formats

**Manifest scope** (`full` replaced; `s04` unchanged):

```yaml
  full:
    docs_page: {sigs: [auth, network, release], from_release: "1.20"}
    release_record: {repos: [website, kubernetes], from_release: "1.20"}  # kubernetes (CHANGELOG) added by T6
    feature_gate_reference: {from_release: "1.20"}
    kep: all  # every KEP in sources.kep.sig_dirs (T4)
    governance_doc: all  # T4
    blog_post: all  # T5; sources.blog_post.from_release and exclude_drafts apply
```

**Blog permalink** (added to `sources.blog_post`):

```yaml
    # Hugo's blog permalink; the same in all 69 site-config versions since 1.20 (spike §5).
    permalink: "/:section/:year/:month/:day/:slug/"
```

**Canonical ids:**
- KEP folder: `kep:<number>`, as in S04. A slug rename keeps the number (1669, 3257, 4444): one document.
- Old single-file KEP: `kep:` + its path under `keps/` without `.md`: `kep:sig-auth/0014-dynamic-audit-configuration`.
- Governance: `community:<path>`, `sig-release:<path>` (ADR-002 D4), from the chain's first path: `sig-release:release-engineering/versioning.md`, with alias `sig-release:release-engineering/reference/versioning.md`.
- Blog: `web:` + the URL at publication, normalized like web URLs (lowercase, trailing slash): `web:/blog/2025/11/12/ingress-nginx-retirement/`.
- CHANGELOG: `changelog:1.R`.

**Blog rules (ADR-002 D2–D4, decision 5):**
- **History:** one entry per first-parent commit on website `main` (up to the lock head) touching a post's `.md` file, following renames (`git log --first-parent --find-renames --raw -z`). An entry's state is the file's content at that commit, or none once deleted.
- **A version** is an entry whose normalized hash (the `blog_post` strip list) differs from the previous entry's.
- **Due time** of a state: none if it's deleted or `draft: true`; else `publishDate`, else the page date (front-matter `date`, else the filename's `YYYY-MM-DD-`, else `publishDate`, else `lastmod`; `publishDate` added in the R3 sitting, as built), else the commit time. A date without an offset is UTC; one with an offset keeps it; `+0000` (no colon) is parsed too.
- **Publication** is the first moment Hugo renders the post: for each entry in order, max(commit time, due time), if that is before the next entry's commit time (or it's the last entry). A post never published isn't stored.
- **Stored versions:** the version live at publication, from the publication moment, then every later version, each from its commit time. A version superseded before publication isn't stored. After publication, a deletion or `draft: true` closes the open version at that commit; a later rendered version opens a new one.
- **URL** (as `spikes/blog_identity.py`'s `hugo_url`): the front-matter `url:` (tokens allowed), else the permalink. `:year`/`:month`/`:day` come from the page date as written; `:slug` is the front-matter `slug`, else the filename's slug (only when the date came from the filename), else the title through the urlize approximation (lowercase, punctuation dropped, spaces to hyphens); `:section` is `blog`.
- **Aliases:** the URL of every later stored version that differs from the id, plus the front-matter `aliases` of stored versions, never the id itself.
- **Snapshot of a version:** repo `website`, ref `main`, the entry's commit SHA, its path then.

**CHANGELOG rules (T6):**
- 18 documents, `changelog:1.20` … `changelog:1.37`, source type `release_record`, each read from `CHANGELOG/CHANGELOG-1.R.md` at the kubernetes lock head (its own snapshot, not the website lock: parked P2).
- One version per ingestion snapshot that changes the normalized hash (empty front matter, no strip list): release window `[R, R]` set at insert; `valid_from_date` = the head commit's time (decision 6); date `until` open.
- Chunks: leave out the text before the first heading, and every section whose heading path holds a heading starting with `Downloads for ` (decision 8). The hash still covers the whole file.

**R10 (decision 7):** the `close_version` UPDATE also requires `valid_until_release IS NULL OR valid_until_release = <passed>`; no row → ValueError naming both reasons.

#### Handoffs between tasks

- **T4 → T5:** first-parent merge times; the release clamp (decision 1), used by blog windows only if needed (blog dates start at 2020-12-08); the re-creation guard.
- **T4 → T6:** nothing direct.
- **T6 → R3:** the final source list for T7's scanner re-check; CHANGELOG oversize chunks for T7's decision.

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **T4:**
  - 3 KEP numbers have 2 folder names, never present together (1669, 3257, 4444): one document each.
  - KEPs that leave the 3 SIG folders close as removed: 506 (`[20,21] [21,25]`: its first merge, 2020-12-16, is after 1.20's release; corrected in the R3 sitting), 2004 and 2030 (`[20–21]`).
  - KEP-1205's `kep.yaml` at 1.20 holds two YAML documents: only the first is read (already in S04's parser).
  - Skipped with a reason: the 7 symlinks; `keps/sig-network/README.md` (an index, not a KEP); files in a KEP folder other than `README.md` and `kep.yaml` (e.g. `images/authorizer-chain-computation.md`) are ignored.
  - Governance: the R100 move (`baseimage-exception-list.md`) adds no version; its open version keeps the old path and snapshot. Chains continue from 1.37 to `head` (`branch-creation.md`, `release-cuts.md`: 2 edits). `go.md` → `go-updates.md` at 66% links.
  - An old path that comes back after its move: the duplicate-id error, never a silent merge (0 on real data).
  - A KEP or governance doc deleted and re-created: its new version must start after the closed one; otherwise a ValueError for that document, not a database error (E1; 0 on real data).
  - A re-ingest that only closes a version (E2): tested.
- **T5:**
  - The kubescape fragment (never published): not stored.
  - The 1.23 and 1.24 release interviews (extensionless after PR #53902): their open versions close at that merge (2026-02-21).
  - The VAP GA post (`------`): stored. `k8s-book-club`'s fix commit (`------` → `---` plus rewrapped lines) may add no version.
  - 8 dates with `+0000`-style offsets; 1 with milliseconds.
  - 3 URLs change after publication → aliases: `introducing-headlamp-plugin-for-karpenter` (09/23 → 10/06), `ingress-nginx-retirement` (11/12 → 11/11), `ccm-new-metric-route-sync-total` (02/26 → 05/15; its front-matter alias equals its id and is skipped).
  - A post re-dated after publication keeps the post's first publication; its later versions start at their commit times (a known approximation). The ccm post's new date is 13.5 min before its commit, so not in the future; the future-date case is covered by a hand-built test (corrected in the R3 sitting).
- **T6:**
  - Stray closing fences in `CHANGELOG-1.22.md` (line 3085) and `CHANGELOG-1.36.md` (line 1602): scanner rule 3; all 371 sections must still appear.
  - `CHANGELOG-1.38.md` exists at the head but is out of range: not read.
  - 1.37 has 8 sections; 1.20 has 23.
- **SQL:** no string-built SQL (ADR-005); the reviewer checks by hand.
- **Network:** the run reads blobs by id only, as R1 does. `git grep` on a partial clone fetches missing blobs (seen in the sitting), so it isn't used.

#### Files in scope

- **T4:** `config/corpus_manifest.yaml` (the `full` scope's `kep` and `governance_doc`), `manifest.py`, `git_reader.py`, `history.py`, `identity.py`, `normalize.py`, `renames.py` (incl. P11's docstring), `chunker.py`, `ingest.py`, `docs/domain-model.md`, tests, fixtures (small real KEP and governance files).
- **T5:** `config/corpus_manifest.yaml` (`blog_post` scope and `permalink`), `manifest.py`, `git_reader.py`, `blog.py` (new), `normalize.py` (the dashes and date types), `identity.py`, `ingest.py`, `docs/domain-model.md`, tests, fixtures (real post excerpts).
- **T6:** `config/corpus_manifest.yaml` (`release_record` repos), `manifest.py`, `history.py`, `identity.py`, `chunker.py`, `ingest.py`, `db/versions.py` (R10), `docs/domain-model.md` (R10, CHANGELOG), tests, fixtures (a CHANGELOG excerpt with a Downloads section and a stray fence), `docs/architecture.md` (at the end of the run).
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Out of scope:**
  - `{#id}` anchors, scanner rule 5, chunk-size rules (T7); the report (T8); `make embed` (T9)
  - any retrieval or generation change
  - migrations (the `canonical_id` prefixes and source types already allow every new id)
  - `eval/`

#### Proof map

Expected values were computed in the sitting with the spike's normalizer (`spikes/measure.py`) and plain git, never with the new code.

| Task | Done when / rule | Proof | Source of expected values |
|---|---|---|---|
| T4 | Re-run adds 0 versions (done when) | Integration test + demo | — |
| T4 | **KEP-2579's versions start at their merge times (done when)** | Integration test on a tiny repo with a merge commit + demo | `[21,22] [22,24] [24,25] [25,–]`, starting 2021-05-12T16:25:28Z, 2021-11-11T16:46:07Z, 2022-06-06T16:34:23Z, 2022-09-22T15:59:06Z (`git log --first-parent`, in the sitting; S04 stored 2021-05-11T20:46:27Z, …) |
| T4 | KEP counts (done when: explained against the spike) | Demo | **141 documents / 472 versions**: 116 folders / 447 + 25 single-file / 25; 113 open at `head`. The spike counted files (153 `.md` + 200 `kep.yaml` documents); the difference is explained in the brief |
| T4 | Older than 1.20 (decision 1) | Unit test: a 2019 merge time gives `valid_from_release` 20 with its date kept | Hand-written; 67 documents affected (git) |
| T4 | Governance (decision 2) | Unit tests of the date link rules + integration test on a tiny repo with a move + demo | **29 documents / 140 versions** (community 12 / 73, sig-release 17 / 67; 23 open at `head`); 8 governance aliases. The spike's 37 / 143: 8 moved paths linked, 3 of whose moves change no normalized content |
| T4 | The devil's-advocate tests | Tests | `baseimage` (R100) 3 versions, none added at 1.37; `versioning.md` 4 versions, its 1.37 one starting at PR #2984's merge (2026-05-28T11:40:47Z); an old path that returns → duplicate-id error; a chain from 1.37 to `head`; `go.md` → `go-updates.md` at 66% |
| T4 | Old KEP ids (decision 3) | Test | `kep:sig-auth/0014-dynamic-audit-configuration`, `claimed_status` `implementable` |
| T4 | Governance title (decision 4) | Unit tests | "Kubernetes Release Versioning"; `<!-- omit in toc -->` removed; no heading → the path |
| T4 | E1, E2 | Unit test (re-created document → ValueError); integration test (a re-ingest that only closes) | Hand-written |
| T5 | Re-run adds 0 versions (done when) | Integration test + demo | — |
| T5 | Counts (done when: explained against the spike) | Demo | **417 documents / 924 ± 1 versions**: the spike's 416 posts and 1,138 − 214 = 924 versions, +1 post (VAP GA, 1 version), −1 version if `k8s-book-club`'s fix commit is whitespace-only once `------` parses. The brief names which |
| T5 | Publication (ADR-002 D3) | Unit tests on hand-built histories | `valid_from` = max(merge, publication); a version superseded before publication isn't stored; a deletion after publication closes |
| T5 | Id at publication, later URLs as aliases | Unit test + demo | The 3 posts above (spike §5 I) |
| T5 | URL rules | Unit tests | The spike's hand checks: `/blog/2018/07/16/how-the-sausage-is-made-the-kubernetes-1.11-release-interview-from-the-kubernetes-podcast/`; `+0000` dates; a front-matter `url:` |
| T6 | **18 documents, 371 patch sections (done when)** | Demo | 18 / 18 versions; 371 distinct first headings `v1.R.x` (`grep -c '^# v'`, spike §7 P) |
| T6 | **No chunk holds a sha512 row (done when)** | Integration test + demo SQL | 0 chunks match 128 hex characters |
| T6 | **A set release `until` can't change (done when)** | Integration test: close `[30,30]` with 31 → ValueError; with 30 → closes | Hand-written |
| T6 | Date and window (decision 6) | Test + demo | 2026-09-30T01:30:57Z; `[R, R]` |
| Bundle | All three together | The counts query after T6 | docs pages 64 / 405 · release records **26 / 73** (8 / 55 + 18 / 18; the spike's 29 / 73 minus the 3 moves R1 linked) · feature gates 491 / 868 · KEPs 141 / 472 · governance 29 / 140 · blog 417 / 924 ± 1 · aliases 9 (R1) + 8 governance + the blog's (3 URL changes plus front-matter aliases, each listed in the brief) |

#### Break-it rules

- **T4:**
  1. **Most important.** Date by any commit instead of first-parent → the KEP-2579 test fails.
  2. Drop the release clamp → the pre-1.20 test fails.
  3. Drop the governance similarity rule → the `versioning.md` chain test fails.
- **T5:**
  1. **Most important.** `valid_from` = merge time only → the publication test fails.
  2. Store versions superseded before publication → the superseded-draft test fails.
  3. The latest URL as the id → the id test fails.
- **T6:**
  1. **Most important.** Drop the R10 condition → the `[30,30]` test fails.
  2. Keep the Downloads sections → the sha512 test fails.
  3. Date from `fetched_at` → the date test fails.
- After every restore, `git status --short` is clean (new files: compare sha256).

#### Real-data demos

- **Every task:** `make reset-corpus && time make ingest`, the counts query (S05-R1's), then `make ingest` again: 0 new documents, versions and chunks.
- **T4:** KEP-2579's windows; the `versioning.md` chain (id, alias, each version's windows and `source_path`); the 8 governance aliases.
- **T5:** the 3 blog posts with later URLs (id, aliases, windows); the VAP GA and `k8s-book-club` versions.
- **T6:** sections per CHANGELOG, and the sha512 check:

  ```bash
  docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT count(*) FROM chunks WHERE text ~ '[0-9a-f]{128}'"
  ```

- Ingest run time with all sources is measured and reported.

#### Bundle-level check

1. `make check`
2. `make reset-corpus && make ingest`, then `make ingest` again: 0 new documents, versions and chunks; exit 0
3. The counts query: every value in the proof map's Bundle row
4. `make test-int`, with the dev database ingested
5. `git status --short` clean after every break-it restore

#### PR plan

- **1 PR** (decision 11): `s05-r2-date-scoped`, the contract, then T4, T5, T6. Expected above the ~800-line alarm (~2,000–2,600 reviewable lines); accepted in the sitting, so the run doesn't split it.
- Greptile once (8 → 9 of 50). Record the PR's size in its brief.

**Paid calls allowed:** none. No Voyage and no Anthropic calls, and `make embed` doesn't run.

### Run S05-R3: final chunk text, ingestion report, full embed

- **Status:** running (T7, T8, T9 done)
- **Branch:** `s05-r3-final-corpus`
- **Tasks, in this order:** S05-T7 (chunker fixes) → S05-T8 (ingestion report) → S05-T9 (embed the full corpus) → the slice retro (`/slice-retro`, the run's last commit).
- **Closes the slice:** yes.
- **Goal (plain words):**
  - Make the chunk text final: section names without `{#id}` anchors, no hidden HTML comments, no download-hash tables, HTML tables whole, and oversize lists and tables cut between items or rows.
  - Prove that two ingests from empty store identical data, with a report and a fingerprint.
  - Embed every distinct chunk text once with `voyage-4-large`.
  - Close S05 with its retro.

#### Decisions (made in the sitting, 2026-10-07)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Triage of R2's 17 parked items (PR #29): 1–5 corrected in this commit (R2 contract wordings); 6 (README reset note), 12 (blog error labels; the "dated before" count) and 16 (331 skip lines) → T8; 7 (domain-model limit wording) → retro; 17 (a lock refresh re-dates the CHANGELOGs) → the S14 "keep past `head` SHAs" entry, in this commit; 8–11 and 13–15 dropped | Fixing each now | The dropped items have 0 real cases, still fail loudly, or are refactors. R2's P4 (delete `test_spike_renames.py`) stays with the retro |
| S2 | Bundle T7 → T8 → T9, then the retro | — | The last 3 tasks; T8's fingerprint covers T7's chunk texts, and T9 embeds the texts T8 counts |
| 1 | Cut an oversize list between items and an oversize pipe table between rows, repeating the header row; code blocks and HTML tables stay whole | Keep blocks whole; cut without repeating the header; also cut code blocks by lines | 433 texts are over 1,024 tokens (max 15,735) and hold 1.01M of 5.80M tokens; a simulation in the sitting fixes ~363 of them and leaves at most 10 lists or tables over 1,024 (single long items or rows). A row keeps its column names. Cut code misleads |
| 2 | Scanner rule 6: an HTML comment block is dropped from chunk text | Keep comments; park as an S06 experiment | 10.9% of KEP lines (31,841) are hidden template guidance; 427 KEP texts are mostly comment; 260 fake headings in 13 KEPs. Changing chunk text after S06 means relabeling and re-embedding |
| 3 | A stripped `{#id}` anchor is dropped: not in `heading_path`, the chunk header or a governance title | A new `anchors` column; keeping it in `heading_path` and stripping only in the header | No code reads anchors (the section name is display-only); a migration for an unused feature; one section name, not two. Recoverable from git (snapshot + path) |
| 4 | The "Downloads for" rule (S05-R2 decision 8) applies to every source; the table-of-contents rule stays CHANGELOG-only | A special case for the 1.20 notes page; accepting the 32 chunks | `web:/docs/setup/release/notes/` is the only other document with such headings, and its 32 chunks are the only sha512 chunks left (R2 Question 1) |
| 5 | Computed governance and CHANGELOG titles stay in each version's `metadata.title` | A `title` column; computing titles on read | Every version of every source already has `metadata.title` (2,882 of 2,882); titles change between versions for 30 documents; one read path (R2 Question 2) |
| 6 | The ADR README's rule matches practice: one sub-decision may change in place when decided in a sitting with its evidence, and is logged in a dated "Changes" table (Where / Was / Now / Evidence); a superseding ADR only when the main decision changes | Superseding ADRs; leaving the rule and practice apart | S02 and S05-R2 changed ADR-002/003 that way; Greptile flagged the mismatch (R2 Question 3). Edited in this commit; no ADR changes |
| 7 | `make ingest` ends with the full report; `make ingest-report` prints its database part (counts, chunk id range, fingerprint) without reading git | Storing skips in a new table; a dry re-read of git | Skips exist only during a run; no schema change |
| 8 | The fingerprint covers every stored value except generated ids; the report also prints the chunk id range | The slice doc's draft (ids, version hashes, windows); including generated ids | One definition of "identical" (AC8) that covers chunk text, claims, metadata and snapshots, and holds however the database was built |
| 9 | T9 runs in the run as `EMBED_MAX_TOKENS_PER_RUN=6000000 make embed`; the default stays 2,000,000 | Raising the default; T9 by hand in the morning | The guard stays tight for later runs; a corpus over 6M parks instead of overspending. Voyage's free tier: 200M tokens, 0.48M used in S04 |
| 10 | The verification plan below | — | — |
| 11 | **1 PR**, with the retro as its last commit; an explicit exception to the ~800-line size alarm | 2 stacked PRs split after T7 (recommended); a separate retro PR | The developer's call in the sitting |

No ADR-level decision, so no devil's advocate.

**Claude's calls (overrulable):**
- **Heading rule 1:** a tab after the `#`s also makes a heading, as in CommonMark (`###<tab>Keep configuration simple and minimal`, 1 blog version, 4 headings).
- **Heading text:** the scanner strips a trailing anchor (`\s*\{#[^}]*\}\s*$`) and inline HTML comments (`<!--.*?-->`, e.g. `Branch Manager Handbook <!-- omit in toc -->`, 7 distinct headings) from a heading's text, then trims it. Section names, chunk headers and governance titles all get it. (The inline-comment part was added after the read-back, in the same spirit as decisions 2 and 3.)
- **Rules 5 and 6:** outside a code block, a line starting (after at most 3 spaces) with `<table` (any case) opens a block that runs to the first line containing `</table>`; one starting with `<!--` opens a block that runs to the first line containing `-->` (the opening line itself counts). Either opener also ends a paragraph. A table block is kept whole; a comment block makes no text and no heading. An unclosed one runs to the end of the body (0 cases outside code). A comment inside a code block, and a one-line comment inside a paragraph, are untouched.
- **List cuts (decision 1):**
  - Only a paragraph block over `chunk_max_tokens` is cut. Code blocks, HTML tables and blocks within the limit are untouched.
  - An item starts at a line matching `^( *)([-*+]|\d{1,9}[.)])[ \t]` whose indent equals the smallest such indent in the block. Nested items and continuation lines stay with their item; lines before the first item stay with the first piece.
  - The pieces become blocks for the existing packer (greedy, up to `chunk_max_tokens`). A single item over the limit is a piece on its own.
- **Table cuts (decision 1):** a pipe table is a paragraph block whose 2nd line is a delimiter row (only `|`, `-`, `:` and spaces, with at least one `|` and one `-`). Its rows are cut between lines; every piece after the first starts with the block's first 2 lines. A table inside a list is cut as a list.
- **Scanner re-check:** `spikes/scanner_recheck.py` (new; a sitting tool, never imported by `src/`), run with `uv run --with markdown-it-py==3.0.0 python -I spikes/scanner_recheck.py`. markdown-it-py is not a project dependency; it's already in uv's cache. It compares ATX headings per stored file after stripping anchors and inline comments on both sides, classifies each difference by cause, and checks every stored chunk body for HTML comment blocks with markdown-it.
- **Report layout:** the reads live in `db/report.py` (new; the only SQL); the fingerprint and the formatting are pure functions in `ingestion/report.py` (new). `make ingest-report` is a new Makefile target.
- **T9:** no code change expected. README gains the one-off cap override; `.env.example` is unchanged.
- **Docs:** each task updates `docs/domain-model.md` (chunking rules; the fingerprint). `docs/architecture.md` is updated once, at the end of the run.

#### Pinned formats

**A pipe table cut in two** (decision 1), from the real 1.28 feature-gates page (website `release-1.28`, `feature-gates.md` line 56). The second piece starts with the same 2 header lines; there is no blank line between them and the rows:

```
| Feature | Default | Stage | Since | Until |
|---------|---------|-------|-------|-------|
| `APIPriorityAndFairness` | `false` | Alpha | 1.18 | 1.19 |
…
```

**A list cut** (decision 1). Cut points are marked `▶`; nothing else is a cut point:

```
  continuation of the previous item      ← stays with the first piece
▶- Item A
  more text of A
  - nested item of A                     ← stays with A
▶- Item B
▶1. Item C (numbered lists alike)
```

**Fingerprint** (decision 8):
- One row per stored record, each a compact JSON array, `json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`:
  - `["document", canonical_id, source_type]`
  - `["alias", canonical_id, alias]`
  - `["version", canonical_id, content_hash, source_path, snapshot_repo, snapshot_ref, snapshot_sha, valid_from_release, valid_until_release, valid_from_date, valid_until_date, claimed_status, claimed_stage, metadata]`
  - `["chunk", canonical_id, version valid_from_date, ordinal, heading_path, content_hash]`
- Dates are UTC ISO 8601 strings; a null is JSON `null`; `metadata` is the JSON object (its keys sorted by `sort_keys`).
- A chunk names its version by `canonical_id` and `valid_from_date`, unique per document (the date-window exclusion constraint).
- The rows are sorted as strings and joined with `\n`; the fingerprint is the sha256 hex of their UTF-8 bytes, printed as `Fingerprint: sha256:<hex>`. An empty database gives the sha256 of the empty string.

**Skip lines** (T8): one line per (file, reason), listing the snapshots in release order, with consecutive releases as a range: `keps/sig-release/OWNERS: not a .md/.yaml file (1.20–1.37, head)`. A failure line starts with its snapshot label (a blog failure: the commit's short SHA, not "head").

#### Handoffs between tasks

- **T7 → T8:** the final chunk texts, after `make reset-corpus && make ingest`. Document and version counts are unchanged from R2.
- **T8 → T9:** the distinct-text count and the fingerprint. T9 must not change the fingerprint (it writes only `embeddings`).
- **T9 → retro:** the slice's exit checks, all measured.

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **T7:**
  - Version hashes cover the file, not the chunks, so a plain re-ingest keeps the old chunks. Every demo starts from `make reset-corpus`.
  - 71 CHANGELOG texts open with an indented continuation line, not a marker: it stays with the first piece.
  - `---` (a thematic break) isn't an item: a marker must be followed by a space or tab.
  - The gate stages YAML (`- stage: alpha` …) is never over the limit, so it's never cut.
  - At most 10 list or table texts stay over 1,024 tokens, each a single item or row; code blocks and HTML tables stay whole (about 70 texts; max 15,735, `artifacts.md`'s tar listing).
  - KEP `<!-- toc -->` and `<!-- /toc -->` lines are one-line comment blocks: dropped; the visible table of contents between them stays.
  - A comment block whose closing line has text after `-->`: the whole line is dropped (CommonMark).
  - CHANGELOG behaviour is unchanged: 18 documents, 371 patch sections, 0 sha512 chunks; T6's tests stay green.
  - Earlier tests that pin heading paths with `{#…}` or texts with comments are updated to the new rules; that's in scope. Any other break of an earlier test parks.
- **T8:**
  - Dates print in UTC, `metadata` with sorted keys, chunks by ordinal, and every list is sorted, so the report is byte-identical.
  - "no text to chunk" (2) is about versions, not files: its lines keep the version's label.
  - A manifest path absent from every release in range is an error (0 on real data; unit test on a hand-built scope). One absent from some releases stays an INFO line.
  - The blog's out-of-scope log line splits "dated before 1.20" from "no date" (R2 parked 12).
  - `make ingest-report` on an empty database prints zeros and the empty fingerprint.
- **T9:**
  - The estimate is printed before any request; above 6,000,000 the command refuses, and the task parks. The cap is not raised further.
  - An HTTP 429 or 5xx after 3 retries stops `make embed`; stored batches stay, and a re-run sends only what's missing. The same failure 3 times → park (no-progress rule).
  - Orphan deletion removes the S04 vectors whose texts T7 changed; the count is reported.
  - The largest text (15,735 estimated tokens) is sent as written; whether Voyage truncates it isn't visible (Not verified).
- **SQL:** no string-built SQL (ADR-005); the reviewer checks by hand.
- **Network:** ingestion reads blobs by id only, as in R1 and R2. The only network calls are Voyage's (T9) and uv's cache for markdown-it-py (already cached).

#### Files in scope

- **T7:** `src/orgknow/ingestion/chunker.py`; `spikes/scanner_recheck.py` (new); `docs/domain-model.md` (chunking rules); `tests/unit/test_chunker.py` and any test pinning an anchor, a comment or a Downloads section; `tests/fixtures/` (small real excerpts: the 1.28 feature-gates table, a `CHANGELOG-1.27` list around line 2444, KEP-4317's comment block at `enhancements` head lines 932–992, the RBAC table at website head lines 645–698, the blog post `2025-11-25-kubernetes-configuration-best-practices` at `5b9bb69f`).
- **T8:** `src/orgknow/db/report.py` (new), `src/orgknow/ingestion/report.py` (new), `ingest.py` (the report at the end; skips as records; failure labels), `blog.py` (the error label and the out-of-scope counts), `manifest.py` (the absent-path error), `Makefile` (`ingest-report`), `README.md` (the command; R2 parked 6: any chunker change needs `make reset-corpus`), `docs/domain-model.md` (the fingerprint), tests.
- **T9:** `README.md` (the one-off cap override). No `src/` change expected; if one is needed, it parks.
- **Retro:** this slice doc (Retro, Status, Finished), `docs/backlog.md` (S05 ✅, S06 🟨), `docs/learning/S05-stage1-subset-ingestion.md` (new), `docs/architecture.md`, `docs/domain-model.md` (R2 parked 7), `docs/learning/glossary.md` if needed, delete `tests/unit/test_spike_renames.py` (R2's P4).
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Out of scope:**
  - any retrieval or generation change; `orgknow ask`
  - migrations
  - the manifest, the lock and the strip lists
  - `eval/`

#### Proof map

Expected values were measured in the sitting with SQL, git, and throwaway scripts (markdown-it-py as the referee, and a separate simulation of decision 1), never with the new code.

| Task | Done when / rule | Proof | Source of expected values |
|---|---|---|---|
| T7 | **0 heading paths contain `{#` (done when)** | Unit test (a spaced anchor and `…(experimental){#status-supported-features}`) + demo SQL | 1,269 texts / 446 distinct headings → 0 (SQL in the sitting) |
| T7 | **RBAC tables whole (done when)** | Unit test on the real RBAC excerpt (3 blank lines inside) + demo SQL: chunks with `<table` and no `</table>` | 1 per version × 15 → 0; each version has 4 tables, 2 cut (git in the sitting) |
| T7 | **Scanner vs markdown-it (done when)** | `spikes/scanner_recheck.py` on all 2,882 stored files | Before: 822 heading differences in 80 files: 486 Hugo highlight (12 files), 72 list-item headings (18 files), 260 HTML comments (49 files), 4 tab (1 file). After: only the first two causes; comment and tab differences 0. Any other difference is listed |
| T7 | List and table cuts (decision 1) | Hand-written unit tests on the CHANGELOG-1.27 and 1.28 feature-gates excerpts (a small `max_tokens` forces cuts), as pinned above | Pinned formats |
| T7 | Oversize after the cuts | Demo SQL: distinct texts over 1,024 estimated tokens, by largest-block kind | 433 → about 79 (± 10); lists and tables at most 10, each a single item or row; max 15,735 (simulation in the sitting) |
| T7 | Comments dropped (decision 2) | Unit test on the KEP-4317 excerpt (no `Alpha` section, no comment text) + the re-check's markdown-it pass over every stored chunk body | 0 comment blocks |
| T7 | Tab headings | Unit test on the real blog lines | 4 headings found |
| T7 | Downloads everywhere (decision 4) | R2's all-chunks query: `SELECT count(*) FROM chunks WHERE text ~ '[0-9a-f]{128}'` | 32 → 0 |
| T7 | Versions untouched | The counts query | blog 417 / 924 · docs pages 64 / 405 · feature gates 491 / 868 · governance 29 / 140 · KEPs 141 / 472 · release records 26 / 73 · 21 aliases (R2) |
| T8 | **Two from-empty ingests print identical reports (done when)** | `make reset-corpus && make ingest > a.txt`, twice; `diff a.txt b.txt` | Empty diff (stdout only; timing is outside it) |
| T8 | Fingerprint (decision 8) | Hand-built unit tests: rows in any order → same hash; one changed value per kind (a document's source type, an alias, a version's `valid_until_date`, a chunk's content hash, a metadata value) → a different hash; metadata keys in another order → same hash; empty → sha256 of `""` | Hand-written |
| T8 | Skips listed once | Unit test (one file skipped at 3 snapshots → 1 line, `(1.20–1.22)`) + demo | 331 skip lines → 26 lines (awk on the log in the sitting) |
| T8 | Per-release counts | Demo | Docs pages valid at 1.20 → 1.37: 29, 30, 35, 36, 42, 48, 51, 50, 52, 52, 53, 54, 55, 57, 57, 58, 60, 60 (S05-R1 contract) |
| T8 | Absent path is an error | Unit test on a hand-built scope | — |
| T9 | **Every distinct text has a vector (done when)** | SQL: distinct chunk texts with no `voyage-4-large` vector | 0; vectors for the model = T8's distinct-text count |
| T9 | **A second run makes 0 requests (done when)** | `make embed` again | `Requests: 0` |
| T9 | **Voyage's count recorded (done when)** | The summary line | Recorded, not pass/fail; S04's ratio was 0.95 (475,905 / 500,674) |
| T9 | Cap | The estimate in the summary | ≤ 6,000,000 (sitting: 5.31M today; about 5.2–5.5M after T7) |
| Bundle | All together | The bundle-level check | Counts as in T7's row; T8's fingerprint unchanged after T9 |

#### Break-it rules

- **T7:**
  1. **Most important.** Pack lists whole again (no item cuts) → the CHANGELOG list test fails.
  2. Drop the header repeat → the feature-gates table test fails.
  3. Drop rule 6 → the KEP-4317 test fails.
- **T8:**
  1. **Most important.** Leave chunks out of the fingerprint → the chunk-change test fails.
  2. Don't sort the rows → the order test fails.
  3. Count a skip once per snapshot → the dedupe test fails.
- **T9:** delete one vector (`DELETE FROM embeddings WHERE content_hash = '<one hash>'`), then `make embed` → `Requests: 1`, `Texts embedded: 1`; then `make embed` again → `Requests: 0`. A real paid call of one text, inside decision 9's limit.
- After every restore, `git status --short` is clean (new files: compare sha256).

#### Real-data demos

- **Every task:** `make reset-corpus && time make ingest`, the counts query (S05-R1's), then `make ingest` again: 0 new documents, versions and chunks.
- **T7:**
  - the re-check: `uv run --with markdown-it-py==3.0.0 python -I spikes/scanner_recheck.py`
  - the anchor, RBAC, sha512 and oversize queries
  - KEP-4317's section names at `head`; one cut CHANGELOG section and one cut feature-gates table piece, as stored
- **T8:** two from-empty `make ingest` runs and their `diff`; `make ingest-report`.
- **T9:** `EMBED_MAX_TOKENS_PER_RUN=6000000 make embed`, twice; the vector-coverage query:

  ```bash
  docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT count(DISTINCT c.content_hash) AS texts, count(DISTINCT c.content_hash) FILTER (WHERE e.content_hash IS NULL) AS without_vector FROM chunks c LEFT JOIN embeddings e ON e.content_hash = c.content_hash AND e.model = 'voyage-4-large'"
  ```

- Ingest run time is measured and reported.

#### Bundle-level check

1. `make check`
2. `make reset-corpus && make ingest`, then `make ingest` again: 0 new documents, versions and chunks; exit 0
3. The counts query: every value in T7's "Versions untouched" row
4. `make ingest-report`: the fingerprint equals T8's
5. The vector-coverage query: 0 without a vector; `make embed` again: `Requests: 0`
6. `make test-int`, with the dev database ingested and embedded
7. `git status --short` clean after every break-it restore

#### PR plan

- **1 PR** (decision 11): `s05-r3-final-corpus`: the contract, T7, T8, T9, then the retro. Expected above the ~800-line alarm (~1,500–2,000 reviewable lines); accepted in the sitting, so the run doesn't split it.
- Greptile once (9 → 10 of 50). Record the PR's size in its brief.

**Paid calls allowed:** Voyage document embeddings of chunk texts only, through `make embed`, at most 6,000,000 estimated tokens across the run (T9 and its break-it). No Anthropic calls, no question embeddings, and `orgknow ask` doesn't run.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S05-*.md`
