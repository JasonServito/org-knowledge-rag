# Evaluation

How the pipeline is measured: a fixed golden set, one results folder per run, and an ablation table that compares every stage with the dense baseline (AC7).

- The Phase 1 thresholds are in `docs/product-spec.md`.
- The question file format and the label rules are in ADR-007.
- The commands are in the README.

## Golden set v0

- **43 questions:**
  - 36 answerable: 10 CURRENT, 10 HISTORY, 9 CHANGE, 7 WHY.
  - 7 unanswerable.
  - 13 are marked `smoke` for `make eval-smoke`.
- **184 labels.** Each names a document and a heading path, never a chunk id, so labels survive re-chunking.
  - A label is credited when a hit is in that document under that section.
  - **Breadth rule ("A-primary"):** each fact's primary sources are labeled, i.e. the docs page, the KEP, the gate file, the release's CHANGELOG section and the topic's blog posts. Pre-release copies and passing mentions are not.
- **Sign-off:** 3 independent Claude passes checked every question against the stored text, and the developer spot-checked 6.
- **Frozen** since the dense baseline (file hash `1a715968`). New or changed questions go into v1, which gets its own baseline.

## Metrics

K = 10 (`RETRIEVAL_TOP_K`). Retrieval metrics are per answerable question, then averaged over the 36. Each label is credited once, at its first matching hit, so a second copy of a found section adds nothing (ADR-007 D3).

| Metric | Definition | What it tells you |
|---|---|---|
| **Recall@10** | Labels found in the top 10 ÷ labels | How many of a question's primary sources were retrieved |
| **Hit@10** | 1 if any label is found in the top 10, else 0 | Whether the answer had at least one good source |
| **MRR** | 1 ÷ the rank of the first labeled hit; 0 if none | How high the first good source ranks |
| **nDCG@10** | Σ gainᵢ / log₂(i + 1), divided by the best possible sum for min(labels, 10) sources; gainᵢ = 1 if hit i finds a new label | Recall that rewards finding the sources early |
| **Distinct sections** | Distinct (document, heading path) pairs in the top 10 | A diagnostic, not a target: how many slots repeat a section |
| **AC1** | An `answered` answer cites ≥ 1 chunk, each with a source URL, release windows and source type | Citations are present and resolvable |
| **AC2** | Every cited chunk id was retrieved for this question | No invented citations |
| **AC3** | An unanswerable question gets `insufficient_evidence` with a reason | The system says "I don't know" when it should |
| **False refusal** | An answerable question gets `insufficient_evidence` | The system gives up when it shouldn't |
| **p95 latency** | 95th percentile (nearest rank: the ⌈0.95 × n⌉-th smallest; the 41st of 43) of a question's retrieve + answer time | The slow-question experience |
| **Retrieve p95** | The same over the retrieval step alone; n/a for runs before S08-T3, which didn't time it | What retrieval, e.g. a reranker, adds to the wait |
| **Cost per question** | Input tokens × $4/M + output tokens × $20/M (ADR-006 D1 prices, `GENERATION_PRICE_*`; output includes reasoning), averaged over the questions with a model call | What one answer costs |

The ablation table (`eval/results/ablation.md`) shows the last 3 as its `p95 latency (s)`, `Retrieve p95 (s)` and `Cost/question ($)` columns.

## Reading a result

- **Retrieval repeats exactly.** Each question's vector is stored (`eval/question_vectors/`), so every run of one golden set retrieves the same hits. The 4 retrieval metrics have no run-to-run spread.
- **The answer side varies.** The model reasons differently each run, so AC1–AC3, false refusals, latency and cost are run 3 times. The table shows the mean and the (min–max).
- **One question is 0.028.** With 36 answerable questions, one question changing moves a mean by up to 1/36. The product spec's improvement rule (≥ +0.03) and Phase 1 targets (+0.08) count in these steps.
- **Recall@10 is coverage.** A question with 6 labels needs 6 different sections in 10 slots. Hit@10 and MRR show whether one good source was found.

## Dense baseline

S06-T6, 2026-10-08. The question vector's 10 nearest chunk texts by cosine distance, then one Claude Opus 5.5 call at medium effort. 3 runs of `make eval`, 43 questions each.

