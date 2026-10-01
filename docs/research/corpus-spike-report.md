# S02 Corpus spike report

*Slice: `docs/slices/S02-corpus-spike.md` · Status: complete. §1–§7 are the measurements (T2–T5b); §8 is the conclusion (T6).*

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

## 5. Blog identity (S02-T4b)

- **Run:** `uv run python spikes/blog_identity.py` on 2026-09-30, against the same lock. The only new downloads were the site config files, first fetched at the plan review. The posts and the redirect file were already local from T3a and T4a. A second run took 6 seconds, and the cache's object store stayed at the same size (104,390,029 bytes).
- **Method:**
  - **Post histories:** T3a's, unchanged. Each history has one entry per first-parent commit on website `main` that touches the post, and git's rename detection follows moves. That gives 785 histories, 417 of them in scope under T3a's rule. The spike reuses T3a's code: `measure.py`'s `blog_docs` was split so that T4b gets each entry's exact commit time and path. `measure.py`'s output is byte-identical before and after the split.
  - **Caveat: table J's ground truth isn't independent.** "One post" here means one rename-followed history, which comes from git similarity (default threshold 50%). So table J scores each rule against git's pairing, not against an independent source. One known error:
    - In website PR #40392, `2023-04-05-kubescape-validating-admission-policy-library.md` was renamed to `2023-03-30-…`, a week before its date.
    - The pair scores 41%, so git doesn't pair them.
    - So the 417 includes a never-published fragment of that post.
  - **The site config is read, not assumed:**
    - All 69 versions of `config.toml` / `hugo.toml` on `main` since 1.20's release date give the same blog permalink, `/:section/:year/:month/:day/:slug/`.
    - They also give the same front-matter date order: `date`, then the filename, then `publishDate`, then `lastmod`.
    - `timeZone` is `"UTC"`. `buildFuture` is unset, so it's false: Hugo doesn't render a post before its date.
    - The spike refuses to run if any config version differs.
  - **ADR-002 D4 id:** `blog:<date>-<slug>`, from the front matter alone, with the date as written.
  - **Hugo URL** (what the site serves):
    - The pattern is the front-matter `url:` if set (it can contain tokens, and some older posts set it), otherwise the config permalink.
    - The date is the front-matter `date`, else the filename's `YYYY-MM-DD-` prefix, else `publishDate`, else `lastmod`. A date with an offset (`-08:00`) keeps it, as Hugo does, so the URL uses the day as written. Checked: no in-scope URL changes if dates are converted to UTC first.
    - The slug is the front-matter `slug`, else the filename's (only when the date came from the filename too), else the title. Hugo's title-to-slug conversion is approximated: lowercase, punctuation dropped, spaces to hyphens. Hand check below.
  - **Publication:**
    - The first moment Hugo would render the post: the version live at that moment isn't a draft, and its date (`publishDate`, else the date above) has passed. A version with no date at all renders at once.
    - Approximation: the real moment is the first site build after that. This assumes builds run on merge; it wasn't checked against the Netlify build config or build logs. See `ingress-nginx-retirement` under table I.
  - **Units:** identity is checked at every commit, so moves and filename-derived URLs are seen. Version counts use ADR-002 D2 versions: 1,138, the same as T3a's table B.

### I. Front-matter id changes

Each cell is the number of changes between consecutive commits, with the number of posts in brackets. "date missing" means one side has no front-matter date.

| cause | before publication | after publication | never published |
|---|---:|---:|---:|
| date missing | 65 (63) | 1 (1) | 0 (0) |
| date | 47 (46) | 2 (2) | 0 (0) |
| date + slug | 15 (15) | 0 (0) | 0 (0) |
| date missing + slug | 14 (14) | 0 (0) | 0 (0) |
| slug missing | 1 (1) | 2 (2) | 0 (0) |
| date missing + slug missing | 1 (1) | 1 (1) | 0 (0) |
| slug | 1 (1) | 0 (0) | 0 (0) |

- **137 of the 417 posts change id at least once.** The slice's T4a-draft note said 136. That draft wasn't kept, and the one-post difference wasn't traced. It isn't the date's offset or the case of the front-matter keys.
- **Pre-publication versions explain almost all of the changes: 144 of 150 (96%).**
  - "date missing" is mostly placeholder drafts, for example `XXXX-XX-XX-dra-134-update.md`, which has `draft: true` and `date: XXXX-XX-XX`.
  - "date" is mostly re-scheduling. For example, `introducing-jobset` was added as a draft dated 02-03, then re-dated to 03-23 when it was scheduled.
- **The 6 changes after publication, one per post (5 real edits and 1 parser artifact):**
  1. **`kubernetes-1.28-release-interview`:** PR #53902 added a slug. The URL is unchanged, because the title fallback already produced that slug.
  2. **`k8s-book-club`:** a parser artifact, not an edit.
     - Its first 3 versions open the front matter with `------` (§2, finding 3), so the spike reads no date or slug from them. The fix on 2024-05-20 shows up as "date missing + slug missing".
     - The URL is unchanged, because the bundle folder `2024-02-22-k8s-book-club/` gives Hugo's filename date and slug.
     - It's the only in-scope post with unparseable front matter.
  3. **`headlamp-in-2025-project-highlights`:** a slug was added. The URL is unchanged.
  4. **`introducing-headlamp-plugin-for-karpenter`:** a date was added, and the URL moved from 09-23 to 10-06. A redirect covers the old URL.
  5. **`ingress-nginx-retirement`:** the date went from 11-12 to 11-11. There's no redirect and no alias. The old URL may never have been served, but that depends on an unchecked assumption:
     - Version 1 was merged at 15:49 UTC with a date of 17:00 UTC.
     - The next merge, at 17:17 UTC, moved the date to 18:30 UTC.
     - The merge at 17:53 UTC moved it to 11-11, which published it at once.
     - So the old URL could only have been served by a build between 17:00 and 17:17 UTC. There was no merge in that window. Scheduled builds weren't checked.
  6. **`ccm-new-metric-route-sync-total`:** the date went from 02-26 to 05-15. The new version's `aliases` lists the old URL, and the post says it "was originally published with the wrong date".

### J. Identity rules, scored over the in-scope post histories

"Kept whole" means one id across the history. "Published commits" means from the version live at publication onwards. 416 posts were published; the one that wasn't is the kubescape fragment.

| rule | kept whole, every commit | kept whole, published commits | ids shared by two posts | needs rename following |
|---|---:|---:|---:|---:|
| ADR-002 D4 front-matter id, per commit | 276 | 406 of 416 | 0 | no |
| A: latest date and slug, applied backwards | 413 | 412 of 416 | 0 | yes |
| B: Hugo URL, per commit | 284 | 413 of 416 | 0 | no |

- **No collisions under any rule.** No id or URL is shared by two posts.
- **D4 per-version id:** 10 published histories split. These are the 6 changes after publication (table I) and the 4 posts with no `slug`: the 1.21–1.24 release interviews, for which D4 has no id.
- **Rule A keeps every history whole by construction.** It misses only the 4 interviews with no slug. Its weaknesses don't show in the score:
  - It depends on rename following, and git missed the kubescape rename.
  - The id comes from the latest version, so it moves when the latest version changes. For 6 posts (5 without the `k8s-book-club` artifact), the id at publication differs from the id at the head. An ingestion run at publication and another at the head would give those posts different `canonical_id`s.
