# S08: Reranking

- **Status:** 🟨
- **Blueprint stage:** Stage 5 (cross-encoder reranking)
- **Started:** 2026-10-08
- **Finished:**

## Outcome

`make eval` runs a `rerank` pipeline (hybrid candidates, reordered by a local cross-encoder), and its row in the ablation table shows the delta against `hybrid`, with p95 latency and cost per question in the table.

## Why now

- **Hybrid ranks by position, not by reading.** RRF only knows where each list put a text; a cross-encoder reads the question and the text together and scores the pair.
- **2 Phase 1 gaps are carried from S07:** MRR 0.675 vs ≥ 0.69, and Recall@10 0.382 vs ≥ 0.46. Hybrid's Recall@20 is 0.608, so good texts sit at ranks 11–20 for a reranker to lift.
- **It's the next ablation step** in the product spec (AC7): dense → +lexical/RRF → **+rerank** → …
- **It's the first local model.** Its CPU latency sets the instance size for S15.

## Exit checks

- [ ] A reranker interface with a local cross-encoder and a test fake; unit tests need no model download.
- [ ] `RETRIEVAL_MODE=rerank` works in `orgknow ask`, `make eval-retrieval` and `make eval`; `dense` and `hybrid` still print their pinned numbers.
- [ ] `summary.json` and the ablation table record p95 latency and cost per question.
- [ ] The rerank stage's CPU p95 is measured and written down, with an instance-sizing note for S15.
- [ ] The `rerank` row is in the ablation table (3 runs), and `docs/evaluation.md` says whether it meets the improvement rule; if not, the keep/drop reason is written (AC7).
- [ ] ADR-008 is Accepted.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| ADR-008: the reranker model, how it runs, and the candidate count | Fine-tuning a reranker (non-goal) |
| A reranker interface, the local implementation and a fake | An LLM reranker (a prompt that scores texts) |
| `rerank` mode on top of `hybrid`; its settings | Score thresholds that drop texts (top K is always returned) |
| p95 latency and cost per question in the summary and table | Release filters, authority multipliers (S09) |
| A rerank latency benchmark and the S15 sizing note | GPU or a hosted model server; deployment (S15) |
| The rerank eval run (3 runs) and its row | Golden set changes (v0 is frozen); BM25 (proposed addition) |

## Metric to move

**Recall@10** against `hybrid` (0.382), by the improvement rule: ≥ +0.03 on Recall@10, no other retrieval metric down > 0.03, AC1–AC3 and false refusals within hybrid's range. Also mean p95 ≤ 23 s (S08-R1 decision 4). Recall@10 was chosen after the sitting's prototype was seen; `docs/evaluation.md` says so. The Phase 1 targets are Recall@10 ≥ 0.46 and MRR ≥ 0.69.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S08-T1: ADR-008 reranker model and candidate count `[core]` ✅

- **Goal:** decide in the sitting, from measured numbers, which cross-encoder runs, how (library), how many hybrid candidates it reads, and how long a text it reads.
- **Done when:** ADR-008 is written and Accepted in the run PR; its numbers come from the sitting's prototype.
- **Status:** done in the S08-R1 sitting (2026-10-09); ADR-008 is in the run contract commit.
- **Deps:** none.

### S08-T2: Reranker module and `rerank` mode `[core]`

