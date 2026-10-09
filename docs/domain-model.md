# Domain model

- **Status:** Approved by the developer (S03-T2, S03-R1 sitting, 2026-10-04). Amended in the S04-R1 sitting (2026-10-04): one vector per unique text, the chunk header, and how windows are derived. Amended in the S05-R1 sitting (2026-10-07): windows from 1.20, release records, the reset, renames, feature gates. Amended in the S05-R2 sitting (2026-10-07): merge-time dating, the release clamp of date-scoped sources, KEPs and governance docs, blog posts, CHANGELOGs, R10. Amended in the S05-R3 sitting (2026-10-07): the chunking rules (S05-T7), the ingestion report and its fingerprint (S05-T8).
- **Builds on:** ADR-002 (versions, windows, identity), ADR-003 (source types, statuses), ADR-005 (data access, where rules live)
- **Implemented by:** migration `0002` (S03-T3), the data-access functions in `src/orgknow/db/` (S03-T4), the releases seed (S03-T5); migration `0003` and ingestion (S04-R1); migration `0004` and dense retrieval (S04-T5); migration `0005` and lexical search (S07-T1)

This is the spec for the tables, their rules, and the write functions S04 ingestion calls. If code and this doc disagree, fix one of them in the same PR.

## Meaning of a version and its windows

- A **document** has one stable identity, its `canonical_id` (ADR-002 D4). Later URLs or names are **aliases**.
- A **version** is a change in normalized content (ADR-002 D2). A version's content can match an earlier version's (A → B → A): it's still a new version.
- Every version has two windows (ADR-002 D3):

| Window | Bounds | Meaning | Open `until` |
|---|---|---|---|
| **Date** | Half-open `[from, until)`, `timestamptz` | When this text was the live text | This is the current text |
| **Release** | Inclusive `[from, until]`, release minor numbers (24 = v1.24) | Which releases this text speaks for | It still speaks for the latest release |

- **Release window per source:**
  - **Docs and other release-branch sources:** the releases whose branch had this content. The PSP page's second version is `[21, 22]`.
  - **Date-scoped sources** (KEP, blog, governance): the releases in effect while the text was live (ADR-002 D3). Two edits inside one release cycle both get that release, so their release windows overlap.
  - **CHANGELOG-1.R:** always `[R, R]`, set at insert, because it describes release R. A later edit gives a second version with the same release window and a later date window.
- **Only date windows must not overlap** (rule R8). Release windows may overlap, for the reasons above.
- **Validity is not authority.** The v1.30 launch post's current text still "speaks for" 1.37. Whether it's trustworthy for a "now" question is ADR-003's job (tiers, mode adjustments), not the window's.
- **`version_status` (ADR-003 D5) is derived, not stored:**
  - `current`: the date window is open
  - `superseded`: closed, and the document has a later version
  - `removed`: closed, with no later version

## Tables

### `releases`

| Column | Type | Notes |
|---|---|---|
| `minor` | `smallint` PK | 24 for v1.24. Window bounds reference this. Assumes Kubernetes stays on major version 1 |
| `version` | `text` NOT NULL UNIQUE | `'1.24'`, for display. CHECK `version = '1.' \|\| minor` |
| `release_date` | `date` NOT NULL UNIQUE | The v1.R.0 tag date (manifest) |
| `end_of_life_date` | `date` NOT NULL | CHECK `end_of_life_date > release_date` |

### `documents`

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | |
| `canonical_id` | `text` NOT NULL UNIQUE | CHECK: starts with an ADR-002 D4 prefix: `web:`, `gate:`, `kep:`, `changelog:`, `community:`, `sig-release:` |
| `source_type` | `text` NOT NULL | CHECK: one of `docs_page`, `release_record`, `feature_gate_reference`, `kep`, `blog_post`, `governance_doc` (ADR-003 D1; `discussion` arrives with Phase 2) |

### `document_aliases`

| Column | Type | Notes |
|---|---|---|
| `alias` | `text` PK | An old URL (`web:…`) or an old gate name (`gate:…`). Same prefix CHECK as `canonical_id` |
| `document_id` | `bigint` NOT NULL → `documents` | |

### `document_versions`

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | |
| `document_id` | `bigint` NOT NULL → `documents` | |
| `content_hash` | `text` NOT NULL | SHA-256 of the normalized content, 64 lowercase hex characters (CHECK) |
| `source_path` | `text` NOT NULL | Repo-relative path of the file at this version |
| `snapshot_repo` | `text` NOT NULL | Manifest repo key, e.g. `website` |
| `snapshot_ref` | `text` NOT NULL | Branch, e.g. `release-1.24` or `main` |
| `snapshot_sha` | `text` NOT NULL | 40 lowercase hex characters (CHECK) |
| `valid_from_release` | `smallint` NOT NULL → `releases.minor` | |
| `valid_until_release` | `smallint` NULL → `releases.minor` | Inclusive |
| `valid_from_date` | `timestamptz` NOT NULL | |
| `valid_until_date` | `timestamptz` NULL | Exclusive |
| `claimed_status` | `text` NULL | KEP only, stored as written (ADR-003 D5); no CHECK, so unknown values are kept |
| `claimed_stage` | `text` NULL | Same |
| `metadata` | `jsonb` NOT NULL, default `{}` | Parsed front matter (or `kep.yaml`), including stripped keys. A governance doc or a CHANGELOG has no front matter: its metadata holds only its `title` (see "Chunk header") |