- **Rule B splits 133 histories over every commit, as expected.** Re-scheduling a post before publication changes its URL, but those URLs were never public.
  - **Over published commits, it keeps 413 of 416.** The 3 splits are table I's posts 4–6. Its 3 old URLs: 1 has a redirect, 1 an alias, and 1 has neither (`ingress-nginx-retirement`, possibly never served).
  - **Declared signals cover 2 of the 3 old URLs.** The third might never have been served, but only under the build-on-merge assumption. That's 2 data points, too few to claim the blog's redirects and aliases are complete.
  - **It needs no rename following, by inference rather than a direct test.**
    - All 349 in-scope moves by PR #53902 keep the URL (table L), and no URL is shared by two posts. So grouping the published commits by URL would rebuild the same histories without git.
    - The spike didn't run that grouping. Those 349 moves are also the ones git paired.
    - 2 more in-scope posts moved by PR #53902 weren't measured, because they lost their `.md` extension (table L).

### K. Versions by publication phase (ADR-002 D2 versions)

| phase | versions | posts |
|---|---:|---:|
| superseded before publication | 213 | 168 |
| live at publication | 416 | 416 |
| after publication | 508 | 272 |
| never public | 1 | 1 |

- **Superseded before publication:** 213 versions, in 168 posts, were replaced before the post went live, so they were never public.
- **Live at publication:**
  - 317 of the 416 versions live at publication were merged ahead of their date: median 2.6 days, maximum 28.5.
  - With `valid_from` = commit time, those 317 would claim their text was public up to 28 days early.
  - The other 99 were merged after their date, so publication happened at the commit.
  - With `valid_from` = max(commit time, publication time), 25 of the 317 move to a later release row. T3a assigned blog versions to release rows by commit time (§2).
- **Never public:** the 1 version is the kubescape fragment.
- **Effect on earlier sections if T6 excludes never-public versions:** 214 of T3a's 1,138 blog versions go (19%; 213 superseded plus the fragment). That's 6.5% of the 3,281 embeddable versions. §2's per-release counts and §3's cost estimate would both drop. The token effect wasn't computed.

### L. Path changes (moves) in the in-scope histories

| move | moves | same front-matter id | same Hugo URL |
|---|---:|---:|---:|
| PR #53902 | 349 | 348 | 349 |
| other, after publication | 21 | 20 | 20 |
| other, before publication | 100 | 11 | 11 |

- **PR #53902 keeps both identities.** All 349 moves keep the URL. 348 keep the front-matter id; the exception is the 1.28 interview, which gained a slug in the same commit. This answers the T3a review question: no collisions, and the slug fallback matters for 4 posts.
- **Two more in-scope posts were moved by PR #53902 to files with no `.md` extension:** `_posts/2022/kubernetes-1.23-release-interview` and `…/kubernetes-1.24-release-interview`.
  - The spike counts only `*.md` files, like T3a, so it sees these two deleted at the move.
  - Whether Hugo still renders them wasn't checked. Recorded in the backlog for S04.
- **Other moves after publication:** mostly page-bundle conversions (`x.md` → `x/index.md`) and filename fixes (case, typos), which don't change the URL. The 1 exception is `introducing-headlamp-plugin-for-karpenter` (table I, post 4).
- **Other moves before publication:** filename changes while a post is being scheduled, for example `XXXX-XX-XX-dra-134-update.md` → `2025-09-01-dra-134-update.md`.

### Hand checks

| Check | By hand | Spike |
|---|---|---|
| Title fallback (no `slug`) | Links on the site: `/blog/2018/07/16/how-the-sausage-is-made-the-kubernetes-1.11-release-interview-from-the-kubernetes-podcast/` and `/blog/2019/05/13/cat-shirts-and-groundhog-day-the-kubernetes-1.14-release-interview/`. Neither post has `slug` or `url` in its front matter. | `hugo_url` gives both exactly |
| Pre-publication date change: `introducing-jobset` | `git log --raw`: added 2025-01-28 as `2025-02-03-…/index.md` with `draft: true`; renamed 2025-03-05 to `2025-03-23-…` with `date: 2025-03-23`; moved by PR #53902 | 1 version superseded before publication, 1 live at publication (merged 17 days ahead), 1 date change before publication |
| Old URL with a redirect: `introducing-headlamp-plugin-for-karpenter` | `static/_redirects.base` at the head, line 488: `/blog/2025/09/23/… /blog/2025/10/06/… 301` | redirect |
| Old URL with an alias: `ccm-new-metric-route-sync-total` | The front matter at the head has `aliases: [/blog/2026/02/26/ccm-new-metric-route-sync-total]` | alias |
| Old URL with neither: `ingress-nginx-retirement` | 3 commits on 2025-11-12, with `date:` values `12:00-05:00`, `10:30-08:00`, then `2025-11-11T10:30-08:00`. No rule in `_redirects.base` and no `aliases`. | none; the 17:00 UTC publication comes from the approximation, and whether the old URL was served is unverified (table I, post 5) |
| kubescape split | `git diff -M10%` across website PR #40392: `R041 2023-04-05-kubescape-… → 2023-03-30-kubescape-…` | 2 histories, 1 never published |
| Extensionless interviews | `git ls-tree` at the head: `_posts/2022/kubernetes-1.23-release-interview` and `…1.24-release-interview` are blobs with no extension, added by PR #53902 | both histories end in a delete at PR #53902 |

## 6. Format checks (S02-T5a: latest release and feature gates)

- **Run:** `uv run python spikes/formats.py` on 2026-09-30, against the same lock. Nothing was downloaded: the T3a cache already held all 881 feature-gate blobs, and the cache's object store stayed at 104,390,029 bytes across two runs. The second run took 3.5 seconds and printed the same output.
- **Split:** T5 was split at plan review (slice doc, T5 notes). This section answers the latest release and the feature gates. T5b adds the CHANGELOG, blog and `kep.yaml` checks.

| question | answer | example |
|---|---|---|
| What's the latest release, and which branch holds its docs? | **1.37, on website `main`.** There's no `release-1.37` branch yet. The manifest's `latest: "1.37"` and `website_release_branches.latest: main` are correct. | `hugo.toml` on `main`: `latest = "v1.37"`. GitHub's latest release is `v1.37.1` (table M). |
| Does the feature-gates reference give a stage per version? | **Yes, as version ranges, in two formats.** The stage at release R is a range lookup. Every gate has ranges in every release. | `PodSecurity`: alpha 1.22–1.22, beta 1.23–1.24, GA/stable 1.25–1.27, identical in both formats (table O). |
| Is it reliable? | **Mostly, not fully.** The two formats agree on the stage at every minor release 1.0–1.28 for 287 of the 293 gates they share (98%). 0–3% of gates per release have ranges that leave some release's stage undefined or ambiguous. Later files rewrite earlier history for 2 gates. | `EventedPLEG`: beta at 1.27 in the 1.28 table, alpha only in the 1.37 file (table O). |

### M. Latest release (hand check)

| signal | where | result |
|---|---|---|
| Website release branches | `git for-each-ref 'refs/remotes/origin/release-1.*'` in the cache (fetched 2026-09-30) | `release-1.20` to `release-1.36`. No `release-1.37`. |
| Site config | `hugo.toml` at the website lock head, lines 140–144 and 182–186 | `latest = "v1.37"` and `docsbranch = "main"`. The first `[[params.versions]]` entry is v1.37, with `docsbranch = "main"`. v1.36's is `release-1.36`. |
| CHANGELOG | `CHANGELOG-1.37.md` at the kubernetes lock head | `# v1.37.1` (line 157) and `# v1.37.0` (line 254), then rc.1, rc.0, beta.0 and alpha.3 to alpha.1 |
| GitHub, live | `gh api repos/kubernetes/kubernetes/releases/latest`, run 2026-10-01T05:57Z | `v1.37.1`, published 2026-09-23T19:13:17Z, not a pre-release |