- **Goal:** a small reranker interface (question + texts in, one score per text out), a local cross-encoder behind it, and a fake for tests. `rerank` mode takes hybrid's top N fused texts, scores them, and keeps the top K by score.
- **Done when:** unit tests with the fake give the hand-predicted order; an integration test with the real model (marked, skipped when the model isn't cached) ranks a hand-picked relevant text first; `make eval-retrieval` in rerank mode prints the sitting's numbers; dense and hybrid print theirs.
- **Deps:** T1.

### S08-T3: p95 latency and cost in the summary and table `[commodity]`

- **Goal:** `summary.json` gains p95 latency, cost per question, and the retrieve stage's own p95; the ablation table shows them; the 6 existing folders are refilled from their `questions.jsonl` by `make eval-resummarize`.
- **Done when:** unit tests with hand-computed p95 (nearest rank) and cost; the regenerated table matches the numbers in `docs/evaluation.md` (dense p95 10.7 s, hybrid 12.9 s; $0.029, $0.030).
- **Deps:** none.

### S08-T4: Rerank latency benchmark and sizing note `[commodity]`

- **Goal:** `make eval-retrieval` also prints retrieval p50/p95 and the model's load time (S08-R1 decision 5); a short S15 sizing note (11 threads vs. 2 CPUs, peak RAM, load time).
- **Done when:** the line prints; the note is in `docs/evaluation.md` with the machine described.
- **Deps:** T2.

### S08-T5: Rerank eval run `[commodity]`

- **Goal:** run `make eval` 3 times in rerank mode, commit the row, write the result into `docs/evaluation.md`.
- **Done when:** the row and its spread are committed; the doc states pass or fail against the improvement rule with numbers.
- **Notes / pointers:** paid (Anthropic, ~$1.30 per run).
- **Deps:** T2, T3.

## Risks & unknowns

- **A new heavy dependency.** A local cross-encoder needs PyTorch or ONNX Runtime. PyTorch from PyPI on Linux pulls ~2–3 GB of CUDA libraries unless the CPU index is pinned.
- **CPU latency.** 40 pairs of ~260 tokens each (p95 ~540) per question; a large model may cost seconds per question.
- **Truncation.** The p95 distinct text is 2,153 characters (~540 tokens) and the longest 62,939; a 512-token reader cuts the tail.
- **CI.** Tests must not download a model; the real model is tested only where it's cached.
- **Tuning on the test set.** Choosing the model and N on v0 makes v0 a weaker test, as in S07.

## Decisions expected (ADRs)

- **ADR-008:** reranker model, runtime library, candidate count, max text length. Accepted in the S08-R1 sitting (2026-10-09).

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S08-R1: reranking

- **Status:** planned
- **Branch:** `s08-r1-reranking`
- **Tasks, in this order:** S08-T2 (reranker and `rerank` mode) → S08-T3 (p95 and cost in the summary) → S08-T4 (timing line and sizing note) → S08-T5 (rerank eval run). T1 (ADR-008) was done in the sitting.
- **Closes the slice:** no; `/slice-retro` runs after the developer has read T5's result.
- **Goal (plain words):**
  - Let a local model (BGE reranker base) read the question next to each of hybrid's ~21 candidate texts, score each pair, and keep the best 10.
  - Make every eval summary report p95 latency, retrieval-only p95 and cost per question, including the 6 old runs.
  - Time the reranker on this CPU and pinned to 2 CPUs (S15 sizing), then run the paid eval 3 times and record the `rerank` row.

#### Sitting evidence (2026-10-09)

The prototype (scratch venv, not committed) is in ADR-008's Context: 3 models × 3 pool sizes, 2-CPU timing, ONNX Runtime, and repeatability. Also measured in the sitting:

- **Rounding:** sorting by the score rounded to 4 decimals, ties broken by hybrid order, gives the same 4 metrics as raw scores. 54 of 1,697 adjacent score gaps are under 1e-4, and 42 are exact ties, likely texts identical in their first 512 tokens.
- **Old runs** (recomputed from each `questions.jsonl`, all 43 rows, nearest-rank p95, $4 / $20 per M tokens):

| Run | p95 latency | Cost per question |
|---|---|---|
| dense-20261008T230746Z | 11.250 s | $0.029450 |
| dense-20261008T231253Z | 9.450 s | $0.029569 |
| dense-20261008T231659Z | 11.315 s | $0.029341 |
| hybrid-20261009T021400Z | 20.911 s | $0.029954 |
| hybrid-20261009T021907Z | 8.845 s | $0.030054 |
| hybrid-20261009T022231Z | 8.927 s | $0.030345 |

  These match `docs/evaluation.md` (dense 10.7 s, 9.4–11.3; hybrid 12.9 s, 8.8–20.9; $0.0293–0.0296 and $0.0300–0.0303), which S06/S07 computed separately.
- **Threads:** `torch.get_num_threads()` is 11 on this machine and 2 under `taskset -c 0,2`, so a 2-CPU pin needs no setting.
- **Truncation:** 25% of (question, text) pairs exceed 512 tokens.

#### Decisions (made in the sitting, 2026-10-09)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S1 | Slice doc approved; bundle = T2–T5; "S07 parked test gaps" stays a proposed addition | — | — |
| S2 | Run the local prototype before deciding ($0) | Decide from model cards | S07's prototype method; the decisions need measured numbers |
| 1 | **Model:** `BAAI/bge-reranker-base`, revision `2cfc18c9415c912f9d8155881c133215df768a70` (ADR-008 D1); Voyage `rerank-2.5` recorded as the fallback; no Voyage test | v2-m3; MiniLM; Voyage now | Best on all 4 metrics at pool 20; 3.3× faster than v2-m3. Devil's advocate: the gain is Recall and nDCG, MRR is flat; kept as written |
| 2 | **Runtime:** `transformers` + CPU-only `torch` from the PyTorch CPU index (ADR-008 D2, ADR-004 amendment) | ONNX Runtime; `sentence-transformers` | The measured stack; ONNX was no faster and its scores differ by up to 0.29 |
| 3 | **Pool:** 20 candidates per list (~21 texts), rerank all, keep 10, cut at 512 tokens; recheck on v1 (ADR-008 D3) | 30; 40; top 10 only | Best MRR and Hit; half the time of 40; top-10-only can't move Recall@10 |
| 4 | **Target metric: Recall@10**, chosen after seeing the prototype (the docs say so). `rerank` becomes the default only if the improvement rule passes vs. `hybrid` on 3-run means **and** mean p95 ≤ 23 s; otherwise the default stays `hybrid`, and `docs/evaluation.md` names each failed condition and by how much | MRR; nDCG@10; MRR and Recall both | Recall is the reranker's job here (lift ranks 11–20) and the bigger Phase 1 gap |
| 5 | **Reporting:** `summary.json` gains p95 latency, retrieval-only p95 and cost per question; `make eval-resummarize` refills the 6 old folders; `make eval-retrieval` prints a timing line (the T4 benchmark) | No refill; a separate `bench-rerank` | Comparable rows in one table; one command fewer |
| 6 | **1 PR**, an explicit exception to the ~800-line alarm (estimate ~1,000 reviewable lines including tests). Paid calls as listed below | 2 stacked PRs split after T3 (recommended) | The developer's call in the sitting |

ADR-008 had a devil's advocate. Its proposed tests (2-CPU timing, ONNX speed and score agreement) were run in the sitting and are in ADR-008.

**Claude's calls (overrulable):**
- **Layout:**
  - `retrieval/rerank.py`: the `Reranker` protocol (`score(question, texts) -> list[float]`, one score per text, in order) and the pure `rerank(hits, scores, top_k) -> list[Hit]`.
  - `retrieval/cross_encoder.py`: `CrossEncoderReranker`, the `transformers` implementation. It's the only module importing `torch`/`transformers`. It's imported only when the mode is `rerank`, so `dense`/`hybrid` and the unit tests never load torch.
  - Tests use a fake reranker.
- **Ordering in `rerank`:** sort by `round(score, 4)` descending, then by position in hybrid's fused list. `rerank_score` stores the raw score. Hybrid's fields (`rrf_score`, `dense_rank`, `lexical_rank`, `distance`) are kept.
- **Retrieval in rerank mode:** dense N + lexical N → `fuse` with no top-K cut (the whole pool) → `reranker.score` → `rerank(…, RETRIEVAL_TOP_K)`. An empty pool returns `[]` without calling the model. `retrieve` gains a `reranker: Reranker | None = None` argument; rerank mode without one raises `ValueError`.
- **The model's recipe** (must match the prototype for the gate):
  - `AutoTokenizer` + `AutoModelForSequenceClassification` at the pinned revision, `use_safetensors=True`, `.eval()`, under `torch.inference_mode()`.
  - Texts are sorted by character length (stable) and scored in batches of `RERANK_BATCH_SIZE`.
  - Tokenized as (question, text) pairs with `padding=True, truncation=True, max_length=RERANK_MAX_LENGTH`.
  - Score = `logits.view(-1).float()`.
  - Threads: torch's default.
- **Loading:** once per process. The CLI's `ask` builds it in rerank mode. The eval (`run`, `eval-retrieval`) builds it once before the question loop and measures its load time. A missing model is downloaded from Hugging Face at the pinned revision only.
- **Settings:**
  - `RETRIEVAL_MODE` gains `rerank`; the default stays `hybrid` until T5 applies decision 4.
  - `RERANK_MODEL` (default `BAAI/bge-reranker-base`), `RERANK_REVISION` (default the pinned SHA).
  - `RERANK_MAX_LENGTH` (default 512, 1–512), `RERANK_BATCH_SIZE` (default 8, 1–256).
  - `GENERATION_PRICE_INPUT_USD_PER_MTOK` (default 4.0) and `GENERATION_PRICE_OUTPUT_USD_PER_MTOK` (default 20.0), ADR-006 D1's prices.
  - `.env.example` lists all of them.
- **Packaging:** `[[tool.uv.index]]` `pytorch-cpu` (`https://download.pytorch.org/whl/cpu`, `explicit = true`) and `[tool.uv.sources] torch = { index = "pytorch-cpu" }`. If uv can't lock torch for macOS/Windows from that index, restrict `[tool.uv] environments` to Linux (WSL and CI are the only platforms used) and say so in the brief.
- **Real-model test:** a `reranker` pytest marker (registered in `pyproject.toml`), skipped when the pinned model isn't in the local Hugging Face cache (`huggingface_hub.try_to_load_from_cache`). CI skips it and never downloads the model.
- **Eval files:**
  - `run.json` `settings` gain `rerank_model`, `rerank_revision`, `rerank_max_length`, `rerank_batch_size`, `torch_threads`, and `rerank_load_s` at the top level. All are optional (null in other modes and in old folders).
  - Each `questions.jsonl` row gains `retrieve_s` (null in old folders). Each `hits[]` entry gains `rerank_score`.
  - The `--name` default is the mode (`rerank`, `rerank-smoke`).
- **Summary fields** (decision 5):
  - `latency_s_p95`: nearest rank over the rows' `latency_s`.
  - `retrieve_s_p95`: the same over `retrieve_s`; null if no row has it.
  - `cost_usd_mean`: the mean over rows with usage of (input × in-price + output × out-price) / 1e6. Output tokens already include reasoning (ADR-006).
  - All optional, so a summary without them still loads.
- **`make eval-resummarize`** (`python -m orgknow.eval resummarize`): for every results folder with `summary.json` and `questions.jsonl`, rebuild the summary with `summarize` from the saved rows, keeping its name, golden hash and start time. It prints one line per folder, writes nothing else, and is then followed by `make eval-table`.
- **Trace:** the `retrieve` span's output per hit adds `rerank_score`.
- **Docs:**
  - `docs/architecture.md`: reranking, the 3 modes, the summary fields.
  - README: `rerank` mode, `eval-resummarize`, the one-time model download.
  - `docs/evaluation.md`: the metric table gains the 3 columns; T4's sizing note; T5's section with the honesty note from decision 4.
  - Glossary: "cross-encoder" already exists; add nothing unless an interviewer would use a new term.

#### Pinned formats

**`make eval-retrieval` output** (3 lines). Rerank mode:

```
Mode: rerank (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, max length 512). Answerable questions: 36.
Recall@10 0.516  Hit@10 0.972  MRR 0.703  nDCG@10 0.489
Retrieve time: p50 4.31 s, p95 5.40 s (36 questions). Reranker load 3.2 s.
```

- Times are examples; they vary.
- `dense` and `hybrid` keep their first two lines from S07 exactly. Their third line has no "Reranker load" part.
- p50 is the median; p95 is nearest rank.

**Ablation table:** 3 columns after `Errors`: `p95 latency (s)`, `Retrieve p95 (s)`, `Cost/question ($)`.
- Cells are the mean (min–max) over runs, like the others. Seconds use 1 decimal, cost 4 decimals. A run without the value is left out, and no value gives `n/a`.
- Expected after the refill (sitting recompute):
  - dense: `10.7 (9.4–11.3)` | `n/a` | `0.0295 (0.0293–0.0296)`
  - hybrid: `12.9 (8.8–20.9)` | `n/a` | `0.0301 (0.0300–0.0303)`

**`rerank`:** `rerank(hits: Sequence[Hit], scores: Sequence[float], top_k: int) -> list[Hit]`.
- `hits` are in hybrid's fused order, and `scores` has one score per hit.
- It returns the top `top_k` by rounded score (ties: earlier hit first), each with `rerank_score` set.
- A length mismatch raises `ValueError`.

#### Handoffs between tasks

- T2 → T4: the `rerank` mode, the model loaded once, and `eval-retrieval` in all 3 modes.
- T2 → T5: the gate line, the `rerank` name default, the optional `run.json` fields.
- T3 → T5: the summary fields and the table columns, so T5's row shows p95 and cost with no hand calculation.
- T3 does not depend on T2. If T2 parks, T3 still runs; T4 and T5 park with it.

#### Edge cases

- A pool smaller than 10 texts: all are returned, reranked.
- An empty pool (dense finds nothing): `[]`, with no model call.
- A 62,939-character text: tokenized whole, then cut to 512 tokens. No error.
- Exact score ties (42 in the sitting): hybrid order breaks them.
- A text only lexical search found (`distance` null): reranked like any other.
- The model missing from the cache: one download at the pinned revision (allowed); offline, a clear error.
- Old results folders: no `retrieve_s`, no rerank fields. They load, and `retrieve_s_p95` is null.
- A run with an errored question: p95 and cost use the rows that have the value.
- `dense`/`hybrid` modes: torch is never imported.

#### Files in scope

- **New:**
  - `src/orgknow/retrieval/{rerank,cross_encoder}.py`
  - `tests/unit/test_rerank.py`
  - a real-model test (`tests/integration/test_cross_encoder.py`, marked `reranker`)
  - T5's 3 results folders
- **Changed:**
  - Packaging and config: `pyproject.toml`, `uv.lock`, `Makefile`, `.env.example`
  - Code: `src/orgknow/settings.py`, `src/orgknow/db/models.py` (`Hit.rerank_score`), `src/orgknow/retrieval/retrieve.py`, `src/orgknow/cli.py`, `src/orgknow/eval/{runner,table,__main__}.py`
  - Results: the 6 existing `eval/results/*/summary.json` (refill only), `eval/results/ablation.md` (generated)
  - Docs: `README.md`, `docs/{architecture,evaluation}.md`, `docs/backlog.md` (ticks)
  - Tests that touch `Hit`, `run.json`, the summary or the table
- **Not touched:** `eval/golden_set/`, `eval/question_vectors/`, migrations and the schema, chunking, ingestion, generation, and the 6 old folders' `run.json`/`questions.jsonl`.

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T2 | Rerank promotes from deep in the pool | Unit, fake scores: the best-scored hit is 15th of 20 → `rerank` puts it 1st; the top 10 follows the scores | By hand |
| T2 | Ties are stable | Unit: scores 0.50001 and 0.50004 (equal at 4 decimals) keep hybrid order; 3 hits with top_k 10 → 3 returned; `[]` → `[]`; a length mismatch → `ValueError` | By hand |
| T2 | Hybrid fields kept | Unit: each returned hit keeps its `rrf_score` and ranks and gains `rerank_score` | By hand |
| T2 | Real model reads correctly | Integration (`reranker` marker): 3 hand-written texts; the one defining `LegacyServiceAccountTokenCleanUp` scores highest for a question about it | Hand-written fixture |
| T2 | Rerank mode wiring | Integration with the fake reranker on DB fixtures: rerank mode returns the fake's order over hybrid's whole pool; without a reranker → `ValueError` | By hand |
| T2 | No GPU packages | `grep -c nvidia uv.lock` → `0` | Decision 2 |
| T2 | **Gate** | `RETRIEVAL_MODE=rerank make eval-retrieval` → `Recall@10 0.516  Hit@10 0.972  MRR 0.703  nDCG@10 0.489` | Sitting prototype (separate code) |
| T2 | Other modes unchanged | `RETRIEVAL_MODE=dense make eval-retrieval` → 0.384 / 0.944 / 0.614 / 0.369; `hybrid` → 0.382 / 0.944 / 0.675 / 0.385 | S06 / S07 |
| T2 | Settings validation | Unit: `RERANK_MAX_LENGTH=513` → validation error | The contract |
| T3 | p95 math | Unit: latencies 1…20 → p95 `19`; 43 values → the 41st smallest | By hand (nearest rank) |
| T3 | Cost math | Unit: 1,000 in + 100 out tokens at $4 / $20 → `0.006` | By hand |
| T3 | Refill exact | After `make eval-resummarize`: a script shows every old key unchanged in the 6 summaries and only the 3 new keys added, with `latency_s_p95` and `cost_usd_mean` equal to the sitting's table above (cost to 6 decimals) | Sitting recompute |
| T3 | Table | `make eval-table`: dense and hybrid rows end with the pinned cells above; the existing columns are unchanged (diff) | Sitting recompute |
| T4 | Timing line | `make eval-retrieval` in all 3 modes prints the third line; in rerank mode p50 is within 3–6 s (sitting: 4.2 s) | Sitting prototype |
| T4 | Sizing note | `docs/evaluation.md`: the machine, 11-thread and `taskset -c 0,2` timing lines, peak RAM (`/usr/bin/time -v`, max resident set), load time | Measured in the run |
| T5 | Gate before paid calls | The T2 gate line, re-run just before the first paid run | Sitting prototype |
| T5 | Row + verdict | 3 × `RETRIEVAL_MODE=rerank make eval`, each `git_dirty: false`; `ablation.md` has a `rerank` row with p95 and cost; `docs/evaluation.md` has a rerank section: the 4 retrieval means, AC1–AC3, false refusals, p95, cost, and pass/fail per condition (decision 4), with the post-hoc target note | Results files |
| T5 | Default mode | Per decision 4: the settings default and `.env.example` match the verdict | The rule |

#### Break-it rules

- T2: rerank only the first 10 hits of the pool → the "15th → 1st" test fails.
- T2: drop the rounding (raw scores only) → the tie test fails.
- T3: p95 index off by one (`ceil(n × 0.95)` instead of `ceil(n × 0.95) − 1`) → the "= 19" test fails.

#### Real-data demo

```bash
RETRIEVAL_MODE=dense make eval-retrieval
RETRIEVAL_MODE=hybrid make eval-retrieval
RETRIEVAL_MODE=rerank make eval-retrieval
RETRIEVAL_MODE=rerank uv run orgknow ask "What enforces pod security standards in-tree?"   # ≤ 3 asks; Langfuse trace link in the brief
```

#### Bundle-level check

1. `make check`; note how much longer CI takes with torch.
2. `make test-int` (Postgres checked healthy at run start).
3. `make eval-retrieval` in all 3 modes: the pinned lines.
4. `eval/results/ablation.md` has `dense` and `hybrid` rows (existing columns unchanged, 3 new cells filled) and a `rerank` row with 3 runs.
5. `git status --short`: only intended files.

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 6). Greptile: 1 trigger (12/50 used before the run).

#### Paid calls allowed

- **Anthropic:** ≤ 129 eval asks (3 × 43) + ≤ 3 demo asks; cap $5. Only after the gate passes.
- **Voyage:** ≤ 3 requests, for the demo asks only (the eval uses stored vectors).
- **Langfuse:** traces of the demo asks.
- **Hugging Face:** none expected (the pinned model is cached). If missing: only the pinned revision of `BAAI/bge-reranker-base`.
- **Package installs:** `torch` (PyTorch CPU index) and `transformers` with their dependencies (decision 2).
- No other network calls. No content reads on the corpus clones.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S08-reranking.md`