| Measure | Value | Spread over 3 runs |
|---|---|---|
| Recall@10 | 0.384 | none |
| Hit@10 | 0.944 (34 of 36) | none |
| MRR | 0.614 | none |
| nDCG@10 | 0.369 | none |
| Distinct sections | 7.1 of 10 | none |
| AC1 | 100% | 33–34 answered, all pass |
| AC2 | 100% (43 of 43) | none |
| AC3 | 100% (7 of 7) | none |
| False refusals | 2.3 of 36 | 2–3 |
| p95 latency | 10.7 s | 9.4–11.3 s |
| Cost per question | $0.029 | $0.0293–0.0296 |
| Errors | 0 | none |

By question type (retrieval only; 7–10 questions each, so one question moves a row by 0.10–0.14):

| Mode | Questions | Recall@10 | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| CURRENT | 10 | 0.353 | 0.900 | 0.467 | 0.308 |
| HISTORY | 10 | 0.323 | 0.900 | 0.550 | 0.324 |
| CHANGE | 9 | 0.350 | 1.000 | 0.624 | 0.333 |
| WHY | 7 | 0.562 | 1.000 | 0.905 | 0.569 |

What the runs show:

- **Refusals follow retrieval misses.**
  - q31 and q43 have no labeled source in their top 10, and the model refused both in every run.
  - Not every refusal is a miss: q41 found 1 of its 5 labeled sources (at rank 3), and was answered, refused, then answered.
- **About 3 of 10 slots repeat a section**: another version of it, or another packed piece of a long one.
- **CURRENT questions rank worst:** MRR 0.467, against 0.905 for WHY.
- **Same prompt every run.** Input tokens were identical in all 3 runs (232,992), because the hits were. Output was 16,484–16,975 tokens, of which 1,388–1,548 were reasoning.
- **Each run took 3 min 38 s to 4 min 50 s** and cost $1.26–1.27.

## Hybrid

S07-T4, 2026-10-09 (UTC). Two searches, merged into one list:

- **Dense:** the question vector's 20 nearest chunk texts (HNSW search width 100: how many candidates the vector index explores).
- **Lexical:** the 20 best Postgres full-text matches. Every content word of the question must match; `ts_rank_cd` ranks texts with the words close together higher.
- **Reciprocal Rank Fusion (RRF), k = 60:** a text scores 1 ÷ (60 + its rank) in each list that holds it, summed. The best 10 go to the same Claude call as the baseline.
- 3 runs of `RETRIEVAL_MODE=hybrid make eval` on commit `c77484b`, 43 questions each. First, the free gate: `make eval-retrieval` matched the sitting's numbers exactly.

| Measure | Hybrid | Spread over 3 runs | Dense baseline |
|---|---|---|---|
| Recall@10 | 0.382 | none | 0.384 |
| Hit@10 | 0.944 (34 of 36) | none | 0.944 (34 of 36) |
| MRR | 0.675 | none | 0.614 |
| nDCG@10 | 0.385 | none | 0.369 |
| Distinct sections | 7.1 of 10 | none | 7.1 of 10 |
| AC1 | 100% | 33–34 answered, all pass | 100% |
| AC2 | 100% (43 of 43) | none | 100% (43 of 43) |
| AC3 | 100% (7 of 7) | none | 100% (7 of 7) |
| False refusals | 2.3 of 36 | 2–3 | 2.3 of 36 (2–3) |
| p95 latency | 12.9 s | 8.8–20.9 s | 10.7 s (9.4–11.3 s) |
| Cost per question | $0.030 | $0.0300–0.0303 | $0.029 ($0.0293–0.0296) |
| Errors | 0 | none | 0 |

**The improvement rule** (`docs/product-spec.md`), on the 3-run means (S07-R1 decision 6). Changes are computed before rounding.

| Condition | Dense | Hybrid | Change | Result |
|---|---|---|---|---|
| MRR rises by ≥ 0.03 | 0.6144 | 0.6745 | +0.0602 | Pass |
| Recall@10 drops by ≤ 0.03 | 0.3844 | 0.3819 | −0.0025 | Pass |
| Hit@10 drops by ≤ 0.03 | 0.9444 | 0.9444 | 0 | Pass |
| nDCG@10 drops by ≤ 0.03 | 0.3694 | 0.3853 | +0.0160 | Pass |
| AC1, AC2, AC3 at or above the baseline's range (100% in all 3 runs) | 100% | 100% in all 3 runs | 0 | Pass |
| False refusals at or below the baseline's range (2–3 of 36) | 2.33 | 2.33 (runs: 3, 2, 2) | 0 | Pass |

