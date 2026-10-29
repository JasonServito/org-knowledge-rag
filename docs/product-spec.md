# Product Spec: Phase 1 MVP

- **Status:** Draft v1
- **Date:** 2026-09-22
- **Blueprint refs:** §3.1, §4, §19, §30.1; readiness gap #2
- **Depends on:** ADR-001, ADR-002, ADR-003

## User outcome (one sentence)

An engineer asks a question about Kubernetes release process, authentication/security, or networking policy, across v1.20 → latest. They get one of three results:
- a correct answer, grounded in evidence valid for the right release or time, with citations that show authority and version, and with superseded or conflicting information flagged; **or**
- an explicit "insufficient evidence" response.

## Must-haves (Phase 1)

1. Manifest-driven ingestion of the ADR-002 subset. It must be reproducible and incremental (content-hash dedup).
2. Structure-aware chunks with deterministic metadata headers (source type, title, document id, heading path). Release window, tier and status are attached to each retrieved chunk from the database at answer time, not embedded (amended 2026-10-04, S04-R1 design review: they change when a newer version arrives, or depend on the question).
3. Dense retrieval, then lexical retrieval plus RRF, then a cross-encoder reranker. Each is added as its own ablation step.
4. Query modes: CURRENT, HISTORY, CHANGE, WHY. Unanswerable questions are handled by the grader.
5. Temporal filtering and authority adjustment per ADR-003.
6. Conflict detection. It must, at minimum, surface `claim_mismatch` and cross-version supersession.
7. Structured output per blueprint §18. Citations resolve to stored chunks.
8. Bounded LangGraph corrective retrieval (≤ 3 iterations). It is kept only if it measurably helps. Tested in S11 and not adopted (ADR-011, 2026-10-12).
9. A fixed golden set and a one-command eval run, producing an ablation table.
10. A FastAPI `/query` endpoint and Langfuse traces. Done in S12-T2: `POST /query` (`make serve`) answers through the same pipeline as `orgknow ask`, with one Langfuse trace per request.

## Non-goals (Phase 1)

- Phase 2 decision-provenance UI, and ingestion of issues/PRs (beyond linked chain items)
- AWS deployment, Next.js, auth, async SQS ingestion. A local job abstraction is fine.
- Non-English docs, and SIGs outside Release/Auth/Network
- LLM chunk enrichment, and embedding-model shopping before the harness exists

## Acceptance criteria

The **hard gates** apply to the finished Phase 1 system, not to the dense baseline. The baseline is expected to fail some of them; that failure is the story the ablation table tells.

| # | Criterion | How it's tested |
|---|---|---|
| AC1 | 100% of answered responses have ≥ 1 citation. Each citation resolves to a stored chunk with source URL, release/date, `source_type` and tier. | Eval harness schema check. Since S09-T6 it also requires each citation's tier, or the superseded-proposal flag for a withdrawn, rejected or replaced KEP (S04-R2 decision 5; S09-R2) |
| AC2 | 0 fabricated citations: no chunk IDs or URLs that aren't in the retrieved evidence | Eval harness |
| AC3 | All seed UNANSWERABLE questions return `insufficient_evidence` with a reason. This includes the 4 gated-Google-Doc cases. | Golden set |
| AC4 | On the 4 seed conflict cases, the answer surfaces the conflict (claimed vs. observed, or old vs. new) rather than asserting one side | Conflict set v0 (ADR-007 D4), end to end: the seed questions are fixed without looking at their results, and each reports whether search retrieved it (S10-R2 decision 3) |
| AC5 | CURRENT questions: the primary claim is supported by evidence valid at the latest release on every seed CURRENT question | Golden set, by the rule in the AC5 note below (S12-R1) |
| AC6 | HISTORY questions naming a release or date: the cited evidence is valid within the requested window | Golden set, by the rule in the AC6 note below (S12-R1) |
| AC7 | The ablation table covers the full sequence: dense → +lexical/RRF → +rerank → +temporal/authority → +conflict → +corrective. Every stage kept either improves its target metric or has its retention justified in writing. +corrective was tested in the S11-R1 design review and not adopted (ADR-011): its evidence is retrieval-only design-review probes, not an ablation row. | README / eval report |
| AC8 | Reproducibility: re-ingesting the same manifest yields identical version counts and hashes. `make eval` (or equivalent) runs end to end locally. | CI or manual run |

