# Slice brief: S12 Phase 1 closeout

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → Store → Chunk → Embed → Retrieve → **Answer**, plus `Supporting: evaluation`.
- The pipeline doesn't change. `POST /query` is a second way into the same answer path.
- AC5 and AC6 score the answers' citations from saved eval runs, with no paid call.

## What was built

- **Two answer-side checks.** AC5: every citation of a "now" (CURRENT) answer is valid at the latest release, 1.37. AC6: at least one citation of a dated "back then" (HISTORY) answer falls inside the asked-for window.
- **The rules were picked with a negative control** (a baseline that shouldn't pass): the time-blind dense pipeline scores 2 of 10 and 6 of 9, the final pipeline 8 of 10 and 8 of 9. All 16 saved runs are scored.
- **An HTTP endpoint.** `POST /query` answers through the same function as `orgknow ask`. The server loads the reranker (a ~7.5 s model load per `ask`) once, and each request leaves one Langfuse trace (a timed record of each step).
- **A measured "no" on a separate conflict detector.** A second Haiku call raised conflict recall 0.33 → 0.55 (wording A), but A failed q01's check; wording B, which fixed q01, had judged precision (its flags checked one by one) 0.690, under the spec's 0.90 (ADR-010 amendment).
- **The M1 report and the README story.** Each of AC1–AC8 and must-have 10 with its result and proof command; Phase 1 closes with 3 stated exceptions (fails recorded with their measured cause, not re-scoped): AC4 1 of 4, AC5 8 of 10, AC6 8 of 9.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| No separate detector call (decision 1) | Build wording B (fixes q01) or wording A (recall 0.55) | B's judged precision 0.690 < 0.90; A fails q01's summary check 3 of 3 times | Conflict recall stays 0.333; the probe cost US$0.099 |
| AC4 closes as a stated exception, 1 of 4 (decision 2) | Amend AC4 to retrieved seeds only; keep S12 open | Re-scoping moves the goalposts and still gives 1 of 2; q08 and c01 need tuning on frozen v0 | A failing criterion at M1; v1's AC4 wording is fixed now |
| AC5: every citation valid at 1.37 (decision 3) | At least one valid citation | "At least one" passes dense 8–9 of 10, so it can't tell the systems apart | 8 of 10, a stated exception |
| AC6: at least one citation inside the exact window (decision 4) | Every citation within ±1 release; every citation exact | ±1 passes the time filter by construction; "every exact" fails every system (0–3 of 9) | 8 of 9, a stated exception (6 of 7 on the spec's literal 7 questions) |
| Load the reranker once at server startup (T2) | Load it per request, as each `ask` does | It's the slow step: ~7.5 s per load | Concurrent requests share one reranker (a known limit) |
| `uvicorn` as the API server (ADR-004 amendment) | No server, test client only | A test client can't serve a request | 1 new package; its 2 dependencies were already locked |
| FastAPI's built-in `/docs` page as the dev UI | Streamlit; a hand-written HTML page | S17 builds the real UI | 0 lines, 0 dependencies; Streamlit is a note for S17's sitting |

## Likely interview questions

1. **Q: Three acceptance criteria fail. Why call Phase 1 done?**
   - Each has a measured cause; AC4's 3 misses: q08's source drops from rank 10 to 20 after the reranker; c01's isn't among its 20 candidates; q01's flagged pair names the wrong fact; AC5: q01, q16 cite older release notes; AC6: q02's citations postdate its window.
   - Re-scoping AC4 to "retrieved seeds only" was rejected: it moves the goalposts. v1's AC4 wording is written before any v1 result.
2. **Q: You picked the AC5/AC6 rules after seeing the runs. How do you know they aren't fitted?**
   - A negative control: a rule the time-blind dense baseline passes proves nothing. "At least one valid citation" passed dense 8–9 of 10, so it was dropped.
   - The chosen rules separate dense from the final pipeline (2 → 8 of 10, 6 → 8 of 9). Golden set v1 is still the clean test.
3. **Q: A separate detector raised conflict recall from 0.33 to 0.55. Why not ship it?**
   - Pass criteria were fixed before the probe. Wording A failed q01's check; wording B's raw precision was 0.620 and its judged precision 0.690, against a 0.90 bar.
   - 19 of B's 27 false flags compared a KEP claim not valid at the target release with a later state.
4. **Q: How does the API avoid reloading the model on every request?**
   - FastAPI's startup hook builds the clients and the reranker once; requests reuse them. The demo log shows 1 load at startup and none after, 12.0 s and 11.2 s per request.
   - Trade-off: concurrent requests share one reranker; fine for a local dev server, and documented as a known limit.
5. **Q: AC5 passes on 8 of 10. Does that mean those answers are correct?** (follow-up)
   - No: it checks each citation's release window, not whether the text supports the claim. No grading model reads the answer.
   - It's on the M1 report's "Not verified" list, with faithfulness.

## Numbers to remember

- **Final pipeline (conflict row):** Recall@10 0.552, MRR 0.813, Hit@10 1.000; p95 16.3 s; $0.0378 per question.
- **AC5:** 8 of 10 (dense 2 of 10). **AC6:** 8 of 9 (dense 6 of 9; 6 of 7 on the spec's literal population).
- **AC4:** 1 of 4 (2 of 4 by matching alone).
- **Detector probe:** A recall 0.550, raw precision 0.707; B recall 0.583, raw 0.620, judged 0.690; US$0.099.
- **q08's source:** rank 10 in hybrid mode, rank 20 after the reranker.
- **API demo:** 2 requests, HTTP 200, 12.0 s and 11.2 s, 9 evidence items each, ~US$0.07.
- **Tests:** 896 unit (853 at S11's close), 189 integration.
- **Paid in S12:** ~US$0.17 (the sitting's probe US$0.099, the demo ~US$0.07).