- **`hugo.toml`'s `githubbranch = "v1.37.0"` lags the patch release,** so it can't be used as a patch signal. Only the minor release matters here.
- **`CHANGELOG-1.38.md` exists at the kubernetes head but wasn't read.** It's outside the manifest, and downloading it was declined at plan review.

### N. Feature gates per release

- **Formats:**
  - **1.20–1.28:** markdown tables in `feature-gates.md`, under "Feature gates for Alpha or Beta features" and "Feature gates for graduated or deprecated features". From 1.25, also `feature-gates-removed.md`, whose table names its columns `From | To` instead of `Since | Until`. Each row is one gate and one stage.
  - **1.29–1.37:** one file per gate, with a `stages:` list in the front matter. Each entry has `stage`, `fromVersion` and, optionally, `toVersion`. Other keys (`defaultValue`, `locked`) are ignored here.
- **Gate identity:** the gate name, which is the first table column or the file's `title` (T4a).
- **Ranges** include both ends. An open end is an empty cell or `-` in the tables (591 `-` cells across the 9 table releases), and a missing `toVersion` in the files.
- **Stage values** are compared after case and whitespace normalization, with GA = stable: the tables say `GA`, the files `stable`. Any other value is reported as is, not mapped.
- **Range problems:**
  - an unparseable version
  - a range that ends before it starts
  - an open range that isn't the last
  - an overlap
  - a gap

  The next range must start at the next minor release, or at the next patch when the previous range ends at a patch.
- **Version values:** all 2,949 `fromVersion`/`toVersion` values in the 868 distinct gate-file versions of 1.29–1.37 are quoted strings (scratch check). So YAML never reads `1.10` as the float `1.1`. S04's parser should still reject values that aren't strings.

| release | format | gates | with ranges | stage values | gates with a problem |
|---|---|---:|---:|---|---|
| 1.20 | tables | 153 | 153 | Alpha 139, Beta 103, GA 52, Deprecated 14, True 1 | open range not last 5 |
| 1.21 | tables | 170 | 170 | Alpha 152, Beta 115, GA 65, Deprecated 13, Derecated 1 | open range not last 2, gap 1 |
| 1.22 | tables | 196 | 196 | Alpha 179, Beta 136, GA 77, Deprecated 25, Derecated 1 | open range not last 4, gap 1 |
| 1.23 | tables | 216 | 216 | Alpha 196, Beta 151, GA 81, Deprecated 26 | open range not last 2, gap 1 |
| 1.24 | tables | 224 | 224 | Alpha 202, Beta 163, GA 100, Deprecated 26 | gap 1 |
| 1.25 | tables | 238 | 238 | Alpha 217, Beta 173, GA 112, Deprecated 26 | unparseable version 1 |
| 1.26 | tables | 257 | 257 | Alpha 233, Beta 182, GA 127, Deprecated 26 | unparseable version 1 |
| 1.27 | tables | 272 | 272 | Alpha 245, Beta 204, GA 135, Deprecated 26, ``Beta` `` 1 | unparseable version 1 |
| 1.28 | tables | 294 | 294 | Alpha 261, Beta 219, GA 147, Deprecated 32 | open range not last 2, unparseable version 1 |
| 1.29 | per-gate files | 316 | 316 | alpha 278, beta 234, stable 157, deprecated 34 | none |
| 1.30 | per-gate files | 328 | 328 | alpha 288, beta 250, stable 169, deprecated 34 | overlap 3, open range not last 1 |
| 1.31 | per-gate files | 346 | 346 | alpha 299, beta 275, stable 182, deprecated 36 | overlap 3, open range not last 1 |
| 1.32 | per-gate files | 372 | 372 | alpha 320, beta 290, stable 197, deprecated 38 | overlap 3, open range not last 2 |
| 1.33 | per-gate files | 398 | 398 | alpha 341, beta 314, stable 214, deprecated 44 | overlap 3, open range not last 2 |
| 1.34 | per-gate files | 420 | 420 | alpha 353, beta 340, stable 241, deprecated 45 | open range not last 3, overlap 3 |
| 1.35 | per-gate files | 440 | 440 | alpha 367, beta 361, stable 248, deprecated 46 | open range not last 3, overlap 3 |
| 1.36 | per-gate files | 465 | 465 | beta 389, alpha 383, stable 266, deprecated 47 | open range not last 3, overlap 3 |
| 1.37 | per-gate files | 488 | 488 | beta 410, alpha 401, stable 280, deprecated 49 | overlap 5, open range not last 4 |

- **Every gate has ranges in every release.**
- **Typos in the table stages and versions, one row each:**
  - `True` in the Stage column (1.20, `LegacyNodeRoleBehavior`)
  - `Derecated` (1.21–1.22, `RequestManagement`)
  - ``Beta` `` with a stray backtick (1.27, `ElasticIndexedJob`)
  - `1,24` for 1.24 (1.25–1.28, `SetHostnameAsFQDN`, on the removed page)

  The per-gate files have no values outside alpha, beta, stable and deprecated.
- **Range problems affect 0–3% of gates per release:** at most 5 gates in the tables (5 of 153 at 1.20 is 3.3%), and at most 9 of 488 (1.8%) in the files, at 1.37. The script lists each one.
  - **In the tables, most problems are a gate listed twice,** either in both tables of the page or on both pages. For example, at 1.28 `DaemonSetUpdateSurge` is open-ended GA on the main page and GA 1.25–1.26 on the removed page.
  - **The rest of the table problems:**
    - an earlier stage with no Until, for example `CSIMigrationAWS` at 1.20: Alpha 1.14–, Beta 1.17–
    - a gap: `CSIMigrationAzureFile` is alpha up to 1.19 and beta from 1.21
  - **In the files:**
    - overlaps at a boundary, for example `DRADeviceTaints` at 1.37: beta 1.36–1.37 and stable from 1.37, so 1.37 is both
    - earlier stages with no `toVersion`, for example `ContextualLogging`: alpha 1.24–, beta 1.30–
- **The files have patch-level ranges:**
  - `DisableNodeKubeProxyVersion`: beta 1.31.0–1.31.0, deprecated from 1.31.1
  - `MaxUnavailableStatefulSet`: beta 1.35.0–1.35.3, then beta 1.35.4–1.36

  A stage can change inside a minor release.

### O. Agreement: the 1.28 tables vs the 1.37 files

293 gates are in both the 1.28 tables and the 1.37 files.

| stage at 1.28 | gates | examples |
|---|---:|---|
| same stage | 149 | `APIListChunking`, `APIPriorityAndFairness`, `APIResponseCompression` |
| no stage in either (removed before 1.28) | 141 | `Accelerators`, `AdvancedAuditing`, `AffinityInAnnotations` |
| a stage on one side only | 2 | `DaemonSetUpdateSurge`, `DynamicResourceAllocation` |
| different stage | 1 | `EventedPLEG` |

- **31 of the 149 matches rely on GA = stable.**
- **"No stage in either" is a vacuous match,** so the spike also compares the stage at every minor release 1.0–1.28: **287 of 293 match.** The 6 that don't:

