# ADR-011: Corrective retrieval: not adopted

- **Status:** Accepted (2026-10-12, decided in the S11-R1 design review)
- **Date:** 2026-10-12
- **Blueprint/spec refs:** blueprint §17, §19.2; product spec must-have 8, AC4, AC7; ADR-006, ADR-009, ADR-010
- **Evidence:** `eval/results/s11-sitting/` (the probe scripts, their raw outputs, and `summarize.py`, which prints every number below for free), run S11-R1. Three devil's-advocate reviews argued against the recommendations first.

## Context

- **Spec must-have 8:** bounded LangGraph corrective retrieval (≤ 3 iterations), "kept only if it measurably helps". Corrective retrieval means: grade the search results, and when they fall short, search again with a changed query before answering.
- **Little headroom on golden set v0.** Today's pipeline (authority mode with conflicts) gets Hit@10 36 of 36, AC3 7 of 7, 0 false refusals in 36, Recall@10 0.552.
- **A harder set exists:** S09's 36 blind Slack-style rewordings of v0's answerable questions (`eval/candidates/router-rewording-v0.yaml`), scored with v0's labels. An LLM read all 36 as meaning-preserving; the author spot-checked 5 (q30, q02, q03, q04, q07): all match. Search is clearly worse on them: Recall@10 0.427, Hit@10 0.944 (q08 and q31 find no labeled source), MRR 0.606.
- **A cheap grader exists:** `claude-haiku-5-5` at effort low reads a question's 10 hits for ~$0.0006, in 1.3 s at p50.

### Design-review evidence (2026-10-12)

Every probe ran on the authority-mode pipeline with v0's stored routes and vectors. "Second search" means a search with a model-written query under the same route filter.

| Probe | What it tested | Result |
|---|---|---|
| 1 | Haiku grades v0's hits: enough / retry with a query / stop (the corpus can't hold it) | 36 of 36 answerable "enough", the 12 with Recall@10 < 0.5 included; 6 of 7 unanswerable "stop"; q48 (a future-release trap) and c01 "retry". Both retries helped nothing |
| 2 | The same grader on the rephrased set | 34 of 36 "enough" (q31 with no labeled source included); the 2 retries changed nothing |
| 3 | A second search on every question; new texts scored against the original question and re-cut to 10 | v0 Recall@10 0.552 → 0.562, MRR 0.813 → 0.748; rephrased 0.427 → 0.437, MRR 0.606 → 0.571 |
| 4 | A second search on every question, ranked on its own query, then RRF with the first 10 | v0 0.552 → 0.555, MRR 0.813 → 0.819 (neutral); rephrased 0.427 → 0.468, MRR 0.607 → 0.671. One run |
| 5 | The devil's advocate's concession test: probe 4's merge with a stop / search grader, 3 runs, 4 checks fixed before the runs | Rephrased Recall@10 −0.006, +0.008, −0.007 (needed ≥ +0.03 in every run); v0 MRR −0.031 in run 3 (allowed ≥ −0.03). Fail. Haiku said "stop" on 32–33 of v0's 36 answerable questions and 24–25 of the rephrased 36 |

- **The checks that passed in probe 5:** p95 17.0–20.0 s with both searches (≤ 23 s); all 7 unanswerable questions got "stop" in all 3 runs, so q48 gained no text.
- **Probe 4's design differs from probe 5's** only by the "stop" option. Re-testing it after the fail was rejected: it would be a second try picked after seeing results, and even a pass gives an always-on stage near the 23 s ceiling.
- **Spent:** ~US$0.40 (Haiku US$0.24, router US$0.15, Voyage under US$0.01).

## Decision

### D1. No corrective step in Phase 1

