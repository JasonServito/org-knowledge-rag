# Slice brief: S07 Hybrid retrieval

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → **Store** → Chunk → Embed → **Retrieve** → Answer. Store gained a word index; Retrieve gained a second search and a merge step.

## What was built

- **Word search next to meaning search.**
  - Each chunk now has a word index that Postgres keeps in sync with the text, with no ingest code.
  - A question returns the 20 texts that hold every one of its content words, ranked by how close together the words sit.
- **RRF merges the two lists.** RRF (Reciprocal Rank Fusion) gives a text 1/(60 + rank) per list and adds them up. It uses positions only, because a vector distance and a word rank can't be added. The best 10 go to the answer step.
- **A setting picks the mode** (`dense` or `hybrid`). Each hit records why it ranked there: its distance, fused score and rank in each list.
- **A free retrieval score**, `make eval-retrieval`, uses the stored question vectors and costs nothing. It must match the expected numbers before any paid run.
- **Hybrid passed the improvement rule, so it is the default.** MRR (how high the first good source ranks) went from 0.614 to 0.675. No other measure dropped by more than 0.03.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Every content word must match (`plainto_tsquery`), ranked by closeness (`ts_rank_cd`) | Any word matches; all-words falling back to any-word; a BM25 extension | Textbook form; the only tried option that passed the rule (MRR +0.061); best Recall@20, 0.608 vs 0.540 | 23 of 36 questions match no text |
| A generated word-index column on `chunks` + GIN index | A separate per-text table; an index on an expression only | Postgres keeps it in sync; 0 lines of ingest code | Duplicate rows: 2.2× the distinct texts (the table is 56 MB) |
| 20 candidates per list, HNSW search width 100, RRF k = 60, equal weights | 50 or 10 candidates; tuned k or weights | The only measured setup identical to an exact scan (0 of 43 differ); k = 60 is the RRF paper's value | Every dense search keeps 100 candidates, not the default 40 |
| Each hit records distance, fused score and both ranks | The fused score only | "Why did this rank here?" is answered from the results file | 3 more fields per hit |
| A free retrieval-only score as the gate before paid runs | A skip-answers flag on the paid command | It catches a wrong setup for $0 | One more command to maintain |
| The improvement rule sets the default mode, mechanically | Always hybrid; always dense | The run judges nothing; the developer reviews before merging | The setup was chosen on the same 43 questions it was judged on |
| Carry the 2 Phase 1 gaps to S08 (retro) | Revise the targets now | Only 1 of the 5 planned retrieval stages is done | The targets may still prove out of reach |

## Likely interview questions

1. **Q: Why merge the lists with RRF instead of adding the scores?**
   - Cosine distance (0–2) and a word-match rank are on different scales, so only positions can be compared.
   - k = 60 keeps one list's first place (1/61) from outweighing two lists that agree.
2. **Q: Why require every word when 23 of 36 questions then match nothing?**
   - Any-word matching added noise: Hit@10 fell to 0.889 and Recall@20 to 0.540 in the sitting.
   - With all-words matching, the word search adds precise hits when it fires and stays silent otherwise; the dense list fills the slots.
3. **Q: Is +0.06 MRR real, or noise?**
   - Retrieval repeats exactly, so it's not run-to-run noise. It's about 2 questions' worth: 5 questions moved to rank 1, 4 lost one rank, and 4 lost some Recall@10 (q04 did both).
   - Follow-up: about 30 setups were tried on the same golden set, so v1 is the clean test.
4. **Q: Is Postgres full-text search BM25?**
   - No. Its ranking has no IDF (inverse document frequency), so "kubernetes" weighs as much as "PodSecurity".
   - BM25 needs an extension and a custom database image. It's deferred until S08 or S09 shows word search is the bottleneck.
5. **Q: Why set the HNSW search width yourself?**
   - HNSW is approximate, and a scan returns at most `ef_search` rows (default 40). Asking for 20 candidates at width 100 matched an exact scan on all 43 questions.
   - It's set with `SET LOCAL` inside a transaction, so it applies to that query only.

## Numbers to remember

- **Hybrid vs dense:** MRR 0.675 vs 0.614 (+0.060); Recall@10 0.382 vs 0.384; Hit@10 0.944 both; nDCG@10 0.385 vs 0.369.
- **Answer checks:** AC1–AC3 100%; false refusals 2.3 of 36, the same as dense.
- **Who moved:** 12 of 36 answerable questions changed. MRR rose on 5 and fell on 4; Recall@10 fell on 4.
- **Word search:** 23 of 36 answerable questions match no text. Of 430 fused hits, 13 came from it alone and 39 from both lists.
- **Speed and cost:** p95 12.9 s (8.8–20.9; dense 10.7 s); $0.030 per question (dense $0.029); input tokens +3.7%. The word query takes about 1 ms.
- **Phase 1 gaps carried to S08:** MRR 0.675 vs ≥ 0.69; Recall@10 0.382 vs ≥ 0.46.
- **Paid in S07:** 130 Anthropic calls (about $3.89 for the 3 runs), 1 Voyage request.
- **Tests:** 478 unit and 120 integration (from 453 and 106). The PR had about 1,290 reviewable lines (estimate about 1,000).
