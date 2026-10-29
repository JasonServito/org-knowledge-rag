# ADR-008: Reranker model, runtime and candidate count

- **Status:** Accepted (2026-10-09, decided in the S08-R1 design review)
- **Date:** 2026-10-09
- **Blueprint/spec refs:** blueprint "Reranking: add local BGE cross-encoder; re-evaluate"; product spec must-have 3, AC7, p95 threshold; ADR-004 (dependencies)

## Context

- **Hybrid retrieval (S07) ranks by position only.** RRF merges where dense and lexical search put each text. Nothing reads the question and a text together. A cross-encoder does: it scores each (question, text) pair.
- **Hybrid's numbers** on golden set v0 (36 answerable questions): Recall@10 0.382, Hit@10 0.944, MRR 0.675, nDCG@10 0.385. The Phase 1 targets are Recall@10 ≥ 0.46 and MRR ≥ 0.69. The p95 ceiling is 23 s (retrieve + answer).
- **Hybrid's pool.** With 20 candidates per list, dense + lexical fuse to 20.9 texts on average, because lexical AND-matching finds nothing for 23 of 36 questions. A perfect reader of that pool would reach Recall@10 0.613. At 40 per list the pool is 40.6 texts, with a ceiling of 0.792.
- **Hardware.** The dev machine is a laptop: Intel Core Ultra 7 155H under WSL2, 22 logical CPUs (11 cores), 15 GB RAM, no GPU. S15's budget (≤ $50/month in total) suggests about 2 vCPUs.
- **Chunk lengths.** 21,552 distinct chunk texts: mean 1,049 characters, p95 2,153, max 62,939. 25% of (question, text) pairs exceed 512 XLM-R tokens.

### Design review prototype (2026-10-09, scratch venv, not committed)

Setup:
- Rerank hybrid's whole fused pool by cross-encoder score and keep the top 10.
- Scored with the project's own `score_retrieval`.
- Batches of 8 texts sorted by length, max 512 tokens, 11 threads.

| Model (size) | Pool | Recall@10 | Hit@10 | MRR | nDCG@10 | Rerank time per question |
|---|---|---|---|---|---|---|
| none (hybrid) | — | 0.382 | 0.944 | 0.675 | 0.385 | — |
| ms-marco-MiniLM-L-6-v2 (22M) | 20 | 0.461 | 0.972 | 0.621 | 0.420 | 0.8 s p50 |
| **bge-reranker-base (278M)** | **20** | **0.516** | **0.972** | **0.703** | **0.489** | **4.2 s p50 (~5.4 p95)** |
| bge-reranker-base | 30 | 0.521 | 0.944 | 0.662 | 0.482 | — |
| bge-reranker-base | 40 | 0.522 | 0.944 | 0.634 | 0.473 | 8.1 s p50, 10.1 p95 |
| bge-reranker-v2-m3 (568M) | 20 | 0.495 | 0.944 | 0.655 | 0.469 | 13.9 s p50 |
| bge-reranker-v2-m3 | 40 | 0.510 | 0.944 | 0.606 | 0.461 | 28.4 s p50, 36.5 p95 |

- **2 CPUs** (`taskset`, 2 threads), bge-reranker-base, pool 20, 12 questions: 10.0 s p50, 15.0 s max. This is the same for 1 core with 2 hyperthreads, for 2 cores, and for ONNX Runtime.
- **ONNX Runtime with BAAI's own export:**
  - Same top 10 on 43/43 questions and the same 4 metrics.
  - Not faster: 4.8 s p50 at 11 threads.
  - Scores differ from PyTorch's by up to 0.29, on short texts, for an unexplained reason.
- **Repeatability:**
  - Scores agree between runs to ~1e-5.
  - A rerun swapped near-tied texts on 2 of 43 questions, with identical metrics.
  - Batch size 1 vs. 8: the top 10 was the same on 43/43 questions.
- **Model load (cold disk):** base 26 s, v2-m3 42 s; base 3 s warm.
- **What changed (base, pool 20):**
  - MRR rose on 10 questions and fell on 10. Recall rose on 20 and fell on 2.
  - Wins are often exact pages (feature-gate pages to rank 1).
  - Losses are often CHANGELOG pre-release sections, which v0 leaves unlabeled (the "any of" label limit).
- **Tuning caveat.** About 9 setups were tried here, plus ~30 in S07, all on the same 36 questions. v0 is not a clean test of the chosen setup; v1 is.

## Decision

### D1. `BAAI/bge-reranker-base`, pinned to revision `2cfc18c9415c912f9d8155881c133215df768a70`