**AC4–AC6 at Phase 1's close (S12-R1 design review, 2026-10-12).** Phase 1 closes with these 3 as stated exceptions: each fails, with its measured cause written down, rather than being re-scoped to pass (`docs/m1-report.md`).

- **AC4 note: 1 of 4 at Phase 1's close: a stated exception (S12-R1 decision 2).** The 3 causes (`docs/evaluation.md`, "Phase 1 closeout (S12)"):
  - q01 (KEP-2572): the flagged pair matches the seed's sides, but its summary names the wrong disagreement (S11-R1 Step 0). The separate detector that fixed it had judged precision 0.690, below 0.90, and wasn't adopted (ADR-010, amendment 2026-10-12).
  - q08 (KEP-2579's date): a search miss. Its text is rank 10 in hybrid mode and rank 20 after the reranker, so the reranker pushes it out of the top 10.
  - c01 (`versioning.md`'s "every three months"): a search miss. As routed (HISTORY, 1.30), none of `versioning.md`'s texts is among its 20 candidates.
  - **v1's AC4 wording, written now:** "On the v1 seed conflict cases, fixed before any v1 result, every seed counts, search misses included. A seed is surfaced only when a flagged conflict matches its sides and its summary names the seed's fact."
  - Decided in the S12-R1 design review, after S10's saved runs. Rejected: counting only the seeds search retrieved (still 1 of 2, and it moves the goalposts S10-R2 set).
- **AC5 note: the rule (S12-R1 decision 3).** Per CURRENT golden question: the answer is `answered` and **every** citation has a release window that holds the latest release (1.37; an open window holds it). A refusal or an error fails.
  - **8 of 10: a stated exception,** in each of the final pipeline's 3 runs. q01 and q16 also cite older release notes.
  - It checks citation validity, not claim support: no grader reads the answer's claims.
  - Chosen in the S12-R1 design review on S10's saved runs, with a negative control: a rule the time-blind dense baseline also passes proves nothing. Dense scores 2 of 10 under this rule; "at least one citation valid" would give dense 8–9 of 10.
- **AC6 note: the rule and population (S12-R1 decision 4).** Over the 9 HISTORY golden questions with a golden release window: the answer is `answered` and **at least one** citation's release windows overlap that window exactly (no slack). A refusal or an error fails.
  - **8 of 9: a stated exception,** in each of the final pipeline's 3 runs. q02's citations all postdate "before 2021".
  - The criterion's literal population, questions naming a release or date, is 7 of the 9 (not q12, q17): 6 of 7 by the same rule.
  - Chosen in the S12-R1 design review on S10's saved runs, with the same negative control: dense scores 6 of 9. "At least one" rather than "every": history is often written down later, so "every citation inside" fails every system (0–3 of 9).
  - Golden set v1 is the first test of both rules on questions they weren't chosen on.

**Measured, with thresholds set after the baseline.** Setting numbers before a baseline exists would be guesswork. The dense baseline set the first ones (below):
- Recall@10, MRR, nDCG
- Citation correctness, faithfulness
- Stale-result rate, temporal accuracy, authority-selection accuracy
- Conflict precision/recall, router accuracy
- p95 latency, cost per query

**Thresholds (S06-T6 decisions 1–3, 2026-10-08).** They come from the dense baseline on golden set v0: 3 runs, 36 answerable questions (`docs/evaluation.md`). One answerable question is 1/36 = 0.028 of any mean, so the rules below count in steps of about one question.

| Metric | Dense baseline | Phase 1 threshold |
|---|---|---|
| Recall@10 | 0.384 | ≥ 0.46 (≈ baseline + 0.08) |
| MRR | 0.614 | ≥ 0.69 (≈ baseline + 0.08) |
| nDCG@10 | 0.369 | ≥ 0.45 (≈ baseline + 0.08) |
| Hit@10 | 0.944 (34 of 36) | ≥ 0.944 (a floor: + 0.08 would pass 1.0) |
| Citation correctness: AC1, AC2 | 100%, 100% | 100% (the hard gates above) |
| AC3 | 7 of 7 | 100% (the hard gate above) |
| False refusals | 2–3 of 36 | No more than the baseline's range |
| p95 latency, as the eval measures it (retrieve + answer; the question vector is stored) | 9.4–11.3 s | ≤ 23 s (2× the baseline) |
| Cost per question (mean) | $0.029 | ≤ $0.06 (2× the baseline) |
| Stale-result rate (lower is better) | 0.390 (39 of 100 CURRENT hits) | ≤ 0.01 (S09: 0 of 100; 1/100 = 0.01) |
| Temporal accuracy | 0.344 (31 of 90 dated HISTORY hits) | ≥ 0.51 (S09: 47 of 90; 46/90 = 0.511, rounded down) |
| Authority-selection accuracy | 0.333 (3 of 9 CURRENT questions) | ≥ 0.88 (S09: 9 of 9; 8/9 = 0.889, rounded down) |
| Router accuracy | n/a (no router) | ≥ 0.90, i.e. ≥ 33 of 36 (ADR-009; S09: 35 of 36) |
| Conflict precision, judged | n/a (no conflict step) | ≥ 0.90 (S10: worst run 21 of 22; 20/22 = 0.909, rounded down) |
| Conflict recall | n/a (no conflict step) | ≥ 0.30 (S10: worst run 19 of 60; 18/60 = 0.300) |
| AC4 | n/a (no conflict step) | 4 of 4 (the hard gate above; S10: 2 of 4, both misses not retrieved) |

- **A stage improves its target metric (AC7)** when that metric rises by at least 0.03 (about one question's worth), no other retrieval metric drops by more than 0.03, and AC1–AC3 stay at or above, and false refusals at or below, the baseline's 3-run range. A paired statistical test is the upgrade once a golden set passes ~100 questions.
- **The +0.08 targets are about 3 questions' worth**, one rule for every metric. Hybrid search and reranking gains on this corpus are unknown, so a target that proves too easy or out of reach is revised in writing.
- **The 4 S09 rows come from the final S09 mode, not the dense baseline** (S09-R2 decision 5; S09-T8, 2026-10-11): `authority`'s result over its 3 runs, loosened by one unit of its own count (1 hit or 1 question), rounded to 2 decimals toward the loose side. Router accuracy keeps ADR-009's ≥ 0.90. Their dense column is from `make eval-retrieval` (free).
- **The 2 conflict rows come from S10's 3 `conflict` runs on conflict set v0 (`887201b7`)** (S10-R2 decision 6; S10-T8, 2026-10-12): each metric's worst run, minus one conflict (1 ÷ that run's count), rounded down to 2 decimals. AC4 stays a hard gate.
  - Precision is the judged one. The set's 3 labeling passes split 0.526 of the time (above 0.20), so every flag outside the set got the LLM's verdict (`docs/evaluation.md`).
  - Raw, the worst run is 18 of 22 (17/22 = 0.77). If the borderline verdict (q35) is reversed, the judged worst run is 20 of 22 (19/22 = 0.86).
- **Metrics not measured yet get their threshold in the slice that first measures them:** faithfulness once a grader exists.

## Golden set v0

- 30–50 questions, starting from the 20 seeds in the validation gate's Appendix A.
- Class mix per blueprint §19.1.
- Relevance is labeled at the **document + heading-path** level, never by chunk ID, so labels survive re-chunking. The format, matching and counting rules are ADR-007.
- The set is frozen once the dense baseline has been run on it. New questions go into v1, which is re-baselined.

## Done means

Blueprint §30.1 is satisfied, and AC1–AC8 pass.

- **Phase 1 closed (M1) in S12 with 3 stated exceptions:** AC1–AC3, AC7 and AC8 pass, and must-have 10 is done; AC4 is 1 of 4, AC5 8 of 10 and AC6 8 of 9, each with its measured cause (notes above). The proof for each is in `docs/m1-report.md`.
