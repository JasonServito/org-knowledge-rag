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
- **Done when:**
  - 0 heading paths contain `{#`.
  - The RBAC page's 12 cut HTML tables are whole.
  - The scanner's headings match markdown-it's on every S05 source, or each difference is listed and explained.
- **Notes / pointers:**
  - S05 rebuilds the database from empty, so no re-chunk machinery is needed; vectors are reused by content hash.
  - From the triaged backlog items:
    - **Rule 5:** 12 of 78 HTML tables in the S04 scope (all on the RBAC page) are cut into 24 chunks. Recheck with it: a tab-indented line would close an indented fence under rule 3 (0 cases in S04).
    - **Anchors:** 1,754 of S04's 4,967 chunks have an anchor in `heading_path`. S06 labels relevance by heading path. The parked item suggested keeping the id for citation URL fragments; where it goes is an R3 decision.
  - **Decide in the R3 sitting: oversize blocks** (measured in the R1 sitting with today's chunker).
    - Lists without blank lines and pipe tables count as one block, and a block is never cut. So they become single chunks far over 512 tokens.
    - The pre-1.29 feature-gates page reaches **11,219 tokens** in one chunk.
    - R1 sources have 33 chunks over 2,000 tokens.
    - A preview of `CHANGELOG-1.30` gives 275 chunks, where 32 over 1,024 tokens hold 51,056 of its 108,825 tokens (47%), mostly release-note lists.
    - Option to weigh: cut an oversize list between items and an oversize pipe table between rows, repeating the header row. Code blocks and HTML tables stay whole.
  - The scanner already matches markdown-it on every R1 source: 1,382 distinct files, 8,239 headings, 0 differences (R1 sitting).
- **Deps:** T1–T6 (so the re-check covers every source).

### S05-T8: Ingestion report `[commodity]`

- **Goal:** `make ingest-report` prints:
  - documents, versions, chunks and distinct texts, per source type and per release
  - skipped and failed files with reasons
  - a fingerprint (one hash over every document's `canonical_id`, version hashes and windows) to compare two ingests
- **Done when:** two from-empty ingests print identical reports.
- **Notes / pointers:** the parked "clearer failures" items:
  - each failure line carries its snapshot label
  - a skipped file is counted once, not once per snapshot
  - a manifest path absent from every release in range is an error
- **Deps:** T1–T6.

### S05-T9: Embed the full corpus `[commodity]`

- **Goal:** `make embed` over the full corpus with `voyage-4-large`, with the per-run token cap raised to fit (about 5.5–6.5M estimated tokens, inside the free tier).
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
- **R2 sitting:**
  - ids for the 25 old single-file KEPs
  - the governance-doc title rule
  - the blog URL rules in code
  - the CHANGELOG date and the R10 change
- **R3 sitting:**
  - where a stripped anchor goes
  - the embed cap
- No new ADR is expected: ADR-002 and ADR-003 already decide the rules. A rule that turns out wrong on real data is an ADR-002 amendment, decided in a sitting.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S05-R1: release-scoped website sources

- **Status:** running (T1, T2, T3 done)
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
- **Stages YAML:** only for `gate:` documents whose metadata has `stages`; built from the version's `metadata`.
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
  - Stage values can carry trailing spaces (`alpha `): kept as written in `metadata` and in the YAML.
  - 242 gate file versions have `removed: true`.
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

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S05-*.md`