- The best measured model on every metric at pool 20, and 3.3× faster than v2-m3. License: MIT.
- Its gain is **Recall@10 (+0.134) and nDCG@10 (+0.104). MRR is about flat** (+0.028, 10 questions up and 10 down), and it clears the MRR target by 0.013, less than one question.
- v2-m3 is rejected on speed (3.3× slower). Its quality difference here is under one question, and it was capped at 512 tokens.
- The model name and revision are settings (`RERANK_MODEL`, `RERANK_REVISION`). Weights are loaded from safetensors only.

### D2. `transformers` + CPU-only `torch`, behind a small `Reranker` interface

- About 15 lines: tokenizer + `AutoModelForSequenceClassification`, the stack the prototype measured, so the gate reproduces its numbers.
- `torch` comes from the PyTorch CPU package index, pinned in `pyproject.toml`. Without it, uv installs ~2–3 GB of CUDA libraries. With it, torch is ~740 MB installed.
- **The interface:** question + texts in, one score per text out. It gives unit tests a fake (no 1.1 GB download in CI) and keeps a hosted reranker swappable.
- **Threads:** torch's default, the number of physical cores, which follows the CPU affinity (2 under a 2-CPU `taskset`). 22 threads was 4–9× slower than 11 in the design review.

### D3. 20 candidates per list (~21 texts); rerank the whole pool; keep 10; 512 tokens

- **Candidates:** the reranker reads every text hybrid fuses from 20 dense + 20 lexical candidates (`RETRIEVAL_CANDIDATES`, unchanged), then keeps `RETRIEVAL_TOP_K` (10) by score.
- **Ordering:** the score is rounded to 4 decimals, then ties keep hybrid order, so near-ties don't reorder between runs.
- **Length:** texts longer than 512 tokens are cut (`RERANK_MAX_LENGTH`), keeping the start, which holds the header.
- **Batching:** batches of 8 (`RERANK_BATCH_SIZE`), sorted by length.
- **Rejected sizes:**
  - Pools 30 and 40 raised Recall by ≤ 0.006, lowered MRR by 0.04–0.07, and doubled the time.
  - Reranking only the top 10 can't change Recall@10.
- **Recheck the pool size on golden set v1:** the MRR loss at larger pools may come from v0's unlabeled CHANGELOG copies, not the model.

## Alternatives considered

| Option | Why not |
|---|---|
| `bge-reranker-v2-m3` | Worse here at every pool size (Recall 0.495, MRR 0.655 at pool 20), and 14–28 s per question on this CPU |
| `ms-marco-MiniLM-L-6-v2` | 5× faster, but MRR falls to 0.621 (fails the improvement rule) |
| Voyage `rerank-2.5` (hosted) | No torch, reads 32K tokens, ~$0.0004 per question (aggregator prices, not verified), and reuses the Voyage client. But it's paid and needs the network on every eval, can change behind the API, and isn't the blueprint's local model. **Kept as the fallback** if S15's server can't run the model fast enough. The author skipped the $0.02 test |
| ONNX Runtime + `tokenizers` | ~63 MB vs ~740 MB installed, same order on 43/43, same speed. Rejected: scores differ by up to 0.29 for an unexplained reason, more code (tokenizer setup, arrays), and the gate would need its own numbers. Switching later costs about one task |
| `sentence-transformers` `CrossEncoder` | ~3 lines, but one more dependency on top of the same `transformers` + `torch` |

A devil's advocate argued against D1–D3. Its tests were run in the design review: 2-CPU timing, and ONNX speed and score agreement. None changed a decision. Its framing of D1 ("Recall and nDCG gain; MRR flat") is used above.

## Consequences

- **New runtime dependencies (ADR-004 amendment 2026-10-09):** `torch` (CPU index) and `transformers`. The model weights (1.1 GB) live in the Hugging Face cache, outside the repo. CI never downloads them: the real-model test is skipped when the model isn't cached.
- **Latency:**
  - About +4 s per question on the laptop (11 threads), and about +10 s on 2 CPUs.
  - Projected eval p95 from hybrid's runs: 25.3, 13.3 and 13.0 s (mean ~17 s vs. the 23 s ceiling).
  - Each `orgknow ask` loads the model (3–26 s) until the API keeps it loaded (S12).
- **S15 sizing:** 2 vCPUs keep rerank alone at 10–15 s per question. A bigger instance, the Voyage fallback, or ONNX quantization are the levers.
- **The improvement rule's target for this stage is Recall@10** (S08-R1 decision 4). It was chosen after seeing the prototype; `docs/evaluation.md` says so.
- **Revisit triggers:** golden set v1 (pool size, model); the S15 instance choice (runtime, hosted fallback); a reranker that reads past 512 tokens if truncation shows up in misses.
