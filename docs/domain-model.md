# Domain model

- **Status:** Approved by the developer (S03-T2, S03-R1 sitting, 2026-10-04). Amended in the S04-R1 sitting (2026-10-04): one vector per unique text, the chunk header, and how windows are derived. Amended in the S05-R1 sitting (2026-10-07): windows from 1.20, release records, the reset, renames.
- **Builds on:** ADR-002 (versions, windows, identity), ADR-003 (source types, statuses), ADR-005 (data access, where rules live)
- **Implemented by:** migration `0002` (S03-T3), the data-access functions in `src/orgknow/db/` (S03-T4), the releases seed (S03-T5); migration `0003` and ingestion (S04-R1); migration `0004` and dense retrieval (S04-T5)

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
  - **CHANGELOG-1.R:** always `[R, R]`, because it describes release R. A later edit gives a second version with the same release window and a later date window.
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
| `metadata` | `jsonb` NOT NULL, default `{}` | Parsed front matter (or `kep.yaml`), including stripped keys |

### `chunks`

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | What citations point to (AC1, AC2) |
| `document_version_id` | `bigint` NOT NULL → `document_versions`, ON DELETE CASCADE | Re-chunking a version deletes its old chunks |
| `ordinal` | `integer` NOT NULL | Position in the version, from 0 (CHECK `>= 0`). UNIQUE with `document_version_id` |
| `heading_path` | `text[]` NOT NULL | Headings above the chunk, outermost first; `{}` for text before the first heading |
| `text` | `text` NOT NULL | Exactly the text that is embedded: header + body (see "Chunk header") |
| `content_hash` | `text` NOT NULL | SHA-256 of `text`, computed by the write function, never passed in. Indexed (migration `0003`): vectors are looked up by it |

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

- **Title:** the front-matter `title`; for a KEP, `KEP-<number>: <kep.yaml title>`.
- **Section:** omitted when the heading path is empty (text before the first heading).
- **Not in the header:** release window, `version_status`, tier. They change when a newer version arrives, or depend on the question (ADR-003 D3), so they're attached to each retrieved chunk from these tables at answer time (product spec must-have 2, amended).

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
| R10 | A window is closed once: only an open version can be closed, and nothing reopens or moves it | Code in `close_version` | `ValueError` |
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

## Data-access functions (S03-T4, S03-T5, S04-R1, S04-T0, S04-T5, S05-T1)

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
| `close_version(conn, version_id, valid_until_release, valid_until_date)` | Close an open version (R10) |
| `add_chunks(conn, version_id, chunks) -> ids` | Insert chunks; computes each `content_hash` (R13) |
| `versions_without_chunks(conn) -> list` | Every version with no chunks yet, oldest id first, with its document's `canonical_id` and source type: what `make ingest` chunks (S04-R1) |
| `texts_without_embedding(conn, model) -> list` | Each distinct chunk text (hash + text) with no vector for `model`, ordered by hash: what `make embed` sends (S04-R1) |
| `add_embedding(conn, content_hash, model, embedding)` | Insert one vector, sent as a `'[…]'::vector` literal (signature changed by `0003`) |
| `delete_orphan_embeddings(conn) -> count` | Delete every vector, of any model, whose hash no chunk has (S04-R1) |
| `list_versions(conn, document_id) -> list` | All versions of a document, oldest first: what re-ingest compares with (S04-R1) |
| `search(conn, question_vector, model, k) -> list[Hit]` | The `k` texts nearest the vector by cosine distance, among `model`'s vectors that a chunk holds; ties by hash. One hit per text: it cites the chunk in the newest version holding the text (latest date window; lowest chunk id within it) and lists every holding version's release window, never merged (S04-T5) |
| `versions_at_release(conn, document_id, release) -> list` | Versions whose release window includes `release` (inclusive). Can be several for date-scoped sources |
| `version_at_time(conn, document_id, at) -> version \| None` | The version whose date window contains `at` (half-open) |

`versions_at_release` and `version_at_time` hold the window conventions in one place, and their tests cover both edges of a window.

## Revisit triggers

