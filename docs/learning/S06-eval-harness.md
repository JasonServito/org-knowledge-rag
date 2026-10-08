# Slice brief: S06 Eval harness + golden set v0 + dense baseline

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → Store → Chunk → Embed → **Retrieve** → **Answer**. This is `Supporting: evaluation`: S06 measures these two stages and changes neither.

## What was built

- **A golden set**, the fixed question list every later stage is scored on:
  - 43 questions: 36 answerable and 7 unanswerable.
  - 184 labels. Each label names a document and a section (its heading path), never a chunk id, so labels survive re-chunking (ADR-007).
  - 3 independent Claude passes checked every question, and the developer spot-checked 6. The set is frozen.
- **One command scores the whole pipeline.** `make eval` works in 4 steps:
  1. It checks every label against the database before any paid call.
  2. It retrieves the top 10 for each question and asks Claude once per question.
  3. It scores retrieval with **Recall@10** (share of a question's labeled sources found), **Hit@10** (any found), **MRR** (how high the first one ranks) and **nDCG@10** (found, weighted by rank). It checks the answer with AC1–AC3: citations present, none invented, "insufficient evidence" when the question is unanswerable.
  4. It writes one results folder and rebuilds the ablation table.
- **Retrieval repeats exactly.** Each question's vector is stored in a committed file. The 3 baseline runs retrieved identical hits, so only the answer model varies.
- **The dense baseline row is committed:**
  - Recall@10 0.384, Hit@10 0.944, MRR 0.614, nDCG@10 0.369
  - AC1–AC3 at 100%
  - $0.029 per question
  - This is the row every later stage (S07 lexical search, S08 reranking, …) must beat.
- **The Phase 1 bar is written down.**
  - A stage counts as an improvement at ≥ +0.03 (one question is 0.028).
  - The finished system targets the baseline + 0.08.
  - Latency and cost may at most double.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Labels = document + heading-path prefix (ADR-007 D2) | Chunk-id labels | Survive re-chunking; one label covers every version and packed piece | A label can't say which version is right (that's AC6, S09) |
| Each label credited once, relevance yes/no (ADR-007 D3) | Every matching hit counts; graded labels | Near-duplicates can't inflate scores: 7.1 distinct sections per 10 hits | Recall reads as coverage of the primary sources |
| Label only the primary sources ("A-primary") | Label every copy; 1 source per fact | Recall isn't swamped by duplicates, and good hits still score | Equally good copies score 0 → v1 "any of" groups (proposed) |
| Claude verifies all 43; the developer spot-checks 6 | The developer reviews all 43 | 3 independent passes, plus a human-checked sample to quote | 37 questions have no human check |
| Question vectors stored in a committed file | Embed every run; a DB table | Retrieval is exactly repeatable, and costs 0 Voyage requests after the first run | A new embedding model needs new vectors |
| 3 runs, shown as mean and (min–max) | 1 run | The answer side varies: q41 flipped, false refusals 2–3 | $1.27 per extra run |
| Answer model frozen: Opus 5.5 at medium effort (ADR-006 amendment) | Sonnet 5.5 | Measured $0.029 per question; better at "insufficient evidence" | About 2× Sonnet's price per question |
| Improvement = ≥ +0.03, nothing else drops > 0.03 | Any increase; a paired statistical test | One question = 0.028; 36 questions are too few for a test | A judgment call; ignores *which* questions moved |
| Phase 1 targets = baseline + 0.08 | Floors only; a hand-picked number per metric | One rule, about 3 questions' worth | Hybrid search and reranking gains here are unknown |
| Ceilings = 2× baseline: p95 ≤ 23 s, ≤ $0.06 per question | 15 s and $0.04; no ceiling | Leaves room for a CPU reranker and one retry | The 2× multiplier is a judgment call |

## Likely interview questions

1. **Q: How do you know a retrieval change helped, and isn't noise?**
   - Retrieval is exactly repeatable (stored question vectors), so the only noise is which 36 questions are in the set. One question is 0.028, so the rule is ≥ +0.03 with nothing else dropping more than 0.03.
   - Follow-up, "why not a significance test?": 36 questions only detect big effects. A paired test comes in once a set passes ~100.
2. **Q: Why label by section instead of by chunk id?**
   - Chunks change when the chunker changes. A document plus a heading path survives that, and one label covers every version of the section.
   - Each label is credited once, so 3 copies of one section in the top 10 count once.
3. **Q: Recall@10 is 0.384 but Hit@10 is 0.944. What does that mean?**
   - 34 of 36 questions got at least one primary source in the top 10. But on average only 38% of a question's ~5 labeled sources made it.
   - About 3 of 10 slots repeat a section, either an older version or another piece of a long section. That's S09's crowding problem.
4. **Q: How do you evaluate the answers, not just retrieval?**
   - AC1–AC3 check structure: every citation resolves to a stored chunk, none was invented (checked against the retrieved ids), and unanswerable questions get "insufficient evidence". False refusals are counted.
   - Limit: there's no correctness grading against the expected answer yet. Faithfulness needs a grading model.
5. **Q: How did you build a golden set without days of labeling?**
   - Claude drafted it from the database, and 3 independent Claude passes checked each question against the stored text. The developer spot-checked 1 per class plus 1 random.
   - Every label is checked against the database before a run: 184 labels, 0 unmatched.

## Numbers to remember

- **Golden set v0:** 43 questions.
  - 36 answerable: 10 CURRENT, 10 HISTORY, 9 CHANGE, 7 WHY.
  - 7 unanswerable; 13 smoke.
  - 184 labels, about 5.1 per answerable question.
- **Dense baseline:** Recall@10 0.384, Hit@10 0.944, MRR 0.614, nDCG@10 0.369. Identical in all 3 runs.
- **Answer checks:** AC1 100%, AC2 100%, AC3 7 of 7. False refusals: 2–3 of 36 (q31 and q43 every run; neither had a labeled source in its top 10).
- **By question type:** CURRENT ranks worst (MRR 0.467); WHY ranks best (0.905).
- **Cost and speed:** $0.029 per question; $1.26–1.27 per 43-question run; p95 latency 9.4–11.3 s; about 4 minutes per run.
- **Phase 1 targets:** Recall@10 ≥ 0.46, MRR ≥ 0.69, nDCG@10 ≥ 0.45, Hit@10 ≥ 0.944; p95 ≤ 23 s; ≤ $0.06 per question.
- **Paid in S06:**
  - Anthropic: 9 demo asks in S06-R1, then 142 asks ($4.14) in S06-T6.
  - Voyage: 2 requests (3 + 40 question vectors).
- **Tests:** 453 unit and 106 integration (from 390 and 93).
- **PRs:** S06-R1 had 2,895 reviewable lines, about 2× its 1,400 estimate (tests were 1,609 of them). S06-T5 added 5 files.
