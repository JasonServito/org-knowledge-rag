# ADR-007: Golden-set schema and labeling

- **Status:** Accepted (2026-10-08, decided in the S06-R1 sitting). D4, the conflict set: Accepted 2026-10-11 in the S10-R2 sitting (amendment below).
- **Date:** 2026-10-08
- **Blueprint/spec refs:** §19.1–19.2; product spec "Golden set v0", AC1–AC3, AC7; ADR-002 (`canonical_id`, aliases)

## Context

- The golden set is the fixed list of questions every ablation row is scored on (AC7). The developer labels 30–50 questions by hand; the set freezes after the dense baseline, and new questions go into v1.
- The spec requires labels at the **document + heading-path** level, never chunk ids, so labels survive re-chunking.
- Dense retrieval returns one hit per distinct chunk text, carrying its `canonical_id` and `heading_path` (`db/models.py:Hit`). Each text belongs to exactly one document and one heading path (its header names both).
- Real data (dev database, 2026-10-08): 48,273 chunks, 21,552 distinct texts, 14,052 (document, heading path) pairs.
  - 3,587 pairs span several texts, up to 156 (versions of a section, and packed pieces of a long one).
  - 2,605 chunks have no heading path: all 868 feature-gate versions and 1,273 blog chunks (text before the first heading).
  - Heading paths hold backticks (1,551 chunks), Hugo shortcodes (279) and `->` (432); 0 hold `" > "`.
  - KEP heading paths start with the KEP title, e.g. `KEP-2579: Pod Security Admission Control > Implementation History`.
- Later slices reuse the set: S09 needs release windows and the expected query mode; S10 owns its own conflict test set.
- A devil's advocate argued against each of D1–D3. Its changes are folded in below.

## Decision

### D1. One YAML file; these fields per question

`eval/golden_set/v0.yaml` holds `version: v0` and a `questions` list. Each question has:

