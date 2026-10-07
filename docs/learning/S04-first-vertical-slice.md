# Slice brief: S04 First vertical slice: PSP → PSA

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → **Ingest** → **Store** → **Chunk** → **Embed** → **Retrieve** → **Answer**

## What was built

- **Ingestion:**
  - It reads the SIG Auth docs at 14 releases (1.24–1.37) and KEP-2579 from pinned commits.
  - It stores 220 versions of 44 documents, each with an exact release window and date window. A re-run adds 0.
- **Chunks and vectors:**
  - Each version is split at its headings into 4,967 chunks (pieces small enough to retrieve), giving 1,583 distinct texts.
  - Each distinct text is embedded once with `voyage-4-large`. A re-run calls Voyage 0 times.
- **Dense retrieval:** an HNSW index (a graph index for fast nearest-neighbour search) finds the 10 texts nearest a question. Each is shown once, with every release window it was valid in.
- **`orgknow ask`:**
  - One Claude Opus 5.5 call returns a structured answer that cites chunk ids.
  - Plain code rejects any citation that wasn't retrieved.
  - Each ask leaves one Langfuse trace (a log of every step, with tokens).
- **Seeds #6–#10:**
  - 3 pass, 2 partial, 0 fail, with 0 unsupported claims.
  - The failures point at near-duplicate crowding (S09), an unflagged source error (S10) and a missing blog source (S05).

This matters to the project's thesis because every piece of evidence now reaches the model with its release window attached. Citations are checked by code, not trusted to the LLM.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Docs at every release 1.24–1.37 (14 snapshots) | 2 snapshots (1.24 + 1.37); every release from 1.20 | Exact windows, not guesses; no renames in 1.24–1.37 | 1.20–1.23 wait for rename handling (S05) |
| Re-ingest = compare and extend (insert, nothing, close + insert, or mismatch) | Skip stored documents; delete and rebuild | Idempotent and incremental; chunk ids, used as citations, stay stable | A diverged history stops that document with a non-zero exit |
| One vector per distinct text, keyed `(content_hash, model)`; no per-version field in the chunk header | One vector per chunk; release in the header | 68% of chunks repeat across versions; identical vectors would crowd the top 10 | `make embed` must delete orphan vectors |
| A hand-written scanner with 4 rules for headings and code blocks | markdown-it-py (a new dependency) | Matched markdown-it on all 231 versions and `CHANGELOG-1.22` (426 = 426 headings) | HTML tables with a blank line in a cell are cut (24 chunks) |
| `voyage-4-large` through `urllib`, behind a small `Embedder` interface | voyage-4 or voyage-4-lite; the `voyageai` SDK | Strongest retrieval at $0 (free tier); one POST needs no dependency | Question vectors vary slightly between calls (≤ 0.0044 distance) |
| One result per distinct text, listing every release window | One row per chunk; newest window only | 1,016 of 1,583 texts sit in 2+ chunks; 2 texts skip a release | Sections differing by one line still crowd: 6 of 10 distinct in seeds #6 and #8 |
| Top-k 10, pgvector's HNSW defaults, no similarity cutoff | k = 5; k = 20 | Matches Recall@10; the index equals exact search on 200 of 200 results | Weak hits still reach the model (distances of 0.65+ on seed #9) |
| Claude Opus 5.5 at `medium` effort, SDK structured output (ADR-006) | Sonnet 5.5; Haiku 4.5; raw HTTP | Strongest at saying "insufficient evidence"; the SDK converts the Pydantic schema | ~$0.03 per ask; a cut-off loses its stop reason (open question) |
| The model returns ids only; code fills in provenance; one bad id → `insufficient_evidence` | Ids + quotes; drop bad ids; retry once | Provenance can't be invented; AC2 holds by construction; no extra paid call | One bad id throws away an otherwise good answer |
| Langfuse SDK v4, one trace per ask (ADR-006) | OTLP by hand; the legacy API (sunset 2026-11-16) | S11's LangGraph integration needs the SDK | +17 packages; the public key appears in trace metadata (open question) |

## Likely interview questions

1. **Q: How do you stop the model from inventing citations?**
   - A schema can't limit ids to this query's results, so plain code checks each cited id against the retrieved set. One bad id rejects the whole answer.
   - A test feeds a fake model that cites 2 and 999 from hits 1–3. Removing the check makes it fail.
2. **Q: Why one vector per distinct text instead of one per chunk?**
   - 68% of chunks repeat across versions, so this saves calls, and identical vectors can't fill the top 10.
   - Follow-up: near-duplicates (one-line diffs) still crowd it; seeds #6 and #8 had 6 distinct sections in 10. S09's release filter is the next fix.
3. **Q: How do you know the HNSW index returns the right results?**
   - On fixtures: 4 hand-made vectors come back at distances 0, 0.2929, 1 and 2, computed by hand as 1 − cos θ.
   - On real data: for 20 real queries, the index's top 10 equals exact search's top 10, 200 of 200.
4. **Q: Did the system confuse old and new releases?**
   - Not in 5 seeds: the evidence shows each text's release windows, and the model used them (e.g. "removed in v1.25" over "will be removed").
   - A wrong date inside a source did pass through (KEP-2579's beta date). Conflict checks are S10, and questions about older releases are S09's test.
5. **Q (follow-up): Why write your own Markdown scanner?**
   - 4 rules matched markdown-it's headings on every version in scope (426 = 426 on a hard CHANGELOG), with no new dependency.
   - The known gap: HTML tables with a blank line inside a cell, parked for the S05 sitting.

## Numbers to remember

- 44 documents, 220 versions (216 docs versions from 231 raw files, plus 4 KEP versions).
- 4,967 chunks, 1,583 distinct texts (68% repeat); 512-token chunk maximum.
- 1,583 vectors from 13 Voyage requests and 475,905 tokens (5% under the chars ÷ 4 estimate).
- HNSW top 10 = exact top 10 on 200 of 200 results.
- Seeds #6–#10: 3 pass, 2 partial, 0 fail; 0 unsupported claims.
- An ask uses 3.2K–6K input tokens and 0 reasoning tokens (8 traced asks), costs ~$0.03, and took 4.6–15.7 s in T8.
- Paid calls for the slice: about $0.22 of Anthropic (9 Opus calls); Voyage within the free tier.
- 224 unit and 80 integration tests (from 94 and 45).
- 5 PRs (#21–#25); runs came out ~2.2× their size estimates.
