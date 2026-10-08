# ADR-007: Golden-set schema and labeling

- **Status:** Accepted (2026-10-08, decided in the S06-R1 sitting)
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
