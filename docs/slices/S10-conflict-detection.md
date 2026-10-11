# S10: Conflict detection

- **Status:** 🟨
- **Blueprint stage:** Stage 7 (conflict detection: §16; `conflicts[]` in the structured output: §18)
- **Started:** 2026-10-11
- **Finished:**

## Outcome

Every answer carries a `conflicts[]` list: claimed vs. observed, old vs. new text, and contradictions between sources, each marked resolved (by an ADR-003 D6 rule) or unresolved. `make eval` prints conflict precision and recall on a human-verified conflict set, and AC4 passes on the 4 seed cases.

## Why now

- **Disagreements are left to the model.** The prompt shows each KEP's claim and observed stage (S09-T6), so q18's answer mentions KEP-4858's "stable" claim vs. "beta" in prose. Nothing records it, checks it, or handles old vs. new text and contradictions.
- **It's the next ablation step** (AC7): dense → +lexical/RRF → +rerank → +temporal/authority → **+conflict** → +corrective.
- **Spec must-have 6 and AC4** (a hard gate) need it: surface `claim_mismatch` and cross-version supersession.
- **Probe on v0's authority hits (S10-R1 sitting):** KEP-4858's claim (stable) disagrees with the 1.37 reference (beta) in 6 questions; old and new versions of one section appear together in 24 of 43 questions (75 pairs), mostly cosmetic edits (typos, author lines, table-of-contents links).

## Exit checks

