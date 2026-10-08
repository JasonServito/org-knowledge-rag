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
2. Structure-aware chunks with deterministic metadata headers (source type, title, document id, heading path). Release window, tier and status are attached to each retrieved chunk from the database at answer time, not embedded (amended 2026-10-04, S04-R1 sitting: they change when a newer version arrives, or depend on the question).
3. Dense retrieval, then lexical retrieval plus RRF, then a cross-encoder reranker. Each is added as its own ablation step.
4. Query modes: CURRENT, HISTORY, CHANGE, WHY. Unanswerable questions are handled by the grader.
5. Temporal filtering and authority adjustment per ADR-003.
6. Conflict detection. It must, at minimum, surface `claim_mismatch` and cross-version supersession.
7. Structured output per blueprint §18. Citations resolve to stored chunks.
8. Bounded LangGraph corrective retrieval (≤ 3 iterations). It is kept only if it measurably helps.
9. A fixed golden set and a one-command eval run, producing an ablation table.
10. A FastAPI `/query` endpoint and Langfuse traces.

## Non-goals (Phase 1)

- Phase 2 decision-provenance UI, and ingestion of issues/PRs (beyond linked chain items)
- AWS deployment, Next.js, auth, async SQS ingestion. A local job abstraction is fine.
- Non-English docs, and SIGs outside Release/Auth/Network
- LLM chunk enrichment, and embedding-model shopping before the harness exists

## Acceptance criteria

The **hard gates** apply to the finished Phase 1 system, not to the dense baseline. The baseline is expected to fail some of them; that failure is the story the ablation table tells.

| # | Criterion | How it's tested |
|---|---|---|
| AC1 | 100% of answered responses have ≥ 1 citation. Each citation resolves to a stored chunk with source URL, release/date, `source_type` and tier. | Eval harness schema check. Tier joins citations in S09 (S04-R2 decision 5); until then the check covers the other fields (S06-R1 sitting, decision 4) |
| AC2 | 0 fabricated citations: no chunk IDs or URLs that aren't in the retrieved evidence | Eval harness |
| AC3 | All seed UNANSWERABLE questions return `insufficient_evidence` with a reason. This includes the 4 gated-Google-Doc cases. | Golden set |
| AC4 | On the 4 seed conflict cases, the answer surfaces the conflict (claimed vs. observed, or old vs. new) rather than asserting one side | Golden set, conflict subset |
| AC5 | CURRENT questions: the primary claim is supported by evidence valid at the latest release on every seed CURRENT question | Golden set |
| AC6 | HISTORY questions naming a release or date: the cited evidence is valid within the requested window | Golden set |
| AC7 | The ablation table covers the full sequence: dense → +lexical/RRF → +rerank → +temporal/authority → +conflict → +corrective. Every stage kept either improves its target metric or has its retention justified in writing. | README / eval report |
| AC8 | Reproducibility: re-ingesting the same manifest yields identical version counts and hashes. `make eval` (or equivalent) runs end to end locally. | CI or manual run |

**Measured, with thresholds set after the baseline.** Setting numbers before a baseline exists would be guesswork. The dense baseline set the first ones (below):
- Recall@10, MRR, nDCG
- Citation correctness, faithfulness
- Stale-result rate, temporal accuracy, authority-selection accuracy
- Conflict precision/recall, router accuracy
- p95 latency, cost per query

**Thresholds (S06-T6 decisions 1–3, 2026-10-08).** They come from the dense baseline on golden set v0: 3 runs, 36 answerable questions (`docs/evaluation.md`). One answerable question is 1/36 = 0.028 of any mean, so the rules below count in steps of about one question.

| Metric | Dense baseline | Phase 1 threshold |
|---|---|---|
| Recall@10 | 0.384 | ≥ 0.46 (baseline + 0.08) |
| MRR | 0.614 | ≥ 0.69 (baseline + 0.08) |
| nDCG@10 | 0.369 | ≥ 0.45 (baseline + 0.08) |
| Hit@10 | 0.944 (34 of 36) | ≥ 0.944 (a floor: + 0.08 would pass 1.0) |
| Citation correctness: AC1, AC2 | 100%, 100% | 100% (the hard gates above) |
| AC3 | 7 of 7 | 100% (the hard gate above) |
| False refusals | 2–3 of 36 | No more than the baseline's range |
| p95 latency, as the eval measures it (retrieve + answer; the question vector is stored) | 9.4–11.3 s | ≤ 23 s (2× the baseline) |
| Cost per question (mean) | $0.029 | ≤ $0.06 (2× the baseline) |

- **A stage improves its target metric (AC7)** when that metric rises by at least 0.03 (about one question's worth), no other retrieval metric drops by more than 0.03, and AC1–AC3 stay at or above, and false refusals at or below, the baseline's 3-run range. A paired statistical test is the upgrade once a golden set passes ~100 questions.
- **The +0.08 targets are about 3 questions' worth**, one rule for every metric. Hybrid search and reranking gains on this corpus are unknown, so a target that proves too easy or out of reach is revised in writing.
- **Metrics not measured yet get their threshold in the slice that first measures them:** stale-result rate, temporal accuracy, authority-selection accuracy and router accuracy (S09); conflict precision/recall (S10); faithfulness once a grader exists.

## Golden set v0

- 30–50 questions, starting from the 20 seeds in the validation gate's Appendix A.
- Class mix per blueprint §19.1.
- Relevance is labeled at the **document + heading-path** level, never by chunk ID, so labels survive re-chunking. The format, matching and counting rules are ADR-007.
- The set is frozen once the dense baseline has been run on it. New questions go into v1, which is re-baselined.

## Done means

Blueprint §30.1 is satisfied, and AC1–AC8 pass.
