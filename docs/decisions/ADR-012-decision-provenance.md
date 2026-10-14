# ADR-012: Decision provenance

- **Status:** Accepted (S13-R1 sitting, 2026-10-13)
- **Date:** 2026-10-13
- **Blueprint/spec refs:** §3.2, §13, §19.2, §29 stage 9; ADR-001 (Phase 2 sources), ADR-002 D3–D4, ADR-003 D1, D3
- **Evidence:** `eval/results/s13-sitting/`; the S13 slice doc's run contract (S13-R1)

## Context

- Phase 2 adds one capability: reconstruct why a decision changed and how it evolved (blueprint §3.2), as 6 steps: problem → discussion → proposal → decision → implementation → current docs.
- The chain's steps sit in different sources, years apart. Similarity search neither connects them nor orders them.
- Kubernetes records the links in machine-readable form (sitting checks, `probe_rules.log`, `prow_order.log`):
  - a KEP's number is its tracking issue's number;
  - the tracking-issue template has "Kubernetes Enhancement Proposal:" and "Discussion Link:" fields (4 of 4 sampled KEPs);
  - the decision is recorded as Prow `/approve` comments and a merge time.
- Gaps: the discussion link is public GitHub for 2 of 4 sampled KEPs (2 are gated Google Docs); only 1 stored text links KEP-2572; no current docs page links it.
- ADR-001: GitHub items are Phase 2 only, and only those a traced chain links to.

## Decision

### D1. The chain is built by rules over recorded links and dates, not by an LLM

- Start at the seed KEP; its tracking issue by number; the template fields give the proposal PR and the discussion.
- **problem:** the discussion's opening post (else the KEP's Motivation). **discussion:** its first comment. **proposal:** the KEP's Summary, dated by the proposal PR's opening.
- **decision:** the PR's merge time, citing the last `/approve` before it (not the last Prow command, which can be `/hold cancel`).
- **implementation:** the earliest stored blog post or release record linking the KEP, dated on or after the decision.
- **current docs:** no link exists, so the nearest text, valid at the latest release, to the KEP's stored Summary vector (no API call).
- Each step cites exactly 1 stored text. A step the rules can't fill is stored **missing, with its reason** (`not_public`, `not_ingested`, `no_link`, …), never guessed.
- The full rules are pinned in the S13-R1 contract.

### D2. The chain is stored in 2 tables, as derived data

- `decisions` (one per seed KEP) and `decision_evidence` (one row per step: the cited chunk or a missing reason, the date, **how it was found** from a fixed list, and the chunk holding the link).
- Rebuilt by `make chains` after ingest and embed, like embeddings; `make reset-corpus` empties it with the texts it cites.
- No general link table: one chain needs no graph traversal (blueprint §13: joins first).

### D3. GitHub items are `discussion` documents

- One document per issue, PR or discussion: `gh:<repo key>/<issues|pull|discussions>/<number>` (ADR-002 D4 change, S13-R1), tier 7 (ADR-003 D3), searchable in every mode.
- Text: the opening post, then each human comment, reply and non-empty review body as its own section headed by author and date; bots dropped by login; diff-line comments not fetched.
- Fetched by its own command into the corpus cache, pinned by hash in the lock; ingest never calls the network. GitHub text is never committed.

### D4. Decision-chain completeness is scored against human gold chains, beside a like-for-like control

- **Gold:** `eval/golden_set/chains-v0.yaml`, human-owned: per step, acceptable texts (document and section, ADR-007 D2's rule) and a date, or "not public" / "not stored" / "none".
- **Headline:** a step counts when it is the right kind and cites an acceptable text. Steps that share a document must be labeled with different sections. A "not public" step counts only when the builder reports it missing as not public.
- **Beside it:** right text and the same UTC day, over the 5 event steps.
- **Two chains:** release cadence (built on) and a random held-out KEP, drawn after the rules were committed.
- **Control:** plain search (Phase 1's final mode, set to WHY) for 1 WHY question per chain, top 10; a lookup by source type slots hits into steps; graded by the same headline rule. The builder **beats** it on a chain with at least 1 more step right.
- Both rules were fixed in the sitting, before any score (the S12 retro).

## Alternatives considered

| Option | Why not |
|---|---|
| An LLM picks and dates each step | Costs per build, varies by run, needs its own evaluation; it can't read gated docs either and still needs the links to find candidates |
| A hand-curated chain | Not a reconstruction; scoring it against a gold chain is circular |
| A general `document_relationships` table | No reader in S13 besides the builder: scaffolding for later |
| No tables (rebuild per request) | A rebuild costs seconds (a 2.4 s link scan in the sitting); nothing to inspect or audit |
| Matching by document only, or any step | Any chunk of PR #2567 would pass "decision"; 1 hit on #1290 would credit 2 steps |
| A lenient control (q04's top 10, any step; or q01–q04 merged) | A different grading rule from the builder's; chain 1 only |
| No held-out chain | "6 rules, 1 chain, 100%" can't be defended |

## Consequences

- Provenance is data: each step says how it was found, and a failure names its cause.
- Two chains show feasibility, not a rate. The held-out score is the generalization evidence; it is reported, not tuned.
- Rules depend on the template: an older KEP, or a discussion in a gated doc, leaves steps missing. That is visible in the chain and the score.
- The new texts join Phase 1 search; v0's retrieval metrics are re-measured (free).
- `ask` doesn't show chains (S13-R1 decision 6); S17's sitting decides how answers and chains meet.
- **Revisit trigger:** a held-out chain that scores worse than its control, or a need to build chains for KEPs without template links → test an LLM picker against these rules on the same gold.
