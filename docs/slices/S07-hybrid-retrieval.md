# S07: Hybrid retrieval

- **Status:** 🟨
- **Blueprint stage:** Stage 4 (lexical retrieval + RRF fusion)
- **Started:** 2026-10-08
- **Finished:**

## Outcome

`make eval` runs a `hybrid` pipeline (dense + Postgres full-text search, fused with RRF), and its row in the ablation table shows the delta against the dense baseline.

## Why now

- **Dense search misses exact terms.** A question naming `LegacyServiceAccountTokenCleanUp` or `--service-account-issuer` needs the literal token; an embedding only finds "something about service accounts".
- **It's the next ablation step** in the product spec (AC7): dense → +lexical/RRF → +rerank → …
- **S08's reranker reorders a candidate list.** This slice builds the list it will rerank.

## Exit checks

- [ ] `search_vector` column and GIN index exist (migration); `make migrate` is idempotent.
- [ ] RRF is a pure function with hand-calculated unit tests.
- [ ] `RETRIEVAL_MODE=hybrid` works in `orgknow ask` and `make eval`; `dense` still reproduces the baseline.
- [ ] The `hybrid` row is in the ablation table (3 runs), and `docs/evaluation.md` says whether it meets the improvement rule (product spec); if not, the keep/drop reason is written (AC7).
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| A generated `search_vector` column on `chunks` + GIN index | BM25 via a Postgres extension (new dependency, custom image) |
| A lexical search returning one hit per distinct text, like dense | Weighted RRF, or tuning weights per query mode (S09 owns per-mode plans) |
| RRF as a pure function; candidate counts and k in settings | Reranking (S08) |
| A retrieval-mode setting used by `ask` and the eval | Release filters, authority multipliers (S09) |
| The hybrid eval run (3 runs) and its row | Golden set changes (v0 is frozen) |
| Two small eval fixes that protect the runs (dirty check, smoke rows) | p95/cost columns in the summary (proposed for S08) |

## Metric to move

**MRR** (how high the first good source ranks), target ≥ +0.03 over the dense baseline's 0.614, with no other retrieval metric dropping > 0.03 (the product spec's improvement rule). Recall@10, Hit@10 and nDCG@10 are recorded.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S07-T1: Lexical search `[core]`

- **Goal:** a migration adds `search_vector` (a stored generated `tsvector` of the chunk text) and a GIN index; a query returns the top N distinct chunk texts for a question, ranked by Postgres full-text rank, with the same fields as a dense hit.
- **Done when:** integration tests on fixtures: an exact term ranks its text first; a text held by several chunks appears once; no match → empty list.
- **Notes / pointers:** ADR-005 (hand-written SQL in `db/`); `db/retrieval.py:search` (the expansion to cited chunk + release windows is reused).
- **Deps:** none.

### S07-T2: RRF `[core]`

- **Goal:** Reciprocal Rank Fusion as a pure function: ranked lists of ids in, one fused ranking with scores out.
- **Done when:** unit tests match hand-calculated scores, including an id in one list only, ties, and empty lists.
- **Deps:** none.

### S07-T3: Hybrid retrieval and config `[core]`

- **Goal:** `retrieve` runs dense and lexical (N candidates each), fuses them with RRF and returns the top K; the mode, N, k and the HNSW search width come from settings; `ask` and the eval use the mode and record it; `make eval-retrieval` scores retrieval alone, with no paid call.
- **Done when:** integration test: hybrid on fixtures returns the hand-predicted order; `dense` mode returns exactly what it did before; `make eval-retrieval` gives the sitting's numbers in both modes.
- **Deps:** T1, T2.

### S07-T4: Hybrid eval run `[commodity]`

- **Goal:** fix the two eval issues that would taint repeated runs, run `make eval` 3 times in hybrid mode, commit the row, and write the result into `docs/evaluation.md`.
- **Done when:** the row and its spread are committed; the doc states pass or fail against the improvement rule with numbers.
- **Notes / pointers:** paid (Anthropic, ~$1.27 per run).
- **Deps:** T3.

## Risks & unknowns

