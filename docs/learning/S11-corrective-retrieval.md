# Slice brief: S11 Corrective agentic retrieval

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → Store → Chunk → Embed → **Retrieve** → Answer, plus `Supporting: evaluation`.
- The step tested sat between Retrieve and Answer. It was not adopted, so the pipeline is unchanged: route → retrieve → conflicts → answer.
- No code changed in S11. The slice's output is a measured "no", its evidence, and a rule a later attempt must pass.

## What was built

- **A measured negative result (ADR-011).** Corrective retrieval: a grader model reads a question's 10 search results and, when they fall short, a second search runs with a model-written query. 5 probes found no grader that tells thin evidence from enough.
- **A harder test set.** S09's 36 Slack-style rewordings of v0's answerable questions, scored with v0's labels. Search is worse on them (Recall@10 0.427 vs. 0.552), so a corrective step has something to fix.
- **A keep rule fixed before the test (ADR-011 D2).** A later attempt is kept only if every one of 3 runs passes 4 checks: the rephrased set's Recall@10 up ≥ 0.03, no retrieval metric down more than 0.03 on either set, answers intact, speed and cost under the ceilings.
- **Evidence that re-prints for free.** The probe scripts and raw outputs are committed; one script re-prints every number of probes 1–5 from the saved outputs, with no paid call.
- **Owners for AC4's open seeds (S12).** q01 gets ADR-010 D4's fallbacks; q08 and c01 go to S12's sitting, with a lead: c01's source is found when its 1.30 window is dropped.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| No corrective step in Phase 1 (ADR-011 D1) | Build the loop and measure it with 3 paid runs | The probes showed the grader doesn't fire on what needs fixing | ~US$0.40 of probes instead of ~US$6 of runs; no +corrective ablation row |
| Test on v0 plus the rephrased set, after a probe (decision 2) | v0 only; stop S11 at once | On v0 the loop has almost nothing to fix: Hit@10 is 1.000 | The rephrased set is spot-checked (5 of 36), not verified |
| Close S11 after probe 5 failed (decision 3) | Build the RRF second search anyway; re-test it without "stop" | The rule fixed before the test says close; a re-test after a fail is picked after seeing results | Probe 4's gain becomes a proposed addition (query rewriting), untested |
| Keep rule: every run of 3 must pass (decision 5) | Pass on the 3-run mean | Once a model writes the queries, retrieval varies from run to run | A real but noisy gain can fail on one run |
| LangGraph for a future loop, with guardrails (decision 4) | A plain function | The developer's choice (résumé value) | Moot: nothing built; the spike took 82 lines vs. 30 |
| Don't test a stronger grader (ADR-011) | Sonnet 5.5 or Opus 5.5 as the grader | 20× (Sonnet) to 40× (Opus) Haiku's price per token | Left as a revisit trigger |
| AC4's q01 fallbacks are an early S12 task; q08 and c01 go to S12's sitting (decisions 1, 6) | Fallbacks inside S11's eval; change AC4 now | One change per ablation row; decide with q01's result in hand | AC4 stays at 1 of 4 until S12 |

## Likely interview questions

1. **Q: Did you build an agentic, corrective RAG loop? Why not?**
   - I probed it first for ~US$0.40: Haiku said "enough" on all 12 hard v0 questions (Recall@10 < 0.5).
   - Offered "stop", it stopped on 32–33 of v0's 36 answerable questions. No grader tested could tell thin evidence from enough.
2. **Q: How did you avoid fooling yourself with a lucky result?**
   - The keep rule was fixed before the test: every run of 3 must pass. Probe 5's recall change was −0.006, +0.008, −0.007 against a ≥ +0.03 target.
   - Probe 4's gain was 1 run and the best of 4 designs on the same set; re-testing it after the fail was rejected.
3. **Q: Why did one second-search design hurt ranking and another help?**
   - Scoring the new texts against the informal question undid the rewrite: rephrased q08's 4 found labels ranked 14–20 (probe 3: rephrased MRR 0.606 → 0.571).
   - Ranking the second search on its own query, then fusing with RRF, kept both views (probe 4: rephrased MRR 0.607 → 0.671).
4. **Q: What do you do when your test set is too easy for the feature?**
   - v0 already finds a labeled source for every answerable question, so I used S09's 36 blind rewordings, scored with v0's labels.
   - Search is worse on them (Recall@10 0.427, q08 and q31 find no labeled source); the developer spot-checked 5, Claude read all 36.
5. **Q: Why LangGraph rather than a plain loop?** (follow-up)
   - The spike: the same flow took 82 lines with LangGraph and 30 as a plain loop, and the LangGraph version needs 1 type cast to pass mypy --strict (not in the committed spike).
   - Picked for a future attempt with guardrails: pinned, imported in one file, StateGraph only. Nothing is built now.

## Numbers to remember

- **v0, authority mode:** Recall@10 0.552, Hit@10 1.000, MRR 0.813.
- **The rephrased set's first search:** Recall@10 0.427, Hit@10 0.944, MRR 0.606 (probe 2; 0.607 in probes 4–5, with v0's routes).
- **The grader (probe 1):** 36 of 36 answerable "enough", the 12 with Recall@10 < 0.5 included; p50 1.34 s, p95 2.35 s.
- **Probe 3 (texts scored against the original question):** MRR 0.813 → 0.748 on v0, 0.606 → 0.571 on the rephrased set.
- **Probe 4 (RRF, 1 run):** rephrased Recall@10 0.427 → 0.468, MRR 0.607 → 0.671; v0 0.552 → 0.555 (neutral).
- **Probe 5 (probe 4's design; its prompt adds only a "stop" option; 3 runs):** rephrased Recall@10 −0.006, +0.008, −0.007 (needed ≥ +0.03); v0 MRR −0.031 in run 3. Fail.
- **Probe 5's "stop":** 32–33 of v0's 36 answerable questions, 24–25 of the rephrased 36; p95 17.0–20.0 s (≤ 23 s).
- **A second search:** ~5.5 s more per question, mostly CPU reranking.
- **AC4:** 1 of 4 until S12.
- **Paid in S11:** ~US$0.40 (Haiku US$0.24, router US$0.15, Voyage under US$0.01), all in the sitting.
