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
