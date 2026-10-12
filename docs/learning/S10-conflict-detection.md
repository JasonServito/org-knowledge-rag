# Slice brief: S10 Conflict detection

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → Store → Chunk → Embed → Retrieve → **Answer**, plus `Supporting: evaluation`.
- Answer now lists where its evidence disagrees, and which side wins.
- Retrieval is unchanged: the same 10 hits, in the same order, as S09.

## What was built

- **Code-found conflicts from stored facts.** A `claim_mismatch` is a KEP (a feature's design doc) claiming one stage while the release's feature-gate docs show another, e.g. KEP-4858 claims stable but 1.37 says beta. A `history_date` is a KEP's release date that is off from the releases table by more than 7 days. Both run before the answer call, free.
- **Model-found conflicts in the same answer call.** The model lists pairs of chunks whose texts disagree. Code checks the ids and labels each pair: same section → supersession (old vs. new text), else contradiction. Code also picks the winner by ADR-003 D6: observed beats claimed, then the text valid at the asked-about release, then the more trusted tier.
- **`conflicts[]` on every answer,** in `ask`'s JSON, the trace and the eval rows. The prompt names the release to settle at.
- **An answer key for conflicts (conflict set v0):** every disagreement among each eval question's 10 results. Claude drafted it in 3 independent passes, and you verified it: 62 conflicts, 4 seed cases fixed in advance. The eval scores precision, recall and AC4 per seed against it.
- **A refusal bug found and fixed:** showing a KEP's future milestone ("v1.38") let the model guess a release on an unanswerable question. The milestone now shows only when it's in the past.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Rules for stored facts, the answer model for texts | Rules only; a separate detector call | Rules can't tell ~60 cosmetic edits from real ones; a second call costs +$0.022 per question | +$0.0061 per question, +1.4 s p95 |
| Code resolves every conflict by ADR-003 D6 | Let the model decide | Deterministic and testable; the prompt states the same rule | The model's prose can still differ; the settle line aligns them |
| Answer key = every disagreement in each question's fixed 10 results, labeled before the runs | Only the 4 seeds | Precision and recall need a denominator; seeds alone give 4 data points | 3 labeling passes and your review; split rate 0.526 |
| AC4 end to end on blind seeds; a miss in search reports "not retrieved" | Pick seed questions that retrieve the evidence | Picking by results hides search misses; those are S11's target | AC4 2 of 4 today |
| Match by kind: a rule label only by its rule, a two-text label only by a pair hitting both sides | Any flag on the right documents | A flag can't get credit for a different kind of disagreement | Still fooled when one document holds 2 facts (q01) |
| Hide a KEP's future milestone (ADR-010 D1 amended) | Mark it "planned"; a prompt rule against using it | The model already called it "a planned target" and still answered; hiding it is deterministic | Hides a true plan; voided 1 run (US$1.74) |
| Thresholds: worst of 3 runs minus one conflict | A fixed number | S09-R2's rule; leaves room for run-to-run noise | Precision ≥ 0.90 (judged), recall ≥ 0.30 |

## Likely interview questions

1. **Q: How does your system handle sources that disagree?**
   - Code checks stored facts (a KEP's claim vs. the observed stage), and the answer model flags text pairs in the same call; code then resolves each by a fixed authority rule.
   - Every answer carries the list, so a user sees the disagreement, not just a winner.
2. **Q: How do you know the conflict detector works?**
   - An answer key labeled before any paid run, over search results proven identical across runs (43 of 43).
   - Rules: 8 of 8 precision and recall. The model: judged precision 0.955–1.000, but recall only 0.32–0.35.
3. **Q: Why is recall so low, and what would you do about it?**
   - The model lists 13–14 pairs per run out of 52 two-text conflicts; it flags the salient ones only.
   - ADR-010 D4 names the fallback: a separate detector call, if seeds that search retrieves are missed.
4. **Q: Can adding context to a prompt make answers worse?**
   - Yes: showing a KEP's future milestone turned a refusal into a guess on q48 (AC3 6 of 7). The full run's hard gate caught it.
   - The fix shows only past milestones; q48 went from 0 of 3 refusals to 3 of 3.
5. **Q: How reliable is your answer key?**
   - The 3 labeling passes disagreed on 0.526 of items, so precision is reported raw and judged.
   - Each unmatched flag got a verdict from the stored text; 3 real conflicts were missing from the key.

## Numbers to remember

- **Conflict precision:** 0.818–0.952 raw, 0.955–1.000 judged. **Recall:** 0.317–0.350 (rules 8 of 8; two-text 11–13 of 52).
- **AC4:** 2 of 4 (q08 and c01 not retrieved); 1 of 4 if q01's summaries fail.
- **Answers:** AC1–AC3 100% and false refusals 0 of 36 in all 3 runs; hits identical to authority's.
- **Cost and speed:** $0.0378 per question (+19%); p95 16.3 s (+1.4 s); both under $0.06 and 23 s.
- **Conflict set v0:** 62 conflicts, 4 seeds, 45 questions; labeling split rate 0.526.
- **q48:** refused 0 of 3 before the milestone fix, 3 of 3 after, and in all 3 runs.
- **Paid in S10:** about US$7.7.
