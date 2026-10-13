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

The 3 time metrics (S09) are pooled over hits instead, by each question's golden mode or window (S09-R1 decision 1). Authority selection (S09-T7) is per CURRENT question, over a fixed subset of them.

| Metric | Definition | What it tells you |
|---|---|---|
| **Recall@10** | Labels found in the top 10 ÷ labels | How many of a question's primary sources were retrieved |
| **Hit@10** | 1 if any label is found in the top 10, else 0 | Whether the answer had at least one good source |
| **MRR** | 1 ÷ the rank of the first labeled hit; 0 if none | How high the first good source ranks |
| **nDCG@10** | Σ gainᵢ / log₂(i + 1), divided by the best possible sum for min(labels, 10) sources; gainᵢ = 1 if hit i finds a new label | Recall that rewards finding the sources early |
| **Distinct sections** | Distinct (document, heading path) pairs in the top 10 | A diagnostic, not a target: how many slots repeat a section |
| **Stale-result rate** | Stale hits ÷ hits, over the CURRENT questions' top 10. A hit is stale when no current version (open date window) holds its text | How often a "now" question gets text a later edit replaced; lower is better |
| **Temporal accuracy** | Hits with a release window overlapping the exact golden `release_window` ÷ hits, over the questions with one. An open end is open | How often a dated question gets text from the releases it asks about |
| **Router accuracy** | Answerable questions routed to their golden mode ÷ answerable questions | Whether the router (ADR-009) picks the right kind of question |
| **Authority selection** | Over the CURRENT questions whose labeled documents span 2+ authority tiers, the share whose first labeled top-10 hit has the best (lowest) label tier. A label's tier is its document's newest version's at the latest release; a superseded proposal (no tier) is the worst | Whether a "now" question's first good source is its most trusted one (S09-R2 decision 4) |
| **CURRENT MRR** | MRR over the 10 CURRENT questions (printed by `make eval-retrieval` only) | The guard beside authority selection: whether the first good source still ranks high |
| **AC1** | An `answered` answer cites ≥ 1 chunk, each with a source URL, release windows and source type, and a tier or the superseded-proposal flag (S09-T6) | Citations are present and resolvable |
| **AC2** | Every cited chunk id was retrieved for this question | No invented citations |
| **AC3** | An unanswerable question gets `insufficient_evidence` with a reason | The system says "I don't know" when it should |
| **False refusal** | An answerable question gets `insufficient_evidence` | The system gives up when it shouldn't |
| **p95 latency** | 95th percentile (nearest rank: the ⌈0.95 × n⌉-th smallest; the 41st of 43) of a question's retrieve + answer time | The slow-question experience |
| **Retrieve p95** | The same over the retrieval step alone; n/a for runs before S08-T3, which didn't time it | What retrieval, e.g. a reranker, adds to the wait |
| **Cost per question** | Input tokens × $4/M + output tokens × $20/M (ADR-006 D1 prices, `GENERATION_PRICE_*`; output includes reasoning), averaged over the questions with a model call | What one answer costs |

The ablation table (`eval/results/ablation.md`) shows the last 3 as its `p95 latency (s)`, `Retrieve p95 (s)` and `Cost/question ($)` columns, the 3 time metrics as `Stale rate`, `Temporal acc.` and `Router acc.`, and authority selection as `Authority sel.`.