### `chunks`

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | What citations point to (AC1, AC2) |
| `document_version_id` | `bigint` NOT NULL → `document_versions`, ON DELETE CASCADE | Re-chunking a version deletes its old chunks |
| `ordinal` | `integer` NOT NULL | Position in the version, from 0 (CHECK `>= 0`). UNIQUE with `document_version_id` |
| `heading_path` | `text[]` NOT NULL | Headings above the chunk, outermost first; `{}` for text before the first heading |
| `text` | `text` NOT NULL | Exactly the text that is embedded: header + body (see "Chunk header") |
| `content_hash` | `text` NOT NULL | SHA-256 of `text`, computed by the write function, never passed in. Indexed (migration `0003`): vectors are looked up by it |
| `search_vector` | `tsvector` GENERATED ALWAYS AS (`to_tsvector('english', text)`) STORED | The words of `text` (header and body), stop words dropped and the rest stemmed, for lexical search. Postgres computes it on every write, so ingestion never sets it (migration `0005`, S07-R1 decision 2) |

**Search index** (migration `0005`, S07-T1): `chunks_search_vector_idx`, GIN on `search_vector`, so it serves the full-text match `@@`. Every chunk of a text has the same `search_vector`; `search_lexical` ranks texts, not chunks.

### `embeddings`

Changed by migration `0003` (S04-R1 sitting, decision 4): **one vector per unique chunk text per model**, not one per chunk.

| Column | Type | Notes |
|---|---|---|
| `content_hash` | `text` NOT NULL | The `chunks.content_hash` of the embedded text. 64 lowercase hex characters (CHECK). No foreign key: many chunks share one text |
| `model` | `text` NOT NULL | Embedding model name, from settings (`voyage-4-large` in S04) |
| `embedding` | `vector(1024)` NOT NULL | |
| | PK `(content_hash, model)` | One vector per text per model, so model ablations don't overwrite each other (ADR-002) |

- **Why per text:** the chunk header holds no per-version field, so a section unchanged between versions has byte-identical text. On the S04 scope, 69% of sections repeat unchanged; per chunk, identical vectors would tie and crowd a top-k search.
- **The table is the embedding cache:** only hashes with no row for the model are sent to the API.
- **Orphans:** a vector whose hash no chunk uses any more (only after the chunker changes) is deleted by `make embed`. Retrieval joins to `chunks`, so an orphan can never be cited.
- **A search hit is one text.** `search` expands it to the chunks and versions holding that text (S04-R2 decision 4; see "Data-access functions").

**Search index** (migration `0004`, S04-T5): `embeddings_embedding_hnsw_idx`, HNSW on `embedding` with `vector_cosine_ops`, so it serves cosine distance `<=>`. pgvector's default build settings (`m` 16, `ef_construction` 64). It is approximate: on 20 real queries it returned the exact top 10 (200 of 200). One index holds every model's vectors; the search filters by model.

### Chunk header

Every chunk's `text` is a header, a blank line, then the body. The header holds only fields that are the same in every version of a document (S04-R1 sitting, decision 4):

```
Source: <source_type>
Title: <title>
Document: <canonical_id>
Section: <heading path joined with " > ">
```

- **Title:** the version's metadata `title`:
  - a docs page, release record, gate or blog post: the front-matter `title`
  - a KEP folder: `KEP-<number>: <kep.yaml title>`
  - an old single-file KEP: its front-matter `title`, with no `KEP-<n>:` prefix (it has no number)
  - a governance doc (S05-R2 decision 4): the version's first `# ` heading, as the chunker reads it (see "Chunking rules": no inline HTML comment, no `{#id}` anchor, none inside a comment block; `# Google Cloud Platform <!-- omit in toc -->` → `Google Cloud Platform`), else its repo path. Ingestion stores it as the version's metadata `title`, so the chunk header and citations read it like any other title.
  - a CHANGELOG (decision 4): its file name, `CHANGELOG-1.R`, stored the same way.
- **Section:** omitted when the heading path is empty (text before the first heading).

**A gate's chunk text** (S05-R1 decision 1). A gate's stages live only in its front matter, so a `gate:` document whose file has `stages` gets them at the start of its body: the header, a blank line, the YAML, a blank line, then the body.

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

- The YAML is `yaml.safe_dump(..., sort_keys=False)` of `stages`, then `removed` if present, and nothing else. Values are what YAML reads: the trailing space in a real `- stage: alpha ` line isn't part of the value.
- It is read from the version's file at chunk time: the same values as the version's `metadata`, but in the file's key order. Postgres `jsonb` reorders keys (`stage`, `toVersion`, `fromVersion`, `defaultValue`).
- The YAML is part of the body, so the chunker packs it like any paragraph. Every real gate is one chunk (at most 451 tokens with its YAML).
- The feature-gates pages are `web:` documents and get no YAML.
- **Not in the header:** release window, `version_status`, tier. They change when a newer version arrives, or depend on the question (ADR-003 D3), so they're attached to each retrieved chunk from these tables at answer time (product spec must-have 2, amended).