| gate | first differs | 1.28 tables | 1.37 files | cause |
|---|---|---|---|---|
| `EventedPLEG` | 1.27 | Alpha 1.26–1.26, Beta 1.27– | alpha 1.26– | **A real change, rewritten later.** Beta (off by default) from 1.27, then reverted to alpha by patch releases 1.27.10, 1.28.6 and 1.29.1; 1.30.0 shipped it as alpha. Each of those CHANGELOG sections says "Reverts the EventedPLEG feature (beta, but disabled by default) back to alpha". The 1.28 table was right for 1.28.0–1.28.5 and was never updated after the revert. The 1.37 file drops the beta altogether. |
| `DynamicResourceAllocation` | 1.26 | Alpha 1.26– | alpha 1.30–1.31, beta 1.32–1.33, stable 1.34–1.34, stable 1.35– | **History rewritten at 1.32.** The 1.31 file still says alpha from 1.26; the 1.32 file starts at 1.30. 1.32 removed "classic" DRA (CHANGELOG-1.32), and the gate now covers the structured-parameters model only. |
| `DaemonSetUpdateSurge` | 1.27 | GA 1.25– (main page) and GA 1.25–1.26 (removed page) | stable 1.25–1.26 | **A stale duplicate row in the table.** The removed page agrees with the file. |
| `NewVolumeManagerReconstruction` | 1.25 | Beta 1.27–1.27, Beta 1.28– | alpha 1.25–1.26, beta 1.27–1.29, stable 1.30–1.31 | **The table has no alpha row.** |
| `SetHostnameAsFQDN` | 1.22 | GA 1.22–`1,24` | stable 1.22–1.24 | **The `1,24` typo.** Read as 1.24, the two match. |
| `WindowsGMSA` | 1.19 | GA 1.18–1.20 | stable 1.18–1.18 | **They disagree on when the stage ended.** Not resolved here. |

- **2 of the 295 gate names exist only in the pre-1.29 tables. Both are typos fixed later, not gates the files lost:**
  - `PersistentVolumeLastPhaseTransistionTime`: the 1.28 table row (line 165). The same page's description list spells it `…Transition…` (line 670), and so does the 1.29 file.
  - `csiMigrationRBD`: the 1.23–1.24 tables. It's `CSIMigrationRBD` from 1.25.

  So 293 of the 295 table names join a per-gate file exactly, and all 295 do once the two typos are corrected.
- **The site records one gate rename in front matter.** At 1.37, `PodReadyToStartContainersCondition` has `former_titles: [PodHasNetworkCondition]`. Both names also keep their own ranges, in the 1.28 tables and in every file release: the old gate alpha 1.25–1.27, the new one from 1.28.

**In-scope examples:** all four match at every minor release 1.0–1.28.

| gate | 1.28 tables | 1.37 files | first difference |
|---|---|---|---|
| `PodSecurity` (KEP-2579) | Alpha 1.22–1.22, Beta 1.23–1.24, GA 1.25–1.27 | alpha 1.22–1.22, beta 1.23–1.24, stable 1.25–1.27 | none |
| `LegacyServiceAccountTokenNoAutoGeneration` (KEP-2799) | Beta 1.24–1.25, GA 1.26– | beta 1.24–1.25, stable 1.26–1.28 | none |
| `LegacyServiceAccountTokenTracking` (KEP-2799) | Alpha 1.26–1.26, Beta 1.27–1.27, GA 1.28– | alpha 1.26–1.26, beta 1.27–1.27, stable 1.28–1.29 | none |
| `LegacyServiceAccountTokenCleanUp` (KEP-2799) | Alpha 1.28– | alpha 1.28–1.28, beta 1.29–1.29, stable 1.30–1.31 | none |

### For T6

- **ADR-003's open question:** "Does the feature-gates page give a reliable stage-per-version table for every gate in scope?"
  - **Answer:** every gate has one in every release. The two formats match for 98% of the gates they share, over their whole history.
  - **But it's a claim to check, not ground truth:**
    1. 0–3% of gates per release have ranges that leave a release's stage undefined or ambiguous. The parser should flag those gates, for example with `status_confidence = low`, not pick one range.
    2. **Neither snapshot is a complete record.** The 1.28 docs still say `EventedPLEG` is beta after 1.28.6 reverted it, and the 1.37 file drops the beta altogether. Only the CHANGELOG has the revert. That supports ADR-002 D5 using both the CHANGELOG and the gate reference for `observed_stage`. The difference between a release's snapshot and a later one is conflict evidence (ADR-003 D6).
    3. **Later files rewrite earlier ranges** (`EventedPLEG`, `DynamicResourceAllocation`). `observed_stage` for release R should come from R's own snapshot (ADR-002 D1), not from the latest file.
- **Stages can change at a patch release.**
  - Examples: `EventedPLEG`'s revert, and the patch-level ranges of `DisableNodeKubeProxyVersion` and `MaxUnavailableStatefulSet`.
  - ADR-003 D5 keys `lifecycle_stage` by feature × release (minor).
  - T6 decides: keep the minor-release key and record patch changes as a known limit, or key by patch release.
- **Stage vocabulary:**
  - Map `GA` → `stable` at parse time, the only synonym needed.
  - Flag the four table typos and report them; don't map them.
- **Gate identity:** the gate name works across the 1.28→1.29 format change, apart from the two misspelled table names.
  - A case-insensitive match would recover `csiMigrationRBD`, but not `…Transistion…`.
  - `former_titles` is a declared rename signal, in the spirit of T4a's "declared signals first". It covers 1 gate here.

### Hand checks

| Check | By hand | Spike |
|---|---|---|
| `PodSecurity` in the 1.28 tables | `git show <1.28>:…/feature-gates-removed.md`, lines 290–292: alpha 1.22–1.22, beta 1.23–1.24, GA 1.25–1.27 | same ranges |
| `PodSecurity` at 1.37 | `feature-gates/PodSecurity.md`: `stages:` alpha 1.22–1.22, beta 1.23–1.24, stable 1.25–1.27 | same ranges; no difference at any minor |
| KEP-2799 gates in the 1.28 tables | `feature-gates.md`, lines 137 and 289–293 | same ranges for all three |
| `EventedPLEG` disagreement | 1.28 `feature-gates.md` lines 103–104: Alpha 1.26–1.26, Beta 1.27 (Until empty). The 1.37 file has one stage: alpha from 1.26. The revert note is in the CHANGELOG sections `v1.27.10`, `v1.28.6`, `v1.29.1`, `v1.30.0-alpha.1` and `v1.30.0`. | different stage at 1.27 |
| `DaemonSetUpdateSurge` duplicate | 1.28 `feature-gates.md` lines 251–253 (GA 1.25, Until empty) and `feature-gates-removed.md` lines 141–143 (GA 1.25–1.26) | listed twice; differs from 1.27 |
| `1,24` typo | 1.28 `feature-gates-removed.md` line 353: `\| GA \| 1.22 \| 1,24 \|` | unparseable version |
| Table-name typos | 1.28 `feature-gates.md` line 165 `PersistentVolumeLastPhaseTransistionTime`, line 670 `…Transition…`. 1.24 line 88 `csiMigrationRBD`; 1.25 line 82 `CSIMigrationRBD`. | 2 gates only in the tables |
| `DynamicResourceAllocation` rewrite | 1.31 file `dynamic-resource-allocation.md`: alpha from 1.26. 1.32 file `DynamicResourceAllocation.md`: alpha 1.30–1.31, beta from 1.32. | first differs at 1.26 |

## 7. Format checks (S02-T5b: CHANGELOG, KEP metadata and blog)