- **Stale means replaced, not "not valid at 1.37".** A CHANGELOG section is valid only at its own release, but isn't stale until an edit replaces it. On v0's 105 CURRENT, CHANGE and WHY labels, "replaced" flags 2 correct labels; "not valid at 1.37" would flag 26.
- **Temporal accuracy uses the exact golden window,** not one widened by 1 release. The planned HISTORY filter keeps texts within ±1 release (S09-R1 decision 2), so a widened window would read 100% by construction.
- **Authority selection's denominator is fixed by the labels:** 9 of v0's 10 CURRENT questions have labels in 2+ tiers. A question counts even when its top 10 holds only one tier, or no labeled hit (then it's wrong), so a mode can't shrink the denominator.
- **Authority selection leans toward the weights.** The same tier code drives authority mode's weights and this metric, so a mode that boosts low tier numbers scores well by construction. The check, in the S09-R2 sitting and again in S09-T7: flipping every tier (t → 7 − t) lifts authority mode from 3 to 6 of 9 under the flipped tiers, but lowers CURRENT MRR from 0.637 to 0.628; real tiers give 9 of 9 and 0.783. So CURRENT MRR, which doesn't read tiers, is printed beside it.

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
- **Verdict: pass.** `RETRIEVAL_MODE` defaulted to `hybrid` (decision 6) until rerank passed (below).
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

## Rerank

S08-T5, 2026-10-09 (UTC). Hybrid's candidates, reordered by a local model (ADR-008):

- **The pool:** hybrid's 20 dense and 20 lexical candidates, fused with RRF and not cut to 10: about 21 texts per question.
- **The cross-encoder** (`BAAI/bge-reranker-base`) reads the question next to each text, cut to 512 tokens, and scores the pair. The 10 best scores go to the same Claude call; ties keep hybrid's order.
- 3 runs of `RETRIEVAL_MODE=rerank make eval` on commit `4b674fb`, 43 questions each, all `git_dirty: false`: `rerank-20261009T083721Z`, `rerank-20261009T084531Z`, `rerank-20261009T085359Z`.
- First, the free gate: `make eval-retrieval` matched the sitting's prototype exactly (0.516, 0.972, 0.703, 0.489).

| Measure | Rerank | Spread over 3 runs | Hybrid |
|---|---|---|---|
| Recall@10 | 0.516 | none | 0.382 |
| Hit@10 | 0.972 (35 of 36) | none | 0.944 (34 of 36) |
| MRR | 0.703 | none | 0.675 |
| nDCG@10 | 0.489 | none | 0.385 |
| Distinct sections | 7.4 of 10 | none | 7.1 of 10 |
| AC1 | 100% | 34–35 answered, all pass | 100% |
| AC2 | 100% (43 of 43) | none | 100% (43 of 43) |
| AC3 | 100% (7 of 7) | none | 100% (7 of 7) |
| False refusals | 1.3 of 36 | 1–2 (runs: 2, 1, 1) | 2.3 of 36 (2–3) |
| p95 latency | 14.2 s | 13.4–15.0 s (runs: 15.0, 14.2, 13.4) | 12.9 s (8.8–20.9 s) |
| Retrieve p95 | 6.7 s | 6.6–6.9 s | n/a (0.01 s in `make eval-retrieval`) |
| Cost per question | $0.031 | $0.0307–0.0309 | $0.030 ($0.0300–0.0303) |
| Errors | 0 | none | 0 |

**The improvement rule** against hybrid, on the 3-run means, with Recall@10 as the target and a p95 ceiling (S08-R1 decision 4). Changes are computed before rounding.

| Condition | Hybrid | Rerank | Change | Result |
|---|---|---|---|---|
| Recall@10 rises by ≥ 0.03 | 0.3819 | 0.5156 | +0.1338 | Pass |
| Hit@10 drops by ≤ 0.03 | 0.9444 | 0.9722 | +0.0278 | Pass |
| MRR drops by ≤ 0.03 | 0.6745 | 0.7032 | +0.0287 | Pass |
| nDCG@10 drops by ≤ 0.03 | 0.3853 | 0.4888 | +0.1034 | Pass |
| AC1, AC2, AC3 at or above hybrid's range (100% in all 3 runs) | 100% | 100% in all 3 runs | 0 | Pass |
| False refusals at or below hybrid's range (2–3 of 36) | 2.33 | 1.33 (runs: 2, 1, 1) | −1.00 | Pass |
| Mean p95 latency ≤ 23 s | 12.89 s | 14.20 s | +1.31 s | Pass |

- **Verdict: pass.** `RETRIEVAL_MODE` now defaults to `rerank` (decision 4).
- **The Recall@10 gain is about 5 questions' worth** (0.134 ÷ 0.028 = 4.8). MRR rose by about 1 (0.029).
- **Phase 1 thresholds on v0:** Recall@10 (≥ 0.46), MRR (≥ 0.69), nDCG@10 (≥ 0.45) and Hit@10 (≥ 0.944) all pass now. MRR clears its threshold by 0.013, under one question.
- **Not a clean test.** Recall@10 was chosen as the target after the sitting's prototype was seen (S08-R1 decision 4). v0 was also used to choose the model and the pool (3 models × 3 pool sizes, ~9 setups). Part of the gain may fit v0 only; v1 is the clean test.

By question type (retrieval only; hybrid in brackets; one question moves a row by 0.10–0.14):

| Mode | Questions | Recall@10 | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| CURRENT | 10 | 0.557 (0.374) | 1.000 (0.900) | 0.588 (0.692) | 0.488 (0.385) |
| HISTORY | 10 | 0.400 (0.330) | 0.900 (0.900) | 0.577 (0.625) | 0.375 (0.346) |
| CHANGE | 9 | 0.560 (0.336) | 1.000 (1.000) | 0.944 (0.569) | 0.577 (0.314) |
| WHY | 7 | 0.564 (0.526) | 1.000 (1.000) | 0.738 (0.857) | 0.538 (0.534) |

What the runs show:

- **Every question got a different top 10.** 164 of the 430 hits (38%) were outside hybrid's top 10, i.e. from the pool's lower ranks.
  - All 3 runs retrieved the same top 10 on all 43 questions.
- **Recall@10 rose on 20 of 36 answerable questions and fell on 2:** q04 and q14 (−0.25 each, a labeled source pushed out). 14 are unchanged.
- **q31 found its first labeled source** (none → rank 1), the only Hit@10 change. Refused in every hybrid run, it was answered in every rerank run.
- **MRR is nearly flat: up on 10 questions, down on 10.**
  - CHANGE gains most (0.569 → 0.944): q03, q08, q13, q18 and q45 now have a labeled source at rank 1, from rank 2–6.
  - 6 questions lost their rank-1 source: q09, q16, q17 and q40 to rank 3–6; q12 and q30 to rank 2. q02 and q21 fell from rank 4 to 10.
  - So CURRENT MRR drops (0.692 → 0.588) despite q31, as do HISTORY and WHY.
- **Refusals:**
  - q43 in every run: no labeled source in its top 10 in any mode.
  - q14 once (run 1). Runs 2 and 3 answered it from the same hits.
  - q41, refused once in hybrid, was answered in all 3.
- **p95 latency 13.4–15.0 s, mean 14.2 s.** The reranker's retrieve time is 5.3–5.6 s at p50 and 6.6–6.9 s at p95.
  - Hybrid's runs 2 and 3 had 8.8–8.9 s; hybrid's mean (12.9 s) is lifted by run 1's 20.9 s.
  - Answer time alone (latency minus retrieve, p95): 7.0–8.8 s.
  - No question took over 16.7 s in any rerank run (hybrid's run 1: 26.2 s).
  - The model loads once per run (7.2–7.6 s), outside every question's latency.
- **Input tokens: 253,805 per run, +12,134 (+5.0%) over hybrid**, identical in all 3 runs. Output was 15,222–15,747 tokens, of which 973–1,347 were reasoning.
- **Each run took 7 min 44 s to 8 min 3 s** and cost $1.32–1.33 ($3.98 for the 3).

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
  - The same sum on this laptop: 15.0–27.1 s, mean 19.0 s. T5 measured 13.4–15.0 s, mean 14.2 s (see Rerank).
  - With T5's answer time alone (p95 7.0–8.8 s) instead of hybrid's latency: 24.2, 23.8 and 22.3 s, over the 23 s ceiling in 2 of 3 runs (mean 23.4 s).
- **Not counted:** a live `orgknow ask` also embeds the question (one Voyage call), and loads the reranker (~7.5 s) until the API keeps it loaded (S12).
- **RAM:** ~1.6 GiB for this process alone.
- **The levers (ADR-008):**
  - A bigger instance: 11 threads here give ~4.9 s.
  - The hosted Voyage `rerank-2.5` fallback: no local model, ~$0.0004 per question (not verified).
  - ONNX quantization: not measured; unquantized ONNX was no faster.

## Time and authority scores by stage

S09-R1 and S09-R2, 2026-10-10. Retrieval only, from `make eval-retrieval` in each mode: free, from the stored question vectors and, for `temporal` and `authority`, the stored routes. The paid S09 row and its improvement-rule verdict are in the next section (Authority).

| Stage | Recall@10 | MRR | Stale rate | Temporal accuracy | Authority selection | CURRENT MRR | Router accuracy |
|---|---|---|---|---|---|---|---|
| dense | 0.384 | 0.614 | 0.390 | 0.344 | 0.333 | 0.467 | n/a |
| hybrid | 0.382 | 0.675 | 0.390 | 0.333 | 0.222 | 0.692 | n/a |
| rerank | 0.516 | 0.703 | 0.380 | 0.356 | 0.556 | 0.588 | n/a |
| temporal | 0.560 | 0.759 | 0.000 | 0.522 | 0.556 | 0.637 | 0.972 |
| authority | 0.552 | 0.813 | 0.000 | 0.522 | 1.000 | 0.783 | 0.972 |

- **Stale rate** is over the 100 hits of the 10 CURRENT questions; **temporal accuracy** over the 90 hits of the 9 HISTORY questions with a golden window; **authority selection** over the 9 CURRENT questions whose labels span 2+ tiers (see Metrics).
- **`temporal` is rerank plus the route's filter** inside both searches (S09-R1 decisions 2–4). Its lines:

```
Recall@10 0.560  Hit@10 1.000  MRR 0.759  nDCG@10 0.535
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
```

- **These lines are the code's `make eval-retrieval` output.** They equal the sitting prototype's numbers (variant C), which ran the same filter as hand SQL with hand-resolved windows.
- **The router's one miss is q07** (labeled HISTORY, routed CHANGE). Both plans apply no filter, since q07 names no release, so its retrieval is unchanged (ADR-009).
- **Windows 7 of 9:** 2 HISTORY questions imply their time instead of naming it, so they get no window and no filter.
- **Temporal accuracy is 0.522, not 1.0,** because the filter keeps ±1 release and the metric checks the exact window. In the sitting, the exact window (no slack) put 82 of 90 hits in it but lowered Recall@10 to 0.541, MRR to 0.750 and nDCG@10 to 0.525 (S09-R1 decision 2).
- **The other 3 stages are unchanged** by S09-T4's iterative index scan (`hnsw.iterative_scan`, now on in every mode): their lines match S06, S07 and S08.
- **`authority` is temporal plus the weights** (S09-R2 decisions 3 and 9): the reranked pool sorted by the reranker's probability × 1.25 (sources the routed mode trusts) or × 0.8 (weak ones), then the top 10. Its lines:

```
Recall@10 0.552  Hit@10 1.000  MRR 0.813  nDCG@10 0.535
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Authority selection 1.000 (9 of 9 CURRENT questions)  CURRENT MRR 0.783
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
```

- **These equal the sitting prototype's numbers** (variant A), which weighed the saved temporal pools by hand. Against temporal: MRR 0.759 → 0.813, authority selection 5 → 9 of 9, CURRENT MRR 0.637 → 0.783, Recall@10 0.560 → 0.552; stale and in-window hits unchanged. With boost 1 and demote 1 it prints temporal's scores exactly.
- **The weights were set on v0,** so part of the gain may fit v0 only; v1 is their clean test (ADR-003).

**Router timing** (S09-T2's `make eval-routes`, all 43 golden questions, `claude-opus-5-5` at effort low; paid, once):

```
Routed 43 questions with claude-opus-5-5 (0 already stored). Route time: p50 1.71 s, p95 4.27 s. Cost $0.18.
```

- **Each live `orgknow ask` in temporal or authority mode adds one router call:** ~1.7 s at p50, ~4.3 s at p95, ~$0.004.
- **The eval's latency leaves it out:** the routes are stored, like the question vectors.

## Authority

S09-T8, 2026-10-10 and 2026-10-11 (UTC). Rerank plus both S09 stages:

- **The time filter** (`temporal`, S09-R1): the router sorts each question into CURRENT, HISTORY, CHANGE or WHY; a CURRENT question searches current text only, a dated HISTORY question texts valid in its releases ±1.
- **The authority weights** (`authority`, S09-R2): after the reranker, each text's probability × 1.25 for a source the routed mode trusts, × 0.8 for a weak one, then the best 10.
- **The mode rule** (S09-R2 decision 10), free: against temporal, authority selection rose by 0.444 (5 → 9 of 9) and no retrieval metric dropped by more than 0.03 (Recall@10 −0.0074, MRR +0.0547, nDCG@10 −0.0003, Hit@10 0; from the 4-decimal values in the S09 slice doc). So the runs used `authority`.
- First, the free gate: `make eval-retrieval` in authority and temporal modes printed the pinned lines (side table above).
- 3 runs of `RETRIEVAL_MODE=authority make eval`, 43 questions each, all `git_dirty: false`: `authority-20261010T112851Z` (commit `47c8c06`), `authority-20261011T051049Z` and `authority-20261011T051924Z` (commit `011c8b0`).
- **Run 1 ran on `47c8c06`, before resume decision R3** (the 5 review answers). Its hits equal the final code's for 43 of 43 questions (chunk ids, tiers, authority scores), and all 3 runs sent the same input tokens.
- **A second run on `47c8c06` was dropped:** the Anthropic credit ran out from q23 (21 error rows). It isn't in the table (resume decision R2).

| Measure | Authority | Spread over 3 runs | Rerank |
|---|---|---|---|
| Recall@10 | 0.552 | none | 0.516 |
| Hit@10 | 1.000 (36 of 36) | none | 0.972 (35 of 36) |
| MRR | 0.813 | none | 0.703 |
| nDCG@10 | 0.535 | none | 0.489 |
| Distinct sections | 8.3 of 10 | none | 7.4 of 10 |
| Stale rate | 0.000 (0 of 100) | none | 0.380 (38 of 100) |
| Temporal accuracy | 0.522 (47 of 90) | none | 0.356 (32 of 90) |
| Authority selection | 1.000 (9 of 9) | none | 0.556 (5 of 9) |
| CURRENT MRR | 0.783 | none | 0.588 |
| Router accuracy | 0.972 (35 of 36) | none | n/a (no router) |
| AC1 | 100% | 36 answered, all pass | 100% |
| AC2 | 100% (43 of 43) | none | 100% (43 of 43) |
| AC3 | 100% (7 of 7) | none | 100% (7 of 7) |
| False refusals | 0 of 36 | none | 1.3 of 36 (1–2) |
| p95 latency | 14.9 s | 14.5–15.3 s (runs: 15.1, 15.3, 14.5) | 14.2 s (13.4–15.0 s) |
| Retrieve p95 | 6.5 s | 6.3–6.7 s | 6.7 s (6.6–6.9 s) |
| Cost per question | $0.032 | $0.0316–0.0317 | $0.031 ($0.0307–0.0309) |
| Errors | 0 | none | 0 |

Rerank's stale, temporal, authority and CURRENT MRR values are from `make eval-retrieval` (free). It gives the same 4 retrieval metrics as rerank's paid runs, which predate these metrics; their hits weren't compared one by one.

**The improvement rule** against rerank, on the 3-run means, with the 3 S09 metrics as the targets (S09-R2, pinned T8). Changes are computed before rounding.

| Condition | Rerank | Authority | Change | Result |
|---|---|---|---|---|
| Stale rate drops by ≥ 0.03 | 0.3800 | 0.0000 | −0.3800 | Pass |
| Temporal accuracy rises by ≥ 0.03 | 0.3556 | 0.5222 | +0.1667 | Pass |
| Authority selection rises by ≥ 0.03 | 0.5556 | 1.0000 | +0.4444 | Pass |
| Recall@10 drops by ≤ 0.03 | 0.5156 | 0.5522 | +0.0366 | Pass |
| Hit@10 drops by ≤ 0.03 | 0.9722 | 1.0000 | +0.0278 | Pass |
| MRR drops by ≤ 0.03 | 0.7032 | 0.8133 | +0.1100 | Pass |
| nDCG@10 drops by ≤ 0.03 | 0.4888 | 0.5348 | +0.0460 | Pass |
| AC1, AC2, AC3 at or above rerank's range (100% in all 3 runs) | 100% | 100% in all 3 runs | 0 | Pass |
| False refusals at or below rerank's range (1–2 of 36) | 1.33 | 0 (runs: 0, 0, 0) | −1.33 | Pass |

- **Verdict: pass.** `RETRIEVAL_MODE` now defaults to `authority` (S09-R2, pinned T8).
- **Phase 1 thresholds on v0:** Recall@10 (≥ 0.46), MRR (≥ 0.69), nDCG@10 (≥ 0.45), Hit@10 (≥ 0.944), p95 latency (≤ 23 s) and cost per question (≤ $0.06) all pass. The 4 S09 thresholds come from these runs (`docs/product-spec.md`).
- **Each stage's share** (free, side table above):
  - The filter (temporal against rerank): stale 38 → 0 of 100, in-window hits 32 → 47 of 90, Recall@10 +0.044, MRR +0.055.
  - The weights (authority against temporal): authority selection 5 → 9 of 9, CURRENT MRR 0.637 → 0.783, MRR +0.055, Recall@10 −0.007.
- **Not a clean test:** the filter's slack and the weights were chosen on v0 (see Known limits). v1 is the clean test.

By question type (retrieval only; rerank in brackets; one question moves a row by 0.10–0.14):

| Mode | Questions | Recall@10 | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| CURRENT | 10 | 0.588 (0.557) | 1.000 (1.000) | 0.783 (0.588) | 0.545 (0.488) |
| HISTORY | 10 | 0.492 (0.400) | 1.000 (0.900) | 0.728 (0.577) | 0.468 (0.375) |
| CHANGE | 9 | 0.560 (0.560) | 1.000 (1.000) | 0.944 (0.944) | 0.577 (0.577) |
| WHY | 7 | 0.576 (0.564) | 1.000 (1.000) | 0.810 (0.738) | 0.561 (0.538) |

What the runs show:

- **33 of 43 questions got a different top 10 from rerank's:** 24 with different texts, 9 in a different order. 88 of the 430 hits (20%) were outside rerank's top 10.
  - All 3 runs retrieved the same top 10 on all 43 questions.
- **Recall@10 rose on 7 questions and fell on 4:**
  - q11 (−0.20), q09 and q30 (−0.17 each): a labeled source pushed out.
  - q07 (−0.125): labeled HISTORY, routed CHANGE (unfiltered), so the CHANGE weights (release notes boosted) moved it; temporal left it as rerank had it.
- **MRR rose on 9 questions and fell on 1** (q19: rank 2 → 3). q04, q16, q24, q30 and q43 now have a labeled source at rank 1.
- **CHANGE questions score as in rerank** on all 4 metrics, though 4 of 9 got a different top 10.
- **q43 found its first labeled sources** (Hit@10 0 → 1; Recall@10 0 → 0.6), through the HISTORY filter (releases 1.19–1.21; HISTORY is unweighted).
- **No refusals.** q43 (refused in all 3 rerank runs) and q14 (refused once) were answered in all 3 runs.
- **p95 latency 14.5–15.3 s, mean 14.9 s** (+0.7 s over rerank).
  - Retrieve p95 6.3–6.7 s; answer time alone (latency minus retrieve, p95): 8.7–9.1 s.
  - Run 1's slowest answer was q42 at 29.7 s. Runs 2 and 3 took 10.2–11.8 s on it, with the same hits. It is the 43rd of 43, so the p95 (the 41st) leaves it out.
  - The reranker loads once per run (7.6–8.2 s), outside every question's latency.
- **The router's time isn't in it.** The eval uses stored routes; a live ask adds one router call: p50 1.71 s, p95 4.27 s over 43 calls (S09-T2, above), ~$0.004.
  - The eval's p95 plus the router's p95: about 19.2 s, under the 23 s ceiling. Adding two p95s overstates it.
- **Input tokens: 260,127 per run, +6,322 (+2.5%) over rerank**, identical in all 3 runs. Output was 15,984–16,210 tokens, of which 634–746 were reasoning.
- **Each run took 7 min 54 s to 8 min 15 s** and cost $1.36 ($4.09 for the 3).

## Conflicts

S10-R1, 2026-10-11 (UTC). Every answer now carries `conflicts[]` (ADR-010). Retrieval is unchanged, so this section shows what the conflict step finds, not a new retrieval score. Conflict precision and recall need conflict set v0 (S10-T6, T7); the paid 3-run eval (S10-T8) is at the end of this section.

**The rule line, free.** `HF_HUB_OFFLINE=1 make eval-retrieval` in authority mode prints S09's lines exactly, plus:

```
Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date
```

- **q16–q19:** KEP-4858 claims stable (latest milestone v1.38); the 1.37 feature-gate reference says beta.
- **q32:** KEP-3299 at 1.28, found only because the claim comes from the KEP version valid at the target release.
- **Taking each hit's own version instead** gives 6 (q16 q17 q18 q19 q44 q45): KEP-3299 is missed, and q44, q45 are false (an old version claims alpha, observed stable). The sitting predicted q36 and q44; q36 appears under a different reading of "the hit's own version" (any hit's claim vs. all its hits' gates).
- **Only 36 answerable questions run,** so q20 and q48 (KEP-4858 too) aren't in the line.
- **history_date fires in hybrid mode only:** `RETRIEVAL_MODE=hybrid` gives `4 claim_mismatch (q16 q17 q18 q19), 1 history_date (q08)`, KEP-2579's "v1.23 … 2021-11-03" (released 2021-12-07, 34 days off).

**The smoke run, paid.** `conflict-smoke-20261011T083501Z`: 13 questions, 1 run, `git_dirty: true` (run before the T5 commit, on T4's commit `3b6738d` plus T5's uncommitted code).

| Measure | conflict-smoke | S09 run 3, same 13 questions |
|---|---|---|
| Hits | identical (130 of 130, by rank) | — |
| AC1, AC2, AC3 | 10/10, 13/13, 3/3 | 10/10, 13/13, 3/3 |
| False refusals | 0 of 10 | 0 of 10 |
| Conflicts | 6: 2 rule, 4 model | not recorded |
| Loser-only answers | 0 | — |
| Input / output tokens | 78,851 / 6,218 | 71,316 / 4,180 |
| Cost per question | $0.0338 | $0.0284 |
| p95 latency (the slowest of 13) | 16.3 s | 11.9 s |

The conflicts found:

| Question | Kind | Found by | Chunks (prevails in bold) | Resolution |
|---|---|---|---|---|
| q01 | contradiction | model | **7600** (release page, tier 2) vs. 33023 (KEP-1498) | lower_tier |
| q01 | contradiction | model | **7600** vs. 33441 (KEP-2572, seed) | lower_tier |
| q13 | supersession | model | 15760 (old KEP-2799) vs. **16072** (current) | valid_at_target |
| q13 | supersession | model | 15864 (older KEP-2799) vs. **16072** | valid_at_target |
| q16 | claim_mismatch | rule | 5 KEP-4858 chunks | observed_beats_claimed |
| q18 | claim_mismatch | rule | 8 KEP-4858 chunks | observed_beats_claimed |

- **The model's pairs are real disagreements:** "about three times per year" vs. "every 3 months"; KEP-2799's GA planned for 1.26, then 1.29, then 1.30.
- **Cost +$0.0054 per question (+19%):** the conflicts field and the rules in the prompt add input; listing pairs adds output (+49%).
- **Latency:** one run of 13, so its p95 is the slowest question (q01). T8's 3 runs of 43 measure it against the 23 s ceiling.

**The demo asks (live, authority mode):**

- **"When was Pod Security Admission's beta released?"** Route CHANGE, no filter. A `history_date` on `kep:2579`: "says v1.23 was released 2021-11-03; the releases table says 2021-12-07". The answer says the release date wins.
- **"How many Kubernetes minor releases are supported at the same time?"** Route CURRENT. A model `contradiction`: the version-skew page (7201, tier 2, prevails) says three, `versioning.md` (36383, tier 4) says four. The answer says three.
- **"What are the release stages of strict IP/CIDR validation (KEP-4858)?"** KEP-4858's `claim_mismatch`, as above.
- **"Is KEP-2572's three-releases-per-year cadence implemented?"** Missed: all 10 hits were KEP-2572 chunks, so there was no docs page to pair it with. The smoke run's q01 did pair KEP-2572 with the release page.

### The S10 eval (S10-T8)

2026-10-12 (UTC). 3 runs of `HF_HUB_OFFLINE=1 uv run python -m orgknow.eval run --name conflict`: the 43 golden questions plus the conflict set's c01 and c02, scored against conflict set v0 (`887201b7`: 62 conflicts, 4 seeds).

- **Precision:** flagged conflicts that match a conflict in the set ÷ flagged conflicts. **Recall:** reachable conflicts that a flag matched ÷ reachable conflicts (both sides among the question's top 10).
- **Folders:** `conflict-20261012T170000Z`, `conflict-20261012T171009Z` and `conflict-20261012T171932Z`, all on commit `10eb649` with `git_dirty: false`.
- **Each run took 9 min 31 s, 8 min 55 s and 8 min 48 s.**

**The free gate, first:** `make check` (853 passed), `HF_HUB_OFFLINE=1 make eval-retrieval` (the S09/R1 lines exactly) and `HF_HUB_OFFLINE=1 make eval-conflicts`:

```
Conflict set eval/golden_set/conflicts-v0.yaml (887201b7): 62 conflicts (4 seeds) on 45 questions (2 new). Unmatched sides: 0.
Reachable: 60 of 62 (not reachable: k03 q08; k04 c01).
Seeds retrieved: 2 of 4 (not retrieved: k03 q08; k04 c01).
Rule-found: 8 flagged (q16 q17 q18 q19 q20 q32 q48 c02); precision 1.000 (8 of 8); recall 1.000 (8 of 8 reachable).
```

- The file holds 9 rule-kind conflicts (7 `claim_mismatch`, 2 `history_date`). k03 isn't reachable, which leaves 8, as printed.

**The runs' summary lines,** as printed:

```
# Run 1: conflict-20261012T170000Z
43 questions (36 answerable), 0 errors. Recall@10 0.552, Hit@10 1.000, MRR 0.813, nDCG@10 0.535. AC1 36/36, AC2 43/43, AC3 7/7, false refusals 0/36. Tokens: 285,061 in, 24,417 out. Mean latency 12.0 s. Conflicts: 22 (8 rule, 14 model), 0 loser-only answers. Conflict precision 0.818 (18 of 22), recall 0.317 (19 of 60 reachable), AC4 2 of 4 (q08: not retrieved; c01: not retrieved).
Conflict questions: 2 (c01 c02), 0 errors, cost $0.0699.
# Run 2: conflict-20261012T171009Z
43 questions (36 answerable), 0 errors. Recall@10 0.552, Hit@10 1.000, MRR 0.813, nDCG@10 0.535. AC1 36/36, AC2 43/43, AC3 7/7, false refusals 0/36. Tokens: 285,061 in, 24,115 out. Mean latency 11.2 s. Conflicts: 22 (8 rule, 14 model), 0 loser-only answers. Conflict precision 0.864 (19 of 22), recall 0.333 (20 of 60 reachable), AC4 2 of 4 (q08: not retrieved; c01: not retrieved).
Conflict questions: 2 (c01 c02), 0 errors, cost $0.0703.
# Run 3: conflict-20261012T171932Z
43 questions (36 answerable), 0 errors. Recall@10 0.552, Hit@10 1.000, MRR 0.813, nDCG@10 0.535. AC1 36/36, AC2 43/43, AC3 7/7, false refusals 0/36. Tokens: 285,061 in, 23,966 out. Mean latency 11.0 s. Conflicts: 21 (8 rule, 13 model), 0 loser-only answers. Conflict precision 0.952 (20 of 21), recall 0.350 (21 of 60 reachable), AC4 2 of 4 (q08: not retrieved; c01: not retrieved).
Conflict questions: 2 (c01 c02), 0 errors, cost $0.0706.
```

**The row against `authority`:**

| Measure | Conflict | Spread over 3 runs | Authority |
|---|---|---|---|
| Hits | identical to `authority-20261011T051924Z`'s, by rank: 43 of 43 questions | the same in each run | — |
| Recall@10, Hit@10, MRR, nDCG@10 | 0.552, 1.000, 0.813, 0.535 | none | the same |
| AC1 | 100% (36 of 36) | none | 100% |
| AC2 | 100% (43 of 43) | none | 100% |
| AC3 | 100% (7 of 7) | none | 100% |
| False refusals | 0 of 36 | none | 0 of 36 |
| Errors | 0 | none | 0 |
| p95 latency | 16.3 s | 14.9–18.7 s (runs: 18.7, 15.3, 14.9) | 14.9 s (14.5–15.3 s) |
| Retrieve p95 | 6.9 s | 6.3–7.8 s | 6.5 s (6.3–6.7 s) |
| Cost per golden question | $0.0378 | $0.0377–0.0379 | $0.0317 |
| Cost per question, c01 and c02 included | — | $0.0376–0.0377 | — |
| Cost per run, c01 and c02 included | $5.08 for the 3 | $1.70, $1.69, $1.69 | $1.36 |
| Input tokens per run (golden) | 285,061 | identical | 260,127 |
| Output tokens per run (golden) | — | 23,966–24,417 | 15,984–16,210 |

- **Cost +$0.0061 per golden question (+19%)** and **p95 +1.4 s,** both within the Phase 1 ceilings ($0.06, 23 s). Input +24,934 tokens (+9.6%) per run; output about +50%.
- **Retrieve p95 varies though the hits don't:** it's machine time.
- **The costs with c01 and c02** come from each run's rows at the `GENERATION_PRICE_*` prices (the eval's own cost function, in a scratch script); the summary's cost is golden-only.

**Precision and recall per run:**

| Run | Flagged (rule, model) | Precision | Rule; model | Recall | Rule kinds; `texts` | Unreachable |
|---|---|---|---|---|---|---|
| 1 | 22 (8, 14) | 0.818 (18 of 22) | 8 of 8; 10 of 14 | 0.317 (19 of 60) | 8 of 8; 11 of 52 | 2 |
| 2 | 22 (8, 14) | 0.864 (19 of 22) | 8 of 8; 11 of 14 | 0.333 (20 of 60) | 8 of 8; 12 of 52 | 2 |
| 3 | 21 (8, 13) | 0.952 (20 of 21) | 8 of 8; 12 of 13 | 0.350 (21 of 60) | 8 of 8; 13 of 52 | 2 |

- **The rules are exact:** 8 of 8 in precision and recall, in every run.
- **Two-text recall is the weak part:** the model lists 13–14 pairs per run, and the set holds 52 reachable `texts` conflicts. 11 were found in all 3 runs, 2 in some (k58, k66), and 39 in none.

**AC4 per seed:**

| Seed | Question | Retrieved | Surfaced (runs 1, 2, 3) |
|---|---|---|---|
| k01: KEP-4858 claims stable, 1.37 says beta | q18 | yes | yes, yes, yes (the rule) |
| k02: KEP-2572's out-of-date status | q01 | yes | yes, yes, yes by matching; the summary check below |
| k03: KEP-2579's beta date | q08 | no | not retrieved |
| k04: `versioning.md`'s "every three months" | c01 | no | not retrieved |

- **q01's summaries, verbatim, for the developer to confirm.** The pair is the same in each run: 7600 (the release page, prevails) vs. 33441 (KEP-2572's Motivation).
  - Run 1: "The release-cycle doc says about three releases per year, while KEP-2572's motivation says Kubernetes currently releases 4 times per year."
  - Run 2: "The release-cycle doc says about three releases per year, while KEP-2572's motivation says Kubernetes currently releases 4 times per year; the tier-2 doc wins."
  - Run 3: "The release-cycle doc says about three releases per year, while KEP-2572's motivation says Kubernetes currently releases 4 times per year."
- **Claude's reading: all 3 fail the pinned summary check.** It asks for KEP-2572's out-of-date status or the cadence not being implemented, "not only its Motivation's '4 times per year'".
  - The pair matches k02 because k02's first side is the whole KEP. Its fact is k05's (4 a year vs. 3 a year), which the same pair also matches.
  - This is the R2 devil's advocate's "q01 can match on the wrong disagreement". With this reading, AC4 is 1 of 4 in each run.
- **c01's summaries:** none. No conflict was flagged on c01 in any run, since k04's sides were never both retrieved.
  - Its answers: `insufficient_evidence`, answered, `insufficient_evidence`. The answered one says "roughly one year", from KEP-1498's Motivation.

**Every unmatched flagged conflict, with Claude's verdict** (read from the stored chunk text):

| Question | Pair (prevails in bold), kind | Runs | The model's summary (first run) | Verdict |
|---|---|---|---|---|
| q18 | `gate:StrictIPCIDRValidation` 10419 (1.33–1.35) vs. **10420** (1.36–now), supersession | 1, 2 | "The older feature-gate page (1.33–1.35) lists only the alpha stage, while the newer page (valid at 1.37) adds beta, enabled by default from 1.36; the newer page is valid at 1.37 and wins." | **Real.** Alpha from 1.33 with no end vs. alpha to 1.35, then beta from 1.36: the stage changed between versions |
| q34 | `gate:KMSv2` 9930 (1.29–1.31) vs. **9931** (1.32–now), supersession | 1 | "The older feature-gate entry lists the stable stage from 1.29 with no end, while the newer entry (valid at 1.37) ends stable at 1.31 and marks the gate as removed." | **Real.** Stable with no end vs. stable to 1.31 and `removed: true` |
| q35 | the v1.28 release blog, one section: 41925 (1.28) vs. **42160** (1.36–now), supersession | 1, 2, 3 | "One version of the 1.28 blog says only the v1beta1 API group must be enabled for the beta, while the other says both the API group and the ValidatingAdmissionPolicy feature gate must be enabled; 42160 is valid at 1.37 and wins." | **Real, borderline.** What must be enabled changed: the API group vs. the API group and the gate. A reader could call it detail added, which doesn't count |
| q45 | `kep:1880`, one section: 24104 (1.24–1.26) vs. **24214** (1.28–1.30), supersession | 1, 2 | "The older KEP draft names the default object ServiceCIDRConfig and targets an alpha upgrade to 1.25, while the later shipped KEP text names it ServiceCIDR and uses a generic N+1 release." | **Not real.** The developer dropped this pair at T7 (d25, "a type renamed during design"). "1.25" → "N+1" removes a value, it doesn't change it |

- **None of the 3 labeling passes listed the 3 real ones.** They're candidates for the set's next version, which is human-owned and unchanged here.

**The agreement check:** the 3 labeling passes split 0.526 of the time (41 of 78 groups not found by all 3), above 0.20. The developer's whole question (q32) was "missing: none". So precision is provisional, and it's reported both ways:

| Run | Raw | Unmatched judged real | Judged |
|---|---|---|---|
| 1 | 0.818 (18 of 22) | 3 of 4 | 0.955 (21 of 22) |
| 2 | 0.864 (19 of 22) | 2 of 3 | 0.955 (21 of 22) |
| 3 | 0.952 (20 of 21) | 1 of 1 | 1.000 (21 of 21) |

- The precision threshold uses the judged values (product spec).
- If q35 is judged not real, judged precision is 20 of 22, 20 of 22 and 20 of 21.

**Other checks:**

- **Model pairs inside one version (decision 1):** 0 of 14, 0 of 14 and 0 of 13. The supersession pairs (8, 7, 5) all span two versions.
- **Loser-only answers:** 0 in each run.
- **q48:** `insufficient_evidence` in all 3 runs.

**ADR-010 D4:**

- **The switch rule** counts only model-found seeds that search retrieved: k02 (q01). k04 (c01) wasn't retrieved.
  - By the matching, k02 surfaced in 3 of 3 runs, and 0 answers cite only the losing side: the rule doesn't fire.
  - If the developer confirms Claude's reading of q01's summaries, k02 was missed in all 3 runs, and the rule fires: a later run adds a separate detector call.
- **The KEP-2572 fallback** (a rule for a KEP still claiming an in-progress status 2+ releases past its latest milestone) fires on the same condition: seed KEP-2572 missed in any run.
- Both wait on the developer's confirmation. Neither is built here.

**AC7's improvement rule,** against `authority` (product spec):

| Condition | Authority | Conflict | Result |
|---|---|---|---|
| Conflict recall rises by ≥ 0.03 | 0 of 60: it has no conflict step, so its rows flag nothing | 0.333 (0.317–0.350) | Pass |
| Conflict precision | n/a (no flags) | 0.878 raw (0.818–0.952); judged 0.955–1.000 | New |
| No retrieval metric drops by more than 0.03 | 0.552, 1.000, 0.813, 0.535 | identical hits, identical values | Pass |
| AC1, AC2, AC3 at or above authority's range (100%) | 100% | 100% in all 3 runs | Pass |
| False refusals at or below authority's range (0 of 36) | 0 | 0 in all 3 runs | Pass |

- **Verdict: pass.** The +conflict stage is kept.
- **A weak test:** the target metric is new, so authority's 0 holds by construction.
  - The stage's case rests on its own numbers: the rules 8 of 8, judged precision 0.955–1.000, recall 0.317–0.350, for +$0.0061 per question and +1.4 s p95.
- **AC4,** a hard gate on the finished Phase 1, is 2 of 4 by matching. Both misses are search misses (S11's corrective retrieval), and q01's summary check may make it 1 of 4.

**The void run, q48 and S10-T5c:**

- **The first run, `conflict-20261012T055648Z`, is void** (decision Q5). It's kept in history at `3872104`, and its row left the table.
  - It ran on commit `759a4db` and cost US$1.74, with AC3 6 of 7 (and AC1 37 of 37).
- **q48's miss:** unanswerable q48 ("In which Kubernetes release will StrictIPCIDRValidation graduate to GA?") was answered with "GA being targeted for Kubernetes 1.38".
  - The answer came from the KEP claim line's "(latest milestone v1.38)", a plan, not a release.
- **The fix (S10-T5c; ADR-010 D1 amended):** a KEP's latest milestone shows only when it's older than the target release, in the claim line and the rule-found summary.
- **T5c's check, paid (~US$0.29):** q48 asked 3 times before the change gave 0 of 3 `insufficient_evidence`; 3 times after gave 3 of 3. The 3 runs above add 3 of 3.

## Known limits

- **Answers aren't graded against the expected answer.** There's no grading model yet, so AC1–AC3 check structure, not correctness.
- **37 of the 43 questions were checked by Claude only.** The developer spot-checked 6.
- **Latency leaves out the question embedding, the router call and the reranker's load.** The vectors and routes are stored, so a live `orgknow ask` adds one Voyage call and, in temporal and authority modes, one router call (p95 4.27 s). It also loads the reranker (~7.5 s) on every ask, until the API keeps it loaded (S12).
- **Retrieve p95 is n/a for the dense and hybrid runs.** They ran before the retrieval step was timed (S08-T3).
  - Their p95 latency and cost were added to each `summary.json` from its `questions.jsonl` by `make eval-resummarize`, and match the numbers above.
- **The time metrics are n/a for the dense, hybrid and rerank runs.** Their hits don't record whether they're current or their release windows (S09-T3). `make eval-retrieval` scores both for any mode, free.
- **Authority selection is n/a for the same runs.** Their rows don't record label tiers or hit tiers (S09-T7). `make eval-retrieval` scores it for any mode, free.
- **The dense baseline's run 3 says `git_dirty: true`.** Its only changed tracked file was the ablation table, which run 2 had just rewritten. The code was the same commit.
  - Since S07 the dirty check ignores `eval/results/`. All 3 hybrid runs and all 3 rerank runs say `git_dirty: false`.
- **v0 isn't a clean test of hybrid, rerank or authority.** v1 is the clean test.
  - Hybrid: about 30 retrieval configurations were tried on v0 in the S07 sitting before this one was chosen, so part of the +0.060 MRR may fit v0 only.
  - Rerank: ~9 setups (3 models × 3 pool sizes) were tried on v0 in the S08 sitting, and Recall@10 was named the target after they were seen, so part of the +0.134 Recall@10 may fit v0 only.
  - Authority: the filter's ±1 release slack (against the exact window, S09-R1) and the weights (4 variants, S09-R2) were chosen on v0, so part of the S09 gains may fit v0 only.