- **Postgres ranking has no IDF.** `ts_rank` counts how often and how close the words appear, not how rare they are, so "kubernetes" weighs as much as "PodSecurity". Real BM25 needs an extension.
- **Natural-language questions rarely match every word.** With AND matching, 23 of 36 golden questions match no text (sitting, 2026-10-08).
- **HNSW is approximate.** More dense candidates need a wider search (`ef_search`), or the list silently differs from an exact scan.
- **Tuning on the test set.** The sitting tried ~30 configurations on v0, so v0 is not a clean test of the chosen one; v1 is.

## Decisions expected (ADRs)

- None expected: the product spec already calls for lexical + RRF, and ADR-005 names Postgres full-text search. Decisions go in the run contract.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S07-R1: hybrid retrieval

- **Status:** PR open
- **Branch:** `s07-r1-hybrid-retrieval`
- **Tasks, in this order:** S07-T1 (lexical search) → S07-T2 (RRF) → S07-T3 (hybrid retrieval and config) → S07-T4 (hybrid eval run).
- **Closes the slice:** no; `/slice-retro` runs after the developer has read T4's result (a fail needs the developer's AC7 write-up).
- **Goal (plain words):**
  - Add a word search next to the meaning search, each giving its top 20 texts.
  - Merge the two lists with RRF and keep the best 10; a setting picks `dense` or `hybrid`.
  - Check the merged scores for free against the sitting's numbers, then run the paid eval 3 times and record the `hybrid` row.

#### Sitting evidence (2026-10-08)

A throwaway script (scratchpad, not committed) scored retrieval on golden set v0's 36 answerable questions from the stored question vectors, on the real database. It reproduced the dense baseline exactly. Measured:

| Retrieval (top 10) | Recall@10 | Hit@10 | MRR | nDCG@10 | Recall@20 |
|---|---|---|---|---|---|
| Dense (baseline) | 0.384 | 0.944 | 0.614 | 0.369 | 0.603 |
| **Hybrid, decisions 1–3** | **0.382** | **0.944** | **0.675** | **0.385** | 0.608 |
| OR matching + `ts_rank(…, 1)` | 0.417 | 0.889 | 0.650 | 0.400 | 0.540 |
| AND, falling back to OR | 0.422 | 0.889 | 0.661 | 0.410 | 0.543 |
| Lexical alone (best) | 0.281 | 0.639 | 0.426 | 0.260 | — |

- AND matching finds 0 texts for 23 of 36 questions (`websearch_to_tsquery`: 22); OR: 0.
- Hybrid (decisions 1–3) changes 13 questions at @10: MRR up on q06, q12, q14, q22, q30; down a little on q02, q04, q07, q19, q25, q35, q40.
- HNSW search width vs. an exact scan (43 questions): 20 candidates at width 100 → 0 differ; 50 at width 50 → 17 differ; 50 at width 400 → 1 differs. 10 at width 40, 50, 100, 200 or 400 → 0 differ.
- Lexical query over 48,273 chunks (temp GIN index): 1 ms median, 5 ms max. `to_tsvector('english', …)` over every chunk: no error.
- About 30 configurations were tried on v0, so v0 is not a clean test of the chosen one (a known limit; v1 is).

