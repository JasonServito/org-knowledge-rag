# Slice brief: S13 Phase 2 provenance MVP

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** **Sources** → **Ingest** → **Store** → **Chunk** → **Embed** → Retrieve → Answer, plus `Supporting: evaluation`.
- New sources (GitHub issues, PRs, discussions) go through the existing ingest, chunk and embed path.
- The chain builder is a new branch after Store: it reads stored texts and links, not search results. `ask` is unchanged.

## What was built

- **Decision provenance (where a decision came from):** `orgknow chain kep:2572` prints the release-cadence decision as 6 dated steps (problem, discussion, proposal, decision, implementation, current docs), each citing a stored text.
- **Built by rules, not an LLM (ADR-012):** the KEP number names its tracking issue; the issue's template fields link the discussion and the proposal PR; the last `/approve` before the merge is the decision; the earliest blog or release record linking the KEP is the implementation; the nearest current page by vector is the docs step. A step the rules can't fill is stored missing, with its reason.
- **GitHub items as a new source type (`discussion`, tier 7):** 5 items fetched once into the local cache, pinned by sha256, rendered post by post with bots dropped; re-ingesting gives the same fingerprint. Only items a chain links to are stored (ADR-001).
- **Stored and served:** 2 tables (`decisions`, `decision_evidence`), rebuilt by `make chains`; `GET /decisions/{canonical_id}` returns the same chain as JSON for S17's UI.
- **A new metric with its control fixed first:** decision-chain completeness against human-signed gold chains, on the chain the rules were written on and a random held-out KEP, beside plain search graded by the same rule. The builder beats it on both: 6 vs. 3 and 5 vs. 1 of 6.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Rules over the project's own links and dates (decision 1) | An LLM picks each step; a hand-curated chain | Kubernetes records the links (4 of 4 sampled KEPs use the template fields); rules fail visibly, step by step | Fixed rules miss unusual records: KEP-3015's bare `#5140` |
| A random held-out KEP, drawn after the rules were committed (decision 2) | Score only the chain the rules were written on | "6 rules, 1 chain, 100%" proves nothing | 1 more chain to label; still n = 2 |
| Only full URLs count as links (option A, after the draw) | Read a bare `#N` as that repo's item | B was chosen after seeing it would find the decision: tuning on the test | KEP-3015's decision step missing (5 of 6) |
| 2 tables with a structured "how found" (decision 3) | A general link table; rebuild on every request | A rebuild costs seconds; 6 stored rows are read in milliseconds and can be inspected | Derived data to rebuild after an ingest (`make chains`) |
| Headline: the right kind of step citing an acceptable text, by section; dates scored apart (decision 4) | Require the date in the headline; match by document only | 2 pairs of steps share a document; the proposal has 2 defensible dates | 2 numbers to read per chain |
| Control: 1 WHY question, top 10, a lookup by source type, same grader (decision 5) | Grade q04's top 10 leniently | Same test and grader for both systems; "beats" needs 1 more step | Builder 6 vs. 3 and 5 vs. 1 |
| Discussion texts searchable in every mode, no multiplier (call c) | Leave them out of search; demote them | ADR-003 unchanged; measure first | Phase 1 MRR −0.032 (q01): an open question |

## Likely interview questions

1. **Q: How do you rebuild a decision's history without an LLM?**
   - Follow the links people already recorded: KEP number → tracking issue → its template fields → the discussion and the proposal PR → the last `/approve` before the merge.
   - Each step stores how it was found and the text holding the link, so a reviewer can check every hop.
2. **Q: You wrote the rules on one chain. How do you know they aren't fitted?**
   - A held-out KEP was drawn at random (seeded by the contract's commit) after the rules were frozen: 5 of 6 steps right.
   - The miss was kept: its update PR is a bare `#5140`, which the frozen rule ignores; fixing it is tested only on a fresh chain.
3. **Q: How do you know the chain beats plain search?**
   - Same question, same grader: search's top 10 mapped to steps by source type scores 3 of 6 and 1 of 6; the builder 6 and 5.
   - Search never surfaces a discussion's opening post or the merging PR's posts; KEP-3015's best "proposal" hit is a different KEP.
4. **Q: Why store the chain instead of building it per request?**
   - A rebuild reads every chunk for links to one KEP (2.4 s in the sitting) plus a vector query; a stored chain is 6 rows read in milliseconds.
   - It's derived data, like embeddings: `make chains` rebuilds it, and a reset empties it through cascading deletes.
5. **Q: Adding GitHub threads hurt your Phase 1 numbers. What would you do?** (follow-up)
   - Diagnose first: 5 of 36 questions moved; with the threads removed in a rolled-back transaction, all 36 return exactly.
   - The cause is open windows passing the "now" filter; options are demoting threads in CURRENT mode or filtering them, measured on golden v1, not v0.

## Numbers to remember

- **Completeness:** chain 1 builder 6 of 6 (same day 4 of 5), control 3 of 6; held-out KEP-3015 builder 5 of 6 (same day 2 of 4), control 1 of 6.
- **New texts:** 5 GitHub items, 210 chunks; posts stored 89, 3, 51 (chain 1), 49, 9 (held-out).
- **Phase 1 re-check:** Recall@10 0.552 → 0.522, Hit@10 1.000 → 0.972, MRR 0.813 → 0.781; 5 of 36 questions' scores change.
- **The draw:** 1 KEP from 35 implemented KEPs in 3 SIGs (latest milestone ≥ v1.25).
- **Gold:** 12 steps (11 with text labels, 1 `not_stored`), 32 text labels, all matching stored texts.
- **Tests:** 1,061 unit (896 at S12's close), 214 integration (189).
- **Paid:** ~US$0.007 Voyage (39,143 tokens); no Anthropic calls.