- **Run:** `uv run python spikes/source_formats.py` on 2026-10-01, against the same lock.
  - **Network:** only the CHANGELOG sample. Two historical versions of `CHANGELOG-1.28.md` came through read-only `gh api` and are saved under `$CORPUS_CACHE_DIR/gh/` (746 KB). T2's depth-1 kubernetes clone wasn't touched.
  - **Everything else was local since T3a.** The five clones' object stores stayed at 138,020,474 bytes in total. The website's share is the 104,390,029 bytes quoted in §5 and §6.
  - **A second run** took 1.7 seconds, made no `gh` calls, and printed the same output.
- **Method:** the three checks are listed in the spike's docstring. In brief:
  - **CHANGELOG:** split each file at its level-1 headings. Sections are paired **by heading, never by position**, because the files are newest first and each release is prepended.
  - **KEP metadata:** `status` and `stage` are classified as parsed by YAML. A case or whitespace variant normalizes; any other value is out of vocabulary, reported and not mapped (T5 notes).
  - **Blog:** T4b's numbers, plus the raw `date` line of each in-scope post at the head.

| question | answer | example |
|---|---|---|
| Does each CHANGELOG have one section per release, under a unique version heading? | **Yes.** 18 files, 371 `# v1.R.x` sections. There are no duplicates, every heading parses as a version of its file's `1.R`, and every file opens with a generated TOC (table P). | `CHANGELOG-1.28.md`: 23 sections, `v1.28.0-alpha.1` to `v1.28.15` |
| Is the structure under each section regular? | **Yes, with one trap.** 3 `##` headings are in all 371 sections, and "Changes by Kind" is in 362. But a stray closing fence in 2 files hides 6 sections from a parser that toggles on every fence (table P). | `CHANGELOG-1.22.md` line 3085 |
| Are written sections immutable (ADR-002 D1)? | **No, in the one sampled file; not exhaustive.** At least 3 of the 23 sections in `CHANGELOG-1.28.md` changed after they were written. That's a lower bound: edits before v1.28.0 weren't measured. Two of the edits are typo fixes; one is a factual correction (table Q). | `v1.28.0`: the pod-index label became `apps.kubernetes.io/pod-index`, 13 months after the release (PR #125502) |
| Are KEP `status` values in vocabulary? | **Yes.** All 440 metadata versions use the template's 7 values or have none (1). There are no case or whitespace variants after YAML parsing (table R). | KEP-2572: `implementable` |
| Are KEP `stage` values in vocabulary? | **No: 1 typo, and 1 valid value that ADR-003 D5 lacks.** `GA` is outside both vocabularies. `disabled` is valid under the KEP template, which allows deprecated, disabled or removed for deprecation KEPs, but ADR-003 D5 has no `disabled`. 76 versions have no stage (table R). | KEP-1611 claimed `stage: "GA"` at 7 release snapshots, 1.27–1.33 |
| Does YAML read any milestone as a non-string (unquoted `1.30` → `1.3`, `yes` → `true`)? | **No.** 0 of 415 `kep.yaml` versions (table R). | KEP-4858: `latest-milestone: "v1.38"` |
| Do blog posts have front-matter dates? | **Yes, all 412 in-scope posts at the head.** S04's parser must accept three YAML types, though: PyYAML returns an offset without a colon as a string (table S). | `date: 2023-03-17T14:00:00+0000` is a `str` |
| Are in-place edits visible in git history? | **Yes.** T4b counted 508 versions committed after publication, in 272 of the 416 published posts (§5, table K). | The NSA/CISA post's "Update, November 2023" note arrived in its own commit, 2 years after publication (hand checks) |

### P. CHANGELOG sections (at the kubernetes lock head)

| release | sections | oldest … newest |
|---|---:|---|
| 1.20 | 23 | v1.20.0-alpha.1 … v1.20.15 |
| 1.21 | 21 | v1.21.0-alpha.1 … v1.21.14 |
| 1.22 | 25 | v1.22.0-alpha.1 … v1.22.17 |
| 1.23 | 25 | v1.23.0-alpha.1 … v1.23.17 |
| 1.24 | 25 | v1.24.0-alpha.1 … v1.24.17 |
| 1.25 | 23 | v1.25.0-alpha.1 … v1.25.16 |
| 1.26 | 22 | v1.26.0-alpha.1 … v1.26.15 |
| 1.27 | 23 | v1.27.0-alpha.1 … v1.27.16 |
| 1.28 | 23 | v1.28.0-alpha.1 … v1.28.15 |
| 1.29 | 22 | v1.29.0-alpha.1 … v1.29.15 |
| 1.30 | 22 | v1.30.0-alpha.1 … v1.30.14 |
| 1.31 | 21 | v1.31.0-alpha.1 … v1.31.14 |
| 1.32 | 21 | v1.32.0-alpha.1 … v1.32.13 |
| 1.33 | 20 | v1.33.0-alpha.1 … v1.33.13 |
| 1.34 | 20 | v1.34.0-alpha.1 … v1.34.12 |
| 1.35 | 16 | v1.35.0-alpha.1 … v1.35.9 |
| 1.36 | 11 | v1.36.0-alpha.1 … v1.36.5 |
| 1.37 | 8 | v1.37.0-alpha.1 … v1.37.1 |

- **No duplicate headings, no level-1 heading that isn't a version of the file's release, and a generated TOC in every file.** The TOC sits before the first section (`<!-- BEGIN MUNGE: GENERATED_TOC -->`), and it changes whenever a release is prepended. Like the sha512 download tables (backlog, from T3b), it has no retrieval value.
- **The `##` headings, by the number of sections that have each:**

| `##` heading | sections (of 371) |
|---|---:|
| Changelog since `<v>` | 371 |
| Dependencies | 371 |
| Downloads for `<v>` | 371 |
| Changes by Kind | 362 |
| Urgent Upgrade Notes | 59 |
| Important Security Information | 44 |
| Known Issues | 6 |
| What's New (Major Themes) | 5 |
| Major Themes | 1 |

- **The stray-fence trap:**
  - Two release notes end with a closing code fence (a line of three backticks) that was never opened. It's left over from the PR template's release-note block:
    - `CHANGELOG-1.22.md` line 3085, in `v1.22.0-beta.1`
    - `CHANGELOG-1.36.md` line 1602, in `v1.36.0-beta.0`
  - **What goes wrong:** a parser that toggles "inside code" on every fence line reads the rest of the file as code. It loses 4 sections in 1.22 (`beta.0`, `alpha.3`–`alpha.1`) and 2 in 1.36 (`alpha.2`, `alpha.1`). The spike's first run did exactly that, and the hand count below caught it.
  - **The fix:** in CommonMark, a fence indented inside a list item ends with the item. The spike now closes an indented fence at the next line in column 0. After the fix, the section counts match `grep -c '^# v'` for all 18 files.
  - **T3b's `split_sections` has the same toggle,** so T3b undercounted these 2 files' sections and chunks (recount below; recorded for S04-T3 in the backlog).

**T3b recount for the two files.** Method: a scratch script. It applies T3b's own estimate (`analyse`, `tally`, `embed_totals`) and changes only the fence rule in `split_sections`. The other 16 CHANGELOGs come out identical.

| file | bound | sections | chunks @512 | embedded tokens @512 |
|---|---|---:|---:|---:|
| `CHANGELOG-1.22.md` | upper | 341 → 427 | 497 → 556 (+59) | 136,067 → 138,435 (+2,368) |
| `CHANGELOG-1.22.md` | lower | 253 → 325 | 409 → 454 (+45) | 131,872 → 133,609 (+1,737) |
| `CHANGELOG-1.36.md` | upper | 141 → 193 | 295 → 332 (+37) | 104,923 → 106,408 (+1,485) |
| `CHANGELOG-1.36.md` | lower | 111 → 153 | 265 → 292 (+27) | 103,512 → 104,538 (+1,026) |

- **Against §3's totals at 512 tokens:**
  - The upper bound gains 96 chunks (55,821 → 55,917, +0.17%) and 3,853 embedded tokens (+0.03%, +$0.0002 at voyage-4).
  - The lower bound gains 72 chunks (26,588 → 26,660, +0.27%) and 2,763 embedded tokens.
  - At 256 and 1,024 tokens: upper +98 and +104 chunks, lower +74 and +80.
- **Body tokens move by less than 70 per file.** The estimate rounds up per section, and some of the new sections are duplicates within their file, so the lower bound drops them.
- **Not done:** §3's tables aren't edited, the floor wasn't recounted, and other sources weren't checked for stray fences.

### Q. Immutability sample: `CHANGELOG-1.28.md` (one sampled file, not exhaustive)

- **Versions:**
  - **after v1.28.0:** commit `8cb979ae`, 2023-08-15, "CHANGELOG: Update directory for v1.28.0 release". It holds 8 sections, `alpha.1` to `v1.28.0`.
  - **after v1.28.15:** commit `6d99b1c8`, 2024-10-23, the last patch release's update. It holds all 23 sections.
  - **locked head:** the kubernetes lock head. Its blob is the file as of `c8681531`, 2025-09-05, the last commit to touch it (hand checks).
- **Commits touching the file:** 34 in total (`gh api …/commits?path=…`).
  - 23 are release-tool commits, one per release from `alpha.1` to `v1.28.15`.
  - 7 commits come before v1.28.0: 5 whose messages describe release-note corrections and 2 merge commits. An example of the first kind is "Remove release-notes for the PR#118895". The sample starts after them, so it doesn't measure them.
  - 4 commits come after v1.28.0. They make 3 edits, and the sample sees all 3.

| pair | identical | identical after `clean_text` | changed | removed | added | duplicate heading |
|---|---:|---:|---:|---:|---:|---:|
| after v1.28.0 → after v1.28.15 | 7 | 0 | 1 | 0 | 15 | 0 |
| after v1.28.0 → locked head | 6 | 0 | 2 | 0 | 15 | 0 |
| after v1.28.15 → locked head | 20 | 0 | 3 | 0 | 0 | 0 |

- **The 3 edits after v1.28.0:**
  1. **PR #125502** (commit `bcd1d845`, merged 2024-09-26), "Fix pod-index label name for StatefulSet Pods". In `v1.28.0`, `statefulset.kubernetes.io/pod-index` became `apps.kubernetes.io/pod-index`. **This corrects a fact,** 13 months after the release: an answer from the earlier text would give the wrong label name.
  2. **`f0ac94ff`, 2024-10-23:** in `v1.28.15`, `kubeamd join` became `kubeadm join`, on the day the section was written.
  3. **`c8681531`, 2025-09-05:** `sattsfied` became `satisfied` in both `v1.28.0-alpha.1` and `v1.28.0`. The `v1.28.0` section repeats the pre-release notes, so one typo appears twice.
- **No section was removed, and none differs only in whitespace or link targets.** Every edit changes words.

### R. KEP metadata (`status`, `stage`, milestones)

- **Units:** distinct metadata versions (blobs) across the 19 enhancements snapshots in the lock, under the three SIG directories.
  - **415 `kep.yaml` versions.** A 416th doesn't parse; see below.
  - **25 single-file KEPs,** whose metadata is front matter. All 25 exist only in the 1.20 snapshot. By 1.21 they've moved to KEP directories: for example, `0014-dynamic-audit-configuration.md` and `600-dynamic-audit-configuration/kep.yaml` have the same title.
  - **8 single `.md` files without metadata,** which are left out: `keps/sig-network/README.md` (an index) and 7 symlinks (mode `120000`) into KEP directories, for example `keps/sig-release/k8s-image-promoter.md` → `1734-k8s-image-promoter/README.md`.
- **Vocabularies:**
  - **The KEP template at the lock head:** `status: provisional|implementable|implemented|deferred|rejected|withdrawn|replaced` and `stage: alpha|beta|stable`. The comment above `stage` adds that a deprecation KEP uses `deprecated|disabled|removed`. So the template allows six stages, and that's the spike's template vocabulary.
  - **ADR-003 D5:** the same 7 statuses, and `lifecycle_stage` = alpha, beta, stable, deprecated, removed. It has no `disabled`.
  - **The enhancements repo's own validator** (`api/proposal.go`, `ValidStages`) accepts the same six stages as the template.

**`status`**

| value | template = ADR-003 D5 | at head | all versions | of which single-file | example |
|---|---|---:|---:|---:|---|
| `implementable` | in vocabulary | 26 | 284 | 14 | `sig-auth/0014-dynamic-audit-configuration.md` |
| `implemented` | in vocabulary | 74 | 121 | 6 | `sig-auth/0000-20170814-bounding-self-labeling-kubelets.md` |
| `provisional` | in vocabulary | 7 | 28 | 4 | `sig-auth/1687-hierarchical-namespaces-subproject/kep.yaml` |
| `withdrawn` | in vocabulary | 4 | 4 | 0 | `sig-auth/600-dynamic-audit-configuration/kep.yaml` |
| `replaced` | in vocabulary | 2 | 2 | 0 | `sig-network/536-topology-aware-routing/kep.yaml` |
| (none) | missing | 0 | 1 | 1 | `sig-network/20190920-external-dns.md` |

**`stage`**

| value | KEP template | ADR-003 D5 | at head | all versions | of which single-file | example |
|---|---|---|---:|---:|---:|---|
| `stable` | in vocabulary | in vocabulary | 79 | 148 | 0 | `sig-network/1453-ingress-api/kep.yaml` |
| `alpha` | in vocabulary | in vocabulary | 20 | 126 | 0 | `sig-network/1435-mixed-protocol-lb/kep.yaml` |
| `beta` | in vocabulary | in vocabulary | 5 | 81 | 0 | `sig-auth/541-external-credential-providers/kep.yaml` |
| (none) | missing | missing | 5 | 76 | 25 | `sig-auth/0000-20170814-bounding-self-labeling-kubelets.md` |
| `deprecated` | in vocabulary | in vocabulary | 3 | 6 | 0 | `sig-network/4974-deprecate-endpoints/kep.yaml` |
| `disabled` | in vocabulary | **out of vocabulary** | 1 | 2 | 0 | `sig-network/4004-deprecate-kube-proxy-version/kep.yaml` |
| `GA` | **out of vocabulary** | **out of vocabulary** | 0 | 1 | 0 | `sig-network/1611-network-policy-validation/kep.yaml` |

- **"Normalizes" is empty: YAML absorbs the variants.** At the head, 9 raw `stage:` lines are quoted (7, such as `stage: "stable"`) or end in a space (2). YAML reads all 9 as plain in-vocabulary strings.
- **`GA` is a typo with a long life.** KEP-1611's single `kep.yaml` version with `stage: "GA"` is the claim at 7 release snapshots, 1.27–1.33. It became `stable` by 1.34. Its status was `implemented` throughout.
- **`disabled` isn't a typo.** KEP-4004, which deprecates the kube-proxy version field, has used it from the 1.33 snapshot to the head. The template allows it for deprecation KEPs and the validator accepts it. Only ADR-003 D5 lacks it.
- **76 versions have no stage:**
  - all 25 single-file KEPs, because the old format had no `stage` key
  - 51 `kep.yaml` versions, 5 of them at the head
- **Milestones:**
  - **0 non-string values.** Every `latest-milestone` and `milestone.<stage>` value is quoted or starts with `v`.
  - 47 of the 415 `kep.yaml` versions have an empty or missing `latest-milestone`.
  - **The `milestone` keys:** `alpha` 291, `stable` 286, `beta` 285, `deprecated` 9 and `disabled` 2 (both valid under the template), and `GA` 1. The `GA` key is KEP-2595's, at the 1.22 snapshot only; it's a different KEP from the `GA` stage.
- **One `kep.yaml` doesn't parse:** KEP-1205's (bound service account tokens) at the 1.20 snapshot.
  - It starts and ends with `---`, so `yaml.safe_load` sees a second, empty document and raises "expected a single document in the stream". Its later versions parse.
  - Reading the first document with `safe_load_all` would recover `status: implementable` and `stage: beta`.
- **T3a counted the 7 symlinks as KEP documents:** `measure.ls_tree` keeps every blob, and a symlink is a blob. That's 7 tiny versions of 3,281, too few to recompute. S04 should skip symlinks.

**Traced KEPs at the head** (parsed and raw `latest-milestone` are identical; all are quoted):

| KEP | status | stage | `latest-milestone` (raw) | `milestone` |
|---|---|---|---|---|
| 2572 | implementable | alpha | `"v1.22"` | alpha v1.22, beta v1.23, stable v1.26 |
| 2579 | implemented | stable | `"v1.25"` | alpha v1.22, beta v1.23, stable v1.25 |
| 2799 | implemented | stable | `"v1.30"` | beta v1.24, stable v1.30 |
| 4858 | implemented | stable | `"v1.38"` | alpha v1.33, beta v1.36, stable v1.38 |

- **KEP-2572** still claims `alpha` and `implementable`, while its own milestone map says stable at v1.26. That's ADR-003's first example.
- **KEP-4858** claims `implemented` and `stable` for v1.38, which isn't released: the latest is 1.37 (§6, table M). That's ADR-003's other example, the claim running ahead of the release.
- **KEP-2579's** stable v1.25 matches `PodSecurity`'s GA from 1.25 in both feature-gate formats (§6, table O).

### S. Blog: front-matter dates and in-place edits

- **Dates:** T3a's scope rule applied to the files at the website head gives 412 posts. That's T3a's 417 in-scope histories minus 5 that end in a delete, among them the 2 extensionless interviews (§5, table L) and the kubescape fragment (§5, table J). All 412 have a front-matter `date`.

| raw `date`, digits as 9 | posts | PyYAML returns |
|---|---:|---|
| `9999-99-99` | 259 | `date` |
| `9999-99-99T99:99:99-99:99` | 137 | `datetime` with offset |
| `9999-99-99T99:99:99+99:99` | 7 | `datetime` with offset |
| `9999-99-99T99:99:99+9999` | 7 | **`str`** |
| `9999-99-99T99:99:99-9999` | 1 | **`str`** |
| `9999-99-99T99:99:99.999Z` | 1 | `datetime`, UTC |

- **8 posts write the offset without a colon** (`+0000`, `-0800`). YAML 1.1's timestamp pattern needs the colon, so PyYAML returns a string. Python's `datetime.fromisoformat` parses those strings, and T4b's `front_time` already handles them. S04's parser must accept all three types. No date is quoted.
- **2 of the 773 post files at the head have no front-matter date.** Both are outside T3a's scope:
  - `2026/scaling-kubernetes-workloads-with-node-swap/index.md`, a draft
  - `2024/validating-admission-policy-ga/index.md`, whose front matter opens with `------` (§2, finding 3; not fetched live, as agreed in the T5 notes)
- **In-place edits:** yes. T4b's table K counts 508 ADR-002 D2 versions committed after publication, in 272 of the 416 published posts. The hand check below follows one dated update note.

### For T6

Questions for T6, with the evidence above:

- **ADR-002 D1 assumes CHANGELOG sections never change. Does that still hold?**
  - In the sample, at least 3 sections changed after they were written: two typo fixes, and one factual fix 13 months after the release (table Q).
  - One sampled file can't give a rate.
  - If the assumption goes: should a corrected section replace the old text, or become a new version like other date-scoped sources (ADR-002 D2/D3)? And should S04 re-read and hash every section at each ingestion?
- **Should `disabled` join ADR-003 D5's `claimed_stage` vocabulary?** The KEP template allows it for deprecation KEPs and the validator accepts it (KEP-4004). Direction at the T5b review: yes, add it.
- **Should `GA` be mapped to `stable`, or flagged?** It was KEP-1611's claim at 7 release snapshots. T5a maps `GA` → `stable` for feature gates.
- **What should ADR-003 D2's fallback do for the 76 versions with no `stage`** (25 old-format KEPs, 51 `kep.yaml` versions)? Is "no claim" a separate state from `status_confidence = low`?
- **How should a `kep.yaml` that fails to parse be handled?** KEP-1205's 1.20 version parses if its first YAML document is read (`safe_load_all`).
- **Does §3's cost estimate need a correction for the stray fence?** The recount adds 96 chunks (+0.17%) and 3,853 embedded tokens (+$0.0002 at voyage-4) to the upper bound at 512 (table P).
- **Can ADR-002's validation item on blog dates and in-place edits be ticked?** Both checks say yes (table S; §5, table K). The NSA/CISA hand check also shows that an update note's own date ("November 2023") can differ from its commit date (2023-12-27). T4b's `valid_from` rule follows the commit.

### Hand checks

| Check | By hand | Spike |
|---|---|---|
| CHANGELOG section counts | `grep -c '^# v'` on each of the 18 files at the lock head | same count for all 18. Before the stray-fence fix, the spike gave 21 for 1.22 and 9 for 1.36, against 25 and 11. |
| Stray fence | `CHANGELOG-1.22.md` lines 3084–3087: a release-note line, a line of three backticks indented 2 spaces, a blank line, then the PR template's `#### Additional documentation…`. `CHANGELOG-1.36.md` line 1602 is the same, indented 3. | 25 and 11 sections |
| Sample commits | `gh api --paginate 'repos/kubernetes/kubernetes/commits?path=CHANGELOG/CHANGELOG-1.28.md'`: 34 commits. `8cb979ae` is "…for v1.28.0 release" and `6d99b1c8` is "…for v1.28.15 release". | the pinned `SAMPLE_REFS` |
| Locked head = last edit | The `gh api` raw file at `c8681531`, piped to `git hash-object --stdin`, gives `34535d47…`, the blob at the kubernetes lock head | the "locked head" rows |
| Label fix | `gh api repos/kubernetes/kubernetes/pulls/125502/files`: one changed line in `CHANGELOG-1.28.md`. `…/pulls/125502/commits` lists `bcd1d845` only. | `v1.28.0` changed |
| KEP-2572 at the head | `git show <head>:keps/sig-release/2572-release-cadence/kep.yaml`: line 14 `status: implementable`, line 30 `stage: alpha`, line 35 `latest-milestone: "v1.22"` | same |
| `GA` and `disabled` across snapshots | KEP-1611's `kep.yaml`: `stage: "GA"` at 1.27–1.33, `"stable"` from 1.34. KEP-4004's: `alpha` at 1.29–1.30, `beta` at 1.31–1.32, `disabled` from 1.33. | 1 and 2 versions |
| `GA` as a milestone key | Every `kep.yaml` version at every snapshot: only KEP-2595's (`2595-expanded-dns-config`), at the 1.22 snapshot | `GA` 1 |
| Unparseable `kep.yaml` | KEP-1205's at the 1.20 snapshot has `---` on lines 1 and 38. `yaml.safe_load` raises "expected a single document in the stream". | the one `kep.yaml` without metadata |
| Symlinks | `git ls-tree <head> -- keps/sig-release/ keps/sig-auth/`: mode `120000` on the 7 files, for example `k8s-image-promoter.md`, whose content is `1734-k8s-image-promoter/README.md` | 7 `.md` files without metadata |
| Vocabularies | `gh api` at the enhancements lock head: `keps/NNNN-kep-template/kep.yaml` line 9 (`status`) and lines 24–27 (the `stage` line and the deprecation comment above it), and `api/proposal.go` lines 44–51 | `STATUSES`, `TEMPLATE_STAGES` |
| Offset without a colon | `yaml.safe_load("date: 2024-03-01T10:00:00+0000")` gives a `str`, and T4b's `front_time` reads it as 10:00 UTC. `git grep` lists 9 such dates or millisecond dates, matching the table's 8 + 1. | 8 + 1 posts |
| In-place edit: NSA/CISA post | Added 2021-10-04 (`a72f7fac`, PR #29791) with `date: 2021-10-05`. On 2023-12-27, `8aecf063` (PR #44031) added `**Update, November 2023:**` and changed the guidance link. PR #53902 moved it with no content change (R100). | after publication, so 1 of T4b's 508 |

## 8. Conclusion (S02-T6)

- **Decided:** 2026-10-01, by the developer, on the questions raised in §2–§7.
- **Result:** ADR-002 and ADR-003 are Accepted, with amendments. Each ADR ends with a "Changes from the S02 spike" table that lists what changed and the evidence for it.
- **This report's tables stay as measured.** The decisions below change some counts slightly; the cost section says by how much.

### T. ADR-002's validation items

| item | answer | evidence |
|---|---|---|
| Files and versions per release; chunk estimate; embedding cost | 1,745 documents and 3,862 versions, 3,281 of them embeddable. 26,588–55,821 chunks at 512 tokens, $0.42–$0.79 at voyage-4. | §2 A–B, §3 C–D |
| Do the release branches exist, and do the paths match? | Yes: `release-1.20` to `release-1.36`, with 1.37 on `main`. A release's file count matches `git ls-tree`. | §2 hand checks, §6 M |
| Rename detection on a known Auth or Network move | The PSP page, 1.22→1.23, at 81%, confirmed by its redirect | §4 E |
| Do blog posts have dates, and are in-place edits visible in git? | Yes. All 412 in-scope posts at the head have a front-matter date. 508 versions were committed after publication, in 272 posts. | §5 K, §7 S |

### Cost against the budget

- **Budget:** up to $5, one-off, to embed the Stage 1 subset once. Set by the developer at T6.
- **The estimate fits.** It's $0.42 at voyage-4 (512-token chunks, lower bound). The most expensive row is $1.66 (voyage-4-large, 256-token chunks, upper bound), and $3.33 if characters ÷ 4 undercounts by half. Every row also fits within Voyage's 200M free tokens (§3 D).
- **Each extra embedding model** in an ablation costs about the same again.
- **Changes since §3, not applied to its tables:**
  - the stray-fence recount: +96 chunks, +0.17% on the upper bound at 512 (§7 P)
  - never-public blog versions aren't stored (ADR-002 D3): −214 of the 3,281 embeddable versions (−6.5%). The token effect wasn't computed.
  - 7 symlinks that T3a counted as KEP documents: −7 versions (§7 R)
  - gate-name identity: the 1.32 gate renames stop being new documents, so the lower bound drops slightly (§3 caveats)
  - the `head` snapshot for KEPs and governance docs (ADR-002 D1) adds nothing: §2's `head` row already counts those changes.

  Together these move the estimate by a few percent at most, so the budget conclusion doesn't change.

### U. Decisions

| # | question | decision | evidence | ADR |
|---|---|---|---|---|
| 1 | CHANGELOG sections are edited after they're written | Version the file by D2 at each ingestion. Text from before the first ingestion isn't reconstructed. | §7 Q | 002 D1, D3 |
| 2 | KEP and governance changes after the latest release are missed | Add a `head` snapshot, at the lock's default-branch heads | §2, finding 4 | 002 D1 |
| 3 | Identity of docs pages and feature gates | The URL for rendered pages (`web:<URL path>`); the gate name for gate files | §4 H, §6 O | 002 D4 |
| 4 | Rename detection | Declared signals first: a redirect to a page that's new in that release, `aliases`, `former_titles`. git similarity at 50% as the fallback. | §4 E–G | 002 D4 |
| 5 | Blog identity | The URL at publication, never changed; later URLs become aliases | §5 J, L | 002 D4 |
| 6 | Blog `valid_from` | max(commit time, publication time) | §5 K | 002 D3 |
| 7 | Never-public blog versions | Not stored: decision 6 gives them an empty window | §5 K | 002 D3 |
| 8 | The 25 single-file KEPs at 1.20 | A known limit: separate documents from their later KEP directories | §7 R | 002 Consequences |
| 9 | `disabled` and `GA` | Add `disabled` to `claimed_stage`. `GA` → `stable` is the only synonym; other unknown values are flagged. | §6 N, §7 R | 003 D5 |
| 10 | KEP versions with no `stage` | "No claim": separate from low confidence, and never a `claim_mismatch` | §7 R | 003 D2 |
| 11 | Stages that change at a patch release | Keep the per-minor key, and flag the release with `status_confidence = low` | §6 N–O | 003 D2, D5 |
| 12 | Is the feature-gates reference reliable? (ADR-003's open question) | Answered. It's an observation, not ground truth: `observed_stage` comes from R's own snapshot, and the CHANGELOG is a second source. | §6 O | 003 D2 |

The other questions in §7's "For T6":
- **A `kep.yaml` that fails to parse:** read its first YAML document, and record any failure in the ingestion report. That's an S04-T2 parsing rule, already in the backlog; no ADR change.
- **A §3 correction for the stray fence:** not needed (see the cost section).

### Not validated by the spike

These are assumptions in the accepted ADRs that the spike didn't test:

- `git log --follow` for governance docs (ADR-002 D4). Never run.
- Grouping blog versions by URL with no git rename following. Inferred from table L, not run directly (§5 J).
- The blog publication time assumes the site builds on every merge. Not checked against the build config or logs (§5, method).
- CHANGELOG edits: one sampled file, so there's no rate (§7 Q).
- Token counts use characters ÷ 4, not Voyage's tokenizer (backlog, S04-T4).

### Handed to later slices

- **S03-T2 (domain model):**
  - one vector per chunk row, or one per content hash (§3 caveats; already in the backlog)
  - the CHANGELOG's release window, now that its versions are dated by ingestion (the manifest lists it under `clock: release`)
  - `document_aliases` holds both old URLs and old gate names
- **S04/S05:** the parsing items in the backlog's proposed additions: stray fences, front-matter variants, KEP metadata, the extensionless interviews.
- **S09:** whether the blog ranks above governance docs; turning CHANGELOG notes into `observed_stage`; comparing a claimed `disabled` with observed stages.