- **"At or below the range"** is read as: the hybrid mean is at most the range's top (3 of 36). The stricter readings pass too: every hybrid run is inside 2–3, and the means are equal.
- **Distinct sections** is a diagnostic, not one of the rule's metrics: 7.14 → 7.11, i.e. 1 section fewer over all 36 questions.
- **Verdict: pass.** `RETRIEVAL_MODE` now defaults to `hybrid` (decision 6).
- **The gain is about 2 questions' worth** (0.060 ÷ 0.028 = 2.2), on a set the setup was chosen on (see Known limits).

By question type (retrieval only; the dense baseline in brackets; one question moves a row by 0.10–0.14):

| Mode | Questions | Recall@10 | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| CURRENT | 10 | 0.374 (0.353) | 0.900 (0.900) | 0.692 (0.467) | 0.385 (0.308) |
| HISTORY | 10 | 0.330 (0.323) | 0.900 (0.900) | 0.625 (0.550) | 0.346 (0.324) |
| CHANGE | 9 | 0.336 (0.350) | 1.000 (1.000) | 0.569 (0.624) | 0.314 (0.333) |
| WHY | 7 | 0.526 (0.562) | 1.000 (1.000) | 0.857 (0.905) | 0.534 (0.569) |

What the runs show:

- **12 of 43 questions got a different top 10**, all answerable. The other 31 kept dense's exact list.
  - Lexical search adds little at 10: 13 of the 430 hits were found by it alone.
  - 30 of 43 questions have no lexical hit in their top 10. All-words matching finds nothing for 23 of the 36 answerable questions (S07 sitting), so they keep the dense order.
- **Better on 5: MRR up** on q06, q12, q14, q22 and q30. Each one's first labeled source moved to rank 1, from rank 3–6.
  - q06, q12 and q30 also found 1 more labeled source (Recall@10 +0.17 to +0.20).
- **Worse on 7:**
  - MRR: rank 1 → 2 on q04, q19 and q25; rank 3 → 4 on q02.
  - Recall@10, a labeled source pushed out of the top 10: q04 (−0.25), q07, q35 and q40 (−0.125 each).
- **CURRENT questions gain most:** MRR 0.467 → 0.692 (q06, q22, q30). CHANGE and WHY lose about 0.05 each (q25; q04 and q19, against q14 up).
- **The same questions are refused as in dense.** Their retrieval didn't change.
  - q31 and q43 in every run: no labeled source in their top 10 in either mode.
  - q41 once (run 1). Dense also refused it once (run 2).
- **Run 1's p95 (20.9 s) is 3 slow answers:** q17 26.2 s, q10 21.9 s, q25 20.9 s.
  - In runs 2 and 3 the same questions took 2.2–6.7 s, with the same hits and similar output (q10: 144 tokens, against 173–179). The cause isn't recorded.
  - Runs 2 and 3: 8.8–8.9 s. All 3 runs are under the Phase 1 threshold (≤ 23 s).
- **Input tokens: 241,671 per run, +8,679 (+3.7%) over dense**, identical in all 3 runs. Output was 16,066–16,908 tokens, of which 1,388–1,648 were reasoning.
- **Each run took 3 min 22 s to 5 min 6 s** and cost $1.29–1.30.

## Reranker timing and S15 sizing

S08-T4, 2026-10-09. How long rerank mode's retrieval takes on this laptop and on 2 CPUs, to size S15's server (ADR-008 assumes about 2 vCPUs). Measured with `make eval-retrieval`: free, from the stored question vectors, with no answer call.

- **The machine:** Intel Core Ultra 7 155H under WSL2, 22 logical CPUs (11 cores, 2 threads each), 15 GB RAM, no GPU (torch is the CPU-only build).
- **Retrieve time:** one question's wall time in retrieval: its stored vector, the dense and lexical searches, fusion, and the reranker scoring ~21 texts.
  - Dense and hybrid take 0.01 s (p50 and p95), so in rerank mode it is almost all reranking.
