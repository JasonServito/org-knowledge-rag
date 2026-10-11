# Slice brief: S09 Temporal and authority-aware retrieval

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → **Store** → Chunk → Embed → **Retrieve** → **Answer**, plus `Supporting: evaluation`.
- Retrieve gained a question router, time filters and trust weights.
- Store gained the gate-stage table.
- Answer now shows each source's trust tier and a KEP's stage.

## What was built

- **A question router.** One Claude call (Opus 5.5, effort low) sorts each question into CURRENT ("now"), HISTORY ("back then"), CHANGE or WHY. It also extracts the time the question names ("before 1.28", "in 2022"). Code then turns that time into a release window using the release-dates table. It got 35 of 36 v0 questions right.
- **Time filters inside both searches (`temporal` mode).**
  - "Now" questions drop text that a later edit replaced: stale hits went from 38 to 0 of 100.
  - Dated "back then" questions keep text valid within the window ±1 release: in-window hits went from 32 to 47 of 90.
- **Each feature gate's stage at each release.** A feature gate is a feature's on/off switch, with a stage. The stage is read from that release's own docs: 3,295 rows over 1.20–1.37. This lets a KEP's claimed stage be checked against what shipped (a KEP is a Kubernetes Enhancement Proposal, a design doc).
- **A trust tier on every result,** shown in the prompt and in the citations. Docs pages are tier 1 and blogs tier 6; a KEP is 3 if shipped, else 5.
- **An `authority` mode** that nudges trusted sources up after the reranker, multiplying its probability by 1.25 or 0.8. The most trusted correct source now comes first for 9 of 9 "now" questions (rerank: 5 of 9).
- **4 new eval measures,** printed in every mode they apply to:
  - stale-result rate
  - temporal accuracy
  - router accuracy
  - authority-selection accuracy, with "now"-question MRR beside it

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| An LLM router (Opus 5.5, effort low) | Keyword rules; Haiku 5.5 | Rules: 12 of 36 on a blind rewording; Opus: 35 of 36 | +1 call per ask: p50 1.71 s, p95 4.27 s |
| "Back then" questions: a hard filter on the window ±1 release | Exact window; in-window first | Best on all 4 retrieval metrics; ADR-003 named it before any data | 43 of 90 dated hits still fall outside the exact window |
| Filters run inside both searches | Filter after merging | Each search still returns 20 candidates; filtering afterwards left ~12 | A filter clause in both SQL queries |
| Stale = no current version holds the text | "Not valid at the latest release" | CHANGELOG sections are valid only at their own release: 26 of 105 labels would count as stale | — |
| Gate stage: one row per gate × release; blank and low confidence when unclear | A row per stage; raw ranges | One fact per gate per release; at most 5 unclear rows per release | 35 low rows |
| Tiers by source type; a KEP is tier 3 if shipped by the target release or implemented | Tiers that depend on validity | Same ranking on v0; every citation gets a tier | A fixed rule, not tunable |
| Weights after the reranker: probability × 1.25 or × 0.8 | +2 on the raw score; weights after RRF | MRR 0.759 → 0.813 (+2 gives 0.783); after RRF they do nothing, because rerank re-sorts | Set on v0; 66 of 228 reorderings jump more than 2 logits |
| Authority metric over the 9 questions the labels fix, with "now"-question MRR beside it | MRR only | Inverted tiers lift the metric (3 → 6 of 9) but lower MRR; MRR guards the lean | A metric that leans toward the weights |

## Likely interview questions

1. **Q: Why an LLM to route questions instead of keyword rules?**
   - Rules scored 36 of 36 on the wording they were written from, but 12 of 36 on a blind rewording. Opus scored 35 of 36 on both.
   - One extra call per ask (p95 4.3 s); the eval stores routes, so scoring stays free and repeatable.
2. **Q: How do you keep "now" answers from citing outdated text?**
   - Each chunk text knows every version holding it. A "now" question keeps only text that some current version still holds: stale hits 38 → 0 of 100.
   - The filter runs inside both searches, so each still returns 20 candidates.
3. **Q: How do you know a KEP actually shipped?**
   - One of its gates appears in the release's own feature-gate docs, at the asked-about release or earlier. 42 of 65 gated KEPs have no row at 1.37 (removed after GA), so "seen at the target release" would demote shipped KEPs.
   - Its stage counts as "observed" only when every gate it names has a row and they agree; otherwise it's the KEP's claim, flagged low.
4. **Q: Why multiply the reranker's probability instead of adding to its score?**
   - Weights applied before the reranker do nothing, because it re-sorts the pool. The probability is 0–1, so ×1.25 is a proportional nudge: MRR 0.759 → 0.813.
5. **Q: Isn't the authority metric grading itself?**
   - Partly, because the same tier code drives both. Inverted tiers still lift it (6 of 9), but "now"-question MRR from human labels falls (0.628, vs. 0.783 with the real tiers). Both are printed.

## Numbers to remember

- **authority vs. rerank:** Recall@10 0.552 vs 0.516 · MRR 0.813 vs 0.703 · nDCG@10 0.535 vs 0.489 · Hit@10 1.000 vs 0.972.
- **Stale "now" hits:** 38 → 0 of 100. **Dated "back then" hits in the window:** 32 → 47 of 90.
- **Authority selection:** 9 of 9 (rerank 5, temporal 5, dense 3, hybrid 2). "Now"-question MRR 0.783 (rerank 0.588).
- **Router:** 35 of 36 modes; 7 of 9 windows; p50 1.71 s, p95 4.27 s.
- **Gate stages:** 3,295 rows over 18 releases, 35 low. KEPs at 1.37: 82 tier 3, 25 tier 5, 6 superseded.
- **Answers (3 runs):** AC1–AC3 100%; false refusals 0 of 36 (rerank 1–2); p95 14.9 s (rerank 14.2); $0.032 per question.
- **Paid in S09:** about $5.4 (3 kept eval runs $4.09; the partial run lost to an empty credit balance $0.67; router test, routes and demo asks the rest).
- **Tests:** 707 unit and 177 integration (from 506 and 126). PR sizes: R1 ~2,900 reviewable lines (estimate 1,400); R2 ~3,000 (estimate 2,000).
