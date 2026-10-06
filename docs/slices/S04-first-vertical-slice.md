# S04: First vertical slice: PSP → PSA

- **Status:** 🟨
- **Blueprint stage:** Stage 2, narrowed (the full manifest is S05)
- **Started:** 2026-10-04
- **Finished:**

## Outcome

`orgknow ask "<question>"` returns a cited, structured answer, or `insufficient_evidence`, over the SIG Auth docs at every release from v1.24 to v1.37, plus KEP-2579.

## Why now

- It's the first end-to-end path. It tests the S03 schema, ADR-002's version rules and the answer contract on real files, before S05 scales to the full manifest and S06 builds the eval harness.
- It retires the risk that the window and identity rules break on real data.
- Seeds #6–#10 give a first list of failures (temporal confusion is expected), which motivates S09 (temporal) and S10 (conflicts).

## Exit checks

- [ ] `make ingest` run twice: the second run adds 0 versions and 0 chunks. The version count is explained against the 231 distinct raw files of the scope (normalization can only merge, never split).
- [ ] A second embedding run makes 0 Voyage calls.
- [ ] `orgknow ask` answers seeds #6–#10 with schema-valid output, and a test proves a citation outside the retrieved set is rejected.
- [ ] Every `ask` produces a Langfuse trace.
- [ ] Seed outputs and failure notes are in `eval/results/s04/` (T8).
- [ ] ADR-006 Accepted.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| The manifest's SIG Auth docs paths, every release 1.24 → 1.37 (14 snapshots; no renames in range, checked in the R1 sitting) | Releases 1.20–1.23: the PSP page moved at 1.23, so they need rename handling (S05) |
| KEP-2579 (README + `kep.yaml`), at each release date 1.20–1.37 plus `head` (ADR-002 D1) | Other SIGs and KEPs, CHANGELOG, blog, feature gates, governance (S05) |
| Normalize and hash, versions with both windows, idempotent re-ingest | Rename and alias detection; the ingestion report command (S05) |
| Markdown chunker with heading path and a deterministic header | LLM chunk enrichment (non-goal) |
| Voyage embeddings with a content-hash cache | Embedding-model comparisons (after S06) |
| Dense retrieval: pgvector cosine search with an HNSW index | Lexical search and RRF (S07), reranking (S08) |
| Structured answer, citation validator, CLI `ask`, a Langfuse trace per query | Temporal filtering, authority scoring, query modes (S09); conflicts (S10); LangGraph (S11); FastAPI `/query` (S12) |

## Metric to move

n/a (first vertical slice). The dense-baseline ablation row comes in S06. T8 records qualitative failure notes on seeds #6–#10.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S04-T1: ADR-006, generation model/provider and tracing `[human]`

- **Goal:** choose the generation LLM and provider, the structured-output method, and the Langfuse Cloud setup.
- **Done when:** ADR-006 is Accepted. Decided in the S04-R2 sitting (2026-10-06): `docs/decisions/ADR-006-generation-and-tracing.md`.

### S04-T2: Slice-scope ingestion `[core]`

- **Goal:** read the slice's files at the locked SHAs, normalize and hash them (ADR-002 D2), derive versions with both windows (D3), and store them with the S03 data-access functions.
- **Done when:** a re-run creates 0 new versions (idempotent).
- **Notes / pointers:**
  - SHAs come from `config/corpus_manifest.lock.yaml`; files are read from the partial clones under `CORPUS_CACHE_DIR`.
  - The domain model's "Not enforced here" rules are this task's: windows agree with `releases`; claims appear only on KEP versions; a re-ingest creates nothing.
  - A KEP version covers README + `kep.yaml`, so a `kep.yaml`-only change is a new version (domain model, "Handed to S04").
  - No file is dropped silently: each skipped or failed file is logged with a reason. Symlinks are skipped; only the first YAML document is read.
- **Deps:** S03.

### S04-T3: Markdown chunker `[core]`

- **Goal:** split a version's Markdown into chunks by heading, each with its heading path and a deterministic header; store chunks for every version that has none.
- **Done when:** unit tests pass on fixtures, including table and code-block preservation.
- **Notes / pointers:** real edge cases, each with a fixture:
  - `#` comment lines inside a YAML code block (Pod Security Admission page, lines 64–74) are not headings.
  - A stray closing fence with no opener (`CHANGELOG-1.22.md` line 3085).
  - A Hugo shortcode as a heading (`## {{% heading "whatsnext" %}}`).

### S04-T4: Embedding interface `[commodity]`

- **Goal:** a small embedding interface, a Voyage provider, a test fake, and a cache keyed by content hash.
- **Done when:** a second run makes 0 API calls.
- **Notes / pointers:** Voyage allows 1,000 inputs and 320K tokens per request (voyage-4). Chunks use `input_type="document"`. Record `usage.total_tokens` against the chars ÷ 4 estimate.

### S04-T5: Dense retrieval `[core]`

- **Goal:** pgvector cosine search with an HNSW index, returning chunks with their version, window and source metadata.
- **Done when:** an integration test on fixtures passes.
- **Notes / pointers:** ADR-003 D3 tiers depend on the target release and `effective_stage`. The R2 sitting left tiers to S09 (run S04-R2, decision 5).
- **Deps:** T2–T4.

### S04-T6: Generation `[core]`

- **Goal:** structured output (`answer`, `answer_status`, `evidence[]`, `insufficient_evidence_reason`) plus a citation validator.
- **Done when:** a citation outside the retrieved set is rejected in tests.
- **Deps:** T1, T5.

### S04-T7: CLI `ask` command + Langfuse trace per query `[commodity]`

- **Deps:** T6.

### S04-T8: Run seeds #6–#10 `[human]`

- **Goal:** save the outputs to `eval/results/s04/` and write failure notes. Temporal confusion is expected; it's the motivation for S09.
- **Deps:** T7.

## Risks & unknowns