- The pipeline stays route → retrieve → conflicts → answer. No grader, no second search, no new dependency (LangGraph isn't added).
- **The reason:** no grader tested could tell thin evidence from enough. Asked "enough or retry?", Haiku says "enough" even with no right source in the 10. Offered "stop", it stops on most answerable questions. The one design that gained (probe 4) searches every time, which is query rewriting, not a corrective loop. It gained in 1 run and was the best of 4 designs tried on the same set.

### D2. The rule a revisit must pass

A later attempt (a stronger grader, or query rewriting as its own stage) is kept only if **every** run of 3 passes (S11-R1 decision 5):

- the hard set's Recall@10 rises by ≥ 0.03
- no retrieval metric (Recall@10, Hit@10, MRR, nDCG@10) drops by more than 0.03 on either set
- AC1–AC3 at 100% and 0 false refusals on the golden set
- p95 ≤ 23 s, counting both searches and the grader; cost ≤ $0.06 per question

Orchestration then: LangGraph (S11-R1 decision 4), pinned exactly, imported in one file, StateGraph only, LangSmith tracing off, one graph for `ask` and the eval.

## Alternatives considered

| Option | Why not |
|---|---|
| Build the loop and measure it with 3 paid runs (~US$6) | The design review's probes already showed the grader doesn't fire on what needs fixing; the runs would most likely confirm a drop |
| A grader-gated retry (the blueprint's §17 design) | Fired on 2 of 45 v0 questions and 2 of 36 rephrased ones, and changed nothing (probes 1, 2) |
| Score a second search's texts against the original question | MRR fell 0.065 on v0 and 0.035 on the rephrased set. For rephrased q08, the second search held 4 of its 8 labeled texts, but they ranked 14–20 against the informal question (probe 3) |
| An always-on second search with RRF | The only gain (probe 4): 1 run, ~1.5 questions' worth, neutral on v0, +~5.5 s per question, and it would also run on unanswerable questions (q48's risk). Kept as a proposed addition: query rewriting for informal wording |
| A stronger grader (Sonnet 5.5 or Opus 5.5) | Not tested: 20× (Sonnet) to 40× (Opus) Haiku's price per token. A revisit trigger |
| Relax the time filter as the correction | Makes c01's seed k04 reachable, but it's one question; left to S12's AC4 plan (S11-R1 decision 6) |

## Consequences

- **Spec must-have 8 and AC7:** the ablation sequence ends at +conflict; +corrective is reported as tested and not adopted, from retrieval-only design-review probes (not a 3-run eval row).
- **AC4 loses its owner for q08 and c01:** S12's design review decides them (S11-R1 decision 6); q01 gets ADR-010 D4's fallbacks in S12 (decision 1).
- **No new dependency.** ADR-006 D3's revisit trigger ("the S11 LangGraph integration") and ADR-010's "S11's grader" note close without a change.
- **Limits of the evidence:**
  - Haiku at effort low only, one prompt per probe.
  - The labels list primary sources only (ADR-007), so a displaced hit may be relevant but unlabeled. The one read, q34's new rank 1, was noise.
  - Probes 4 and 5 reused v0's routes for the rephrased questions (the router matched 35 of 36 modes).
  - The rephrased set is spot-checked, not fully verified, by the author.
- **Revisit triggers:** golden set v1 with a verified hard set; a grader model with a measured sufficiency judgement; a faster reranker (a second search costs ~5.5 s, mostly CPU reranking).

## Amendment 2026-10-12 (S12-R1 design review)

- **The Evidence line's "prints every number below" overstates it (S12-R1 triage c).** `summarize.py` prints probes 1–5's results. 4 numbers above are computed from printed ones:
  - 0.065 and 0.035, probe 3's MRR falls: 0.813 − 0.748 and 0.606 − 0.571.
  - ~1.5 questions, probe 4's gain: (0.468 − 0.427) × 36 = 1.48.
  - ~$0.0006, the grader's cost per question: `probe_grader.log`'s total, $0.0283, ÷ 45 questions.
  - Others come from the folder's logs and README: ~5.5 s per second search (`probe_confirm.log`, `second_s`) and the spend (`README.md`).
- No decision changes. Rejected: editing line 6 in place (an accepted ADR's text stays unchanged; `docs/decisions/README.md`).
