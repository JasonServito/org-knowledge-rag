# ADR-010: Conflict detection method

- **Status:** Accepted (2026-10-11, decided in the S10-R1 sitting); changed in the S10-R2 sitting and after S10-T8's run 1 (below)
- **Date:** 2026-10-11
- **Blueprint/spec refs:** §16, §18; product spec must-have 6, AC4, AC7; ADR-003 D2, D6; ADR-006 D2
- **Evidence:** `docs/slices/S10-conflict-detection.md`, run S10-R1 ("Sitting evidence"). Two devil's-advocate reviews argued against the recommendations first.

## Context

- **The evidence disagrees, and nothing records it.** Since S09-T6 the prompt shows each KEP's claim and observed stage, and q18's answer says in prose that KEP-4858 claims stable while 1.37 observes beta. AC4 (a hard gate) needs the answer to surface the conflict on 4 seed cases. Spec must-have 6 names `claim_mismatch` and cross-version supersession.
- **Stored facts can be compared by code; texts can't.** On v0's 43 questions (authority mode, 10 hits each), old and new versions of one section appear together 75 times in 24 questions. Most of the diffs are cosmetic: typos ("pear" → "per"), author lines, table-of-contents links, checkboxes. About a dozen change meaning: a gate's stage alpha → beta, kubelet skew n-2 → n-3. A rule can't tell them apart.
- **Two documents can disagree,** e.g. `versioning.md` (1.36+) "four" minor releases supported vs. the version-skew page's "three". Only something that reads the text sees it.
- **Budget:** the answer call costs $0.032 per question at p95 14.9 s, against Phase 1 ceilings of $0.06 and 23 s. A separate model call over the same 10 hits would cost about $0.022 more, bringing the total to $0.054 with an estimated p95 of 20–23 s, which leaves S11 almost nothing.
- **One bad id already rejects a whole answer** (ADR-006 D2's citation check): an answer citing a chunk it wasn't given becomes `insufficient_evidence`.

## Decision

### D1. Code compares stored facts; the answer model reads texts

- **Rule-found conflicts,** computed by code on each question's hits before the answer call:
  - `claim_mismatch` (ADR-003 D2): a KEP's claimed stage, taken from **its newest version valid at the question's target release**, vs. its observed stage there. "Observed" means every gate the KEP names has one high row at that release giving one stage. A claim that runs ahead of the release still counts: KEP-4858 claims stable for v1.38 while 1.37 says beta. A claimed `disabled` is never compared (ADR-003 D2). One conflict per KEP per question.
  - `history_date`: a KEP line "YYYY-MM-DD: … v1.N … released" whose date differs from the `releases` table's date for 1.N by more than `HISTORY_DATE_TOLERANCE_DAYS` (7). Limits, stated plainly: the corpus holds 5 such lines; 3 name a release in the table, and 1 is wrong (KEP-2579, 34 days early). In the sitting, 1 of 3 natural wordings retrieved that line, at rank 9.
- **Model-found conflicts:** the existing answer call (ADR-006) gets a `conflicts` field in its structured output, a list of pairs of chunk ids whose texts disagree, each with one sentence on what differs. Two documents, or an older and a newer version of one text. The rule-found conflicts are shown to it after the evidence, so it doesn't repeat them.
- **Out-of-date KEP status** (seed KEP-2572: implementable/alpha, latest milestone v1.22, no feature gate) isn't a rule. Instead, a KEP block's claim line shows its latest milestone and, when that milestone is older than the target release, how many releases older it is ("latest milestone v1.22, 15 releases before 1.37"). The model can then pair the KEP with the docs that show the policy in force.

### D2. Code resolves every conflict by ADR-003 D6

- **Kind:** `claim_mismatch` and `history_date` from the rules. For a model pair: same document and heading path → `supersession`, otherwise `contradiction`.
- **Resolution:**
  - Rule conflicts → `observed_beats_claimed`: the observed stage, or the release date, wins.
  - A pair → if exactly one chunk has a release window containing the target release, it prevails (`valid_at_target`). Otherwise, if the tiers differ, the lower tier number prevails (`lower_tier`); a superseded proposal, which has no tier, loses to any tier. Otherwise `unresolved`.
- **The prompt states the same rules and the release they settle at** ("Settle conflicts at release 1.N." before the question), so the answer text and the list agree.

### D3. Output and checks

- **Every answer carries `conflicts[]`:** kind, found by (rule or model), chunk ids, documents, a one-sentence summary, the resolution, and the prevailing chunk id.
- **Rule-found conflicts are attached on every path:** an answer, a model's `insufficient_evidence`, an answer rejected for a bad citation, and the eval's error row.
- **Conflict ids are checked on their own.** A pair naming a chunk outside the retrieved set, the same chunk twice, or a duplicate of a kept conflict is dropped and logged in the trace. It never rejects the answer.
- **The eval flags an answer that cites only the losing side** of a resolved model-found pair: it cites the losing chunk but not the prevailing one.
- **The list is measured against conflict set v0** (ADR-007 D4): precision, recall and AC4 per seed.

### D4. When to change course

- **Switch rule:** if the model misses a model-found seed that search retrieved, in any of S10-T8's 3 runs, or 2+ answers cite only the losing side, a later run adds a separate detector call on a cheaper model. A seed that search missed doesn't count: a separate detector sees the same 10 results.
- **The one-off comparison** (~$0.25) runs only if the switch rule fires, as the first step of that later run.
- **KEP-2572 fallback:** if S10-T8 misses seed KEP-2572 in any run, a later run adds a rule that flags a KEP still claiming an in-progress status 2+ releases past its latest milestone. It's a small pure function, much cheaper than the switch.

## Alternatives considered

| Option | Why not |
|---|---|
| Rules only (every old/new version pair is a conflict) | Flags ~60 cosmetic edits in 24 of 43 questions, and can't see two documents disagreeing |
| A separate model call before the answer | +$0.022 per question ($0.054 of $0.06) and an estimated p95 of 20–23 s of 23 s. Kept as the switch rule's fallback |
| A stale-claim rule for KEP-2572 | One source against the clock: of the 15 KEPs it flags at 1.37 (the same 15 at thresholds 2–4), the corpus shows the work shipped for only 6. "Unresolved" would change D6's meaning. Kept as the fallback in D4 |
| The CHANGELOG as a stage observation (ADR-003 D2's deferral to S10) | Release notes are free text (362 lines name a gate with a stage word), and the one known disagreement, the EventedPLEG revert, doesn't even say "feature gate". Dropped for Phase 1 (ADR-003 S10-R1 change) |
| Reusing the citation check for conflict ids | One bad conflict id would turn an answer into a false refusal and lose the rule-found conflicts |

## Consequences

- **Conflict detection is measured only through answers.** Changing the model-found part means a paid eval (~$4 for 3 runs). The rule-found part is free to check, since `make eval-retrieval` prints it.
- **Retrieval is unchanged:** the same hits, scores and order. CURRENT questions can't show old vs. new, because superseded text is filtered out before ranking (ADR-003 D4).
- **The model's conflict recall is unknown until S10-T8.** AC4 is end to end, on 4 seeds fixed without looking at their results: q18 (KEP-4858), q01 (KEP-2572), q08 (KEP-2579's date) and c01 (`versioning.md`'s "every three months"). Each seed reports whether search retrieved it; KEP-2579 is checked on its date only.
- **S11's grader** sees the rule-found conflicts before the answer, but not the model-found ones. Revisit with S11's design.
- **Revisit triggers:** the switch rule (D4); a new source type with stage claims; the S11 graph.

## Changes from the S10-R2 sitting (2026-10-11)

Decided by the developer in the S10-R2 sitting; the evidence is in `docs/slices/S10-conflict-detection.md`, run S10-R2. A devil's advocate argued against the AC4 recommendation first, and it changed.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D2, "the prompt states the same rules" | The prompt says a chunk valid at "the asked-about release" wins, but only KEP chunks show that release | The prompt adds "Settle conflicts at release 1.N." before the question, and the rule points to it | 7 of v0's 43 questions settle before 1.37 (1.20 ×3, 1.24, 1.27, 1.28 ×2); code always used the target, so only the prose could differ (Greptile on PR #42) |
| D3, how the list is measured | (unstated) | Against conflict set v0 (ADR-007 D4): precision, recall and AC4 per seed | — |
| Consequences, AC4's seeds | "AC4's seeds split between rules (KEP-4858, KEP-2579) and the model (`versioning.md`, KEP-2572)" | AC4 is end to end, on questions fixed without looking at their results: q18 (KEP-4858), q01 (KEP-2572), q08 (KEP-2579's date) and c01 (versioning.md's "every three months", "In Kubernetes 1.30, how long was a minor release supported?"). Each seed reports whether search retrieved it. KEP-2579's `replaces: []` is in no chunk's text, so only its date is checked | q08 doesn't retrieve KEP-2579's date line in authority mode (hybrid did). Picking questions that do would break the slice's rule; the spec's hard gates apply to the finished Phase 1 |
| D4, the switch rule | "If the model misses a model-found seed in any of S10-T8's 3 runs …" | It counts a missed seed only when search retrieved it (a separate detector sees the same 10 results) | — |
| D4, the one-off comparison | "Decided in the S10-R2 sitting" | Only if the switch rule fires, as the first step of that later run | ~100 lines of new code and ~US$0.25 for data needed only then |

## Changes after S10-T8's run 1 (2026-10-12)

Decided by the developer after run 1 missed its AC3 gate; the evidence is in `docs/slices/S10-conflict-detection.md`, run S10-R2, "Decisions after run 1". A devil's advocate argued against the recommendation first.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D1, out-of-date KEP status | The claim line shows the KEP's latest milestone, plus how many releases older it is when older than the target ("latest milestone v1.38" when it isn't); the `claim_mismatch` summary repeats the milestone | The milestone shows only when it is older than the target release, in both places. A milestone at or after the target is a plan, not evidence of a release, and is left out | Run 1 answered unanswerable q48 ("In which release will StrictIPCIDRValidation graduate to GA?") with "GA being targeted for Kubernetes 1.38", from KEP-4858's "(latest milestone v1.38)": AC3 6/7. Its answer already called that "only a planned target", so marking the milestone as a plan was rejected. The stale-KEP signal D1 added it for (KEP-2572, v1.22) is unchanged |