- **Ingestion reads a local partial clone.** Missing blobs are fetched from GitHub on demand. CI can't run real ingestion, so tests use pinned fixtures and a tiny git repo built in the test.
- **Normalization was measured in the spike, not built in `src/`.** Version counts may differ from the spike's raw counts.
- **The chunk header decides the embedding storage shape** (domain model, revisit triggers).
- **The first real ingestion breaks S03's integration tests locally,** because they use real canonical ids, unless tests are isolated from ingested data.
- **Hugo shortcodes** (`{{< glossary_tooltip … >}}`, `{{< feature-state … >}}`) stay in the chunk text in S04. Their effect on retrieval is measured in S06.
- **Voyage needs an API key.** The slice's ~1.3M tokens fit in the 200M free tokens.

## Decisions expected (ADRs)

- **R1 sitting:** test isolation; chunk header and embedding storage shape; chunking rules; Markdown parser; embedding model and HTTP client. Each new dependency needs an ADR-004 amendment.
- **ADR-006 (T1):** generation model, structured output, tracing. Accepted in the R2 sitting (2026-10-06).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S04-R1: indexing path

- **Status:** merged (PRs #21 and #22)
- **Branch:** `s04-r1-indexing`. PR 1's branch `s04-r1a-ingestion` is cut at T2's last commit.
- **Tasks, in this order:** S04-T2 (ingestion, starting with the test database) → S04-T3 (chunker) → S04-T4 (embeddings + migration `0003`).
- **Closes the slice:** no. T1 and T5–T8 remain (S04-R2, after its own sitting).
- **Goal (plain words):** get the slice's text into Postgres in searchable form.
  - Read SIG Auth docs at every release 1.24 → 1.37, and KEP-2579 at every release date plus `head`, from the pinned SHAs.
  - Store one version per content change, with exact windows.
  - Split each version into chunks with a stable header.
  - Embed each unique chunk text once with voyage-4-large.
  - Re-running any step changes nothing and calls Voyage 0 times.

#### Decisions (made in the sitting, 2026-10-04)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Triage: 8 parked items folded into this run, 3 retagged to S05, 5 left; added the v1.30 test-time fix and a tiny-section merge experiment (S06) to Proposed additions | — | See `docs/backlog.md`, Proposed additions |
| S2 | Bundle T2 → T3 → T4 (indexing path); T5–T7 in S04-R2 after ADR-006 | T2–T5 in one run; T2–T3 only | ~1,500 lines already; the read path (retrieval SQL) pairs with generation |
| S3 | Docs at every release 1.24 → 1.37 (14 snapshots, 216 versions); KEP-2579 at release dates 1.20–1.37 + `head` | 2 snapshots (1.24 + 1.37); every release from 1.20 | 2 snapshots make windows guesses; from 1.20 needs rename handling (PSP move at 1.23). No renames in 1.24–1.37 (checked: `overview.md` at 1.29 redirects to an existing page, a removal) |
| 1 | Separate test database `orgknow_test` in the same container; `make test-int` migrates and uses it | Test-only ids; a second container | Real ingested ids no longer collide with tests, now or in future fixture-ingest tests |
| 2 | Re-ingest = compare and extend: none stored → insert all; equal → nothing; stored is a prefix → close the open version + insert; else → report a mismatch, leave the document untouched, exit non-zero | Skip documents with versions; delete and rebuild | Idempotent and incremental; chunk ids (citations) stay stable; drift is loud |
| 3 | A date-scoped version starts at the committer time (UTC) of the **last** commit touching its files since the previous snapshot | First commit; one version per commit | The stored text was exactly live from that instant; the slack falls on the superseded version |
| 4 | Chunk header = source type, title, document id, heading path; no per-version field. Migration `0003` keys `embeddings` by `(content_hash, model)`, indexes `chunks.content_hash`; `make embed` deletes orphan vectors. Product spec must-have 2 and the domain model amended | Stable header with one vector per chunk; header with `valid_from_release` | Release window/status change on supersession and tier depends on the question, so they can't be embedded; 69% of sections repeat across versions and identical vectors would crowd top-k; the table is the cache. Devil's advocate's case (orphans, expansion rule) answered in the sitting |
| 5 | Chunking: every heading (H1–H6) starts a section; 512-token max (chars ÷ 4); long sections packed by whole paragraphs; fenced code, Hugo `highlight` blocks and tables never cut (an oversize block is its own chunk); no merging, no overlap | Merging tiny sections into their first subsection; fixed windows with overlap | Simple and deterministic; meets "table and code-block preservation"; merging becomes an S06 experiment |
| 6 | Hand-written line scanner with 4 rules (below); no Markdown library | markdown-it-py (new dependency) | Matches markdown-it on all 231 doc versions and `CHANGELOG-1.22` (426 = 426 headings) once the Hugo rule is added; the S05 sitting rechecks it on new sources |
| 7 | voyage-4-large at 1024 dimensions, through the standard library's `urllib`, behind a small `Embedder` protocol with a fake | voyage-4 / voyage-4-lite; `httpx2`; the `voyageai` SDK | Best general retrieval at $0 (free tokens), so the S06 baseline stays stable; one POST needs no dependency; ADR-006 revisits the client when the LLM SDK brings `httpx2` anyway |

**Claude's calls (overrulable):**
- **Commands:** `make ingest` (versions, then chunks; free, local) and `make embed` (vectors; paid). Entry points `python -m orgknow.ingestion.ingest` and `python -m orgknow.embeddings.embed`, like `make seed`.
- **Scope in the manifest:** a `scopes:` block (below). `make ingest` reads `INGEST_SCOPE` (default `s04`).
- **Windows:** a release date means 00:00 UTC. `from_release` = the latest release on or before `from`; `until_release` = the latest release strictly before `until`. The first docs version starts at 24.
- **KEP:** the hash covers README + `kep.yaml` (with the `kep_yaml` strip list); the PRR file isn't read in S04. `GA` → `stable`; other claims stored as written; the raw `kep.yaml` goes into `metadata`. The unknown-value flag is derived later (S09).
- **Ingestion:**
  - Front-matter `aliases` become alias rows (`/rbac/` → `web:/rbac/`).
  - One transaction per document.
  - Git is read with the `git` command (`subprocess`); tests build a tiny git repo in a temporary directory.
- **Chunk text:** the raw body with front matter removed and CRLF → LF, not the normalized text. Shortcodes and shortcode headings stay as written.
- **Migration `0003` downgrade:** recreates `0002`'s empty `embeddings` table (vectors are a cache).
- **Settings:** new values with defaults, documented in `.env.example`: `CORPUS_CACHE_DIR` (moves from spike-only to Settings), `CORPUS_LOCK_PATH`, `INGEST_SCOPE`, `VOYAGE_API_KEY` (`SecretStr`, optional), `VOYAGE_API_URL`, `EMBEDDING_MODEL` (`voyage-4-large`), `CHUNK_MAX_TOKENS` (512), `EMBED_BATCH_MAX_TEXTS` (128), `EMBED_BATCH_MAX_TOKENS` (60,000), `EMBED_MAX_TOKENS_PER_RUN` (2,000,000; `make embed` refuses to start above it).
- **Retries:** up to 3 retries with backoff (1 s, 2 s, 4 s) on HTTP 429 or 5xx only; 60 s timeout.
- **Layout:** module layout inside `ingestion/` and `embeddings/`; the fake embedder lives in `tests/`.

#### Pinned formats

**Manifest scope block** (appended to `config/corpus_manifest.yaml`):

```yaml
# Named subsets for slices that ingest less than the whole manifest (S04-R1 sitting).
# `make ingest` reads one (INGEST_SCOPE, default s04). S05 ingests the full manifest.
scopes:
  s04:
    docs_page: {sigs: [auth], from_release: "1.24"}
    kep: {traced: [2579]}
```

**Chunk text** (domain model, "Chunk header"): header lines, a blank line, then the body.

```
Source: docs_page
Title: Pod Security Admission
Document: web:/docs/concepts/security/pod-security-admission/
Section: Exemptions

<body>
```

- KEP: `Source: kep`, `Title: KEP-2579: PSP Replacement Policy`, `Document: kep:2579`.
- `Section:` joins the heading path with ` > ` and is omitted when the path is empty.

**Canonical ids (ADR-002 D4):**
- Docs: `web:` + the path without `content/en` and `.md`, with a trailing slash, lowercase; `_index.md` becomes its folder (`web:/docs/concepts/security/`).
- KEP: `kep:2579`.

**Scanner rules (decision 6):**
1. A line starting at column 0 with 1–6 `#` and then a space is a heading, unless inside a code block.
2. A fence (```` ``` ```` or `~~~`, 3 or more) closes only on a line holding the same character, at least as long.
3. A fence opened with indent N also closes at the first non-blank line indented less than N (its list item ended).
4. `{{< highlight … >}}` … `{{< /highlight >}}` is a code block.

**Voyage request:** `POST {VOYAGE_API_URL}` with `{"input": [...], "model": "voyage-4-large", "input_type": "document", "output_dimension": 1024}` and header `Authorization: Bearer <key>`. Read `data[].embedding` ordered by `data[].index`, and `usage.total_tokens`.

#### Handoffs between tasks

- **T2 → T3:**
  - `documents` and `document_versions` rows. Each version carries `source_path`, `snapshot_repo` and `snapshot_sha`, so its raw file can be re-read from git, and the front matter (or `kep.yaml`) in `metadata`, which holds the title.
  - A read listing versions that have no chunks.
- **T3 → T4:**
  - `chunks` rows (final header + body, `content_hash` computed by `add_chunks`).
  - A read listing distinct `content_hash` values (with their text) that have no vector for a model.
- **T4 → S04-R2:**
  - `embeddings` keyed by `(content_hash, model)`, joinable to `chunks` → `document_versions` → `documents`.
  - The `Embedder` protocol, reused for query embeddings (`input_type="query"`).

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **Test database (first step of T2):**
  - `make up` creates `orgknow_test` if it's missing.
  - `make test-int` migrates it, then runs the tests against it (`TEST_DATABASE_URL`).
  - CI sets `TEST_DATABASE_URL` to its service database.
  - A local `make test-int` must pass with the dev database fully ingested.
- **Windows:**
  - Release bounds are inclusive and date bounds half-open.
  - A file missing from a later snapshot closes its version (`overview.md`: `[27, 28]`, `until_date` 2023-12-13T00:00Z).
  - The first version starts at the scope's first release.
- **KEP dates:**
  - Parse committer times with their offsets (`-07:00`, `+02:00`) into UTC-aware datetimes. Never treat a local time as UTC (the S03 sitting was 6 hours off).
  - A `from` date before the first release in the manifest is an error with a clear message (not reachable in S04).
- **Files:**
  - Skip symlinks (mode `120000`) and non-`.md` files.
  - Read only the first YAML document of `kep.yaml`.
  - Strip a BOM; turn CRLF into LF; allow blank lines before the opening `---`.
  - Every skipped or unparseable file is logged with its path and reason, and counted in the summary. None is dropped silently.
- **Normalization (ADR-002 D2):**
  - Strip the per-source front-matter keys (case-insensitive).
  - Refuse a strip list that contains a `never_strip` key.
  - Drop link targets and collapse whitespace.
  - The spike's normalizer (`spikes/measure.py`) is the independent reference: 216 docs versions.
- **Git:**
  - Missing blobs in the partial clone are fetched on demand.
  - A git failure (e.g. offline) stops ingestion with the git error, never skips a file.
  - Unit tests make no network calls.
- **Re-ingest:**
  - The second run prints 0 new versions and 0 new chunks.
  - A history mismatch is reported per document and makes the exit code non-zero; other documents still ingest.
- **Chunker:**
  - YAML `#` comments inside a fence or a Hugo `highlight` block are not headings (Pod Security Admission page; `authorization.md`).
  - Indented fences inside list items (106 in scope).
  - The stray closing fence in `CHANGELOG-1.22.md`.
  - A shortcode used as a heading.
  - An oversize code block (~1,585 tokens in `authentication.md`) stays whole.
  - The same input chunked twice gives byte-identical output.
- **Embeddings:**
  - A batch never exceeds 128 texts or 60,000 estimated tokens. A single text over the token budget goes alone.
  - Every request asks for `output_dimension` 1024.
  - The API key is never logged or printed.
  - No key → `make embed` stops with a clear message (tests use the fake).
  - Above `EMBED_MAX_TOKENS_PER_RUN` estimated tokens → refuse to start.
- **SQL:** no string-built SQL (ADR-005); the reviewer checks by hand.

#### Files in scope

- **T2:**
  - **Test database:** `Makefile` (`up` creates `orgknow_test`; `test-int` migrates and uses `TEST_DATABASE_URL`), `.github/workflows/ci.yml` (`TEST_DATABASE_URL`), `.env.example`, `tests/integration/conftest.py`
  - `config/corpus_manifest.yaml` (the `scopes` block only)
  - `src/orgknow/settings.py`
  - `src/orgknow/ingestion/` (lock/scope loading in `manifest.py`, plus new modules: git reader, normalize/hash, canonical ids, history + `plan_changes`, `ingest.py` entry point)
  - `src/orgknow/db/models.py`, `src/orgknow/db/versions.py` (a read listing a document's versions)
  - `Makefile` (`ingest` target), `README.md` (the command list)
  - `tests/unit/`, `tests/integration/`, `tests/fixtures/` (small real files from the corpus, pinned)
- **T3:**
  - `src/orgknow/ingestion/` (chunker module; `ingest.py` gains the chunk step)
  - `src/orgknow/db/chunks.py` (a read listing versions without chunks)
  - `src/orgknow/settings.py`
  - `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- **T4:**
  - `src/orgknow/db/migrations/versions/0003_embeddings_per_text.py`
  - `src/orgknow/db/chunks.py` (`add_embedding` by `content_hash`; a read listing texts without a vector; orphan cleanup)
  - `src/orgknow/embeddings/` (the `Embedder` protocol, Voyage provider, batching, `embed.py` entry point)
  - `src/orgknow/settings.py`, `.env.example`, `Makefile` (`embed` target), `README.md`
  - `tests/unit/`, `tests/integration/` (including the R14 tests, updated for `0003`, and `test_migrations.py`)
  - `docs/architecture.md`: updated at the end of the run
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Out of scope:**
  - the HNSW index and any retrieval query (T5)
  - generation and the CLI (T6, T7)
  - releases 1.20–1.23 and rename detection
  - other sources and SIGs
  - any change to the strip lists or the rest of the manifest
  - `eval/golden_set/`

#### Proof map

| Task | Done when / rule | Proof | Source of expected values |
|---|---|---|---|
| T2 | Tests isolated | With the dev database ingested, `make test-int` is green | — |
| T2 | Re-run creates 0 new versions | Integration test on a fixture git repo (ingest twice, count rows) + demo: second `make ingest` prints 0 new versions | — |
| T2 | Docs windows | Integration test on real fixture files: PSP `[24,24]`, `[25, open]`; Pod Security Admission `[24,24] [25,25] [26,27] [28,29] [30, open]`; `overview.md` `[24,24] [25,26] [27,28]`, last `until_date` 2023-12-13T00:00Z. Date bounds = release dates at 00:00Z (e.g. PSP v1 `[2022-05-03, 2022-08-23)`) | Git + the spike normalizer, read in the sitting; manifest release dates |
| T2 | KEP-2579 windows and claims | Unit test of the pure history function on the 4 real snapshots: v1 from 2021-05-11T20:46:27Z `[21,22]` `implementable/alpha`; v2 from 2021-11-05T01:29:13Z `[22,24]` `implementable/beta`; v3 from 2022-06-02T00:05:45Z `[24,25]` `implementable/stable`; v4 from 2022-09-22T08:28:05Z `[25, open]` `implemented/stable`. Each `until` = the next `from` | `TZ=UTC git log --date=iso-strict-local` in the sitting (commits `182464a6`, `69d3fac5`, `cd5f4f26`, `313ad8b5`) |
| T2 | Compare and extend | Unit tests of `plan_changes`: empty → insert all; equal → nothing; prefix with an open last version → close + insert; diverged → mismatch | Hand-written inputs |
| T2 | Real counts | Demo query: 43 `docs_page` documents with 216 versions; 1 `kep` with 4 versions. Any difference is explained in the brief | Spike normalizer (sitting); KEP trace (sitting) |
| T2 | Alias | Integration test: `resolve_document('web:/rbac/')` = the RBAC page | `rbac.md` front matter |
| T2 | Normalization | Unit tests: a reviewer-only change and a link-target-only change keep the hash; a body change changes it; a strip list with `title` is refused; BOM/CRLF input = LF input | ADR-002 D2; manifest |
| T3 | Headings and code blocks | Unit test on the real Pod Security Admission page (1.37): 1 preamble (empty path) + 7 headed sections; none of the 9 `#` lines inside its YAML block is a heading | The file, read in the sitting |
| T3 | Hugo highlight | Unit test on an `authorization.md` excerpt: `# DO NOT USE THE CONFIG AS IS…` is not a heading | The file |
| T3 | Stray fence | Unit test on a `CHANGELOG-1.22.md` excerpt around line 3085: the headings after the stray fence are found | Excerpt read by hand; markdown-it as referee in the sitting |
| T3 | Code-block and table preservation (done when) | Unit tests: the ~1,585-token block in `authentication.md` is exactly one chunk; a table sits whole in one chunk; a 3-paragraph section over 512 tokens splits at a paragraph boundary | The files; a hand-built input with known sizes |
| T3 | Header | Unit test: the exact header string for a docs chunk and a KEP chunk, written by hand | Pinned formats above |
| T3 | Deterministic | Unit test: chunk the same input twice → identical texts | — |
| T3 | Chunks stored once | Integration test: ingest twice → the chunk count doesn't change | — |
| T4 | Second run makes 0 API calls (done when) | Integration test with a call-counting fake: the first run makes ⌈distinct texts ÷ 128⌉ calls, the second makes 0. Demo: the second `make embed` prints 0 requests | Hand-computed for the fixture |
| T4 | Batching | Unit test: 300 small texts → 128 + 128 + 44; texts of 25,000 estimated tokens each → 2 per batch; one text over 60,000 → alone | Hand arithmetic |
| T4 | Request and response | Unit tests of the pure functions: the request body matches the pinned format; a response with `index` 1, 0 is reordered to 0, 1; a vector of the wrong length is refused | Voyage API reference (read 2026-10-04) |
| T4 | Orphan cleanup | Integration test: a vector whose hash no chunk has is deleted; one whose hash a chunk has stays | — |
| T4 | Migration `0003` | `alembic downgrade 0001 && make migrate` round trip (CI step); a test asserts PK `(content_hash, model)` and the `chunks.content_hash` index; R14 tests: duplicate → `UniqueViolation`, 1023 numbers → `DataException`, bad hash → `CheckViolation` | Domain model (amended) |
| T4 | Run cap | Unit test: an estimate above `EMBED_MAX_TOKENS_PER_RUN` refuses before any call | Settings |

#### Break-it rules

- **T2:**
  1. **Most important.** Make a re-run always insert (bypass `plan_changes`) → the idempotency test fails.
  2. Date a KEP version by the first commit → the KEP v4 test fails (it expects 2022-09-22T08:28:05Z).
  3. Close a docs version at `until` = R2 instead of R2 − 1 → the PSP window test fails.
  - Also: point `make test-int` at the dev database after `make ingest` → S03's PSP test fails with R3 `ValueError`. Restore.
- **T3:**
  1. Remove the Hugo `highlight` rule → the `authorization.md` test fails.
  2. Remove the indentation rule → the stray-fence test fails.
  3. Allow a cut inside a code block → the preservation test fails.
- **T4:**
  1. **Most important.** Drop the "no vector yet" filter → the 0-calls test fails.
  2. Drop the reorder by `index` → the response-order test fails.
- After every restore, `git diff` is clean.

#### Real-data demos

- **T2:**
  - `make up && make migrate && make seed && make ingest`, then:

    ```bash
    docker compose exec -T db psql -U orgknow -d orgknow -c "SELECT d.source_type, count(DISTINCT d.id) AS documents, count(v.id) AS versions FROM documents d JOIN document_versions v ON v.document_id = d.id GROUP BY 1 ORDER BY 1"
    ```

  - `make ingest` again: 0 new versions.
  - The windows of `web:/docs/concepts/security/pod-security-policy/` and `kep:2579` (from/until on both clocks, claims).
- **T3:**
  - `make ingest`: chunks added; again: 0. Then `SELECT count(*), count(DISTINCT content_hash) FROM chunks`.
  - Print the current Pod Security Admission chunk whose heading path is `{Exemptions}`.
- **T4:**
  - `make embed`: requests, texts, Voyage's `usage.total_tokens` against the chars ÷ 4 estimate (the parked token-count check).
  - `make embed` again: 0 requests.
  - The vector count for `voyage-4-large` equals `count(DISTINCT chunks.content_hash)`.

#### Bundle-level check

1. `make check`
2. `uv run alembic downgrade 0001 && make migrate`
3. `make seed`, then `make ingest` twice (the second adds 0 versions and 0 chunks)
4. `make embed` twice (the second makes 0 requests)
5. `make test-int`, with the dev database fully ingested
6. `git status --short` is clean after every break-it restore

#### PR plan

- **2 stacked PRs** (natural seam, decided in the sitting; estimate ~1,500 reviewable lines):
  - **PR 1:** `s04-r1a-ingestion`, cut at T2's last commit: the contract, the test database, T2 ("versions are in").
  - **PR 2:** `s04-r1-indexing`, based on PR 1: T3 + T4 ("versions are searchable").
- Greptile once per PR (2 → 4 of 50).
- Record each PR's size in its brief.

**Paid calls allowed:** Voyage embeddings with voyage-4-large only, up to **2M tokens** for the whole run (the slice is about 0.5M after de-duplication). That covers one full `make embed`, re-runs, and the token-count check. All within the 200M free tokens. No LLM calls. The developer sets `VOYAGE_API_KEY` in `.env` and a payment method on the Voyage account before the run. If the key is missing, T4's real demo parks and its tests run on the fake.

### Run S04-R2: answer path

- **Status:** PR open (PRs: retrieval, then the answer path, stacked)
- **Branch:** `s04-r2-answer-path`. PR 1's branch `s04-r2a-retrieval` is cut at T5's last commit.
- **Tasks, in this order:** S04-T0 (tidy-ups, not a backlog task: the sitting's triage) → S04-T5 (dense retrieval) → S04-T6 (generation) → S04-T7 (CLI `ask` + Langfuse trace).
- **Closes the slice:** no. T8 (`[human]`, seeds #6–#10) and the retro remain.
- **Goal (plain words):** answer a question from the stored chunks.
  - Embed the question, then find the 10 nearest chunk texts with an HNSW index.
  - Show each text once, with every release window it was valid in.
  - Ask Claude Opus 5.5 for a structured answer that cites chunk ids, or says `insufficient_evidence`.
  - Reject any citation that wasn't retrieved, in plain code.
  - Print the JSON and leave one Langfuse trace per ask.

#### Decisions (made in the sitting, 2026-10-06)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | `CLAUDE.md`: before merging a stacked PR 1, retarget PR 2 to `main` | Unchanged rule | `--delete-branch` closed PR #22 when PR #21's branch was deleted |
| S2 | R1 questions: KEP dates stay commit time (S05 → merge time); ingest checks `releases` read-only (T0); the claim-synonym setting stays; HTML-table rule 5 in the S05 sitting; strip `{#id}` anchors in S05 before S06; the dev-DB rebuild is covered by CI and the test DB | Fixing each now | Each is outside T5–T7, or measured as low impact on the seeds; see `docs/backlog.md`, Proposed additions |
| S3 | Triage of the other 26 R1 parked items: 8 folded into T0, 8 → Proposed additions (S05), 2 merged into existing items, 2 confirmed as built (body-only 512 limit; KEP chunks from the README only), 7 dropped | One by one | Recorded in the backlog |
| S4 | Bundle: T0 → T5 → T6 → T7; ADR-006 (T1) decided here | T5 alone; T5–T8 | Retrieval and generation are one read path; T8 is human |
| ADR-006 D1 | Claude Opus 5.5 (`claude-opus-5-5`) at `medium` effort, both from settings; T8 logs reasoning tokens; the model is confirmed in writing before the S06 baseline | Sonnet 5.5; Haiku 4.5 | Strongest at "insufficient evidence"; ~$2 in S04; S06 can switch on T8's numbers |
| ADR-006 D2 | `anthropic` SDK, `messages.parse` with a Pydantic model, behind a `Generator` protocol + fake; refusal and `max_tokens` are typed errors | `urllib`; prompt + parse + retry | Conventional; the SDK converts the schema; the validator still guards ids |
| ADR-006 D3 | `langfuse` SDK v4: one trace per ask; no keys → "tracing off"; flush before exit; T8 saves trace ids | OTLP JSON via `urllib`; legacy ingestion API (sunset 2026-11-16) | S11's LangGraph integration needs the SDK; +17 packages accepted |
| 4 | One result per distinct text: cite the chunk in the newest version holding it; list every release window of the versions holding it | One row per chunk; newest window only | 1,016 of 1,583 texts sit in 2+ chunks; 2 texts skip a release (34, 36, 37+), so one span would lie |
| 5 | No authority tier in S04; results carry `source_type`, release windows and KEP claims | A base tier (`docs_page` → 1, `kep` → 5) | ADR-003 tiers need a target release and observed stages (S09) |
| 6 | `RETRIEVAL_TOP_K` = 10 (validated ≤ 40, pgvector's default `ef_search`); HNSW `m=16`, `ef_construction=64` (pgvector defaults); no similarity threshold | k = 5; k = 20 | Matches Recall@10; defaults matched exact search on 20 real queries (200 of 200) |
| 7 | Answer schema: the model returns `answer_status`, `answer`, `evidence` (chunk ids), `insufficient_evidence_reason`; code fills each citation in from the database (pinned below), with a GitHub URL at the snapshot commit | Ids + a verified quote | Smallest; AC2 exact; provenance can't be invented. Quotes fit S06's faithfulness metric |
| 8 | A rejected answer becomes `insufficient_evidence` with reason `citation_validation_failed: [ids]`; the rejected answer stays in the trace | Drop bad ids; retry once; fail | AC2 holds by construction; no extra paid call; fabrication stays countable |
| 9 | 2 stacked PRs (below) | 1 PR | ~1,000 reviewable lines; natural seam between retrieve and answer |

**Claude's calls (overrulable):**
- **Layout:**
  - `src/orgknow/db/retrieval.py`: the search SQL.
  - `src/orgknow/retrieval/dense.py`: embed the question, then search. Its `main()` is the T5 demo, like `ingest`/`embed`.
  - `src/orgknow/generation/`: `schema.py` (models), `prompt.py`, `generator.py` (protocol + `AnthropicGenerator`), `validate.py` (validator + fill-in).
  - `src/orgknow/cli.py`: `ask`, plus the Langfuse spans; it's the only caller.
- **CLI:** `argparse` (no dependency); `[project.scripts] orgknow = "orgknow.cli:main"`.
  - JSON goes to stdout; "tracing off" and errors go to stderr.
  - Exit codes: 0 when an answer prints (either status), 1 on an error, 2 on bad usage.
- **Settings (with defaults, documented in `.env.example`):**
  - `RETRIEVAL_TOP_K` (10)
  - `GENERATION_MODEL` (`claude-opus-5-5`), `GENERATION_EFFORT` (`medium`), `GENERATION_MAX_TOKENS` (16,000; reasoning counts toward it)
  - `ANTHROPIC_API_KEY` (`SecretStr`, optional)
  - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (`SecretStr`), `LANGFUSE_BASE_URL`, all optional
  - No key → `ask` stops with a clear message; no Langfuse keys → tracing off.
- **SDK defaults kept:** timeout and `max_retries` (2). No `temperature` (Opus 5.5 rejects it).
- **Prompt:** a module constant. Answer only from the evidence; cite chunk ids; if the evidence doesn't support an answer, return `insufficient_evidence` with a reason; never invent rationale the corpus doesn't contain (blueprint §18).
- **Fill-in details:**
  - `title` uses the chunker's title logic.
  - `section` = the heading path joined with ` > `, `null` when empty.
  - KEP claims come from the newest version holding the text.
  - Release minors are printed as `"1.N"`.

#### Pinned formats

**Migration `0004`:** `CREATE INDEX embeddings_embedding_hnsw_idx ON embeddings USING hnsw (embedding vector_cosine_ops)`. The downgrade drops it.

**Search SQL shape (`db/retrieval.py`; one fixed query, ADR-005):**

```sql
WITH nearest AS (          -- index-ordered: ORDER BY the distance alone, or HNSW isn't used
    SELECT e.content_hash, e.embedding <=> %(query)s::vector AS distance
    FROM embeddings e
    WHERE e.model = %(model)s
      AND EXISTS (SELECT 1 FROM chunks c WHERE c.content_hash = e.content_hash)
    ORDER BY e.embedding <=> %(query)s::vector
    LIMIT %(k)s
)
-- then: join chunks → document_versions → documents per text; pick the newest version's chunk;
-- aggregate every (valid_from_release, valid_until_release) ordered by valid_from_release;
-- final ORDER BY distance, content_hash (deterministic ties among the k rows)
```

**Retrieval hit (T5 → T6)**, a Pydantic model:
- `chunk_id`, `content_hash`, `distance` (cosine distance, 0–2), `text`
- `canonical_id`, `source_type`, `heading_path`
- `release_windows: list[tuple[int, int | None]]` (minors, ordered)
- `claimed_status`, `claimed_stage`
- `snapshot_repo`, `snapshot_sha`, `source_path`, plus the version `metadata` (title)

**Evidence block in the prompt (one per hit):**

```
[chunk 4182] valid in releases: 1.24–1.29, 1.31–now
<chunk text, which starts with its Source/Title/Document/Section header>
```

KEP hits add the line `claimed: <status>/<stage>` after the window line.

**`ask` output (stdout):**

```json
{"question": "...", "answer_status": "answered", "answer": "...",
 "evidence": [{"chunk_id": 4182, "document": "web:/docs/concepts/security/pod-security-admission/",
   "title": "Pod Security Admission", "section": "Exemptions", "source_type": "docs_page",
   "release_windows": [["1.30", null]], "claimed_status": null, "claimed_stage": null,
   "source_url": "https://github.com/kubernetes/website/blob/<snapshot_sha>/<source_path>"}],
 "insufficient_evidence_reason": null, "model": "claude-opus-5-5", "trace_id": null}
```

- `source_url` = the manifest's `repos.<snapshot_repo>.url` + `/blob/<snapshot_sha>/<source_path>`.
- `evidence` keeps the model's order; duplicate ids are collapsed.
- `trace_id` is `null` when tracing is off.

**Validator (decision 8):** the answer is rejected when
- any cited id is not a retrieved `chunk_id`, or
- `answered` has 0 citations, or
- `insufficient_evidence` has an empty reason.

A rejection becomes `answer_status: insufficient_evidence`, `answer: ""`, `evidence: []`, with reason `citation_validation_failed: [<ids or rule>]`. An `insufficient_evidence` answer may keep valid citations.

**Trace (one per ask):** name `ask`.
- Input: the question.
- Span `retrieve`: k, the model, and hits as (chunk id, distance).
- Generation `generate`: model, effort, prompt, raw parsed output, `usage` (input, output and reasoning tokens where reported), stop reason.
- Span `validate`: the result and any rejected ids.
- Output: the final JSON.

#### Handoffs between tasks

- **T0 → T5:** nothing; T0 is independent.
- **T5 → T6:** `search(conn, question_vector, model, k) -> list[Hit]` and `retrieve(question, embedder, conn, settings) -> list[Hit]` (embeds with `input_type="query"`).
- **T6 → T7:**
  - `answer(question, hits, generator, settings) -> Answer`: prompt, call, validate, fill in.
  - It returns a typed failure (`GenerationError`) for a refusal or a cut-off; it never raises anything else on model output.
- **T7 → T8:** `uv run orgknow ask "<q>"` prints the JSON. T8 saves it under `eval/results/s04/` with the trace id.

#### Edge cases (from the pre-mortem; all must be handled or tested)

- **T0 (releases check):**
  - The releases table missing a manifest release, or holding a different date → exit non-zero with "run `make seed`", before any git read.
  - Extra rows in the table aren't an error.
- **T5:**
  - k > 40 → refused by settings (HNSW returns at most `ef_search` rows).
  - An orphan vector (no chunk) and another model's vector are never returned.
  - A text in versions with a gap → windows listed separately, never merged into one span.
  - Equal distances → ordered by `content_hash`.
  - The question is embedded with `input_type="query"`.
  - An empty table → an empty list, not an error.
- **T6:**
  - Refusal, or `stop_reason: max_tokens` → `GenerationError` with the stop reason.
  - The fake generator returns canned outputs (valid, out-of-set id, 0 citations, empty reason).
  - Unit tests make no network calls.
  - Duplicate cited ids are collapsed.
  - 0 hits → `insufficient_evidence` without calling the model (reason `no evidence retrieved`).
- **T7:**
  - No `ANTHROPIC_API_KEY` → a clear message, exit 1.
  - No Langfuse keys → "tracing off" on stderr, exit 0.
  - Secrets never appear in stdout, stderr or the trace.
  - Flush before exit, including on the error path.
  - An empty question → exit 2.
- **SQL:** no string-built SQL (ADR-005); the reviewer checks by hand.

#### Files in scope

- **T0 (tidy-ups):**
  - `src/orgknow/ingestion/ingest.py`: read-only releases check; summary wording (R1 parked 22-#6)
  - `src/orgknow/db/releases.py`: a read listing releases
  - `src/orgknow/ingestion/normalize.py`: BOM as `"\ufeff"`
  - `src/orgknow/settings.py`: `PositiveInt` batch limits
  - `docs/domain-model.md`: data-access table (`list_versions`, `VersionData`, `versions_without_chunks`, `texts_without_embedding`, `delete_orphan_embeddings`)
  - This slice doc: R1 break-it 4 wording ("R3 `ValueError`")
  - `tests/fixtures/README.md`: source and CC BY 4.0 attribution
  - `tests/integration/test_version_windows.py`: v1.30 times 20:56:34Z and 21:01:40Z
  - The test typed `Any` → `FakeEmbedder`
  - `tests/integration/test_ingest.py` / `test_releases.py`
  - `docs/backlog.md`: remove the v1.30 item once done
- **T5:**
  - `src/orgknow/db/migrations/versions/0004_embeddings_hnsw.py`
  - `src/orgknow/db/retrieval.py`, `src/orgknow/db/models.py` (`Hit`)
  - `src/orgknow/retrieval/dense.py`
  - `src/orgknow/settings.py`, `.env.example`
  - `tests/unit/`, `tests/integration/` (including `test_migrations.py`)
  - `docs/domain-model.md` (the index is no longer open; add `search`)
- **T6:**
  - `src/orgknow/generation/` (new)
  - `src/orgknow/settings.py`, `.env.example`
  - `pyproject.toml` + `uv.lock` (`anthropic`; `httpx2` moves to runtime)
  - `tests/unit/`, `tests/conftest.py` (fake generator)
- **T7:**
  - `src/orgknow/cli.py` (new)
  - `pyproject.toml` (`[project.scripts]`, `langfuse`) + `uv.lock`
  - `src/orgknow/settings.py`, `.env.example`
  - `README.md` (the `ask` command)
  - `tests/integration/` (CLI with fakes)
  - `docs/architecture.md` (end of run)
- **Every task:** `docs/backlog.md` (tick), this contract's Status line.
- **Out of scope:**
  - lexical search, RRF, rerank, tiers, query modes, conflicts
  - any change to chunking, ingestion rules or the manifest
  - FastAPI `/query`
  - `eval/golden_set/` and `eval/results/` (T8 is the developer's)

#### Proof map

| Task | Done when / rule | Proof | Source of expected values |
|---|---|---|---|
| T0 | Ingest no longer writes `releases` | Integration: a row deleted or re-dated → exit non-zero, message names `make seed`, 0 rows written anywhere; matching table → ingests | Hand-edited rows |
| T0 | v1.30 times | Test constants equal 20:56:34Z and 21:01:40Z | `git log` times recorded in the S03 backlog item |
| T0 | Batch limits | `Settings(embed_batch_max_texts=0)` is refused | — |
| T5 | Index (migration `0004`) | Test: `pg_indexes` shows `embeddings_embedding_hnsw_idx` using `hnsw` with `vector_cosine_ops`; round trip 0004 → 0003 → 0004 on the test DB | pgvector docs |
| T5 | **Integration test on fixtures (done when)** | 4 texts with unit vectors `e1`, `(e1+e2)/√2`, `e2`, `−e1`; query `e1` → order and distances 0, 0.2929, 1, 2 (±1e-6) | Hand arithmetic: 1 − cos θ |
| T5 | Expansion (decision 4) | One text in versions [24,24] and [26, open], skipping 25 → 1 hit; `chunk_id` = the chunk in the [26, open] version; windows `[(24,24),(26,None)]` | Hand-written fixture |
| T5 | Filters | An orphan vector nearer than everything isn't returned; a `model='other'` vector isn't returned | — |
| T5 | Settings and query mode | `RETRIEVAL_TOP_K=41` refused; the fake embedder recorded `input_type="query"` | Decision 6 |
| T5 | Real data | With the index: for 20 real vectors used as queries, the top 10 with `enable_indexscan=off` = the top 10 with the index; `EXPLAIN` shows the index scan (with `enable_seqscan=off`) | The sitting: 200 of 200 |
| T6 | **Out-of-set citation rejected (done when)** | Unit: hits 1, 2, 3; the fake cites 2 and 999 → `insufficient_evidence`, reason `citation_validation_failed: [999]`, `evidence` empty | Hand-written |
| T6 | AC1 / AC3 rules | 0 citations → rejected; empty reason → rejected; a valid answer citing 1 and 3 passes, with evidence in that order | Decision 8 |
| T6 | Fill-in | One fixture hit → the exact evidence object, including `source_url` `https://github.com/kubernetes/website/blob/<sha>/<path>` | Pinned format; manifest `repos` |
| T6 | Prompt | The exact evidence block for one docs hit and one KEP hit | Pinned format |
| T6 | Failure states | Stop reasons `refusal` and `max_tokens` → `GenerationError` (pure function over the stop reason) | SDK docs |
| T6 | 0 hits | No model call (the fake records 0 calls) → `insufficient_evidence`, `no evidence retrieved` | — |
| T7 | `ask` works offline | Integration: fake embedder + fake generator + test DB → stdout parses into the output model; exit 0 | Pinned format |
| T7 | No keys / secrets | No Langfuse keys → stderr has "tracing off", exit 0; a fake secret string is absent from stdout and stderr | — |
| T7 | Errors | Fake `GenerationError` → one stderr line, exit 1, no traceback; an empty question → exit 2 | — |

#### Break-it rules

- **T0:** make the releases check always pass → its test fails.
- **T5:**
  1. **Most important.** Group by chunk instead of text → the expansion test fails.
  2. Order by distance descending → the order test fails.
  3. Drop the `model` filter → the filter test fails.
- **T6:**
  1. **Most important.** Remove the "cited id in retrieved set" check → the done-when test fails.
  2. Remove the 0-citation rule → its test fails.
- **T7:** remove the no-keys path → the offline CLI test fails.
- After every restore, `git status --short` is clean (new files: compare sha256).

#### Real-data demos

- **T0:** `make ingest` on the ingested dev DB → `New versions: 0`, with no releases write. Re-date one release in a throwaway transaction or the test DB → the "run `make seed`" exit.
- **T5:**
  - `uv run python -m orgknow.retrieval.dense "What enforces pod security standards in-tree?"` → the top 10 (document, section, windows, distance). 1 Voyage query call.
  - The index-vs-exact check above, and `EXPLAIN`.
- **T6 + T7:**
  - `uv run orgknow ask "What enforces pod security standards in-tree?"` (seed #6)
  - `uv run orgknow ask "What objections were raised in the \"3-Tier Pod Security Proposal\" doc comments?"` (seed #10)
  - Show each JSON, its `usage` (with reasoning tokens) and its trace id.
  - Fetch one trace back through the Langfuse API to prove the flush.
  - 2 Opus calls; re-runs only if a fix needs them.

#### Bundle-level check

1. `make check`
2. `make migrate`; round trip 0004 → 0003 → 0004 on the test DB
3. `make test-int`, with the dev DB fully ingested and embedded
4. The two `ask` demos, plus the trace fetch
5. `git status --short` clean after every break-it restore

#### PR plan

- **2 stacked PRs** (natural seam, decided in the sitting; estimate ~1,000 reviewable lines):
  - **PR 1:** `s04-r2a-retrieval`, cut at T5's last commit: the contract, ADR-006, the ADR-004 amendment, the `CLAUDE.md` fix, T0, T5 ("chunks are findable").
  - **PR 2:** `s04-r2-answer-path`, based on PR 1: T6 + T7 ("ask answers").
- Merge with the new rule: retarget PR 2 to `main` before merging PR 1.
- Greptile once per PR (4 → 6 of 50). Record each PR's size in its brief.

**Paid calls allowed:**
- **Voyage:** query embeddings only, ≤ 50 calls (~1K tokens, free tier). No document re-embedding.
- **Anthropic:** `claude-opus-5-5` only, ≤ 15 asks, hard cap **$3** (expected ~$0.20 for the 2 demos).
- **Langfuse Cloud:** Hobby (free) tier.
- The developer sets `ANTHROPIC_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` in `.env` before the run. A missing key parks that demo; the tests run on fakes.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S04-*.md`