#### Decisions (made in the sitting, 2026-10-08)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Parked items: eval fixes 1 (dirty check) and 2 (smoke rows) → T4; p95/cost in the summary → S08's candidate tasks; the spec's "≈ baseline + 0.08" and the q41 wording fixed in this commit; the 9.45 s rounding and the spec policy-line confirmation dropped | Fixing p95/cost now | S08 must record p95; it changes the pinned results format |
| S2 | Slice doc approved; bundle = T1–T4 (the whole slice) | — | — |
| 1 | Lexical query: `plainto_tsquery('english', question)` (every content word must match), ranked by `ts_rank_cd` (default normalization). BM25 → Proposed additions | OR matching (B); AND → OR fallback (D); a BM25 extension (E) | The textbook form, not picked by tuning; the only tried option that passes the improvement rule (MRR +0.061); the devil's advocate's own test (Recall@20) favored it: B 0.540, D 0.543 vs. A 0.608. Known limits: 23 of 36 questions match nothing; the gain is about 2 questions' worth |
| 2 | `chunks.search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED` + a GIN index; the header is indexed with the body | A per-text table; an expression index only | The database keeps it in sync with 0 ingest code; 2.2× duplicate rows cost little (the table is 56 MB) |
| 3 | 20 candidates per search (`RETRIEVAL_CANDIDATES`), HNSW search width 100 (`HNSW_EF_SEARCH`), RRF k = 60 (`RRF_K`), equal weights | 50 candidates; 10 candidates | The only measured setup identical to an exact scan; best in the prototype; k = 60 is the RRF paper's value, not tuned |
| 4 | Each hit records `distance` (null if only lexical found it), `rrf_score`, `dense_rank`, `lexical_rank`, in `Hit`, the results file and the `ask` trace | Score only; a wrapper type | "Why did this rank here?" is answered from the results file alone |
| 5 | `make eval-retrieval`: retrieval scores only, from stored vectors, no paid call | Nothing new; a skip-answers flag on `run` | Guards the paid runs; a real-data proof for both modes |
| 6 | The improvement rule decides the default mode, on the 3-run means: pass → `RETRIEVAL_MODE` default becomes `hybrid`; fail → stays `dense`, and `docs/evaluation.md` says which condition failed, by how much | Always hybrid; always dense | Mechanical, so the run judges nothing; the developer reviews before merging |
| 7 | Paid: ≤ 129 eval asks + ≤ 3 demo asks; ≤ 3 Voyage requests; cap $5. Gate: `make eval-retrieval` in hybrid must equal the sitting's numbers before any paid eval | 1 run; no paid calls in the run | Same 3-run method as the baseline |
| 8 | 1 PR, an explicit exception to the ~800-line alarm (estimate ~1,000 reviewable lines including tests); Greptile 1 trigger | 2 stacked PRs split after T3 (recommended) | The developer's call in the sitting |

Decision 1 had a devil's advocate; its proposed test (fused Recall@20, per-question changes) was run in the sitting and is in the evidence above.

