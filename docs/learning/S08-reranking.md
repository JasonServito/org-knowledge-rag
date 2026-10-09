# Slice brief: S08 Reranking

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → Store → Chunk → Embed → **Retrieve** → Answer, plus `Supporting: evaluation` (p95 latency and cost in every eval row). Retrieve gained a third stage after the two searches and the merge.

## What was built

- **A second, slower reader of hybrid's candidates.**
  - Hybrid's 20 meaning-search and 20 word-search candidates merge into about 21 texts.
  - A cross-encoder (a model that reads the question and one text side by side and scores the pair) scores each one, and the 10 best go to the answer step.
  - The model is `BAAI/bge-reranker-base` (278M parameters), run locally on the CPU with PyTorch.
- **A small interface around the model:** question and texts in, one score per text out. Tests use a fake that needs no 1.1 GB download, and a hosted reranker could replace it later.
- **Rerank passed the improvement rule, so it is the default.** Recall@10 (share of labeled sources in the top 10) went from 0.382 to 0.516. No other measure fell, and p95 latency stayed under 23 s.
- **Every eval row now shows speed and cost.** p95 latency (95% of questions finish faster), retrieve-only p95 and cost per question, refilled for the 6 old runs too.
- **A server-sizing note for S15:** the reranker takes 4.9 s per question on the laptop's 11 cores and 11.5 s pinned to 2 CPUs.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| `bge-reranker-base`, pinned revision | `bge-reranker-v2-m3`; `ms-marco-MiniLM-L-6-v2`; hosted Voyage `rerank-2.5` | Best of 3 on all 4 metrics at pool 20; 3.3× faster than v2-m3; MiniLM failed MRR (0.621) | 1.1 GB of weights; 278M parameters on CPU |
| `transformers` + CPU-only `torch`, from PyTorch's CPU index | ONNX Runtime; `sentence-transformers` | The measured stack, so the gate reproduces the prototype; ONNX was no faster and its scores differ by up to 0.29 | ~740 MB installed; CI `check` 33 s → 91 s; no Intel Macs |
| Rerank hybrid's whole pool (~21 texts), keep 10, cut texts at 512 tokens | Pools of 30 or 40; rerank only the top 10 | Pool 20 had the best MRR and Hit@10, at half pool 40's time; the top 10 alone can't change Recall@10 | 25% of (question, text) pairs lose their tail |
| Sort by the score rounded to 4 decimals; ties keep hybrid's order | Raw scores | Near-ties (~1e-5 apart) don't reorder between runs; same 4 metrics | A 4-decimal rule to explain |
| Recall@10 as the target metric; default only if the rule passes and mean p95 ≤ 23 s | MRR; nDCG@10 | Lifting good texts from ranks 11–21 is a reranker's job, and Recall was the bigger gap | Chosen after seeing the prototype, which the docs say |
| p95, retrieve p95 and cost in every summary; refill the 6 old runs | Compute them by hand per write-up | Comparable rows in one table, with no hand math | 3 optional fields; old dense rows needed 3 fields made optional |

## Likely interview questions

1. **Q: Why rerank at all, instead of a better embedding model?**
   - An embedding (bi-encoder) compresses each text alone, before the question exists; a cross-encoder reads both together, so it's more accurate but too slow for 21,552 texts.
   - So: cheap search for about 21 candidates, then a precise reader over them. Here, +0.134 Recall@10 for about 5 s per question on CPU.
2. **Q: Recall rose a lot, but MRR barely moved. Why?**
   - The model lifts good texts from ranks 11–21 into the top 10, but reorders the top few both ways: MRR rose on 10 questions and fell on 10.
   - CHANGE questions gained (MRR 0.569 → 0.944); CURRENT, HISTORY and WHY lost. Losses are often CHANGELOG copies that v0 leaves unlabeled.
3. **Q: How do you know the reranker is wired correctly?**
   - A fake model with hand-set scores checks the order rules: the best score at position 15 of 20 moves to first, and near-ties keep hybrid's order.
   - On real data, the free retrieval score matched a separate prototype to 3 decimals before any paid run.
4. **Q: Can this run on a small server?**
   - On 2 CPUs the reranker takes 11.5 s per question at p50, and the projected answer p95 is 22.3–24.2 s, over the 23 s ceiling in 2 of 3 runs.
   - The levers: a bigger instance, the hosted Voyage reranker, or a quantized model. S15 decides.
5. **Q: Isn't the 0.516 tuned to your test set?**
   - Yes, partly: the golden set v0 chose the model and pool (~9 setups), and Recall@10 was picked as the target after the prototype.
   - The docs say so, and golden set v1 is the clean test.

## Numbers to remember

- **Rerank vs hybrid:** Recall@10 0.516 vs 0.382 (+0.134); Hit@10 0.972 vs 0.944; MRR 0.703 vs 0.675; nDCG@10 0.489 vs 0.385.
- **Phase 1 targets on v0:** Recall@10 ≥ 0.46 and MRR ≥ 0.69 both met; MRR by 0.013, under one question.
- **Answers:** AC1–AC3 100%; false refusals 1.3 of 36 (hybrid 2.3).
- **Who moved:** every top 10 changed; 164 of 430 hits came from ranks 11–21. Recall@10 rose on 20 questions and fell on 2.
- **Speed:** p95 14.2 s (13.4–15.0; hybrid 12.9 s); retrieve p95 6.7 s.
- **Model timing:** p50 4.9 s on 11 threads, 11.5 s on 2 CPUs; load 7.4–8.2 s (about 4.2 s of it is imports); peak RAM 1.6 GiB.
- **Cost:** $0.031 per question (hybrid $0.030); input tokens +5.0%. The reranker itself costs $0.
- **Paid in S08:** 130 Anthropic calls ($3.98 for the 3 runs), 1 Voyage request.
- **Tests:** 506 unit and 126 integration (from 478 and 120). The PR had about 1,314 reviewable lines (estimate about 1,000).
