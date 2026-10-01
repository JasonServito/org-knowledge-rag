# S02 Corpus spike report

*Slice: `docs/slices/S02-corpus-spike.md` · Status: in progress. T3a–T5 add their sections; T6 writes the conclusion.*

## 1. Snapshot (S02-T2)

- **Fetched:** 2026-09-30T06:09:15Z, by `uv run python spikes/fetch.py`.
- **SHA record:** `config/corpus_manifest.lock.yaml`, added in commit `edc3730`. The lock file is the **single record** of the 77 corpus SHAs this spike measures:
  - the head of each repo's default branch
  - the website SHA per release (`release-1.R`, or `main` for 1.37)
  - the enhancements, community and sig-release SHA at each release date (the cutoff rule is written in the lock)

  This report doesn't copy them. Re-running the script with the lock present verifies them and leaves the lock unchanged.
- **Clones:** partial clones with `--filter=blob:none`, meaning commits and directory listings only, no file contents yet. They live in `CORPUS_CACHE_DIR`, outside the repo. The total size on disk is about 117 MB.

Default-branch heads at fetch time:

| Repo | Branch | Head | History | Size on disk |
|---|---|---|---|---|
| kubernetes/website | `main` | `256a1f49419171f6c7fbdb1857146da1c63eb533` | all branches, full | 87 MB |
| kubernetes/kubernetes | `master` | `7c596ad7938d030a4cab3c1e55b16b7f61cf7ca5` | depth 1 | 1.5 MB |
| kubernetes/enhancements | `master` | `4be81e27aef5d252972fd02b5a9479a18982dfe5` | full | 11 MB |
| kubernetes/community | `main` | `c591129c16bf6b57b6ef9d689f1f5175ace56634` | full | 13 MB |
| kubernetes/sig-release | `master` | `49d129fa10676ef91d821c006494bfddd5d1fcd2` | full | 4.0 MB |

The website `main` head is also the 1.37 docs snapshot, because 1.37 has no `release-1.37` branch yet. The fetch confirmed that the 4 traced KEP directories (2572, 2579, 2799, 4858) exist at the enhancements head.

## 2. Files and versions (S02-T3a)

- **Run:** `uv run python spikes/measure.py` on 2026-09-30, against the lock above. It downloaded the contents of 5,362 files ("blobs") in batches of 1,000 ids, and the cache grew from about 115 MB to 132 MB. A second run took 5 seconds and downloaded nothing.
- **What counts as a version (ADR-002 D2):** a file's normalized content hash differs from its previous version. Normalization:
  - drop the manifest's strip keys for that source from the front matter, ignoring case
  - sort the remaining keys
  - remove link targets (`[text](url)` becomes `[text]`)
  - collapse whitespace

  The method details are in the T3 notes of the slice doc.
- **Columns:**
  - `files`: in-scope files that exist at the end of the row
  - `versions`: new versions after normalization
  - `raw blob versions`: new versions without normalization, where any byte change counts
- **Rows:**
  - **Releases 1.20–1.37:**
    - Docs, release records and feature gates come from the website `release-1.R` branch (`main` for 1.37).
    - `CHANGELOG-1.R.md` comes from the kubernetes head.
    - KEPs and governance docs come from the default branch at the release date.
  - **Blog:** one version per first-parent commit on website `main` (ADR-002 D3). A commit goes to the first release whose cutoff is at or after it. The cutoff rule is the lock's: the release date at 23:59:59Z.
  - **`head`:** changes after 1.37's release date, up to the lock heads (fetched 2026-09-30). Release-scoped files carry forward unchanged, so the `head` file count is the whole corpus at the lock heads.
- **Identity:** the file path, except that blog moves are followed (finding 1).

### A. Per release

| release | files | versions | raw blob versions |
|---|---:|---:|---:|
| 1.20 | 134 | 134 | 134 |
| 1.21 | 195 | 153 | 155 |
| 1.22 | 232 | 128 | 135 |
| 1.23 | 264 | 119 | 123 |
| 1.24 | 324 | 130 | 154 |
| 1.25 | 361 | 118 | 128 |
| 1.26 | 397 | 141 | 151 |
| 1.27 | 447 | 163 | 182 |
| 1.28 | 486 | 134 | 144 |
| 1.29 | 849 | 462 | 503 |
| 1.30 | 882 | 169 | 190 |
| 1.31 | 928 | 377 | 381 |
| 1.32 | 982 | 474 | 480 |
| 1.33 | 1,038 | 189 | 190 |
| 1.34 | 1,120 | 291 | 294 |
| 1.35 | 1,165 | 166 | 171 |
| 1.36 | 1,232 | 230 | 242 |
| 1.37 | 1,295 | 234 | 245 |
| head | 1,308 | 50 | 69 |