**Claude's calls (overrulable):**
- **Layout:**
  - `db/retrieval.py`: `search` (dense) gains an `ef_search` argument and fills `dense_rank`; new `search_lexical(conn, question, n)` returns `Hit`s with the same expansion as `search` (the cited chunk in the newest version holding the text, and every version's release window), `distance` null and `lexical_rank` filled.
  - `retrieval/fusion.py`: `rrf(rankings, k)` (T2) and `fuse(dense, lexical, k, top_k)`, both pure: the hits of both lists in, the top `top_k` fused `Hit`s out. A text in both lists takes the dense hit's fields (the same cited chunk either way) plus both ranks.
  - `retrieval/retrieve.py`: `retrieve(question, embedder, conn, settings)` picks the mode; `cli.py` and `eval/runner.py` import it from there. `retrieval/dense.py` keeps its demo `main`.
- **The search width** is set inside `search` with `SELECT set_config('hnsw.ef_search', %s, true)`, in a `conn.transaction()` block together with the query, so it applies even on an autocommit connection and ends with the block. It applies in both modes (measured: the dense top 10 is unchanged).
- **The lexical query's ranking** is grouped by content hash (one hit per text; every chunk of a text has the same rank) and ordered by rank, then content hash, like dense.
- **Settings:** `RETRIEVAL_MODE` (`dense` | `hybrid`, default `dense` until T4 applies decision 6), `RETRIEVAL_CANDIDATES` (default 20, 1–1000), `RRF_K` (default 60, ≥ 1), `HNSW_EF_SEARCH` (default 100, 1–1000; a validator requires it ≥ `RETRIEVAL_TOP_K` and ≥ `RETRIEVAL_CANDIDATES`). `.env.example` lists all four.
- **Eval:**
  - `run.json`'s `settings` gain `retrieval_mode`, `retrieval_candidates`, `rrf_k`, `hnsw_ef_search`, each optional (null), so the 3 dense baseline folders still load.
  - The `--name` default becomes the mode (`dense` / `hybrid`); with `--smoke`, `<mode>-smoke` (fix 2). An explicit `--name` is used as given.
  - The dirty check ignores `eval/results/` (fix 1): `git status --porcelain -- . ':!eval/results'`.
  - `python -m orgknow.eval retrieval` (Make target `eval-retrieval`): loads and checks the golden set, uses only stored vectors (a missing one is an error; no Voyage call), scores every answerable question, prints the format below. It writes nothing.
- **Trace:** the `retrieve` span's input adds the mode; its output per hit adds `rrf_score`, `dense_rank`, `lexical_rank`.
- **Docs:** `docs/architecture.md` (lexical search, fusion, modes), `docs/domain-model.md` (`chunks.search_vector`), README (`eval-retrieval`, `RETRIEVAL_MODE`), `docs/evaluation.md` (T4's section), the glossary only if an interviewer would use a new term.

#### Pinned formats

**Migration `0005`:** `ALTER TABLE chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`, then `CREATE INDEX chunks_search_vector_idx ON chunks USING gin (search_vector)`. Downgrade drops both.

**Lexical query shape** (then the same two lateral expansions as `search`):

```sql
WITH matched AS (
    SELECT c.content_hash, max(ts_rank_cd(c.search_vector, q)) AS rank
    FROM chunks c, plainto_tsquery('english', %(question)s) q
    WHERE c.search_vector @@ q
    GROUP BY c.content_hash
    ORDER BY rank DESC, c.content_hash
    LIMIT %(n)s
)
```

**RRF:** `rrf(rankings: Sequence[Sequence[str]], k: int) -> list[tuple[str, float]]`. An id's score is Σ 1/(k + rank) over the lists holding it, rank from 1. Sorted by score descending, then id ascending. An id twice in one list raises `ValueError`.

**`Hit` fields** (decision 4): `distance: float | None`, `rrf_score: float | None`, `dense_rank: int | None`, `lexical_rank: int | None`. Dense mode: `distance` and `dense_rank` set, the other two null. Hybrid: `rrf_score` set; each rank set when that list holds the text.

**Results rows:** each `hits[]` entry gains `rrf_score`, `dense_rank`, `lexical_rank`; `distance` may be null.

**`make eval-retrieval` output:**

```
Mode: hybrid (candidates 20, k 60, width 100). Answerable questions: 36.
Recall@10 0.382  Hit@10 0.944  MRR 0.675  nDCG@10 0.385
```

In dense mode the first line is `Mode: dense (width 100). Answerable questions: 36.`

#### Handoffs between tasks

- T1 → T3: `search_lexical` returns `Hit`s like `search`; ranks start at 1.
- T2 → T3: `rrf` is pure; `fuse` uses it and touches no database.
- T3 → T4: `make eval-retrieval` (the gate), the mode setting, the `--name` default, and the optional `run.json` fields.

#### Edge cases

- A question of only stop words or punctuation: an empty `tsquery`, 0 lexical hits; hybrid = dense order with RRF scores.
- A question with flags or backticks (`--service-account-issuer`): `plainto_tsquery` accepts any text.
- A text found by lexical but with no stored vector: it can still be a hit (lexical needs no vector).
- Fewer than N lexical matches, or 0: fusion uses what there is.
- Fewer than K fused texts: return them all.
- A text in both lists: one hit, both ranks.
- An autocommit connection: the transaction block still scopes the width.
- Old results folders (no retrieval fields in `run.json`): `make eval-table` still builds the dense row unchanged.

#### Files in scope

- New: `src/orgknow/db/migrations/versions/0005_chunks_search_vector.py`, `src/orgknow/retrieval/{fusion,retrieve}.py`, `tests/unit/test_fusion.py`, integration tests for lexical and hybrid search (in `tests/integration/test_retrieval.py` or a new file), T4's 3 results folders.
- Changed: `src/orgknow/db/retrieval.py`, `src/orgknow/db/models.py` (`Hit`), `src/orgknow/retrieval/dense.py`, `src/orgknow/settings.py`, `src/orgknow/cli.py`, `src/orgknow/eval/{runner,__main__}.py`, `Makefile`, `.env.example`, `README.md`, `docs/{architecture,domain-model,evaluation}.md`, `docs/learning/glossary.md` (if needed), `docs/backlog.md` (ticks), `eval/results/ablation.md` (generated), tests touching `Hit` or `run.json`.
- Not touched: `eval/golden_set/`, `eval/question_vectors/` (no new questions), chunking, ingestion, generation.

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T1 | Column + index; migration idempotent | Integration: `search_vector` is a generated column; `chunks_search_vector_idx` is a GIN index; `make migrate` twice | The contract |
| T1 | An exact term ranks its text first | Integration: 3 hand-written texts; `LegacyServiceAccountTokenCleanUp` → that text at rank 1 | Hand-written fixture |
| T1 | Every word must match | Integration: a text holding only some of the question's words is not returned | Decision 1 |
| T1 | Words close together rank higher | Integration: "pod security admission" adjacent beats the same 3 words scattered | `ts_rank_cd`'s definition (cover density) |
| T1 | One text in 2 chunks appears once | Integration: 1 hit, both release windows | Fixture rows |
| T1 | No match; stop words only | Integration: both `[]` | — |
| T2 | Scores and order | Unit, k = 60: [a, b, c] + [c, a] → a 1/61 + 1/62 = **0.032522**, c 1/63 + 1/61 = **0.032266**, b 1/62 = **0.016129**; order a, c, b | By hand |
| T2 | Ties, one list, empty, duplicates | Unit: [y] + [x] → x, y, both 0.016393; [] + [a] → a 0.016393; [] + [] → []; [a, a] → `ValueError` | By hand |
| T3 | Hybrid order | Integration with hand-set vectors and texts: each list's ranks known → fused order and scores by hand | Hand RRF math |
| T3 | `fuse` | Unit: hand-built hit lists → top K, fields from the dense hit, both ranks | By hand |
| T3 | Dense mode unchanged | Existing retrieval tests pass unedited (apart from new `Hit` fields); real data: `make eval-retrieval` with `RETRIEVAL_MODE=dense` → 0.384 / 0.944 / 0.614 / 0.369 | S06 baseline |
| T3 | Hybrid on real data | `RETRIEVAL_MODE=hybrid make eval-retrieval` → **0.382 / 0.944 / 0.675 / 0.385** | Sitting evidence (separate code) |
| T3 | The width is set | Integration: `current_setting('hnsw.ef_search')` read inside the transaction is `100` | Decision 3 |
| T3 | Ranks and score recorded | Integration: dense mode → `dense_rank` only; hybrid → `rrf_score` and both ranks where held | Decision 4 |
| T3 | Old results load; new `run.json` fields | Unit: `make eval-table` output on the 3 dense folders unchanged (diff); a fake run writes the 4 fields | The committed table |
| T3 | Settings validation | Unit: `HNSW_EF_SEARCH=10` with candidates 20 → validation error | Decision 3 |
| T4 | Fixes 1–2 | Runs 2 and 3's `run.json` have `git_dirty: false`; unit: `--smoke` default name `hybrid-smoke` | The contract |
| T4 | Gate | `RETRIEVAL_MODE=hybrid make eval-retrieval` equals the T3 line exactly, before any paid call | Sitting evidence |
| T4 | Row + write-up | 3 × `RETRIEVAL_MODE=hybrid make eval`; `ablation.md` has `dense` and `hybrid` rows; `docs/evaluation.md` has a hybrid section: the 4 retrieval means, AC1–AC3, false refusals, p95 and cost (computed from `questions.jsonl` as in S06), and pass/fail per condition of the rule | Results files |
| T4 | Default mode | Per decision 6; the settings default and `.env.example` match the verdict | The rule |

#### Break-it rules

- T1: drop `GROUP BY content_hash` (rank per chunk) → the "appears once" test fails.
- T1: OR the query terms → the "every word" test fails.
- T2: count ranks from 0 → the 0.032522 test fails (1/60 + 1/61).
- T3: remove the `set_config` line → the width test fails.

#### Real-data demo

```bash
RETRIEVAL_MODE=dense make eval-retrieval
RETRIEVAL_MODE=hybrid make eval-retrieval
RETRIEVAL_MODE=hybrid uv run orgknow ask "What enforces pod security standards in-tree?"   # ≤ 3 asks; Langfuse trace link in the brief
```

#### Bundle-level check

1. `make check`
2. `make test-int` (Postgres checked healthy at run start)
3. `make eval-retrieval` in both modes: the two pinned lines
4. `eval/results/ablation.md` has a `dense` row (unchanged) and a `hybrid` row with 3 runs
5. `git status --short`: only intended files

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 8). Greptile: 1 trigger (11/50 used before the run).

#### Paid calls allowed

- **Anthropic:** ≤ 129 eval asks (3 × 43) + ≤ 3 demo asks; cap $5. Only after the gate passes.
- **Voyage:** ≤ 3 requests, for the demo asks only (the eval uses stored vectors).
- **Langfuse:** traces of the demo asks.
- No other network calls. No content reads on the corpus clones.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S07-*.md`