| Field | Type | Rule |
|---|---|---|
| `id` | string | `q` + 2–3 digits, unique |
| `question` | string | non-empty |
| `mode` | `CURRENT` \| `HISTORY` \| `CHANGE` \| `WHY` | required when answerable, optional otherwise (the router's expected output, S09) |
| `answerable` | bool | |
| `expected_answer` | string | short; for humans now, faithfulness checks later |
| `release_window` | `{from?: "1.N", until?: "1.N"}` | optional; the first and last release the question asks about, inclusive; at least one key; `from` ≤ `until` |
| `smoke` | bool | in the 10–15 question smoke set |
| `labels` | list of `{document, section?}` | non-empty if and only if answerable |

No `tags` or blueprint category field: current-state and historical are `mode`, unanswerable is `answerable`, cross-document is "2+ labeled documents", and conflict cases belong to S10's own set.

### D2. When a hit matches a label

- `document` is a `canonical_id` or any alias of one; the loader resolves aliases (`document_aliases`).
- `section` is a heading path written as `ask` prints it, headings joined with `" > "`:
  - omitted: the whole document (any chunk of it)
  - `""`: only the text before the first heading (empty heading path, exact)
  - `"A > B"`: any chunk whose heading path **starts with** `["A", "B"]`, compared heading by heading (`Install` never matches `Installation`)
- A hit matches a label when its `canonical_id` is the label's resolved document and its heading path matches the section rule.
- The loader rejects, per question: two labels that resolve to the same document and section; a label nested in another of the same document (a whole-document label next to any other, or one section path a prefix of another). `""` is nested in neither.
- The label check reports, per label, how many distinct texts it matches. A label matching 0 fails. Breadth is the labeler's judgement, made visible by the count.

### D3. How hits are counted

- Relevance is binary, and **each label is credited once**, at its first matching hit; later hits matching the same label gain nothing.
- K is the retrieval top-k (10 today). Per answerable question:
  - **Recall@K** = labels matched by a top-K hit ÷ labels
  - **Hit@K** = 1 if any label is matched, else 0
  - **MRR** = 1 ÷ rank of the first matching hit; 0 if none in the top K
  - **nDCG@K** = DCG ÷ IDCG, where DCG = Σ gainᵢ / log₂(i + 1), gainᵢ = 1 if hit i matches a label no earlier hit matched, and IDCG = Σ over i = 1..min(labels, K) of 1 / log₂(i + 1)
  - **Distinct sections** (diagnostic, not a target): distinct (document, heading path) pairs in the top K
- Averages are over answerable questions. Unanswerable questions are scored by AC3 only.

## Alternatives considered

| Option | Why not |
|---|---|
| Labels by chunk id | The spec forbids it: ids change on re-chunking |
| Minimal fields (id, question, class, labels) | S09 would reopen every frozen question to add windows and modes |
| A single `as_of` point | Questions ask about ranges ("before v1.24") |
| A `conflict` tag | Conflict cases are document pairs; S10 owns that set |
| Exact section match only | The labeler would list every subsection; a renamed subsection silently drops out |
| Whole-document labels only for documents without headings | Blog intros (1,273 chunks) couldn't be labeled; KEP-title labels stay loose anyway |
| No alias resolution | Linking the 25 old single-file KEPs later would mean relabeling |
| Every matching hit counts (chunk-level qrels) | Near-duplicate versions inflate both scores and denominators |
| Graded labels (main / supporting) | Another judgement per label, for one metric |
| Hit@K as the only headline | Hides questions that need 2 sources |

## Consequences

- **Known limit:** a section label also matches packed pieces of that section that don't hold the answer, and every version of it. Whether the right *version* was found is AC6's job (S09).
- **Interview line:** "standard nDCG where the relevant items are labels; a repeat of an already-found label scores 0", so crowding by near-duplicates lowers nDCG instead of raising it.
- Results store each hit's document and heading path, so a change to these rules means re-scoring stored runs for free, not a paid re-run.
- Linking the 25 old single-file KEPs (backlog) needs no relabel only if the link stores each old id as an alias.
- Labeling needs exact section names (backticks, shortcodes): the label check and a section-listing command support it.

## S10-R2 amendment (2026-10-11): D4, the conflict set

Decided by the developer in the S10-R2 sitting; the evidence is in `docs/slices/S10-conflict-detection.md`, run S10-R2. A devil's advocate argued against the recommendation first; its points became (a)–(d) and the known limits below.

### Context

- **D1 left conflicts to S10:** "conflict cases belong to S10's own set". S10 needs precision (are the flagged conflicts real?), recall (are the real ones flagged?) and AC4 (the 4 seed cases).
- **Precision needs a verdict on every flagged conflict,** not only the expected ones.
- **Retrieval is deterministic.** With stored question vectors and routes, a fresh retrieval of all 43 v0 questions gave the S09 run's 10 chunk ids by rank (43 of 43). So every pair the system could flag is known before any paid run: 430 hits, 335 distinct chunks, 1,935 pairs.

### D4. The conflict set: every disagreement in the fixed results, labeled before the runs

- **The file:** `eval/golden_set/conflicts-v0.yaml` (human-owned, like v0).
  - It references golden questions by id, and adds its own new questions (`c` ids).
  - It lists conflicts. Each has an id, a question, a kind (`claim_mismatch`, `history_date` or `texts`), an optional `seed` flag (exactly 4), a note quoting both values, and its sides.
  - Each side is a list of `{document, section?}` entries ("any of"), matched by D2's rule. A rule kind has one side, its KEP. `texts` has two, which may be the same section (old vs. new).
- **The pool:** every golden question plus the file's new questions. A question with no conflict has no disagreement. The fixed format and the label check are in the S10-R2 run contract.
- **What counts as a disagreement:**
  - **Counts:** different values for the same fact about the same thing, even when each was true at a different time (stale vs. current).
  - **Doesn't count:** cosmetic edits, added detail, and statements about different things.
  - **KEP-specific kinds:** a KEP's claim vs. the feature-gate reference is only `claim_mismatch`; a KEP history date vs. the releases table is only `history_date`.
- **Matching:**
  - (a) **By kind.** A rule-kind conflict is matched only by a rule-found conflict of that kind with a chunk on its side. A `texts` conflict is matched only by a model-found pair whose two chunks match its two sides, one each, in either order.
  - **Reachable:** a conflict whose sides are among its question's top-K hits.
- **Metrics:**
  - **Precision** = flagged conflicts matching a conflict ÷ flagged conflicts.
  - **Recall** = reachable conflicts matched ÷ reachable conflicts.
  - (c) **Split reporting:** both overall, and split rule-found / model-found.
  - **AC4, per seed:** retrieved (reachable) and surfaced (matched).
- **(b)** The rule above settles stale-vs.-current cases.
- **(d) The agreement check:**
  - **The check:** 3 independent Claude passes and a developer spot-check that includes one whole question.
  - **The trigger:** the passes split on more than 1 in 5 disagreements, or the developer finds one all 3 passes missed.
  - **Then:** precision is provisional; every unmatched flagged conflict gets a verdict after the runs, and precision is reported both ways.

### Alternatives considered

| Option | Why not |
|---|---|
| Label the expected conflicts, judge the rest after the runs (pooling) | A human step after the paid runs; judged after seeing the output; recall only counts what was thought of in advance. Kept as (d)'s fallback |
| Label only the expected conflicts; anything else counts as wrong | Precision understated by every real but unlisted conflict |
| Match by documents only, any kind | Any pair touching a KEP would count as that KEP's claim conflict |
| One label per pair | One disagreement stated by 4 sources would need 4 labels, and recall would expect the model to list it 4 times |

### Consequences

- **Re-scoring is free:** results store each flagged conflict's chunk ids and each hit's document and heading path, so stored runs re-score after a label fix.
- **Known limits:**
  - "Every disagreement" is only as complete as 3 passes of one model family; the spot-check samples it.
  - A flagged pair matching two conflicts credits both.
  - A section-level side also matches packed pieces of one version.
- **S11:** retries fetch new hits, which have no labels. S11's sitting decides how to label them; labels by document and section carry over for unchanged hits.