- [ ] ADR-010 (conflict detection method) is Accepted.
- [ ] Every answer carries `conflicts[]`, each conflict resolved by an ADR-003 D6 rule or marked unresolved; `ask` prints it and the trace logs it.
- [ ] Conflict set v0 is human-verified: every disagreement among each eval question's 10 results, and the 4 seed cases (ADR-007 D4; S10-R2 decisions 2–3).
- [ ] `make eval` prints conflict precision, recall and AC4; the +conflict row (3 runs) is in the ablation table; the product spec has the conflict thresholds.
- [ ] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| ADR-010: how conflicts are found and resolved | Changing retrieval: hits, scores and order stay exactly as in `authority` mode |
| Rule-found conflicts from stored facts (KEP claims vs. observations; KEP release dates vs. the `releases` table) | A second, unfiltered search to keep superseded text for CURRENT questions |
| Model-found conflicts between texts, in the answer call (ADR-010) | A separate detector call (ADR-010 D4's fallback); an LLM judge of the answer text: AC4 is checked on `conflicts[]` |
| Resolution by ADR-003 D6, in code | Golden set changes (v0 is frozen) |
| `conflicts[]` in the answer, `ask`, the trace and the eval rows | Phase 2 sources (issues, PRs) |
| Conflict set v0, its loader, precision, recall and AC4 | The CHANGELOG as a stage observation: dropped for Phase 1 (S10-R1 sitting; ADR-003 change) |
| The S10 eval run and its row | A stale-claim rule (ADR-010 D4's fallback, only if T8 misses seed KEP-2572) |

## Metric to move

- **Conflict recall and precision** on conflict set v0: new; thresholds set in T8 from the 3 runs, like S09's.
- **AC4:** reported per seed, end to end (S10-R2 decision 3). The 4 seed questions were fixed without looking at their results, so a seed that search misses is reported "not retrieved": a miss for S11's corrective retrieval. The hard gate applies to the finished Phase 1 system (product spec).
- **Unchanged by design:** Recall@10, MRR, nDCG@10, Hit@10 and the 4 S09 metrics (retrieval doesn't change). AC1–AC3 and false refusals stay within the baseline's range; p95 ≤ 23 s; cost ≤ $0.06 per question.

## Tasks

These mirror `docs/backlog.md`; details live here.

### S10-T1: ADR-010 conflict detection method `[core]`

- **Goal:** decide in the R1 sitting how conflicts are found (rules, an LLM, or both), resolved and output.
- **Done when:** ADR-010 is Accepted in the R1 run contract commit.
- **Deps:** none.

### S10-T2: KEP metadata conflicts `[core]`

- **Goal:** pure functions, run on each question's hits before the answer:
  - `claim_mismatch`: the claim of the KEP version valid at the target release vs. its observed stage there (ADR-003 D2, ADR-010 D1)
  - `history_date`: a KEP line "YYYY-MM-DD: … v1.N … released" vs. the `releases` table
- **Done when:** hand-worked unit tests pass; `make eval-retrieval` prints the sitting's rule-conflict line.
- **Deps:** T1.

### S10-T3: Kind and resolution of a pair `[core]`

- **Goal:** a pure function: two hits and the target release → the kind (same section: `supersession`, else `contradiction`), and the winner by ADR-003 D6, or unresolved (ADR-010 D2).
- **Done when:** hand-worked unit tests pass, including the sitting's 2 real pairs.
- **Deps:** T1.

### S10-T4: Conflicts in the answer `[core]`

- **Goal:** `conflicts[]` on the answer and the eval rows, on every path; the rule-found block in the prompt; `ask` JSON; the trace.
- **Done when:** hand-worked unit tests pass; `make eval-retrieval` prints S09's numbers; a demo `ask` shows KEP-4858's conflict.
- **Deps:** T2.

### S10-T5: Model-found conflicts `[core]`

- **Goal:** the answer model lists chunk pairs whose texts disagree (ADR-010 D1); ids checked on their own (D3); kind and resolution by T3; ADR-003 D6 and the KEP milestone line in the prompt; the losing-side flag in the eval.
- **Done when:** hand-worked unit tests pass; the smoke run keeps AC1–AC3 at 100% and retrieves S09's hits.
- **Deps:** T3, T4.

### S10-T5b: The release to settle conflicts at `[core]`

- **Goal:** the prompt says which release conflicts are settled at ("Settle conflicts at release 1.N."), so the answer text and the code's list apply ADR-003 D6 at the same release (S10-R2 decision 4; Greptile on PR #42).
- **Done when:** hand-worked unit tests pass; T8's run 1 keeps AC1–AC3 at 100%.
- **Deps:** T5.

### S10-T6: Conflict set format, loader and metrics `[core]`

- **Goal:** the conflict set's format and loader with a label check (ADR-007 D4); conflict precision, recall and AC4 in the eval, its summary and the table; `make eval-conflicts` (free).
- **Done when:** hand-worked unit tests pass; `make eval-conflicts` on the demo sample prints the R2 contract's lines; `make eval-retrieval` prints S09's lines.
- **Deps:** T4.

### S10-T7a: Draft conflict set v0 `[core]`

- **Goal:** Claude's draft: every disagreement among the 10 results of each golden v0 question and the 2 new questions, plus the 4 seeds, in 3 independent passes; the developer's spot-check sheet (S10-R2 decisions 2–3).
- **Done when:** the loader's check passes on the draft; the passes' split rate is reported; the sheet is built by a script from stored text.
- **Deps:** T6.

### S10-T7: Verify conflict set v0 `[human]`

- **Goal:** the developer works through the sheet: each seed, 1 conflict per kind, 1 random, every disputed conflict, and 1 whole question. Then copies the draft, with any fixes, into `eval/golden_set/conflicts-v0.yaml`.
- **Done when:** the sheet is signed off and the file is committed on the run branch; the loader's check passes.
- **Deps:** T7a.

### S10-T8: S10 eval run `[commodity]`

- **Goal:** 3 paid runs with conflicts on; the +conflict row; the write-up; conflict thresholds in the product spec.
- **Done when:**
  - a free gate passes before any paid call
  - run 1 keeps AC1–AC3 at 100% with 0 errors
  - the row and its spread are committed
  - `docs/evaluation.md` states pass or fail against the improvement rule, and lists the seed summaries for the developer
- **Deps:** T5b, T7.

## Risks & unknowns

- **The model already mentions some conflicts.** Since S09-T6 the prompt shows claims and observed stages, and q18's answer flags KEP-4858 in prose. The row may show little change in answer text; the gain is structured, checkable conflicts.
- **Most claim mismatches are plans, not errors.** Over KEP history, 91 of 116 claim ≠ observed rows are a KEP claiming the next stage before it ships (its milestone is later). KEP-4858 is one of them, and AC4 needs it.
- **A hit's claim can be from an old KEP version.** A hit cites the newest version holding its text, so its claim can predate the target release. On v0's hits that gives 2 false conflicts (KEP-3331 in q36, KEP-3866 in q44: an old version claims alpha, observed stable) and misses 1 (KEP-3299 in q32). The claim must come from the KEP version valid at the target release.
- **CURRENT questions can't show old vs. new.** The temporal filter drops superseded text before ranking, so supersession appears only in HISTORY, CHANGE and WHY questions.
- **Precision needs judgement.** A detected conflict not in the set's labels may still be real.
- **Cost and latency.** An extra model call per question would add to p95 (14.9 s of 23 s) and cost ($0.032 of $0.06).
- **history_date fires rarely.** The corpus holds 5 matching lines, 3 of them checkable and 1 wrong (KEP-2579). Only 1 of 3 natural wordings retrieved that line in the sitting, at rank 9. T7 must not pick the question because it retrieves the line.
- **Seed KEP-2572 rests on the model.** The KEP block shows "latest milestone v1.22, 15 releases before 1.37"; the model must pair it with the docs. The fallback is in ADR-010 D4.
- **Seeds fixed blind can miss on retrieval** (S10-R2). In authority mode, q08 doesn't retrieve KEP-2579's date line (hybrid mode did), so AC4 will likely report it "not retrieved".
- **Claude labels Claude.** The labeler and the answer model share a model family. The guards: the 3 passes' split rate, the developer's read of one whole question, and the list of every unmatched flagged conflict in T8's write-up.

## Decisions expected (ADRs)

- **ADR-010:** conflict detection method. Accepted in the R1 sitting.
- **ADR-003 change:** the CHANGELOG isn't a stage observation in Phase 1; a claimed `disabled` is never compared; the claim of the KEP version valid at the target release (R1 sitting, done).
- **The conflict set format** (R2 sitting, done): ADR-007 D4. AC4 end to end, the settle line and the switch rule's limits: ADR-010's S10-R2 changes.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S10-R1: rule-found and model-found conflicts

- **Status:** merged (PR #42)
- **Branch:** `s10-r1-conflicts`
- **Tasks, in this order:** S10-T2 (KEP metadata conflicts) → S10-T3 (kind and resolution of a pair) → S10-T4 (conflicts in the answer) → S10-T5 (model-found conflicts). T1 (ADR-010) was decided in the sitting.
- **Closes the slice:** no. T6 (format and metrics), T7 (`[human]` labels) and T8 (the paid eval) follow in R2.
- **Goal (plain words):**
  - Code flags two kinds of mismatch between stored facts. A KEP claims a stage the feature-gate pages don't show at that release. A KEP's history gives a release date the official dates contradict.
  - The answer model flags pairs of texts that disagree, between documents or between an old and a new version.
  - Code picks each winner by ADR-003 D6's rules, or marks the conflict unresolved. Every answer then carries the list, and retrieval doesn't change.

#### Sitting evidence (2026-10-11)

All on the dev database and the S09 run `authority-20261011T051924Z` (43 questions × 10 hits); scratch SQL and scripts, not committed. Paid: 4 Voyage requests (the KEP-2579 probe), 0 Anthropic calls.

- **Claims vs. observations:** 65 current KEPs name a gate. At 1.37, 19 match, 4 differ and 42 aren't fully observed. Of the 4: KEP-4412, 4858 and 6032 claim the stage planned for v1.38; KEP-4004 claims `disabled` vs. observed `deprecated`. Over history (KEP version × release in its window), 116 rows differ, across 44 KEPs; 91 of them are a claim running ahead of the release.
- **Which claim:** with the claim of the KEP version valid at the target release (the newest when two are valid), v0's hits give 7 conflicts: KEP-4858 at 1.37 in q16, q17, q18, q19, q20 and q48; KEP-3299 at 1.28 in q32. With each hit's own version: 8, adding KEP-3331 (q36) and KEP-3866 (q44) and losing KEP-3299 (q32). KEP-4858's stable claim dates from 2026-09-16, after 1.37 shipped (2026-08-26).
- **Old vs. new pairs:** 85 pairs share a document and heading path. 10 of them are two chunks of one version. 75 never share a version, across 24 questions and 52 sections; 12 of those have identical bodies after whitespace. The diffs are mostly cosmetic: typos, author lines, table-of-contents links, checkboxes. About a dozen change meaning (gate stage tables, kubelet skew n-2 → n-3, KEP-2799 dates, "the legacy repositories went away on March 4, 2024").
- **Out-of-date KEP status** (in-progress status, latest milestone ≤ target − t): 18 KEPs at t = 1 and the same 15 at t = 2, 3 and 4. The corpus shows the work shipped for 6 of the 15: KEP-2572, 3720, 1731, 2829, 3744 and 2433. On v0's hits: KEP-2572 in 6 questions, KEP-3744 in 2.
- **KEP history dates:** 5 lines match the pinned pattern corpus-wide. 3 name a release in `releases`: KEP-2579 v1.22 (0 days off), KEP-2579 v1.23 (−34 days) and KEP-3453 v1.26 (0 days). Probe (authority mode, hand-built routes): "When was Pod Security Admission's beta released?" (CHANGE) retrieves the line at rank 9. "When did Pod Security Admission reach beta?", "Was Pod Security Admission beta in Kubernetes 1.23?" and a leading KEP-2579 question don't.
- **The CHANGELOG:** 4,099 distinct CHANGELOG chunk texts; 362 lines name a feature gate with a stage word. The EventedPLEG revert line doesn't say "feature gate".
- **Before S10:** q18's answer already says "The latest KEP text claims an implemented/stable status, but its observed stage at v1.37 is still beta", in prose only.
- **Devil's advocates** (2, fresh context):
  - D1: one bad conflict id would reject the answer under ADR-006's check (confirmed in `generator.py`). Code would resolve only after the text is written. Seed coverage was unchecked. All three were answered by decision 1's (a)–(c).
  - Rule scope: history_date looked test-fitted and stale-claim was one-sided. Answered by the KEP-2579 probe, the 6-of-15 count, and decision 2.

#### Decisions (made in the sitting, 2026-10-11)

| # | Choice | Rejected | Why |
|---|---|---|---|
| 1 | **ADR-010 D1: the answer model lists pairs of chunks whose texts disagree** (a new field; no extra call). (a) Conflict ids are checked on their own: a bad pair is dropped and logged, never rejecting the answer, and rule-found conflicts are attached on every path. (b) The prompt states ADR-003 D6's rules, and the eval flags an answer citing only the losing side. (c) Switch rule (ADR-010 D4) | Rules only; a separate model call | Rules flag ~60 cosmetic edits and can't see two documents disagreeing. A separate call costs +$0.022 per question ($0.054 of $0.06) at an estimated p95 of 20–23 s |
| 2 | **Seed KEP-2572: a prompt flag.** A KEP block's claim line shows its latest milestone and how many releases before the target release it is | A stale-claim rule; nothing | Only 6 of 15 firings are backed by the corpus; the flag lets code settle the pair by tier (docs 1 beat KEP 5). Fallback: ADR-010 D4 |
| 3 | **history_date in T2** | Drop it; defer it to R2 | The probe retrieved the line with 1 of 3 natural wordings. It's the only way to catch seed KEP-2579's date, since the model never sees release dates |
| 4 | **1 PR,** above the ~800-line alarm (estimate ~2,300 reviewable lines) | 2 stacked PRs split after T3 (recommended) | The developer's call; S08 and S09 did the same |
| 5 | **Paid calls:** ≤ US$1.00 (listed below). Credit at sitting: **US$7.17 (2026-10-11)** | — | Leaves ≥ US$6.17; R2's 3-run eval (~US$4.5) needs a top-up first |
| 6 | **Scope:** slice doc approved; bundle T2–T5; triage: drop "link the 25 old single-file KEPs" (all 25 exist only at 1.20; 0 labels; 6 of 1,290 hits); keep the other items; "KEP history dates" moves into T2; "CHANGELOG and `disabled`" is closed by decisions 7–8 | — | — |
| 7 | *(rec.)* **The CHANGELOG isn't a stage observation in Phase 1** (ADR-003 change; backlog item closed) | Parse release notes | Free text; a keyword parser misses the one known case |
| 8 | *(rec.)* **A claimed `disabled` is never compared** (ADR-003 change) | Treat it as `deprecated` | The reference has no `disabled` stage |
| 9 | *(rec.)* **claim_mismatch uses the claim of the KEP version valid at the target release** (the newest of two); one conflict per KEP per question; a claim ahead of the release counts | Each hit's own version | 2 false conflicts and 1 miss on v0's hits |
| 10 | *(rec.)* **Kind and resolution** as pinned below (ADR-010 D2) | — | ADR-003 D6 |
| 11 | *(rec.)* `HISTORY_DATE_TOLERANCE_DAYS` = 7, in config; duplicates kept once, rule first; old saved answers load with `[]`; `make eval-retrieval` prints the rule-conflict line | — | — |

**Claude's calls (overrulable):**

- **Layout:**
  - `src/orgknow/generation/conflicts.py` (new) holds:
    - the models `Conflict` and `ModelConflict` (or `ModelConflict` in `schema.py` beside `ModelAnswer`)
    - the pure functions `claim_mismatches`, `history_dates`, `pair_conflict`, `model_conflicts`
    - one function that reads the database, `rule_conflicts(conn, hits, settings)`, which makes the reads and calls the pure functions (like `retrieve.attach_authority`)
  - `src/orgknow/db/lifecycle.py`: `kep_versions_at(conn, canonical_ids, release) -> dict[str, NewestVersion]`. It returns the newest version (latest `valid_from_date`) of each KEP whose release window contains `release`; the open end counts as the latest release. It's the only new SQL.
  - Reused, not copied: `kep_gates`, the observed branch of `kep_stage`, `observations`, `list_releases`.
- **Models (pinned):**

  ```python
  ConflictKind = Literal["claim_mismatch", "history_date", "supersession", "contradiction"]
  Resolution = Literal["observed_beats_claimed", "valid_at_target", "lower_tier", "unresolved"]

  class Conflict(BaseModel):
      kind: ConflictKind
      found_by: Literal["rule", "model"]
      chunk_ids: list[int]  # rule: the hits it is about, by rank; model: [first, second] as given
      documents: list[str]  # the canonical ids of chunk_ids, first appearance first, no repeats
      summary: str          # rule: the pinned wording; model: its sentence
      resolution: Resolution
      prevails: int | None  # the winning chunk (valid_at_target, lower_tier); None otherwise

  # In the answer call's schema: comments, not docstrings (they would go to the model).
  class ModelConflict(BaseModel):
      first: int = Field(description="The id of one chunk.")
      second: int = Field(description="The id of a chunk that disagrees with it.")
      summary: str = Field(description="One sentence: what the two chunks disagree about.")
  ```

  - `ModelAnswer.conflicts: list[ModelConflict] = Field(description="Pairs of chunks whose texts disagree; empty when none.")`
  - `Answer.conflicts: list[Conflict] = []`, after `evidence`
  - `AnswerTrace.dropped_conflicts: list[ModelConflict] = []`
  - The eval's `QuestionRow.conflicts: list[Conflict] = []`, and `checks.loser_only: bool | None = None`
- **T2 rules (pinned):**
  - **Target release:** the hits' `authority.target_release` (one per question). No hit with `authority` → no rule conflicts.
  - **claim_mismatch,** per distinct KEP among the hits (`source_type == "kep"`):
    1. Take the version from `kep_versions_at` at the target release R. No version means no conflict.
    2. Its `claimed_stage` is None or `disabled` → no conflict.
    3. Its gates (`kep_gates(metadata)`) are empty → no conflict.
    4. Observed: every gate has a row at R, all high, giving one stage. Otherwise → no conflict.
    5. The claim ≠ the observed stage → one conflict:
       - `chunk_ids`: all of that KEP's hits, by rank
       - resolution: `observed_beats_claimed`; `prevails`: None
       - summary: `"{canonical_id} claims {claim} (latest milestone {lm}); the feature-gate reference at 1.{R} says {observed}."`, with `{lm}` the version's `latest-milestone` as written. When it's missing: `"{canonical_id} claims {claim}; the feature-gate reference at 1.{R} says {observed}."`
  - **history_date,** per KEP hit:
    1. Each line of its text that matches `^\s*[-*]?\s*(\d{4}-\d{2}-\d{2}):?\s+.*?\bv?1\.(\d+)\b.*\breleased\b` (case-insensitive) gives a date D and a minor N.
    2. N isn't in `releases` → skip.
    3. |D − release_date(N)| > `HISTORY_DATE_TOLERANCE_DAYS` → one conflict per (document, N, D) per question:
       - `chunk_ids`: the hits holding the line, by rank
       - resolution: `observed_beats_claimed`; `prevails`: None
       - summary: `"{canonical_id} says v1.{N} was released {D}; the releases table says {release_date}."`
  - **Order:** rule conflicts by their first chunk's rank; claim_mismatch before history_date on a tie.
- **T3 rules (pinned):** `pair_conflict(a: Hit, b: Hit, target: int, latest: int) -> tuple[ConflictKind, Resolution, int | None]`
  - **Kind:** same `canonical_id` and same `heading_path` → `supersession`; otherwise `contradiction`.
  - **Valid at the target:** some window (from, until) has from ≤ target ≤ (until, or `latest` when open).
  - **Exactly one valid** → it prevails, `valid_at_target`.
  - **Otherwise, by tier:** `authority.tier`, where None (a superseded proposal, or no authority) is worse than any tier. Different tiers → the lower number prevails, `lower_tier`. Equal tiers, both None included → `unresolved`, with `prevails` None.
- **T4 rules (pinned):**
  - **`answer(question, hits, generator, settings, rule_conflicts=())`:**
    - No hits → `[]`, and no model call.
    - Answered, or the model's own `insufficient_evidence` → the rule conflicts, then T5's model conflicts.
    - Rejected for a bad citation → the rule conflicts only (the model's output isn't trusted).
  - **Callers:** `cli.ask` and the eval runner compute `rule_conflicts(conn, hits, settings)` after `retrieve`. No network call is needed. On an ask error, the eval row keeps them in `QuestionRow.conflicts`. `ask`'s error output is unchanged.
  - **Prompt block (pinned),** after the evidence blocks and before `Question:`, only when there's at least 1 rule conflict:

    ```
    Conflicts found by code:
    - chunks 101, 102: kep:4858 claims stable (latest milestone v1.38); the feature-gate reference at 1.37 says beta. Resolved: observed beats claimed.
    ```

    - One chunk: `- chunk 205: …`.
    - The resolution phrase for `observed_beats_claimed` is `Resolved: observed beats claimed.`
  - **`ask` JSON:** `conflicts` follows `evidence`.
  - **The trace:** the generation observation logs the conflicts and `dropped_conflicts`. Not tested; see the "trace coverage" proposed addition.
- **T5 rules (pinned):**
  - **A model pair is kept** when `first ≠ second`, both ids are in the hits, and the pair isn't a duplicate. A duplicate is an unordered pair already kept, or a kept rule conflict's `chunk_ids` as a set.
  - **A dropped pair** goes to `AnswerTrace.dropped_conflicts`, and the answer is unaffected.
  - **Each kept pair** → `Conflict(found_by="model", chunk_ids=[first, second], …)`, with kind, resolution and `prevails` from `pair_conflict` at the hits' target release, in the model's order, after the rule conflicts.
  - **`loser_only`:**
    - True when, for some model conflict with `prevails` set, the answer's evidence cites the other chunk but not `prevails`.
    - False when there's an answer and no such conflict.
    - None with no answer.
  - **System prompt (pinned):**
    - The paragraph's last sentence becomes "A KEP chunk adds the status and stage the KEP claimed, with its latest milestone, and its stage at the asked-about release."
    - A new last bullet: "- If two chunks disagree (two sources, or an older and a newer version of one text), list the pair in `conflicts` with one sentence on what differs, and say so in the answer. Settle it this way: an observed stage beats a KEP's claim; a chunk valid at the asked-about release beats one that isn't; otherwise the lower tier number wins; with equal tiers, say it is unresolved. Conflicts found by code are listed after the evidence: don't list them again."
  - **KEP claim line (pinned).** When `latest-milestone` matches `^v?1\.(\d+)` and the hit has `authority`, with N its minor and T its target:
    - N < T: `claimed: implementable/alpha (latest milestone v1.22, 15 releases before 1.37)`, with "1 release" in the singular.
    - N ≥ T: `claimed: implemented/stable (latest milestone v1.38)`.
    - Otherwise, the line is unchanged: `claimed: implementable/alpha`.
    - The milestone is printed as written.
- **Settings:** `HISTORY_DATE_TOLERANCE_DAYS`, default 7, ≥ 0, listed in `.env.example`. `run.json` settings gain `history_date_tolerance_days`.
- **Eval:**
  - **Results files:** rows gain `conflicts` and `checks.loser_only`; `summary.json` gains `conflicts_rule`, `conflicts_model` and `loser_only_answers`. All optional, so old folders load.
  - **The table:** unchanged. R2 adds conflict columns.
  - **The run's summary line** ends with ` Conflicts: {n} ({r} rule, {m} model), {k} loser-only answers.`
- **Docs:**
  - `docs/architecture.md`: the conflict step between retrieval and the answer.
  - `docs/evaluation.md`: what the rule line and the smoke run show.
  - README: `conflicts` in `ask` output and `HISTORY_DATE_TOLERANCE_DAYS`.
  - Glossary: "conflict detection" and "supersession" if absent.
  - Backlog ticks.

#### Pinned: output formats

`HF_HUB_OFFLINE=1 make eval-retrieval` (authority mode, the default): S09's lines exactly, plus the rule-conflict line after the router line. Times are examples.

```
Mode: authority (candidates 20, k 60, width 100, model BAAI/bge-reranker-base@2cfc18c, max length 512, router claude-opus-5-5, slack 1, boost 1.25, demote 0.8). Answerable questions: 36.
Recall@10 0.552  Hit@10 1.000  MRR 0.813  nDCG@10 0.535
Stale rate 0.000 (0 of 100 CURRENT hits)  Temporal accuracy 0.522 (47 of 90 dated HISTORY hits)
Authority selection 1.000 (9 of 9 CURRENT questions)  CURRENT MRR 0.783
Router accuracy 0.972 (35 of 36)  Windows 7 of 9 (0 extra)  Plans: 10 current-only, 7 windowed, 19 unfiltered
Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date
Retrieve time: p50 4.91 s, p95 6.14 s (36 questions). Reranker load 7.4 s.
```

- **Counts:** the line counts conflicts (one per KEP per question) and lists the questions holding one, in file order. A kind with 0 has no list.
- **Coverage:** only the 36 answerable questions are run, so q20 and q48 (unanswerable) aren't in it.
- **Other modes:** they print the line after their authority line. Values aren't pinned.

#### Handoffs between tasks

- **T2 → T4:** `Conflict` and `rule_conflicts`.
- **T3 → T5:** `pair_conflict`.
- **T4 → T5:** `Answer.conflicts`, the `rule_conflicts` argument, the prompt block, and `QuestionRow.conflicts`.
- **If a task parks:** T2 parks → T4 and T5 park. T3 parks → T5 parks. T4 parks → T5 parks.

#### Edge cases

- **No hits:** no conflicts, and no model call. Hits without `authority` (never from `retrieve`) give no rule conflicts.
- **A KEP with no version valid at R** (created later): no claim_mismatch. Two versions valid at R (KEP-2579 at 1.24) → the newest.
- **No observed stage:** a gate with no row at R, a low row, gates that disagree, or no gates → no claim_mismatch. A claim of `disabled` or none → no claim_mismatch.
- **history_date:**
  - A minor not in `releases` (1.12 and 1.19 in KEP-614) → skipped.
  - The same line in 2 hits of one question → one conflict.
  - Within the tolerance → none.
- **Model pairs:** the same id twice, an id outside the hits, or a duplicate → dropped. A pair inside one section → supersession.
- **Model conflicts on the model's own `insufficient_evidence`:** kept. On a rejected answer: dropped, and only the rule conflicts remain.
- **CURRENT questions:** superseded text is filtered out before ranking, so no supersession pair is possible there.
- **Old results folders and saved answers:** no `conflicts` field; they load with `[]`, and the new summary fields are None.

#### Files in scope

- **New:**
  - `src/orgknow/generation/conflicts.py`
  - `tests/unit/test_conflicts.py`
  - an integration test of `kep_versions_at` and `rule_conflicts` on fixtures
  - the smoke results folder `eval/results/conflict-smoke-<UTC timestamp>/`
- **Changed:**
  - Config: `.env.example`
  - Code:
    - `src/orgknow/settings.py`
    - `src/orgknow/db/lifecycle.py`
    - `src/orgknow/generation/{schema,prompt,generator,validate}.py`
    - `src/orgknow/cli.py`
    - `src/orgknow/eval/{runner,checks,__main__}.py`
  - Results: `eval/results/ablation.md` (regenerated; adds the `conflict-smoke` row)
  - Docs:
    - `README.md`
    - `docs/{architecture,evaluation}.md`
    - `docs/learning/glossary.md`
    - `docs/backlog.md` (ticks)
  - Tests that build an `Answer`, a `ModelAnswer`, a row, a summary or the prompt
- **Not touched:**
  - `eval/golden_set/`, `eval/question_vectors/`, `eval/question_routes/`
  - migrations, `src/orgknow/retrieval/` (hits unchanged), chunking
  - every older results folder

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T2 | Rules | Unit, hand-built hits and rows: claim stable vs. observed beta at 37 → 1 conflict with the pinned summary; claim = observed → none; two versions valid at 24 (beta 22–24, stable 24–25) → the stable one; `disabled` → none; no claim → none; a gate with no row, a low row, or 2 gates giving alpha and beta → none; 3 hits of one KEP → 1 conflict holding 3 ids; a non-KEP hit → ignored; history lines: `- 2021-11-03: v1.23 Beta version released` with 1.23 released 2021-12-07 → 1 conflict (34 days); `- 2022-12-08: Kubernetes 1.26 released` → none; `- 2018-09-27 Kubernetes 1.12.0 released with Alpha SCTP support` → skipped; 7 days off → none, 8 → one | By hand; ADR-003 D2; the real lines |
| T2 | **Real hits** | `HF_HUB_OFFLINE=1 make eval-retrieval` → `Rule conflicts: 5 claim_mismatch (q16 q17 q18 q19 q32), 0 history_date` | Sitting SQL |
| T2 | DB read | Integration: `kep_versions_at` returns the newest of two versions valid at a boundary release, none for a release before the KEP's first, and the current version at the latest | By hand |
| T3 | D6 branches | Unit: same section → supersession; one valid at the target → it prevails; both valid with tiers 4 and 1 → tier 1 prevails; neither valid with tiers 6 and 6 → unresolved; a superseded proposal vs. tier 6 → tier 6 prevails; both None → unresolved. Real pairs as hand-built hits: chunk 36383 (versioning.md, tier 4, 1.36–now) vs. 7201 (version-skew page, tier 1, 1.28–now) at 37 → contradiction, `lower_tier`, prevails 7201; chunk 10420 (gate page, tier 1, 1.36–now) vs. 10419 (same section, 1.33–1.35) at 37 → supersession, `valid_at_target`, prevails 10420 | ADR-003 D6, by hand; sitting SQL |
| T4 | Every path | Unit (fake generator): answered, the model's `insufficient_evidence`, rejected for a bad citation, an eval error row → each carries the rule conflicts; no hits → `[]`; an S09 `questions.jsonl` row and `Answer` JSON load with `conflicts == []` | By hand |
| T4 | Prompt | Unit: the pinned block for 1 rule conflict with 2 chunks and for 1 with 1 chunk; no block when there's none | The contract |
| T4 | **Retrieval unchanged** | `HF_HUB_OFFLINE=1 make eval-retrieval` → S09's lines exactly (pinned above) | S09-R2 |
| T4 | Demo (paid) | `ask` on q18's question → `conflicts` holds `claim_mismatch`, `kep:4858`, "claims stable (latest milestone v1.38); the feature-gate reference at 1.37 says beta", `observed_beats_claimed` | Sitting SQL |
| T5 | Checks | Unit (fake generator): a valid pair → a model conflict with T3's kind and resolution; an id outside the hits, the same id twice, and a duplicate → dropped into `dropped_conflicts`, with the answer and its citations unchanged; `loser_only` is True when the loser is cited and the winner isn't, False when both are, None with no answer | By hand |
| T5 | Prompt | Unit: the pinned system-prompt sentences; claim lines for milestone v1.22 at 37 ("15 releases before 1.37"), v1.36 at 37 ("1 release before 1.37"), v1.38 at 37 (no "before"), `1.17` at 37 ("20 releases before 1.37"), and none or `0.0` (unchanged) | By hand (37 − 22 = 15; 37 − 17 = 20) |
| T5 | **Smoke run (paid)** | `HF_HUB_OFFLINE=1 uv run python -m orgknow.eval run --smoke --name conflict-smoke`: 13 questions, 0 errors, AC1–AC3 100%, false refusals 0; its 130 hits equal run `authority-20261011T051924Z`'s for the same questions (chunk ids by rank); rule conflicts: 2 claim_mismatch (q16, q18); model conflicts: recorded as observed | Sitting SQL; S09 run 3 |

If a pinned number differs, the task parks that item (with both numbers) and keeps the code, as in S09.

#### Break-it rules

- **T2:** take the claim from each hit's own version → the line becomes `Rule conflicts: 6 claim_mismatch (q16 q17 q18 q19 q36 q44), 0 history_date`, and the boundary-release unit test fails.
- **T3:** let the higher tier number win → the tier tests fail.
- **T4/T5:** send a bad conflict id through the citation check (`rejection_reason`) → the "answer unchanged" test fails.

#### Real-data demo

```bash
HF_HUB_OFFLINE=1 make eval-retrieval
HF_HUB_OFFLINE=1 uv run orgknow ask "What are the release stages of strict IP/CIDR validation (KEP-4858)?"
HF_HUB_OFFLINE=1 uv run orgknow ask "When was Pod Security Admission's beta released?"
HF_HUB_OFFLINE=1 uv run orgknow ask "How many Kubernetes minor releases are supported at the same time?"
HF_HUB_OFFLINE=1 uv run orgknow ask "Is KEP-2572's three-releases-per-year cadence implemented?"
HF_HUB_OFFLINE=1 uv run python -m orgknow.eval run --smoke --name conflict-smoke
```

- **Ask 1:** KEP-4858's claim_mismatch (pinned).
- **Ask 2:** a history_date conflict on `kep:2579` if the live route gives CHANGE with no window (the probe's route). The route line goes in the brief; otherwise it goes on the "Not verified" list.
- **Asks 3–4, observed:** a model pair versioning.md vs. the version-skew page (prevails: the version-skew page), and KEP-2572 vs. a docs page (prevails: the docs page). A miss goes on the "Not verified" list.
- **Briefs** include the Langfuse trace links.

#### Bundle-level check

1. **Postgres:** checked healthy at run start.
2. `make check`.
3. `make test-int`.
4. `HF_HUB_OFFLINE=1 make eval-retrieval`: the pinned lines.
5. **The smoke run:** checked as in the proof map. Then `make eval-table`: older rows unchanged, and one new `conflict-smoke` row.
6. `git status --short`: only intended files.

#### PR plan

1 PR, above the ~800-line alarm by the developer's choice (decision 4; estimate ~2,300 reviewable lines). Greptile: 1 trigger (15/50 used before the run).

#### Paid calls allowed

- **Anthropic answers:** ≤ 4 demo asks and the 13-question smoke run (≤ 17 calls).
- **Anthropic router:** ≤ 4 calls (the demo asks). The smoke run uses stored routes.
- **Voyage:** ≤ 4 requests (the demo asks). The smoke run uses stored vectors.
- **Cap:** US$1.00 for all Anthropic calls. Credit at sitting: US$7.17 (2026-10-11); check-ins show `Anthropic ~US$N left`.
- **Langfuse:** traces of the demo asks and the smoke run.
- **Hugging Face:** none (`HF_HUB_OFFLINE=1`; the reranker is cached).
- **Package installs:** none.

### Run S10-R2: the conflict set and the S10 eval (one PR, two parts)

- **Status:** planned
- **Branch:** `s10-r2-conflict-eval`
- **Tasks, in this order:**
  - **Part 1:** S10-T5b (the settle line) → S10-T6 (format, loader, metrics) → S10-T7a (Claude's draft).
  - **Pause:** S10-T7 `[human]`, the developer's sign-off, committed on this branch.
  - **Part 2 (`/run-bundle` resumes):** S10-T8 (the eval run) → the retro (`/slice-retro`, as the last commit).
- **Closes the slice:** yes, after part 2.
- **Part 1 ends** with T8 and the retro parked ("needs S10-T7, a human task"), the PR open, one Greptile review, and a check-in pointing to the sheet.
- **Goal (plain words):**
  - Write an answer key of the real disagreements among every eval question's 10 search results, with the 4 seed cases fixed in advance.
  - Score each run's conflict list against it: precision (flags that are real), recall (real conflicts flagged) and AC4 per seed.
  - Tell the answer model which release to settle conflicts at.
  - Run the paid eval 3 times, add the +conflict row, set the conflict thresholds and close S10.

#### Sitting evidence (2026-10-11)

On the dev database and the S09 run `authority-20261011T051924Z` (43 questions × 10 hits). Scratch SQL and scripts, not committed. Paid in the sitting: none.

- **Retrieval is deterministic:** a fresh retrieval of all 43 golden questions (stored vectors and routes) gave the same 10 chunk ids, by rank, as that run: 43 of 43. R1's smoke run matched it too (130 of 130).
- **The pool:** 430 hits, 335 distinct chunks, 1,935 pairs. 85 pairs share a document and section; 10 of them are pieces of one version (q02 ×4, q15 ×3, q21, q26, q31).
- **Rule conflicts on all 43 questions** (R1's merged rules): 7 claim_mismatch, on q16, q17, q18, q19, q20, q32 and q48 (KEP-4858, plus KEP-3299 on q32); 0 history_date.
- **Seeds in the fixed results:**
  - KEP-4858: q16–q20 and q48.
  - KEP-2572: q01 (the release page 7600 and `/docs/setup/release/` 6946, with KEP-2572's chunks).
  - KEP-2579's date line: in no question's results. In authority mode, q08 holds 6 KEP-2579 chunks but not "Implementation History"; R1 found it in hybrid mode.
  - versioning.md's "every three months": in no question's results.
- **versioning.md history:**
  - Its "Supported releases and component skew" section said "approximately every three months … approximately nine months" in the versions from 2021-03-15 to 2026-02-13 (releases 1.20–1.35; chunks 36362, 36369).
  - Then "every four months (three releases per year) … fourteen months" (36376).
  - Since 2026-05-28, also "four minor releases at a time" (36383), against the version-skew page's "three" (7201). q21 holds both.
- **Facts behind the seed questions:**
  - 2023's releases were 1.27 (2023-04-11), 1.28 (2023-08-15) and 1.29 (2023-12-13).
  - 1.30 ran from 2024-04-17 to end of life on 2025-07-15.
  - KEP-2579's "2021-11-03: v1.23 Beta version released" sits only in `KEP-2579: Pod Security Admission Control > Implementation History` (chunks 15293, 15356, 15419); 1.23 was released 2021-12-07.
- **Target releases:** 36 of 43 questions settle at 1.37. 7 HISTORY questions settle earlier: 1.20 ×3, 1.24, 1.27, 1.28 ×2.
- **S09's 3 authority runs:** AC1 36/36, AC2 43/43, AC3 7/7, false refusals 0 of 36 and 0 errors in each; cost $0.0317 per question.
- **Devil's advocates** (2, fresh context):
  - **Against decision 2's labels:**
    - spot-checks can't prove completeness
    - Claude labels Claude
    - the rule left q01's "every 3 months" case open
    - one-sided labels over-credit
    - S11's new hits won't be labeled
    
    Answered by decision 2's changes (a)–(d) and the known limits.
  - **Against seeds on questions known to retrieve both sides:**
    - it breaks this slice's rule ("T7 must not pick the question because it retrieves the line")
    - it hides q08's authority-mode miss
    - a probe with a fallback can't lose
    - q01 can match on the wrong disagreement
    - `replaces: []` is unchecked
    
    The recommendation changed to decision 3's C.

#### Decisions (made in the sitting, 2026-10-11)

| # | Choice | Rejected | Why |
|---|---|---|---|
| S | **1 PR for the rest of S10:** part 1 (T5b, T6, T7a) → T7 (the developer) → part 2 (T8, the retro), above the ~800-line alarm | 2 PRs; a separate R3 sitting | The developer's call; S09-R2 (PR #40) resumed on one PR the same way |
| T | **Triage:** keep R1's 2 contract facts (fixed in the retro) and "the trace doesn't log rule-found conflicts on a generation error" (→ Proposed additions). Drop R1's 3 extra tests, 4 style refactors, the smoke folder's `git_dirty` and the docstring edit | — | — |
| 1 | **Same-section pairs stay `supersession`,** even when both pieces are in one version (`pair_conflict` unchanged); T8 counts how many model pairs fall in one version | Check versions (a new database read, ~80 lines); a third kind | 10 of 85 same-section pairs share a version, and R1's smoke run flagged 0. Hits carry release windows, not versions. Matching ignores the kind |
| 2 | **Conflict set = every disagreement among each question's fixed 10 results, labeled before the runs** (ADR-007 D4), with: (a) matching by kind (a KEP claim or date label only by that rule; a two-text label only by a model pair hitting both sides); (b) the disagreement rule below, stale vs. current included; (c) precision and recall overall and split rule/model; (d) the agreement check, whose fallback judges every unmatched flagged conflict after the runs | Label the expected ones and judge the rest after the runs (the devil's advocate's pick); count anything unlabeled as wrong | Retrieval is deterministic, so the pool is known before any paid run. Part 2 stays unattended, and the labels are written before seeing the model's output |
| 3 | **AC4 end to end, on seeds fixed without looking at their results.** Seeds: q18 (KEP-4858), q01 (KEP-2572), q08 (KEP-2579's date) and new c01 "In Kubernetes 1.30, how long was a minor release supported?" (versioning.md). New c02 "When was Pod Security Admission's beta released?" is a non-seed, picked after R1's probe (disclosed). Each seed reports whether it was retrieved. The developer confirms the 2 model-found seeds' summaries. KEP-2579 is checked on its date only (`replaces: []` is in no chunk's text) | Seeds on questions known to retrieve both sides; end to end without c02 | Keeps this slice's rule; the spec applies hard gates to the finished Phase 1; it exposes q08's authority-mode miss for S11 |
| 4 | **"Settle conflicts at release 1.N." in every prompt** with a target release; checked by T8's run 1 | No change; only the 7 older-target questions | The model and code then settle at the same release (ADR-010 D2) |
| 5 | **ADR-010 D4's detector comparison runs only if the switch rule fires;** the switch counts a missed seed only when it was retrieved | Run it in T8 anyway (~100 lines, ~US$0.25); never compare | A separate detector sees the same 10 results, so it can't fix a retrieval miss |
| 6 | *(rec.)* **Conflict thresholds:** for each of precision and recall, its worst run of 3, minus one conflict (1 ÷ that run's denominator), rounded down to 2 decimals. AC4 stays a hard gate | — | S09-R2's rule |
| 7 | **Paid:** part 1 ≤ US$0.05; part 2 ≤ US$5.50. Credit at sitting: **US$11.58 (2026-10-11)** | — | Leaves about US$6.8, above the US$5 low line |

**Claude's calls** (read back; no overrules):

1. **One file in the human-owned folder:** `eval/golden_set/conflicts-v0.yaml`. Claude's draft goes in `eval/candidates/`.
2. **A side may name several sources ("any of"),** so one disagreement is one label, not one per pair.
3. **Reachable conflicts only.** A conflict is reachable when its sides are among its question's top-10 hits. Recall counts reachable conflicts only; unreachable ones (only seeds can be) are listed, and AC4 reports them as "not retrieved".
4. **New questions run in full runs only,** with the golden set. Their rows go to `conflict_questions.jsonl`, so the golden row can't change.
5. **`make eval-conflicts` (free)** is the check, the demo and T8's free gate.
6. **The table gains 3 columns.**
7. **T7a's merge rule and split rate** (pinned below).
8. **The sheet's sample** (pinned below).

#### Pinned: the conflict set (ADR-007 D4)

```yaml
version: v0
questions:                 # new questions only; golden ones are referenced by id
  - id: c01
    question: "In Kubernetes 1.30, how long was a minor release supported?"
  - id: c02
    question: "When was Pod Security Admission's beta released?"
conflicts:
  - id: k01
    question: q18          # a golden id (EVAL_GOLDEN_PATH) or a new question's id
    kind: claim_mismatch   # claim_mismatch | history_date | texts
    seed: true             # optional; false when absent
    note: "KEP-4858 claims stable (latest milestone v1.38); the 1.37 feature-gate reference says beta."
    first: [{document: "kep:4858"}]
  - id: k02
    question: q01
    kind: texts
    seed: true
    note: "KEP-2572 still claims implementable/alpha (latest milestone v1.22); the docs say three releases a year is the policy in force."
    first: [{document: "kep:2572"}]
    second: [{document: "web:/releases/release/"}, {document: "web:/docs/setup/release/"}]
```

- **Strict, like the golden file:** an unknown key is an error, and no value is converted.
- **Ids:** conflict ids are `k` + 2–3 digits; new question ids are `c` + 2–3 digits. Both unique; a new id never equals a golden id.
- **Rule kinds** (`claim_mismatch`, `history_date`): `first` holds exactly one entry, a `kep:` document, and there's no `second`.
- **`texts`:** `first` and `second`, each with at least one entry. Both sides may be the same section (old vs. new).
- **Entries** are `{document, section?}`, matched by ADR-007 D2's rule (aliases resolved; section by heading prefix; `""` is the intro).
- **Errors:** an entry twice, or one nested in another within one side; two conflicts on one question with the same kind and sides.
- **`note`:** non-empty; it quotes both values.
- **Seeds:** exactly 4.
- **The label check:** every entry matches at least one stored text, and the counts are printed.
- **The pool:** every golden question plus the file's new questions. A question with no conflict has no disagreement.
- **The 4 seeds (pinned):**
  - **q18:** `claim_mismatch` on `kep:4858`, note as above.
  - **q01:** `texts`, first `kep:2572`, second every source stating the 3-per-year policy. Its summary must be about KEP-2572's out-of-date status or the cadence not being implemented, not only its Motivation's "4 times per year".
  - **q08:** `history_date` on `kep:2579`, section `KEP-2579: Pod Security Admission Control > Implementation History`. Note: "KEP-2579 says v1.23's beta was released 2021-11-03; v1.23 was released 2021-12-07."
  - **c01:** `texts`, first `sig-release:release-engineering/versioning.md` section `Kubernetes Release Versioning > Release versioning > Supported releases and component skew`, second every source stating the ~1-year support policy at 1.30. Note: "versioning.md (2021-03-15 to 2026-02-13) says minor releases come about every three months and are supported about nine months; at 1.30 the policy was three releases a year and about a year of support." Its summary must name the three-month cadence or the nine-month support.
  - **Seed sides are written from the corpus** (SQL text search over documents stating the value), not from the seed question's results. A seed is an ordinary conflict marked `seed: true`, never repeated in the pool.

**The disagreement rule (pinned, for T7a):**

- **What counts:** two chunks disagree when they give different values for the same fact about the same thing: a number, date, release, stage, default, limit, policy, or a yes/no.
  - It counts even when each value was true at a different time (stale vs. current, e.g. KEP-1498's "every 3 months" vs. "three per year").
  - It counts between two versions of one text when the value changed (KEP-2799's planned GA 1.26 → 1.29 → 1.30).
- **What doesn't count:**
  - cosmetic edits (typos, links, formatting, author lines, checkboxes)
  - one text adding detail the other lacks
  - statements about different things
- **A KEP's claimed stage vs. the feature-gate reference** is labeled only as `claim_mismatch`, and only where ADR-010 D1's definition holds at the question's target release. The labeler checks the claim and the observed stage on its own.
- **A KEP history date vs. the releases table** is labeled only as `history_date`.
- **A gate-less KEP's out-of-date status vs. a source showing the work shipped or the policy in force** is a `texts` conflict, with the whole KEP as its side.

#### Pinned: matching and metrics (T6)

- **Reachable:** a rule-kind conflict is reachable when a top-K hit of its question matches `first`. A `texts` conflict is reachable when two different hits match, one `first` and the other `second`.
- **A flagged conflict F matches a conflict L on the same question when:**
  - L is a rule kind: F was found by the rule, F's kind equals L's, and a chunk of F matches `first`.
  - L is `texts`: F was found by the model, and F's two chunks match, one `first` and the other `second`, in either order.
  - Each chunk's document and heading path come from the row's hits, by chunk id.
- **Precision** = flagged conflicts matching at least one conflict ÷ flagged conflicts, over every row of the run (golden and new). Split by `found_by`.
- **Recall** = reachable conflicts matched by at least one flagged conflict ÷ reachable conflicts. Split into rule kinds and `texts`. Unreachable conflicts are counted and listed, never in recall.
- **AC4, per seed:**
  - `retrieved` (reachable) and `surfaced` (matched).
  - AC4 = surfaced ÷ seeds whose question ran.
  - The summary check for q01 and c01 is human, in T8's write-up.
- **Rows:**
  - An error row's kept rule conflicts count.
  - A smoke run scores only the questions it ran.
  - A folder whose `run.json` lacks `history_date_tolerance_days` (before S10) gets None for every conflict field.
- **Summary fields** (all optional, None when no conflict set or an older folder):
  - `conflict_precision`, `conflict_precision_rule`, `conflict_precision_model`
  - `conflict_recall`, `conflict_recall_rule`, `conflict_recall_texts` (all `Rate`)
  - `conflict_unreachable: int`
  - `ac4: Rate`
  - `ac4_seeds`: per seed, the conflict id, question id, `retrieved` and `surfaced`
  - The golden fields (tokens, cost, AC cells) stay golden-only.
- **New questions' rows:**
  - They use `QuestionRow` with `metrics` None and the answerable checks.
  - The run prints `Conflict questions: 2 (c01 c02), 0 errors, cost $N.` after its summary line.
- **The run's summary line** ends, after R1's conflicts part, with ` Conflict precision 0.850 (17 of 20), recall 0.800 (16 of 20 reachable), AC4 3 of 4 (q08: not retrieved).`
  - A reachable seed that wasn't matched shows as `(q01: missed)`. Several are joined by `; `.
  - No conflict set → nothing is added.
- **The table:** `Conflict prec.`, `Conflict rec.` and `AC4` after `Authority sel.`, formatted like the AC cells. Older rows show n/a.
- **No conflict file:** `make eval` prints `Conflict set: none (<path> not found).` and runs. `make eval-conflicts` exits 1.
- **`make eval-routes`** also routes, and embeds in one Voyage request, every conflict-set question lacking a route or a vector. Its Makefile comment says so.

**`HF_HUB_OFFLINE=1 make eval-conflicts` (free; prints only; stored vectors and routes; a missing one is an error naming `make eval-routes`). Pinned output on the demo sample** `tests/fixtures/conflicts/demo-sample.yaml`. The sample holds 5 conflicts, ids k01–k05 in this order:
- **the 4 seed conflicts:** k01 q18 claim `kep:4858`; k02 q01 `texts` `kep:2572` vs. [`web:/releases/release/`, `web:/docs/setup/release/`]; k03 q08 `history_date` `kep:2579` § Implementation History; k04 q21 `texts` versioning.md vs. `web:/docs/setup/release/version-skew-policy/`
- **plus:** k05 q32 claim `kep:3299`, not a seed.

```
Conflict set tests/fixtures/conflicts/demo-sample.yaml (<sha8>): 5 conflicts (4 seeds) on 43 questions (0 new). Unmatched sides: 0.
Reachable: 4 of 5 (not reachable: k03 q08).
Seeds retrieved: 3 of 4 (not retrieved: k03 q08).
Rule-found: 7 flagged (q16 q17 q18 q19 q20 q32 q48); precision 0.286 (2 of 7); recall 1.000 (2 of 2 reachable).
```

With every conflict reachable, the line is just `Reachable: 5 of 5.` The flagged questions are listed in run order: the golden file's order, then the new questions.

#### Pinned: the settle line (T5b)

- **User prompt:** `Settle conflicts at release 1.{target}.` on its own line, after the evidence (and after the code-found conflicts block when there is one), before `Question:`. The target is the hits' `authority.target_release`; no hit with `authority` → no line.
- **System prompt:** "a chunk valid at the asked-about release beats one that isn't" becomes "a chunk valid at the release named before the question beats one that isn't".

#### Pinned: T7a's draft

- **The pool's hits:**
  - Golden questions: from `authority-20261011T051924Z/questions.jsonl` (identical to today's retrieval, 43 of 43).
  - c01 and c02: from the same retrieval after `make eval-routes`, dumped by a scratch script (not committed).
- **3 independent passes:**
  - Pass 1 is the T7a builder.
  - Passes 2 and 3 are 2 fresh general-purpose subagents started by the main session. Each gets `CLAUDE.md`, the disagreement rule and the hits, and sees no other pass.
  - Each reads every hit's stored text and writes a pass file in the format, without seeds: `eval/candidates/conflicts-v0-passes/pass{1,2,3}.yaml`.
- **Merge:**
  - A disagreement found by 2 or more passes (same question, kind and documents; sides are the union of what they listed) goes into `eval/candidates/conflicts-v0-draft.yaml`, with the 4 seeds added.
  - One found by only 1 pass is "disputed": on the sheet, not in the draft.
  - **Split rate** = disagreements not found by all 3 passes ÷ disagreements found by any. It's printed in the sheet's header and the check-in.
- **The sheet,** `eval/candidates/conflicts-v0-spot-check.md`, has excerpts copied from stored text by a script (not committed, as S06-T5). Its contents:
  1. the 4 seeds
  2. 1 random non-seed of each kind (`claim_mismatch`, `history_date`, `texts` within one document, `texts` across two), by `random.Random(20261011)`
  3. 1 more random conflict
  4. every disputed disagreement
  5. 1 whole question, `random.Random(20261011).choice` over the 45 pool ids sorted, with its 10 hits' excerpts and the draft's conflicts for it
  6. a sign-off block: ✅/❌ per item, keep/drop per disputed one, "missing: none" or a list for the whole question, and the console balance in USD
- **The agreement check:** a split rate above 0.20, or a disagreement the developer finds missing in the whole question, makes precision provisional. Then T8's write-up gives each unmatched flagged conflict a verdict and reports precision both ways, and the threshold uses the judged one.

#### Pinned: T8

1. **Free gate:**
   - Postgres; `make check`.
   - `HF_HUB_OFFLINE=1 make eval-retrieval` prints the S09/R1 lines exactly (R1's "Pinned: output formats").
   - `HF_HUB_OFFLINE=1 make eval-conflicts` on the verified file: `Unmatched sides: 0`, and the rule-found line equals the counts taken by hand from the file.
2. **Credit:** the balance from the sheet, else US$11.58 minus part 1's spend. Under US$5.50 → park.
3. **Run 1:** `HF_HUB_OFFLINE=1 uv run python -m orgknow.eval run --name conflict`. It must show 0 errors, AC1 36/36, AC2 43/43 and AC3 7/7. Otherwise park runs 2–3 and keep the folder.
4. **Runs 2 and 3,** then `make eval-table`.
5. **`docs/evaluation.md`, in the "Conflicts" section:**
   - the row vs. `authority`: retrieval identical, AC1–AC3, false refusals, p95, cost (new questions included)
   - precision and recall per run, overall and split
   - AC4 per seed per run, `retrieved`/`surfaced`, with q01's and c01's summaries verbatim for the developer to confirm
   - every unmatched flagged conflict with Claude's verdict
   - the agreement check's outcome
   - how many model pairs fall in one version (decision 1)
   - loser-only answers
   - ADR-010 D4's switch rule (retrieved seeds only) and its KEP-2572 fallback check
   - pass or fail against AC7's improvement rule
6. **Thresholds** in the product spec, by decision 6.

#### Handoffs between tasks

- **T6 → T7a:** the format, the loader, `make eval-conflicts`, and `make eval-routes` for new questions.
- **T7a → T7:** the draft, the pass files and the sheet.
- **T7 → T8:** the verified file and the balance.
- **T5b → T8:** the prompt T8 measures.
- **If a task parks:** T6 parks → T7a parks, and part 2 can't start. T5b parks → T8 parks.

#### Edge cases

- **Hits and flags:** a question with no conflict is labeled "none", so every flagged conflict on it counts against precision. A row with no hits flags nothing.
- **Mismatched model pairs:** a model pair repeating a code-found claim (a KEP chunk with its gate page) matches no conflict and counts against precision; the prompt says not to list it.
- **One flag, two labels:** a pair matching two conflicts counts once in precision and credits both in recall (a known limit, like ADR-007's "every version of a section").
- **Seeds that search misses:** q08 likely reports "not retrieved". c01's route and hits are unknown until part 1; both are reported, never tuned.
- **Smoke runs:** `make eval-smoke` runs no new questions. AC4 counts the seeds whose question ran (q01, q18).

#### Files in scope

- **New:**
  - `src/orgknow/eval/conflicts.py`
  - `tests/unit/test_conflict_set.py`
  - an integration test of the label check
  - `tests/fixtures/conflicts/demo-sample.yaml` and small loader fixtures
  - `eval/candidates/conflicts-v0-draft.yaml`, `eval/candidates/conflicts-v0-passes/`, `eval/candidates/conflicts-v0-spot-check.md`
  - **Part 2:** 3 `eval/results/conflict-<UTC>/` folders, and the developer's `eval/golden_set/conflicts-v0.yaml` (T7)
- **Changed:**
  - **Config:** `.env.example`; `Makefile`
  - **Code:** `src/orgknow/settings.py` (`EVAL_CONFLICTS_PATH`); `src/orgknow/eval/{runner,table,__main__}.py`; `src/orgknow/generation/prompt.py`; tests that build a summary, the table or the prompt
  - **Stored inputs:** `eval/question_vectors/voyage-4-large.json` and `eval/question_routes/claude-opus-5-5.json` (c01, c02 added)
  - **Docs and results:**
    - `README.md`
    - `docs/evaluation.md`
    - `docs/learning/glossary.md` ("conflict set")
    - `docs/product-spec.md` (T8)
    - `docs/backlog.md` (ticks)
    - this slice doc (the retro)
    - `docs/learning/S10-conflict-detection.md` (the retro)
    - `eval/results/ablation.md` (part 2)
- **Not touched:**
  - `eval/golden_set/v0.yaml`
  - `eval/golden_set/` by Claude
  - `src/orgknow/retrieval/`
  - migrations and chunking
  - every older results folder (no `make eval-resummarize` in this run)

#### Proof map

| Task | Done when / rule | Proof | Expected values from |
|---|---|---|---|
| T5b | The line | Unit: the line at 1.37 after the evidence, and after the conflicts block when present; 1.20 for a 1.20 target; no line without `authority`; the system prompt's new sentence | The contract |
| T6 | Matching | Unit, on hand-built rows:<br>• claim label vs. its rule conflict ✓, vs. a model pair (the KEP with its gate page) ✗, vs. a `history_date` on the same KEP ✗<br>• `texts` label vs. a pair in either order ✓, vs. 2 chunks matching `first` only ✗, vs. a rule conflict ✗<br>• "any of" second side ✓<br>• same-section label: 2 different hits ✓, 1 hit → not reachable | By hand |
| T6 | Metrics | Unit: 2 reachable conflicts (1 claim, 1 `texts`) + 1 unreachable seed; flags: rule ✓, model ✓, model ✗ → precision 2/3 (rule 1/1, model 1/2), recall 2/2 (rule 1/1, texts 1/1), unreachable 1. AC4 with 4 seeds (surfaced, missed, not retrieved, surfaced) → 2 of 4 `(q…: missed; q…: not retrieved)`. A smoke subset leaves unrun questions out; a pre-S10 summary loads with None | By hand |
| T6 | Loader | Unit: unknown key; bad kind; a rule kind with `second` or a non-KEP `first`; `texts` without `second`; an empty side; 3 or 5 seeds; an unknown question id; duplicate ids; a new id equal to a golden id; a nested entry; a duplicate conflict → one error line each. Integration: an entry matching 0 texts → error; an alias resolves | By hand |
| T6 | **Real data** | `HF_HUB_OFFLINE=1 EVAL_CONFLICTS_PATH=tests/fixtures/conflicts/demo-sample.yaml make eval-conflicts` → the pinned lines | Sitting evidence |
| T6 | Nothing else moves | `HF_HUB_OFFLINE=1 make eval-retrieval` → the S09/R1 lines exactly; `make eval-table` → older rows' cells unchanged, 3 new columns n/a | R1 |
| T7a | The draft | `EVAL_CONFLICTS_PATH=eval/candidates/conflicts-v0-draft.yaml HF_HUB_OFFLINE=1 make eval-conflicts`: `Unmatched sides: 0`; every non-seed conflict reachable; the seeds' retrieval as observed; the split rate; the sheet built by script | Stored text |
| T8 | Gate, run 1, row | As pinned in "T8" above | S09's row; the verified file |

If a pinned number differs, the task parks that item with both numbers and keeps the code, as in R1.

#### Break-it rules

- **T6:** let one chunk satisfy both sides of a `texts` conflict → the "two different chunks" test fails.
- **T6:** count unreachable conflicts in recall → the metrics test fails.
- **T5b:** drop the settle line → the prompt test fails.

#### Real-data demo

```bash
HF_HUB_OFFLINE=1 EVAL_CONFLICTS_PATH=tests/fixtures/conflicts/demo-sample.yaml make eval-conflicts
make eval-routes
HF_HUB_OFFLINE=1 EVAL_CONFLICTS_PATH=eval/candidates/conflicts-v0-draft.yaml make eval-conflicts
```

`make eval-routes` is paid: c01 and c02 only. Part 2's demo is T8's runs.

#### Bundle-level check

- **Part 1:**
  1. Postgres healthy at run start.
  2. `make check`.
  3. `make test-int`.
  4. `HF_HUB_OFFLINE=1 make eval-retrieval`: the pinned lines.
  5. `make eval-conflicts` on the sample (pinned) and on the draft (`Unmatched sides: 0`).
  6. `make eval-table`: older rows unchanged.
  7. `git status --short`: only intended files.
- **Part 2:** the same, plus T8's 3 runs and the new `conflict` row.

#### PR plan

1 PR (decision S), above the ~800-line alarm. The estimate is about 1,500 reviewable lines, excluding the draft, the pass files, the sheet, the results folders, and the slice doc and ADRs approved here.
- It opens at the end of part 1; part 2 adds to it.
- Greptile: 1 trigger, after part 1 (16/50 before the run). No re-review for part 2's results and docs.

#### Paid calls allowed

- **Part 1:** `make eval-routes` for c01 and c02: at most 2 router calls and 1 Voyage request. Cap US$0.05.
- **Part 2:** 3 runs of 45 answer calls (43 golden + c01, c02) on stored vectors and routes: 0 router calls and 0 Voyage requests. Cap US$5.50 (estimate ~US$4.7).
- **Credit at sitting:** US$11.58 (2026-10-11). Check-ins show `Anthropic ~US$N left`.
- **Langfuse:** none (the eval isn't traced). **Hugging Face:** none (`HF_HUB_OFFLINE=1`). **Package installs:** none.

## Retro (fill in at the end)

- **Shipped (with numbers):**
- **Surprises:**
- **What didn't work / negative results:**
- **Do differently next slice:**
- **Slice brief:** `docs/learning/S10-conflict-detection.md`
