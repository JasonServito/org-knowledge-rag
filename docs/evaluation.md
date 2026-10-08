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
| **p95 latency** | 95th percentile (nearest rank) of a question's retrieve + answer time | The slow-question experience |
| **Cost per question** | Input tokens × $4/M + output tokens × $20/M (ADR-006 D1 prices; output includes reasoning) | What one answer costs |

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
| p95 latency | 10.6 s | 9.4–11.3 s |
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
  - q41 was answered, refused, then answered.
- **About 3 of 10 slots repeat a section**: another version of it, or another packed piece of a long one.
- **CURRENT questions rank worst:** MRR 0.467, against 0.905 for WHY.
- **Same prompt every run.** Input tokens were identical in all 3 runs (232,992), because the hits were. Output was 16,484–16,975 tokens, of which 1,388–1,548 were reasoning.
- **Each run took 3 min 38 s to 4 min 50 s** and cost $1.26–1.27.

## Known limits

- **Answers aren't graded against the expected answer.** There's no grading model yet, so AC1–AC3 check structure, not correctness.
- **37 of the 43 questions were checked by Claude only.** The developer spot-checked 6.
- **Latency leaves out the question embedding.** The vectors are stored, so a live `orgknow ask` adds one Voyage call.
- **The summary and table don't report p95 latency or cost yet.** The numbers above were computed from each run's `questions.jsonl`.
- **Run 3's `run.json` says `git_dirty: true`.** Its only changed tracked file was the ablation table, which run 2 had just rewritten. The code was the same commit.