**CHANGELOG chunks hold release notes only** (S05-R2 decision 8). The text before the first heading (the generated table of contents) and every section whose heading path holds a heading starting with `Downloads for ` (the sha512 download tables) make no chunk. Those sections hold every sha512 row of the 18 files (8,397 at the lock head). The version's hash still covers the whole file. Chunks fall per patch section (`v1.R.x` is the heading path's first element): 371 sections in the 18 files at the lock head.
- **Every source** drops `Downloads for ` sections (S05-R3 decision 4): the 1.20 release notes page (`web:/docs/setup/release/notes/`) is the only other document with them. The table-of-contents rule stays CHANGELOG-only.

### Chunking rules

S04-R1 decisions 5 and 6, amended in the S05-R3 sitting (decisions 1–4). Code: `ingestion/chunker.py`, pure functions.

**Sections.** Every heading (H1–H6) starts a section, and a chunk never spans two. A section with no text of its own makes no chunk. No merging, no overlap. The heading path is the enclosing headings, outermost first.

**Heading text.** Inline HTML comments are removed, then a trailing Hugo anchor (`\s*\{#[^}]*\}\s*$`), then the text is trimmed (S05-R3 decision 3): `## Example configuration {#authz-config-example}` → `Example configuration`, `### … (experimental){#status-supported-features}` → `… (experimental)`. The anchor is dropped everywhere: section names, chunk headers, governance titles. An anchor in the middle of the text stays.

**The line scanner** finds headings and blocks with 6 rules:

1. A line starting at column 0 with 1–6 `#` and then a space or a tab is a heading, unless inside a code block, an HTML table or an HTML comment.
2. A fence (```` ``` ```` or `~~~`, 3 or more) closes only on a line holding the same character, at least as long.
3. A fence opened with indent N also closes at the first non-blank line indented less than N (its list item ended).
4. `{{< highlight … >}}` … `{{< /highlight >}}` is a code block.
5. Outside a code block, a line starting (after at most 3 spaces) with `<table` (any case) opens an HTML table, which runs to the first line containing `</table>`. It's one block, blank lines in its cells included (S05-R3).
6. Outside a code block, a line starting (after at most 3 spaces) with `<!--` opens an HTML comment block, which runs to the first line containing `-->` (the opening line counts, so `<!-- toc -->` is a block of one line). It makes no text and no heading; text after `-->` on its closing line goes with it (S05-R3 decision 2).

Rules 5 and 6 also end a paragraph. A table or comment that never closes runs to the end of the body. A comment inside a code block, and a one-line comment inside a paragraph line, stay.

**Blocks and packing.** A block is a paragraph (up to a blank line or the start of another block), a code block or an HTML table. A section's blocks are packed greedily into bodies of at most `CHUNK_MAX_TOKENS` (characters ÷ 4, default 512). A body is the raw lines from its first block to its last, blank lines included and comment blocks left out. A block over the limit is a body on its own, except an oversize list or pipe table, which is cut first (S05-R3 decision 1):

- **Only a paragraph block over the limit is cut.** Code blocks and HTML tables are never cut (cut code misleads).
- **A pipe table** is a paragraph whose 2nd line is a delimiter row (only `|`, `-`, `:` and spaces, with at least one `|` and one `-`). It's cut between rows, and every piece after the first starts with the table's first 2 lines, so a row keeps its column names:

  ```
  | Feature | Default | Stage | Since | Until |
  |---------|---------|-------|-------|-------|
  | `APIPriorityAndFairness` | `false` | Alpha | 1.18 | 1.19 |
  …
  ```

- **A list** (any other paragraph) is cut before each item at the block's smallest list-marker indent: a line matching `^( *)([-*+]|\d{1,9}[.)])[ \t]`. Nested items and continuation lines stay with their item; lines before the first item are the first piece. `---` is not an item (a marker needs a space or tab after it). A table inside a list is cut as a list. Cut points are marked `▶`:

  ```
    continuation of the previous item
  ▶- Item A
    more text of A
    - nested item of A
  ▶- Item B
  ▶1. Item C
  ```

- The pieces are packed like blocks, so neighbouring pieces share a chunk up to the limit. A single item or row over the limit is a chunk on its own.

On the full corpus (S05-T7): 77 distinct texts stay over 1,024 estimated tokens (433 before), of which 69 are code blocks or HTML tables, 7 lists or pipe tables (each one item or one row) and 1 a one-line paragraph.

## Rules

Each rule has an integration test that breaks it on purpose and asserts the exact failure (S03-T4). "Code" means a check in the data-access function, because the database can't express it (ADR-005).

| # | Rule | Enforced by | Failure |
|---|---|---|---|
| R1 | `canonical_id` is unique | UNIQUE | `UniqueViolation` |
| R2 | `canonical_id` and `alias` start with an ADR-002 D4 prefix | CHECK | `CheckViolation` |
| R3 | An id or alias resolves to exactly one document: aliases are unique, and no alias equals any `canonical_id` | PK + code in `create_document` and `add_alias` | `UniqueViolation`; `ValueError` from the code check |
| R4 | `source_type` is in the ADR-003 D1 vocabulary | CHECK | `CheckViolation` |
| R5 | A date window isn't empty: `from < until` | CHECK | `CheckViolation` |
| R6 | A release window is ordered (`from <= until`), and both bounds are real releases | CHECK + FK | `CheckViolation`, `ForeignKeyViolation` |
| R7 | A closed text has a last release: date `until` set ⇒ release `until` set | CHECK | `CheckViolation` |
| R8 | Date windows of one document never overlap | EXCLUDE (`btree_gist`) | `ExclusionViolation` |
| R9 | At most one current version per document | The R8 constraint: two open windows overlap | `ExclusionViolation` |
| R10 | A window is closed once. Only an open version can be closed, a release `until` set at insert never changes, and nothing reopens or moves it (S05-R2 decision 7) | Code in `close_version` | `ValueError` |
| R11 | Hashes are well-formed: `content_hash` 64 hex, `snapshot_sha` 40 hex | CHECK | `CheckViolation` |
| R12 | A chunk position is unique within its version | UNIQUE | `UniqueViolation` |
| R13 | A chunk's `content_hash` is the SHA-256 of its `text` | Code in `add_chunks` (computes it) | (tested against a known SHA-256 value) |
| R14 | One vector per (content hash, model), with exactly 1024 numbers and a well-formed hash | PK + `vector(1024)` + CHECK | `UniqueViolation`; `DataException`; `CheckViolation` |
| R15 | A release is well-formed: `version` matches `minor`, end of life after release, release dates unique | CHECK + UNIQUE | `CheckViolation`, `UniqueViolation` |

**Superseding a version** is two writes in one transaction: close the current version, then insert the new one. In the other order, R8 rejects the insert.

**Not enforced here** (rules for ingestion, S04-T2):
- A version's two windows agree with each other and with `releases`. A CHECK can't read another table.
- `claimed_status` and `claimed_stage` appear only on KEP versions.
- Re-ingesting creates no new versions.

## Data-access functions (S03-T4, S03-T5, S04-R1, S04-T0, S04-T5, S05-T1, S05-T8)

All live in `src/orgknow/db/`, take a `psycopg.Connection`, and leave the transaction to the caller (ADR-005). Inputs are Pydantic models, with timezone-aware datetimes only.

| Function | Does |
|---|---|
| `upsert_releases(conn, releases)` | Insert new releases, update the dates of existing ones, never delete (T5) |
| `list_releases(conn) -> list` | Every stored release, oldest first. Read-only: `make ingest` compares it with the manifest and stops with "run `make seed`" on a missing or re-dated release (S04-T0) |
| `create_document(conn, canonical_id, source_type) -> id` | R3 check against aliases, then insert |
| `add_alias(conn, document_id, alias)` | R3 check against canonical ids, then insert |
| `find_document(conn, canonical_id) -> id \| None` | Look up by `canonical_id` only. `make ingest` stores a document under its own id with it, so an id that is another document's alias gets the R3 error from `create_document`, not that document's history (S05-T1) |
| `resolve_document(conn, id_or_alias) -> id \| None` | Look up by `canonical_id` or alias |
| `insert_version(conn, version) -> id` | Insert one version: a `NewVersion`, which is `VersionData` (the columns ingestion derives from snapshots) plus `document_id` |
| `close_version(conn, version_id, valid_until_release, valid_until_date)` | Close an open version; a release `until` already set must be the one passed (R10) |
| `add_chunks(conn, version_id, chunks) -> ids` | Insert chunks; computes each `content_hash` (R13) |
| `versions_without_chunks(conn) -> list` | Every version with no chunks yet, oldest id first, with its document's `canonical_id` and source type: what `make ingest` chunks (S04-R1) |
| `texts_without_embedding(conn, model) -> list` | Each distinct chunk text (hash + text) with no vector for `model`, ordered by hash: what `make embed` sends (S04-R1) |
| `add_embedding(conn, content_hash, model, embedding)` | Insert one vector, sent as a `'[…]'::vector` literal (signature changed by `0003`) |
| `delete_orphan_embeddings(conn) -> count` | Delete every vector, of any model, whose hash no chunk has (S04-R1) |
| `list_versions(conn, document_id) -> list` | All versions of a document, oldest first: what re-ingest compares with (S04-R1) |
| `search(conn, question_vector, model, k) -> list[Hit]` | The `k` texts nearest the vector by cosine distance, among `model`'s vectors that a chunk holds; ties by hash. One hit per text: it cites the chunk in the newest version holding the text (latest date window; lowest chunk id within it) and lists every holding version's release window, never merged (S04-T5) |
| `search_lexical(conn, question, n) -> list[Hit]` | The `n` texts holding every content word of `question` (`plainto_tsquery('english', …)`: words joined by AND, S07-R1 decision 1), best `ts_rank_cd` first (closer words rank higher), ties by hash. No match, or only stop words: `[]`. Each hit is expanded as in `search`, with `distance` null and `lexical_rank` its position from 1 (S07-T1) |
| `versions_at_release(conn, document_id, release) -> list` | Versions whose release window includes `release` (inclusive). Can be several for date-scoped sources |
| `version_at_time(conn, document_id, at) -> version \| None` | The version whose date window contains `at` (half-open) |
| `counts_by_source_type(conn)`, `counts_by_release(conn) -> list[Counts]` | The ingestion report's counts: documents, versions, chunks and distinct texts per source type with a total row; per release (valid at R) per source type, with a total row per release (S05-T8) |
| `chunk_id_range(conn) -> (min, max) \| None` | The lowest and highest chunk id (S05-T8) |
| `stored_documents`, `stored_aliases`, `stored_versions`, `stored_chunks(conn) -> list` | Every stored record except generated ids, named by `canonical_id` (a chunk also by its version's `valid_from_date`): the fingerprint's input (S05-T8) |

`versions_at_release` and `version_at_time` hold the window conventions in one place, and their tests cover both edges of a window.

## Revisit triggers

| When | What | Why |
|---|---|---|
| ~~S04 sitting (S04-T3 header)~~ | **Done (S04-R1 sitting):** the header holds no per-version field, so `embeddings` is keyed by `(content_hash, model)` (migration `0003`) | Identical sections share text: 69% of sections repeat on the S04 scope, 52% on the full corpus (spike §3) |
| ~~S05 sitting~~ | **Done (S05-T7):** the scanner re-checked against markdown-it on all 2,882 stored files (`spikes/scanner_recheck.py`). The remaining 558 heading differences in 30 files are `#` lines in Hugo highlight blocks (474) or after a ```` ``` ```` line with a backtick in its info string (12), and headings inside list items (68) or indented 1–3 spaces (4) | Before rules 5 and 6 and the tab: 822 in 80 files |
| S09 sitting | ADR-005's plain-SQL choice, if retrieval needs more than ~4 combined query variants | See ADR-005 |
| S15 | `btree_gist` on the RDS instance | Verified on the local image only |
| Kubernetes 2.0 | The `releases.minor` key | Assumes major version 1 |