- **p50** is the median (of 36 questions, the mean of the 18th and 19th). **p95** is nearest rank (the 35th of 36).
- **Reranker load:** once per command, from the local model cache. It includes importing torch and transformers.
  - A separate check split ~7.4 s into 4.2 s of imports and 3.0–3.3 s of model load (the sitting's "3 s warm").
- **Peak RAM:** "Maximum resident set size" from `/usr/bin/time -v` around `uv run`: the most RAM the largest single process (Python) held at once. Postgres runs separately and isn't counted.
- **`taskset -c 0,2`** pins the command to 2 logical CPUs. Torch then uses 2 threads by itself (`torch.get_num_threads()` is 2).

| Setup | Torch threads | Retrieve p50 | Retrieve p95 | Reranker load | Peak RAM | Whole command |
|---|---|---|---|---|---|---|
| Default | 11 | 4.91 s | 6.14 s | 7.4 s | 1.63 GiB (1,708,380 KB) | 3 min 29 s |
| 2 CPUs (`taskset -c 0,2`) | 2 | 11.50 s | 15.36 s | 7.7 s | 1.51 GiB (1,587,180 KB) | 8 min 4 s |

The printed lines (both runs also printed the gate's metrics: Recall@10 0.516, Hit@10 0.972, MRR 0.703, nDCG@10 0.489):

```
Retrieve time: p50 4.91 s, p95 6.14 s (36 questions). Reranker load 7.4 s.
Retrieve time: p50 11.50 s, p95 15.36 s (36 questions). Reranker load 7.7 s.
```

- **2 CPUs are 2.3× slower at p50** (11.50 ÷ 4.91) and 2.5× at p95. The load time doesn't change.
- **Runs vary by ~0.3 s:** a repeat on the default threads gave p50 4.77 s, p95 6.46 s, load 8.2 s.

What it means for S15 (a projection; S15 decides):

- **Rerank alone on 2 CPUs: ~11.5 s per question at p50, ~15.4 s at p95.** ADR-008 expected 10–15 s.
- **Projected answer p95 on 2 CPUs: 24.2–36.3 s, mean 28.3 s,** over the 23 s ceiling in all 3 runs.
  - The sum of hybrid's 3 p95 latencies (8.8, 8.9 and 20.9 s) and the 2-CPU retrieve p95. The answer call runs at Anthropic, so the server's CPUs don't change it.
  - Adding two p95s overstates it when the slow questions differ. With the p50 instead: 20.3–32.4 s, mean 24.4 s.
  - The same sum on this laptop: 15.0–27.1 s, mean 19.0 s. T5 measures the real p95 here.
- **Not counted:** a live `orgknow ask` also embeds the question (one Voyage call), and loads the reranker (~7.5 s) until the API keeps it loaded (S12).
- **RAM:** ~1.6 GiB for this process alone.
- **The levers (ADR-008):**
  - A bigger instance: 11 threads here give ~4.9 s.
  - The hosted Voyage `rerank-2.5` fallback: no local model, ~$0.0004 per question (not verified).
  - ONNX quantization: not measured; unquantized ONNX was no faster.

## Known limits

- **Answers aren't graded against the expected answer.** There's no grading model yet, so AC1–AC3 check structure, not correctness.
- **37 of the 43 questions were checked by Claude only.** The developer spot-checked 6.
- **Latency leaves out the question embedding.** The vectors are stored, so a live `orgknow ask` adds one Voyage call.
- **Retrieve p95 is n/a for the dense and hybrid runs.** They ran before the retrieval step was timed (S08-T3).
  - Their p95 latency and cost were added to each `summary.json` from its `questions.jsonl` by `make eval-resummarize`, and match the numbers above.
- **The dense baseline's run 3 says `git_dirty: true`.** Its only changed tracked file was the ablation table, which run 2 had just rewritten. The code was the same commit.
  - Since S07 the dirty check ignores `eval/results/`. All 3 hybrid runs say `git_dirty: false`.
- **v0 isn't a clean test of hybrid.** About 30 retrieval configurations were tried on v0 in the S07 sitting before this one was chosen, so part of the +0.060 MRR may fit v0 only. v1 is the clean test.
