# Future work

What the project would do next. Each item was found, measured or parked during the build; none is started. Written at the project's close (S18, 2026-11-05).

## Retrieval quality

| Item | Why | Evidence |
|---|---|---|
| Keep GitHub discussion texts out of "now" answers (demote or filter them; explain tier 7 in the prompt) | They fill 9 of the top 10 on 2 release-cadence questions, so both are refused; MRR 0.813 → 0.781 | [Final benchmark](evaluation.md#final-benchmark-s18) |
| Golden set v1 | v0's labels predate the GitHub texts, and the AC5/AC6 rules were chosen on v0's runs; v1 adds "any of" label groups and a reworded router check set | [Evaluation](evaluation.md) |
| BM25 for keyword search | Postgres's `ts_rank_cd` has no IDF (rarer words don't count for more), so common words weigh as much as rare ones | [The lexical search](evaluation.md) |
| Query rewriting for informal wording | Rephrased questions lose recall; a second search with a rewritten query is the candidate | [ADR-011](decisions/ADR-011-corrective-retrieval.md) |
| Dated "how did it change" questions | Retrieve per window end, then merge (ADR-003 D4, deferred): no v0 question needed it | [ADR-003](decisions/ADR-003-authority-and-status.md) |
| 2 known search misses | KEP-2579's history drops from rank 10 to 20 after the reranker (q08); `versioning.md` is outside c01's 20 candidates | [M1 report](m1-report.md) |

## Conflicts and provenance

| Item | Why | Evidence |
|---|---|---|
| A separate conflict detector | A dedicated call raised conflict recall from 0.33 to 0.55 on conflict set v0 in a probe | [Evaluation](evaluation.md) |
| Conflict set v1 | 5 pairs the model flagged that v0 doesn't list (q03, q18, q34, q35, q45), judged in S18 | [Final benchmark](evaluation.md#final-benchmark-s18) |
| Read bare `#N` links in decision chains | KEP-3015's decision step is missing only because its tracking issue writes `#5140`, not a full URL | [Evaluation](evaluation.md) (S13) |
| More chains | 2 chains show the rules work, not a success rate | [ADR-012](decisions/ADR-012-decision-provenance.md) |

## A public deployment

The API never became public, so these stayed designs. Each is in the [security review](security-review.md), sections 7 and 11.

- HTTPS, an API key, a per-key spending cap, rate limits and a question length cap.
- A least-privilege database role for the app; outbound traffic limited to 443 and the database.
- Terraform's write-only values, so no secret sits in the state file.
- A fixed error text with the cause in the log; a deadline per ask.
- The answer prompt states that evidence is data, not instructions.

## Operations

- **A rollback drill** for a release whose migration succeeded ([runbook](deployment.md), step 8): the steps exist, untested together.
- **The `libbrotli1` pin** in the `Dockerfile`: drop it with the next base-image update.
- **The corpus lock:** keep past `head` commits, so an older snapshot can be rebuilt.

## Code health

Small items the reviews parked as beyond each task's plan: trace coverage (a router span with its tokens), atomic saves for the eval's route and vector files, a race-free alias check before a second corpus writer exists, a mypy cache in CI, and a few dead fields and duplicate tests.

## Tested and not adopted

- **Corrective retrieval:** no grader told thin evidence from enough ([ADR-011](decisions/ADR-011-corrective-retrieval.md)).