### B. Per source type

| source | documents | versions | raw blob versions | unique content hashes |
|---|---:|---:|---:|---:|
| blog_post | 417 | 1,138 | 1,271 | 1,136 |
| docs_page | 67 | 406 | 439 | 405 |
| feature_gate_reference | 842 | 1,169 | 1,176 | 868 |
| governance_doc | 37 | 143 | 154 | 140 |
| kep | 153 | 352 | 365 | 349 |
| kep (YAML metadata) | 200 | 581 | 586 | 578 |
| release_record | 29 | 73 | 80 | 72 |
| **total** | 1,745 | 3,862 | 4,071 | 3,548 |

### Reading the numbers

- **3,862 versions across 1,745 documents.** Of these, 3,281 would be embedded. The other 581 are `kep.yaml` and PRR (production readiness review) versions: metadata that carries the `claimed_status` history, not embedded (ADR-003 D1).
- **Blog posts: 417 here, 413 in T1 (PR #8).** 417 = 413 − 1 + 5: T3a also counts 5 in-range posts deleted before the head (T1 counted the head only), and it can't parse `2024/validating-admission-policy-ga` (finding 3), which T1 counted. No posts were lost to a byte-order mark or CRLF.
- **Normalization removes 209 of 4,071 raw versions (5%).** Most version churn is real content change, not reviewer lists or whitespace.
- **Unique content hashes (3,548) are fewer than versions (3,862).** The same content appears at more than one path, mostly the 1.32 feature-gate renames (finding 2). A content-hash cache would embed it once.
- **Three release spikes:**
  - **1.29:** the feature-gate reference was split from one page into one file per gate, adding 318 feature-gate versions.
  - **1.31:** six blog PRs between April and June 2024 (for example website PR #46049) moved each post's author line from the body into `author:` front matter. That gives 249 blog versions in the row. These are real edits: only 5 versions changed `author:` alone.
  - **1.32:** the per-gate files were renamed (finding 2), adding 371 feature-gate versions.

### Findings for T4–T6 (recorded, not fixed here)

1. **Blog posts moved into year folders on 2026-02-21.** Website PR #53902 moved 909 blog files from `_posts/YYYY-MM-DD-slug.md` to `_posts/YYYY/slug.md`, and rewrote `url:` in older posts. Git detects all 909 as renames, at 84–100% similarity. The spike follows them, so 1,656 blog paths become 785 posts, 417 of them in scope. With path-based identity, every moved post would count twice. ADR-002 D4's `blog:<date>-<slug>` identity doesn't depend on the path, which is what's needed. The post checked has `slug` in its front matter; T5 should confirm this holds generally.
2. **Feature-gate files renamed at 1.32.** 343 per-gate files were renamed from kebab-case to the gate name (`api-list-chunking.md` became `APIListChunking.md`), 294 of them byte-identical. With path identity, each is a new document and a new version. This is for T4. An option for T6: use the gate name (front-matter `title`) as the feature gate's `canonical_id`.
3. **Front-matter variants.** Blog posts use a byte-order mark, a leading blank line, or CRLF line endings; the spike handles all three, with a test. One in-scope post, `2024/validating-admission-policy-ga/index.md`, opens its front matter with `------`. It has no parseable date, so the spike leaves it out of the blog scope. Its front matter should be checked in T5. Files with no front matter at all are expected: 18 CHANGELOGs, 128 KEP documents and 37 governance docs. The other 25 KEP `.md` files are older single-file KEPs (for example `keps/sig-auth/0014-dynamic-audit-configuration.md`) that keep their metadata in YAML front matter instead of a `kep.yaml`. T5's `kep.yaml` status check should cover them too.
4. **Date-scoped changes after 1.37: 50 versions** (20 KEP, 27 blog, 3 governance). ADR-002 D1 snapshots KEPs and governance docs only at release dates, so their changes after the latest release are missed unless ingestion also takes a head snapshot. That's for T6.
5. **Only `.md` files are counted,** plus `.yaml` for KEPs. Images and other files under the in-scope paths are skipped.

### Hand checks

| Check | git | Spike |
|---|---|---|
| Blog post, not moved: `2026/kubernetes-v1-37-release/index.md` | `git log --first-parent --oneline` shows 5 commits | 5 raw versions, 5 versions |
| Blog post, moved: `2022/advanced-server-side-apply.md` | Old path: 1 add, 3 edits, then deleted by the move; new path: the byte-identical move from `2022-10-20-advanced-server-side-apply.md` | 5 entries, 4 raw versions (the move keeps the blob), 3 versions: edit `8ae5aaeb40` only changed a link from an absolute to a relative URL |
| docs_page `.md` files at `release-1.25` | `git ls-tree -r` over the SIG paths: 48 | 48 |
| KEP-2579 `README.md` across the 19 enhancements snapshots | absent at 2, then 3 distinct blobs (at 1, 2 and 14 snapshots) | 17 entries, 3 raw versions, 3 versions |

Tokens, chunks, embedding cost and vector storage are in the next section (S02-T3b).

## 3. Tokens, chunks and cost (S02-T3b)

- **Run:** `uv run python spikes/measure.py` on 2026-09-30, against the same lock. The cache was already complete, so nothing was downloaded, and tables A and B above came out unchanged.
- **Method** (agreed at the T3 plan review; see the slice doc's T3 notes):
  - **What's embedded:** every new version from section 2 except `kep.yaml` and PRR metadata: 3,281 versions, with in-scope blog posts only.
  - **Tokens** ≈ characters ÷ 4, counted on the **body only**. The front matter isn't embedded; the chunk header carries the fields that stay the same.
  - **Sections:** the body is split at markdown headings (`#` to `######`), ignoring `#` lines inside code fences. Text before the first heading is its own section.
  - **Chunks:** a section of t tokens becomes ceil(t ÷ size) chunks. A chunk never spans two sections, and small sections aren't merged. The default size is 512 tokens; 256 and 1024 are sensitivity rows.
  - **Header:** 40 tokens per chunk, added to the embedded tokens.
  - **Upper bound:** every section of every new version is embedded.
  - **Lower bound:** each unique (document, section hash) pair is embedded once. This is what a chunk-level content-hash cache sees when the chunk header holds `canonical_id`, because identical text in two documents then has two different headers. The section hash covers the cleaned section, using the same cleaning as the version hash. Document identity is the same as in section 2: the path, with blog moves followed.
  - **Floor:** each unique section hash once, across all documents. It's shown for reference only; it can't be reached with `canonical_id` in the header.
  - **Pricing:** the standard endpoint rates, per million tokens: voyage-4-lite $0.02, voyage-4 $0.06, voyage-4-large $0.12. Source: [docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing), last updated 2026-09-29, read 2026-09-30. The same page says the first 200M tokens on the voyage-4 family are free per account, and that the Batch API is 33% cheaper.
  - **Vector storage:** chunks × dimensions × 4 bytes (float32), raw vectors only. The dimensions come from [docs.voyageai.com/docs/embeddings](https://docs.voyageai.com/docs/embeddings) (updated 2026-08-10): 1024 by default, and 256, 512 and 2048 are also supported. 1 MB = 10⁶ bytes.

### C. Tokens and chunks per source type (chunks @512)

| source | upper: sections | body tokens | chunks | lower: sections | body tokens | chunks |
|---|---:|---:|---:|---:|---:|---:|
| blog_post | 13,280 | 3,322,477 | 14,765 | 4,828 | 1,408,489 | 5,701 |
| docs_page | 7,282 | 2,150,425 | 8,682 | 2,020 | 713,885 | 2,591 |
| feature_gate_reference | 1,267 | 237,580 | 1,566 | 969 | 216,758 | 1,268 |
| governance_doc | 2,927 | 675,689 | 3,418 | 932 | 259,648 | 1,151 |
| kep | 16,606 | 2,410,752 | 17,733 | 7,550 | 1,280,830 | 8,256 |
| release_record | 7,094 | 2,129,387 | 9,657 | 5,066 | 2,040,882 | 7,621 |
| **total** | 48,456 | 10,926,310 | 55,821 | 21,365 | 5,920,492 | 26,588 |

- **Floor:** 18,138 sections, 5,634,504 body tokens, 23,257 chunks, 6,564,784 embedded tokens.
- **Sections under 64 tokens:**
  - upper bound: 15,320 of 48,456 (32%), which is 27% of the chunks
  - lower bound: 6,336 of 21,365 (30%), which is 24% of the chunks

### D. Embedding cost and vector storage

| chunk size | bound | chunks | embedded tokens | voyage-4-lite | voyage-4 | voyage-4-large | vectors @1024d | vectors @512d | vectors @256d |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 256 | upper: every new version | 73,250 | 13,856,310 | $0.28 | $0.83 | $1.66 | 300.0 MB | 150.0 MB | 75.0 MB |
| 256 | lower: unique (document, section) | 36,554 | 7,382,652 | $0.15 | $0.44 | $0.89 | 149.7 MB | 74.9 MB | 37.4 MB |
| 512 | upper: every new version | 55,821 | 13,159,150 | $0.26 | $0.79 | $1.58 | 228.6 MB | 114.3 MB | 57.2 MB |
| 512 | lower: unique (document, section) | 26,588 | 6,984,012 | $0.14 | $0.42 | $0.84 | 108.9 MB | 54.5 MB | 27.2 MB |
| 1,024 | upper: every new version | 50,331 | 12,939,550 | $0.26 | $0.78 | $1.55 | 206.2 MB | 103.1 MB | 51.5 MB |
| 1,024 | lower: unique (document, section) | 22,902 | 6,836,572 | $0.14 | $0.41 | $0.82 | 93.8 MB | 46.9 MB | 23.5 MB |
| 512 | upper, excl. feature_gate_reference | 54,255 | 12,858,930 | $0.26 | $0.77 | $1.54 | 222.2 MB | 111.1 MB | 55.6 MB |
| 512 | lower, excl. feature_gate_reference | 25,320 | 6,716,534 | $0.13 | $0.40 | $0.81 | 103.7 MB | 51.9 MB | 25.9 MB |

### Reading the numbers

- **Cost isn't a constraint.** The largest row (256-token chunks, upper bound) is 13.9M embedded tokens. That's $1.66 at voyage-4-large's list price, and 7% of the 200M free tokens. Even if characters ÷ 4 undercounts by half, the largest row stays under 28M tokens: 14% of the free allowance, or $3.33 at list price. An ablation with another model (ADR-002 keys embeddings by model name) costs the same amount again per model.
- **The cache halves the work.** At 512, the lower bound is 26,588 chunks and 7.0M embedded tokens, against 55,821 and 13.2M for the upper bound. The floor is only 13% fewer chunks than the lower bound, and 6% fewer embedded tokens. So putting `canonical_id` in the header costs little cache reuse.
- **Feature gates are 36% of the embedded versions but 2% of the tokens:** 237,580 of 10.9M body tokens. Leaving them out changes the 512 rows by 2–5% (chunks and tokens). The 1.29 and 1.32 feature-gate churn from section 2 matters for version counts and identity, not for cost.
- **The CHANGELOGs are a third of the lower bound.** At 512-token chunks, the 18 CHANGELOGs (7.74M characters) have 1,923,527 body tokens in the lower bound, which is 94% of `release_record`. As a share of the lower bound, that's:
  - 32% of the **body tokens** (5,920,492, which exclude the chunk headers)
  - 32% of the **embedded tokens**: the CHANGELOGs' 2,208,687 (7,129 chunks × 40 header tokens included) out of 6,984,012
  - 27% of the chunks

  These were computed with a scratch script using the spike's own functions, because `measure.py` doesn't print a per-file split. Each CHANGELOG has one version (the kubernetes head), so the cache barely helps (2.13M upper vs. 2.04M lower for `release_record`). 25% of their characters are sha512 download-table rows. Those are hex strings, which likely tokenize denser than 4 characters per token, and they have no retrieval value. **For S04-T3:** consider leaving download tables out of CHANGELOG chunks.
- **Section size matters more than chunk size.** 30–32% of sections are under 64 tokens, and each one still becomes its own chunk: 24–27% of all chunks. Going from 512 to 1024 cuts chunks by only 10% (55,821 to 50,331), because most sections already fit. **For S04-T3:** merging small sections into a neighbour (keeping the heading path) could remove up to a quarter of the chunks; a bigger chunk size removes a tenth.
- **Vector storage is small.** At 512-token chunks and 1024 dimensions, the raw vectors take 109 MB at the lower bound and 229 MB at the upper bound. Which of the two applies depends on the schema (see caveats). The largest row is 300 MB. The pgvector row overhead and the HNSW index (the approximate nearest-neighbour search index) come on top of that, and aren't estimated here.

### Caveats

- **Characters ÷ 4 likely undercounts** code, YAML, tables and hex (see the CHANGELOG note above). No tokenizer was run, because Voyage's tokenizer would add a dependency.
- **Title and heading-path edits cost cache hits.** The lower bound assumes the header changes only when identity changes. But a document's title and a section's heading path can change between versions: a retitled post, or a renamed parent heading. The affected sections then miss the cache, so the real figure sits somewhat above the lower bound.
- **Identity is the path here** (blog moves followed). The 1.32 feature-gate renames (finding 2) count as new documents. With the gate name as `canonical_id`, the lower bound would drop slightly, but feature gates are only 216,758 of its body tokens.
- **Sections aren't merged or overlapped here.** A real chunker (S04-T3) will give different counts.
- **Which storage bound applies depends on the S03 schema:**
  - **One vector per chunk row:** storage follows the upper bound. The cache saves API calls, not disk.
  - **One vector per unique content hash, referenced by the chunks:** storage follows the lower bound. But one nearest-neighbour hit then maps to several versions, so filtering by release or validity window needs a join after the vector search.

  This is a question for S03-T2 (see the backlog).

### Hand checks

| Check | By hand | Spike |
|---|---|---|
| Docs page `tasks/configure-pod-container/migrate-from-psp.md` at the website head | 19 lines start with `#`; 4 of them are shell comments inside ` ```sh ` fences. So 15 headings, plus the intro, = 16 sections. Body (after the front matter): 18,637 characters ÷ 4 = 4,660 tokens | 16 sections, 4,664 tokens |
| `CHANGELOG/CHANGELOG-1.30.md` at the kubernetes head (no front matter) | 354 headings and no code fences, so 355 sections with the table of contents before the first heading. 407,532 characters ÷ 4 = 101,883 tokens | 355 sections, 101,915 tokens (+0.03%) |

The small token differences are expected: each section is rounded up separately, and the newline between two sections isn't counted.

## 4. Renames (S02-T4a)

- **Run:** `uv run python spikes/renames.py` on 2026-09-30, against the same lock. It downloaded only the 17 redirect files (0.8 MB in total). The `.md` contents were already in the cache from T3a. A second run took 3 seconds and downloaded nothing: the cache's object store stayed at the same size.
- **Method:**
  - **Detection:** `git diff -M10% --name-status` between the locked website snapshots of each pair of adjacent releases: 17 pairs, 1.20→1.21 to 1.36→1.37. The diff covers the in-scope `.md` files of the release-scoped website sources: docs pages, the website's release records, and feature gates.
  - **One run gives every threshold.** git pairs deleted and added files from the highest similarity score down, so a pair scored s% is also found at every threshold up to s. One run at a 10% floor therefore gives the counts for every threshold. Checked: separate runs at 50, 60 and 90% gave exactly the floor run's pairs at or above that score, for all 17 pairs.
  - **Similarity** is git's score on the raw file, front matter included, not on the ADR-002 D2 normalized text.
  - **Oracles** (independent sources of truth, used to grade each rename):
    - **Docs pages and release records:** the site's redirect file at the newer release, or a Hugo `aliases` entry on the new page. The redirect file is Netlify's list of old URL → new URL rules. A file path is turned into the URL Hugo serves it at: drop `content/en` and `.md`, turn `_index.md` and `index.md` into their folder, and lowercase.
    - **Feature gates:** the front-matter `title`, which is the gate name, compared before and after.
    - **Read by hand:** every title mismatch, all 4 docs renames, and 6 inexact gate renames sampled with a fixed seed.
  - **The redirect file from 1.34 on:**
    - Up to 1.33 it's `static/_redirects`. From 1.34, the site builds `_redirects` at build time from a Hugo template (`layouts/index.redirects`). The template adds two API-reference rules and copies in `static/_redirects.base` whole. So the spike reads `_redirects.base` for 1.34–1.37.
    - Wildcard (`*`) and placeholder (`:x`) rules are skipped: 8–11 per release, and none covers an in-scope path.
    - When one source URL has two rules, the first wins, as in Netlify.
  - **Scope:** detection only sees in-scope paths, so a move across the scope boundary shows up as a plain delete or add. The redirect file classifies those (table G). Diffing the whole website tree was rejected, because it would mean downloading every changed English docs file for 17 pairs.

### E. Rename census

All 4 docs and release-record renames:

| pair | score | old → new | oracle | read by hand | verdict |
|---|---:|---|---|---|---|
| 1.20→1.21 | 96% | `setup/release/version-skew-policy.md` → `releases/version-skew-policy.md` | redirect | Title reworded ("Kubernetes version and version skew support policy" → "Version Skew Policy"); 5 lines added, 6 removed | real |
| 1.22→1.23 | 81% | `concepts/policy/pod-security-policy.md` → `concepts/security/pod-security-policy.md` | redirect (301) | Same title; 128 lines added, 89 removed | real |
| 1.26→1.27 | 59% | `concepts/services-networking/topology-aware-hints.md` → `topology-aware-routing.md` | redirect (302) | The feature was renamed: "Topology Aware Hints" → "Topology Aware Routing"; 68 lines added, 30 removed | real |
| 1.36→1.37 | 99% | `reference/using-api/deprecation-policy.md` → `reference/deprecation-policy.md` | alias only | Same title; 2 lines added | real |

- The 1.23 PSP (Pod Security Policy) move is the known Auth move named in the backlog task. Its redirect is line 162 of `static/_redirects` at 1.23.
- Two of the four changed their title, so a title oracle wouldn't work for docs pages.

**Feature gates:** 350 renames at the floor, 345 of them at 1.31→1.32 (the kebab-case → gate-name renames of finding 2). At git's default of 50% there are 343 at 1.31→1.32, which matches T3a. 348 keep their title. The 2 that don't, read by hand:

| pair | score | old → new | verdict |
|---|---:|---|---|
| 1.32→1.33 | 93% | `APIServingWithRoute` → `APIServingWithRoutine` | **Real.** The body and `stages` are identical; only the name changed. The CHANGELOGs only ever say `APIServingWithRoutine` (3 mentions in 1.30, 1 in 1.31), so the old file name was a typo. A gate renamed in the docs is a blind spot of the title oracle. |
| 1.36→1.37 | 40% | `PodInfoAPI` → `InPlacePodVerticalScalingMemoryBackedVolumes` | **Wrong.** These are different gates. One is the kubelet Pod Info gRPC API: alpha since 1.35, and its file is removed at 1.37. The other is memory-backed `emptyDir` resizing, new as alpha in 1.37 (kubernetes PR #139425). The 40% comes from the front matter (`content_type`, `_build`, `stages`) that makes up most of both short files. |

`renames.py` records the first verdict (`HAND_VERDICTS`), so tables E and F count it as real.

**Sample:** 6 of the 55 inexact gate renames (under 100%), drawn with seed 4. All 6 are real:

- **Same gate:** each keeps its name and body.
- **What changed:** only `stages` entries added at 1.32 (3 graduations to stable, 1 to beta, 1 deprecation) or `removed: true`.

So these gates were renamed in the same release their stage changed. With path identity, a gate's stage history would break at exactly those graduations.

**Precision:**

| group | at the floor (10%) | at 50% and above |
|---|---|---|
| docs pages and release records | 4 of 4 | 4 of 4 |
| feature gates | 349 of 350 (99.7%) | 347 of 347 |

### F. Thresholds

Docs pages and release records:

| threshold | detected | real | wrong | precision | real gained | wrong added | real missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100% | 0 | 0 | 0 | - | 0 | 0 | 6 |
| 90% | 2 | 2 | 0 | 100.0% | 2 | 0 | 4 |
| 70% | 3 | 3 | 0 | 100.0% | 1 | 0 | 3 |
| 60% | 3 | 3 | 0 | 100.0% | 0 | 0 | 3 |
| 50% | 4 | 4 | 0 | 100.0% | 1 | 0 | 2 |
| 30% | 4 | 4 | 0 | 100.0% | 0 | 0 | 2 |
| 10% | 4 | 4 | 0 | 100.0% | 0 | 0 | 2 |

Feature gates:

| threshold | detected | real | wrong | precision | real gained | wrong added | real missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100% | 295 | 295 | 0 | 100.0% | 295 | 0 | 56 |
| 90% | 319 | 319 | 0 | 100.0% | 24 | 0 | 32 |
| 70% | 341 | 341 | 0 | 100.0% | 22 | 0 | 10 |
| 60% | 345 | 345 | 0 | 100.0% | 4 | 0 | 6 |
| 50% | 347 | 347 | 0 | 100.0% | 2 | 0 | 4 |
| 30% | 350 | 349 | 1 | 99.7% | 2 | 1 | 2 |
| 10% | 350 | 349 | 1 | 99.7% | 0 | 0 | 2 |

- **Real gained** and **wrong added** compare each row with the stricter row above it.
- **Real missed** counts the real renames scored below the threshold, plus those no threshold finds:
  - docs: the 2 missed renames in table G
  - feature gates: the 2 pages of the 1.29 split (section H)
- **Recommendation:** use git's default of 50% as the similarity fallback, chosen as an untuned default, not fitted to this data.
  - **Why it can't be tuned here:** there are only 4 docs renames, too few to tune a threshold on. Every value from 10% to 59% gives the same docs result: 4 of 4 real, none wrong. The gap between 50% and ADR-002 D4's starting 60% comes down to one rename (topology, 59%). One case isn't evidence for moving the boundary, and 50% isn't picked to catch it.
  - **What supports 50%:** it's git's default, and T3a's blog-move following already uses it. It sits above the only wrong pairing seen (40%, two short files that share boilerplate front matter). Every rename at or above 50% that was graded here is real (351 of 351).
  - **What matters more:** similarity found only 4 of the 6 docs renames that the redirects declare. Declared signals (redirects, aliases, the gate title) should come first, with similarity as the fallback. That's for T6 (see the slice doc's T6 notes).

### G. Unmatched adds and deletes (docs pages and release records)

Each unmatched delete is classified by where its URL redirects at the newer release. A redirect counts as a move only if its target was **added in the same release**. A redirect to a page that already existed means the page was removed and its readers sent elsewhere.

| class | deletes | adds |
|---|---:|---:|
| missed rename (redirect to an in-scope page added in the same release) | 2 | 2 |
| moved out of scope (redirect to an out-of-scope page added in the same release) | 2 | – |
| moved in from out of scope (a redirect from a page deleted in the same release) | – | 1 |
| removed, redirected to an older page (the target existed before that release) | 1 | – |
| removed, no redirect | 1 | – |
| new page (no redirect from a page deleted in the same release) | – | 38 |

Every row except the new pages:

| pair | change | path | class | redirect |
|---|---|---|---|---|
| 1.20→1.21 | deleted | `setup/release/_index.md` | missed rename | → `/releases/` |
| 1.20→1.21 | added | `releases/_index.md` | missed rename (partner) | from `/docs/setup/release/` |
| 1.20→1.21 | deleted | `setup/release/notes.md` | missed rename | → `/releases/notes/` |
| 1.20→1.21 | added | `releases/notes.md` | missed rename (partner) | from `/docs/setup/release/notes/` |
| 1.20→1.21 | deleted | `concepts/services-networking/add-entries-to-pod-etc-hosts-with-host-aliases.md` | moved out of scope | → `/docs/tasks/network/customize-hosts-file-for-pods/` |
| 1.24→1.25 | deleted | `concepts/services-networking/connect-applications-service.md` | moved out of scope | → `/docs/tutorials/services/connect-applications-service/` |
| 1.24→1.25 | added | `reference/networking/ports-and-protocols.md` | moved in from out of scope | from `/docs/reference/ports-and-protocols/` |
| 1.26→1.27 | deleted | `concepts/services-networking/service-topology.md` | removed, no redirect | – |
| 1.28→1.29 | deleted | `concepts/security/overview.md` | removed, redirected to an older page | → `/docs/concepts/security/` (the section index) |

- **The two missed renames continue the URL, not the content.**
  - `setup/release/notes.md` was the 2,141-line v1.20 release notes. `releases/notes.md` is a 13-line page that points to the CHANGELOG.
  - The two `_index.md` files are 4 and 26 lines, with different titles ("Release notes and version skew" → "Releases").
  - git can't pair either. The redirect still says the page moved.
- **`overview.md` and `cloud-native-security.md`:** at 1.29, `concepts/security/overview.md` was deleted and `cloud-native-security.md` added. They aren't a rename: their similarity is under 10%, and the redirect goes to the section index, not the new page.
- **Removed, no redirect:** `service-topology.md` documented the `topologyKeys` API, deprecated since 1.21 in favour of Topology Aware Hints. It was dropped at 1.27 with no redirect.
- **The 38 new pages** have no redirect from a page deleted in the same release. They include the Pod Security Admission pages at 1.22 and `reference/networking/` at 1.25. The full list is in the script output.
- **For T6:** of the 6 deletes with a redirect, 5 point to a page added in the same release (moves) and 1 to an existing page (a removal). A redirect alone isn't enough to create an alias: the target has to be new in that release.
- **Feature gates:** the only unmatched gate deletes are the 2 single pages at 1.29 (section H). The unmatched gate adds are:
  - at 1.25, the `feature-gates-removed.md` page itself
  - at 1.29, the split (section H)
  - from 1.30 on, new gates, 12–26 per release

  After the hand verdicts, `PodInfoAPI` is effectively a delete at 1.37 and `InPlacePodVerticalScalingMemoryBackedVolumes` an add.

### H. The 1.28→1.29 feature-gate split

- **What git shows:** `feature-gates.md` and `feature-gates-removed.md` deleted, and 318 adds: 317 under `feature-gates/` and 1 under `feature-gates-removed/`. git pairs none of them, even at 10%.
- **Two of the adds are the old pages themselves:**
  - `feature-gates/index.md` (title "Feature Gates") and `feature-gates-removed/index.md` (title "Feature Gates (removed)").
  - Hugo serves a folder's `index.md` (a page bundle) at the folder's URL. So these are the same two pages at the same URLs, and there's no redirect because the URL didn't change.
  - git can't pair them because the tables were replaced by a shortcode that renders the per-gate files. The title oracle finds them: they're the 2 feature-gate "missed renames".
- **The other 316 adds are one file per gate.** All have `_build: render: false`: the page includes them, and they aren't pages of their own.
  - 294 of the 316 gate names appear in the 1.28 tables. The other 22 are new gates in 1.29: the 5 checked (`ServiceAccountTokenJTI`, `NFTablesProxyMode`, `LoadBalancerIPMode`, `AllowServiceLBStatusOnNonLB`, `VolumeAttributesClass`) all have their first stage `fromVersion: "1.29"`.
  - So the 1.29 per-gate files are a **split** of the old tables, not renames. Under path identity there are 2 deletes and 318 new documents. Under URL identity the 2 pages continue, and the 316 gate files are new documents whose text came out of the old tables.
  - These are T3a's 318 extra feature-gate versions at 1.29.

### Hand checks

| Check | By hand | Spike |
|---|---|---|
| PSP move, 1.22→1.23 | `git diff -M --name-status` (git's default 50%) between the two locked SHAs, on `content/en/docs/concepts/`: `R081 concepts/policy/pod-security-policy.md → concepts/security/pod-security-policy.md`. `static/_redirects` at 1.23, line 162: `/docs/concepts/policy/pod-security-policy/ → /docs/concepts/security/pod-security-policy/ 301` | 81%, redirect confirms, real |
| Thresholds from one floor run | Separate git runs at 50, 60 and 90% for all 17 pairs | identical to the floor's pairs at or above each score (0 mismatches) |
| Inexact gate renames | Word diff of the 6 sampled pairs: only `stages` additions and `removed: true` | 6 of 6 real |
| 1.28→1.29 split | `git ls-tree` at 1.29: `feature-gates/index.md` and `feature-gates-removed/index.md` exist; `feature-gates.md` doesn't | 2 page files with the old pages' titles |