## How windows are derived (S04-R1 sitting)

- **A release date means 00:00 UTC** of the `releases.release_date`.
- **Release-scoped sources (docs pages, website release records, feature gates):** ingestion reads every release in scope, oldest first, from each release's website branch (1.37 = `main` at the lock head).
  - A version starts at the first release whose snapshot has its content: `valid_from_release` = R, `valid_from_date` = R's release date.
  - It closes at the first later release R2 whose snapshot differs or lacks the document's file (wherever it moved, see "Renames"): `valid_until_release` = R2 − 1, `valid_until_date` = R2's release date.
  - The first version of a page starts at the scope's first release, even if the page is older: 20 from S05 (the `full` scope), 24 in S04.
  - Each source type is hashed with its own strip list: release records with `release_record`'s (which strips `card`), docs pages with `docs_page`'s, feature gates and their pages with `feature_gate_reference`'s (`_build`, `weight`, `card`). `stages` and `removed` are never stripped, so a stage change is a new version.
  - A file matched by the paths of two release-scoped groups is an error when the scope is loaded, before any read or write.
- **Rebuilding from empty (S05-R1 decision 2):** moving the first release from 24 to 20 changes every stored first version, which a re-ingest reports as a history mismatch. `make reset-corpus` empties `documents`, `document_aliases`, `document_versions` and `chunks` (ids restart at 1), then `make ingest` rebuilds them. `releases` and `embeddings` are kept: vectors are a cache keyed by content hash, so an unchanged chunk text keeps its vector. Dev database only.
- **Date-scoped sources (KEPs, governance docs):** snapshots are the repo's default branch at each release date, plus `head`.
  - A new version's `valid_from_date` is its **merge time** (S05-R2 sitting): the committer time, in UTC, of the **last first-parent commit** touching the document's files between the previous snapshot and this one (`git log --first-parent -1 --format=%cI <prev>..<snap> -- <paths>`). For the first snapshot, the range is its whole history. The paths are the document's files at both snapshots, so a move or a KEP folder rename is seen.
  - First-parent follows only the default branch, so a pull request's version starts when it was merged, not at its branch's commits. KEP-2579's first version starts at 2021-05-12T16:25:28Z (its merge), not 2021-05-11T20:46:27Z (its branch's last commit, S04's date).
  - The stored text was exactly live from then; edits in between are folded into the previous version's window.
  - The previous version closes at that same instant.
  - `valid_from_release` = the latest release on or before `valid_from_date`, but **never before the scope's first release** (S05-R2 decision 1): a version older than 1.20's release date keeps its true `valid_from_date`, and its `valid_from_release` is 20. 67 documents start that early (48 KEPs, 19 governance docs). `valid_until_release` = the latest release strictly before `valid_until_date`.
  - Dates that can't make valid windows are a `ValueError` for that document, never a database error: a change dated no later than the open version's start (R5), or a document deleted and re-created with its new version dated before the closed one's `until` (R8; 0 on real data).