| When | What | Why |
|---|---|---|
| ~~S04 sitting (S04-T3 header)~~ | **Done (S04-R1 sitting):** the header holds no per-version field, so `embeddings` is keyed by `(content_hash, model)` (migration `0003`) | Identical sections share text: 69% of sections repeat on the S04 scope, 52% on the full corpus (spike §3) |
| S05 sitting | The hand-written Markdown scanner (S04-R1 decision 6), re-checked against markdown-it on the new sources | It matched CommonMark on all S04 data, but CHANGELOG list-item headings already differ (2 in `CHANGELOG-1.36`) |
| S09 sitting | ADR-005's plain-SQL choice, if retrieval needs more than ~4 combined query variants | See ADR-005 |
| S15 | `btree_gist` on the RDS instance | Verified on the local image only |
| Kubernetes 2.0 | The `releases.minor` key | Assumes major version 1 |

## How windows are derived (S04-R1 sitting)

- **A release date means 00:00 UTC** of the `releases.release_date`.
- **Release-scoped sources (docs pages, website release records):** ingestion reads every release in scope, oldest first, from each release's website branch (1.37 = `main` at the lock head).
  - A version starts at the first release whose snapshot has its content: `valid_from_release` = R, `valid_from_date` = R's release date.
  - It closes at the first later release R2 whose snapshot differs or lacks the document's file (wherever it moved, see "Renames"): `valid_until_release` = R2 − 1, `valid_until_date` = R2's release date.
  - The first version of a page starts at the scope's first release, even if the page is older: 20 from S05 (the `full` scope), 24 in S04.
  - Each source type is hashed with its own strip list: release records with `release_record`'s (which strips `card`), docs pages with `docs_page`'s.
  - A file matched by the paths of two release-scoped groups is an error when the scope is loaded, before any read or write.
- **Rebuilding from empty (S05-R1 decision 2):** moving the first release from 24 to 20 changes every stored first version, which a re-ingest reports as a history mismatch. `make reset-corpus` empties `documents`, `document_aliases`, `document_versions` and `chunks` (ids restart at 1), then `make ingest` rebuilds them. `releases` and `embeddings` are kept: vectors are a cache keyed by content hash, so an unchanged chunk text keeps its vector. Dev database only.
- **Date-scoped sources (KEPs):** snapshots are `main` at each release date, plus `head`.
  - A new version's `valid_from_date` is the committer time, in UTC, of the **last** commit touching the document's files between the previous snapshot and this one. The stored text was exactly live from then; edits in between are folded into the previous version's window.
  - The previous version closes at that same instant.
  - `valid_from_release` = the latest release on or before `valid_from_date`. `valid_until_release` = the latest release strictly before `valid_until_date`.
- **A KEP version covers README + `kep.yaml`:** both are hashed together (with the `kep_yaml` strip list), so a `kep.yaml`-only change is a new version. `claimed_status` and `claimed_stage` come from that version's `kep.yaml`, with `GA` → `stable` the only mapping (ADR-003 D5). The raw `kep.yaml` is kept in `metadata`.
- **Re-ingest (compare and extend):** ingestion computes each document's full history from the snapshots, then compares it with the stored versions.
  - None stored → insert them all.
  - Equal → change nothing.
  - Stored is a prefix (a new release arrived) → close the open version, insert the new ones.
  - Anything else → report a history mismatch for that document, leave it untouched, and exit non-zero.

## Renames: one document across moves (ADR-002 D4, S05-T2)

A page that moves stays one document. Ingestion links the files of the release-scoped sources into **chains**, one per document: a chain is the document's file at each release (`ingestion/renames.py`).

- **Ids and aliases:**
  - `canonical_id` is the chain's first URL (`web:`). The PSP page is `web:/docs/concepts/policy/pod-security-policy/`.
  - Every later URL of the chain is an alias (`web:/docs/concepts/security/pod-security-policy/`), and so is every front-matter `aliases` entry, as in S04.
  - An alias equal to the document's own id is skipped.
- **Links,** one release pair R → R+1 at a time. A link joins a file present at R and gone at R+1 to a file absent at R and present at R+1. The rules run in order, and the first rule that links a file wins. Web pages (docs pages, release records):
  1. Same URL. This covers page bundles: `x.md` → `x/index.md`.
  2. The redirect file at R+1 maps the gone URL to the new page's URL.
  3. The new page's front-matter `aliases` holds the gone URL.
  4. git similarity ≥ 50% (`git diff -M50%` between the two release snapshots), read only for the files no earlier rule linked.
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

## Handed to S04

- ~~How each source's windows are derived~~ (see above).
- ~~What a KEP version covers~~ (see above).
- ~~Re-ingest idempotency~~ (see above) and ~~an index on `chunks.content_hash`~~ (migration `0003`).
- ~~The chunk header's contents~~ (see "Chunk header") and ~~the HNSW index~~ (migration `0004`, see `embeddings`).