- **A KEP version covers README + `kep.yaml`:** both are hashed together (with the `kep_yaml` strip list), so a `kep.yaml`-only change is a new version. `claimed_status` and `claimed_stage` come from that version's `kep.yaml`, with `GA` → `stable` the only mapping (ADR-003 D5). The raw `kep.yaml` is kept in `metadata`.
- **Which KEPs (S05-T4):** every KEP in the manifest's `sig_dirs` (`kep: all` in the `full` scope).
  - A KEP folder `keps/<sig>/<number>-<slug>/` is `kep:<number>`. A folder renamed or moved between the 3 SIG folders keeps its document (1669, 3257 and 4444 each have two names, never at once; two folders with one number at one snapshot is an error). A KEP that leaves the 3 SIG folders closes as removed (506, 2004, 2030).
  - Only the folder's `README.md` and `kep.yaml` are read. Its other files (images, `images/authorizer-chain-computation.md`) are ignored: not read, not reported.
  - **Old single-file KEPs** (25 files at the 1.20 snapshot, `keps/<sig>/<name>.md`) are separate documents, `kep:<sig>/<name>` (S05-R2 decision 3), not linked to their later folders (ADR-002 known limit). Their metadata is their front matter: hashed with the `kep_yaml` strip list, `claimed_status` from `status`, `claimed_stage` from `stage` (none has one). Their body is chunked without the front matter.
  - Skipped with a reason: the 7 symlinks (mode `120000`) and `keps/sig-network/README.md` (an index of the SIG's KEPs).
- **Governance docs (S05-T4):** the manifest's `community` and `sig-release` paths, `.md` files only. A doc has no front matter: its whole text is hashed (no strip list), and its title comes from its first `# ` heading (see "Chunk header").
- **CHANGELOGs (S05-T6):** `CHANGELOG/CHANGELOG-1.R.md` for each release R in scope (1.20–1.37), read at the kubernetes lock head (`master`), a snapshot of their own, not a website release branch. `CHANGELOG-1.38.md` exists there but is out of range, so it isn't read.
  - One document per file, `changelog:1.R`, source type `release_record`. The whole file is hashed with no strip list (it has no front matter).
  - Its version's release window is `[R, R]`, set at insert. Its `valid_from_date` is the head commit's committer time, 2026-09-30T01:30:57Z (S05-R2 decision 6): a git fact read from the clone, not the lock's `fetched_at`. The date `until` stays open.
  - The clone has no history, so text from before the first ingestion isn't reconstructed (ADR-002 D1).
  - **Today (known limit):** the lock is fixed, so a re-ingest reads the same head and changes nothing. A lock refresh isn't supported yet: past head SHAs aren't kept (S14), so every CHANGELOG would start at the new head's time, and a re-ingest would report a history mismatch, changed file or not.
  - **The intended rule, once S14 keeps past heads:** an unchanged file keeps its version; a changed one closes it at the new head's time, keeping its release `until` (R10), and opens a new `[R, R]` version.
- **Blog posts (S05-T5):** not read at snapshots: one first-parent log of website `main` up to the lock head, and a version starts at its publication or its merge (see "Blog posts" below).
- **Re-ingest (compare and extend):** ingestion computes each document's full history from the snapshots, then compares it with the stored versions.
  - None stored → insert them all.
  - Equal → change nothing.
  - Stored is a prefix (a new release arrived) → close the open version, insert the new ones.
  - Anything else → report a history mismatch for that document, leave it untouched, and exit non-zero.

## Renames: one document across moves (ADR-002 D4, S05-T2, S05-T3, S05-T4)

A page or a feature gate that moves stays one document. Ingestion links the files of the release-scoped sources into **chains**, one per document: a chain is the document's file at each release (`ingestion/renames.py`).

- **Two kinds of file, chained apart:**
  - **Web pages:** docs pages, release records, and the 2 feature-gates pages. A page is a file the manifest names one by one (`feature-gates.md`, `feature-gates-removed.md`, up to 1.28) or a folder's `index.md` (a page bundle, from 1.29).
  - **Gate files:** every other file in the manifest's feature-gate folders, one per gate (from 1.29). Hugo doesn't render them (`_build: render: false`), so they have no URL.
  - Each kind has its own link rules and ids, and no rule links a gate to a page. The 316 gate files split out of the feature-gates tables at 1.29 are new documents.
  - The pages of every source type are chained together, so a link between two of their source types is seen, and refused.

- **Ids and aliases:**
  - A page's `canonical_id` is the chain's first URL (`web:`). The PSP page is `web:/docs/concepts/policy/pod-security-policy/`.
  - Every later URL of the chain is an alias (`web:/docs/concepts/security/pod-security-policy/`), and so is every front-matter `aliases` entry, as in S04.
  - A gate's `canonical_id` is `gate:` + the chain's first front-matter `title`, as written (case and typos kept): `gate:ServiceAcccountNodeAudienceRestriction`. Every later title is an alias (`gate:ServiceAccountNodeAudienceRestriction`).
  - `former_titles` never become aliases: the gate a former title names can keep its own file (`PodHasNetworkCondition`, a gate of its own in every release).
  - An alias equal to the document's own id is skipped.
  - Two chains with one id (say, two gate files with one title) are an error, never a silent merge: each is reported, and neither is stored (0 on real data).
- **Links,** one release pair R → R+1 at a time. A link joins a file present at R and gone at R+1 to a file absent at R and present at R+1. The rules run in order, and the first rule that links a file wins. Web pages (docs pages, release records):
  1. Same URL. This covers page bundles: `x.md` → `x/index.md`.
  2. The redirect file at R+1 maps the gone URL to the new page's URL.
  3. The new page's front-matter `aliases` holds the gone URL.
  4. git similarity ≥ 50% (`git diff -M50%` between the two release snapshots), read only for the files no earlier rule linked.
- **Links of gate files,** the same way:
  1. Same path: a file at R and R+1 stays in its chain. A title fixed in place keeps its document.
  2. Same front-matter `title`. This links the 345 renames from kebab case to the gate name at 1.32.
  3. The new file's `former_titles` holds the gone file's title (0 links on real data: the one gate that has it, `PodReadyToStartContainersCondition`, is linked by its title first).
  4. git similarity ≥ 50%: `APIServingWithRoute` → `APIServingWithRoutine` at 1.33 (93%). `PodInfoAPI` → `InPlacePodVerticalScalingMemoryBackedVolumes` at 1.37 scores 40%: two documents.
- **Refused links:**
  - A file one rule links twice (a gone file claimed by two new files, or the reverse) is a conflict. It's logged and never linked, by that rule or a later one.
  - A link between two source types is an error: it's reported, not made, and the exit code is non-zero. Groups read from one repo at the same releases are linked together, so such a link can be seen.
  - A redirect to a URL that existed at R is a removal, not a move: a link's target must be new at R+1. Example: `overview.md` → the security section index at 1.29.
- **The redirect file:** `static/_redirects` at R+1, else `static/_redirects.base` (from 1.34 the site builds `_redirects` from it).
  - Lines are `<from> <to> [status]`. Comments, and rules whose source contains `*` or `:`, are skipped. The first rule per source wins, as in Netlify.
  - URLs are normalized: `https://kubernetes.io`, fragment and query removed; lowercased; a trailing slash added.
  - No redirect file means no redirect links.
- **Versions across a move:** a version is still a change in normalized content, wherever the file lives. A move that changes only stripped keys adds no version, so the open version keeps its `source_path` and snapshot. The deprecation policy moved at 1.37 by adding `aliases` only: its open version stays at the old path, from 1.31.
- **Unmatched adds and deletes** are logged at INFO per release pair, a delete with its redirect target if it has one. A page that moves out of scope closes; a page that moves in from out of scope is a new document.
- A path that comes back after a gap continues its chain, as it did before renames.
- **Governance docs** (S05-R2 decision 2, amending ADR-002 D4's `git log --follow`) use the same chain builder on their date snapshots, with two rules:
  1. Same path: a file at both snapshots stays in its chain.
  2. git similarity ≥ 50% between the adjacent snapshots (`git diff -M50%`), for the files left. They have no URL, redirect or front matter to declare a move.
  - The `canonical_id` is `<repo>:` + the chain's first path (`sig-release:release-engineering/versioning.md`); each later path is an alias (`sig-release:release-engineering/reference/versioning.md`).
  - On real data this links the 8 moves of sig-release PR #2984 (1.36 → 1.37, 66–100% similar). The R100 move of `baseimage-exception-list.md` adds no version: its open version keeps the old path and snapshot. A chain continues from 1.37 to `head` (`branch-creation.md`, `release-cuts.md`).
  - An old path that comes back after its move starts a new chain with the same first path: both chains are refused as one id held twice, never merged (0 on real data).
- The 50% threshold is a named constant citing ADR-002 D4, not a setting: changing it changes `canonical_id`s (S05-R2 decision 9).

## Blog posts: windows from publication, identity at publication (ADR-002 D2–D4, S05-T5)

The rules are `ingestion/blog.py`; the blog's history is read by `git_reader.post_histories`.

- **History** (S05-R2 decision 5): one first-parent log of website `main` up to the lock head, over the `.md` files under the manifest's `blog_post` paths (`git log --first-parent --find-renames=50% --raw -z`). Per post, one entry per commit touching its file: the file's content then, or none once deleted. git's rename detection follows a moved post, so website PR #53902's year-folder move continues each history. A post that loses its `.md` there (the 1.23 and 1.24 release interviews) is deleted: Hugo doesn't render it, so its open version closes at that merge (2026-02-21).
- **A version** is an entry whose normalized hash (the `blog_post` strip list) differs from the previous entry's, as for every source (ADR-002 D2).
- **Due time** of an entry: none if it's deleted or `draft: true`; else `publishDate`, else the page date, else the commit time.
  - The **page date** is Hugo's, in the site's order: front-matter `date`, else the filename's `YYYY-MM-DD-` (a page bundle's folder name), else `publishDate`, else `lastmod`.
  - A date is a YAML `date` (midnight UTC), a `datetime`, or text: `2023-08-15T12:00:00+0000` (no colon in the offset, 8 posts) and milliseconds are text to YAML. A time without an offset is UTC (the site's `timeZone`); one with an offset keeps it. A value that isn't a date (`XXXX-XX-XX`, `date: draft`) is ignored, so the next source of the date is used.
- **Publication** is the first moment Hugo renders the post (`buildFuture` is off): for each entry in order, max(commit time, due time), if that is before the next entry's commit (or it's the last entry). A post never published isn't stored.
- **Stored versions:** the version live at publication, from the publication moment, then every later version from its commit time. A version superseded before publication was never public, so it isn't stored. After publication, a deletion or `draft: true` closes the open version at that commit, and a later rendered version opens a new one. Windows then follow the date-scoped rules above (release window from the latest release on or before the start).
  - Known approximations: publication assumes the site builds on every merge; a version re-dated into the future after publication still starts at its commit.
- **Snapshot of a version:** repo `website`, ref `main`, the entry's commit SHA, and the post's path at that commit. A move that changes no normalized content adds no version, so the open version keeps its old path and snapshot.
- **Scope:** the page date of the version live at publication is on or after 1.20's release date (2020-12-08, 00:00 UTC), and the post was ever published. Posts out of scope are counted in the ingest log, not listed one by one: never published, dated before 1.20, or with no page date (S05-T8).
- **Front matter** may open with 3 or more dashes, as Hugo renders it (the VAP GA post opens with `------`). This applies to every source. A post whose front matter can't be parsed is reported with the commit's short SHA and the reason, and isn't stored.
- **Identity** (ADR-002 D4): `web:` + the URL at publication, lowercase, with a trailing slash: `web:/blog/2025/11/12/ingress-nginx-retirement/`.
  - The URL is the front-matter `url:` (tokens allowed), else the manifest's `permalink` (`/:section/:year/:month/:day/:slug/`). `:year`/`:month`/`:day` come from the page date as written; `:slug` is the front-matter `slug`, else the filename's (only when the date came from the filename), else the title through an approximation of Hugo's urlize (lowercase, punctuation dropped, spaces to hyphens); `:section` is `blog`.
  - **Aliases:** the URL of every later stored version that differs from the id, and every front-matter `aliases` entry of the stored versions, never the id itself. On real data: 3 URLs changed after publication (`introducing-headlamp-plugin-for-karpenter` 09/23 → 10/06, `ingress-nginx-retirement` 11/12 → 11/11, `ccm-new-metric-route-sync-total` 02/26 → 05/15, whose front-matter alias is its id), plus `web:/dockershim/` (the 2022 dockershim FAQ's `aliases`).
  - Two posts with one id are an error, never a merge (0 on real data).

## Ingestion report and fingerprint (S05-T8, S05-R3 decisions 7 and 8)

`make ingest` ends with the report. `make ingest-report` prints its database part alone, read from the database only (no git). The reads are in `db/report.py`; the fingerprint and the formatting are pure functions in `ingestion/report.py`.

- **Run part** (`make ingest` only): this run's new documents, versions and chunks, then what was skipped and what failed. Skips aren't stored: they exist only during a run (no table).
  - **A skipped file** (a symlink, an `OWNERS` file, an image) is one line per (file, reason), with the snapshots it was skipped at in release order, consecutive releases as a range: `keps/sig-release/OWNERS: not a .md/.yaml file (1.20–1.37, head)`. A version with no text to chunk keeps its own line: `web:/docs/concepts/security/ (version 6) content/en/docs/concepts/security/_index.md: no text to chunk`.
  - **A failure at one snapshot** starts with that snapshot's label: `1.24`, `head`, or a blog commit's short SHA (8 hex digits; a blog commit is never labelled `head`). This covers a file that can't be parsed or decoded, a gate without a title, two folders for one KEP number, and dates that can't make valid windows (`SnapshotError`).
  - A failure about a whole document (two chains with one id, a history mismatch, an R3 conflict) starts with the document; a link between two source types, with its release pair; a version that can't be chunked, with the version.
  - **A manifest path absent at every snapshot** of its group is a failure (the manifest's missing-path rule: the manifest is wrong), starting with the group's snapshots: `1.20–1.37: manifest path … is absent at every snapshot`. A path absent from only some snapshots is logged (pages move). 0 on real data.
- **Database part:**
  - documents, versions, chunks and distinct chunk texts per source type, and in total, and the alias count
  - per release R (each row of `releases`): the documents valid at R per source type, and the versions, chunks and distinct texts valid at R over all types. Valid at R: the version's release window contains R (inclusive, as in `versions_at_release`).
  - the chunk id range (ids aren't in the fingerprint), and the fingerprint
- **Fingerprint:** one definition of "identical" (AC8): every stored value except generated ids and `chunks.search_vector` (Postgres computes it from the text), so it covers chunk text (through its hash, R13), claims, metadata and snapshots, however the database was built.
  - One row per stored record, each a compact JSON array, `json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`:
    - `["document", canonical_id, source_type]`
    - `["alias", canonical_id, alias]`
    - `["version", canonical_id, content_hash, source_path, snapshot_repo, snapshot_ref, snapshot_sha, valid_from_release, valid_until_release, valid_from_date, valid_until_date, claimed_status, claimed_stage, metadata]`
    - `["chunk", canonical_id, version valid_from_date, ordinal, heading_path, content_hash]`
  - Dates are UTC ISO 8601 strings (`2020-12-08T00:00:00+00:00`); a null is JSON `null`; `metadata` is the JSON object, its keys sorted.
  - A chunk names its version by `canonical_id` and `valid_from_date`, unique per document (R8).
  - The rows are sorted as strings and joined with `\n`; the fingerprint is the sha256 hex of their UTF-8 bytes, printed `Fingerprint: sha256:<hex>`. An empty database gives the sha256 of the empty string (`e3b0c442…b855`).
  - `embeddings` and `releases` aren't in it: `make embed` doesn't change it.
- **Byte-identical:** dates print in UTC and every list is sorted, so two databases holding the same values print the same database part, and two from-empty ingests the same report. Run times stay out of it.

## Handed to S04

- ~~How each source's windows are derived~~ (see above).
- ~~What a KEP version covers~~ (see above).
- ~~Re-ingest idempotency~~ (see above) and ~~an index on `chunks.content_hash`~~ (migration `0003`).
- ~~The chunk header's contents~~ (see "Chunk header") and ~~the HNSW index~~ (migration `0004`, see `embeddings`).
