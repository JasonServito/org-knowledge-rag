# ADR-003: Source types, authority tiers, and status taxonomy

- **Status:** Accepted (2026-10-01), amended on the S02 spike's evidence and in the S09-R1 (2026-10-09) and S09-R2 (2026-10-10) sittings. See the three "Changes" tables at the end. The weights were set on golden set v0 (S09-R2); v1 is their clean test.
- **Date:** 2026-09-22
- **Blueprint refs:** §15, §16; readiness gap #4
- **Builds on:** validation gate §5.3 (first-draft tiers), ADR-002
- **Evidence:** `docs/research/corpus-spike-report.md` (cited below as "spike §N")

## Context

The gate proposed a 7-tier authority list. Two problems prevent using it as-is:

1. **Two of its tiers are keyed on `kep.yaml` status, which is unreliable.** Examples: KEP-2572 still claims alpha; KEP-4858 claims GA before its release. Tiering on the claim would rank stale proposals as authoritative.
2. **Authority depends on the question.** For WHY, a KEP's Motivation section beats the current docs, which rarely explain rationale. Blueprint §15 already says this. A single total order can't express it.

## Decision

### D1. Source types

| `source_type` | From |
|---|---|
| `docs_page` | website `content/en/docs` |
| `release_record` | CHANGELOG sections; the deprecation guide and release pages in docs |
| `feature_gate_reference` | The feature-gates reference, parsed into stage ranges per gate. Up to 1.28 it's tables on one page; from 1.29 it's one file per gate with a `stages:` list (spike §6 N). |
| `kep` | KEP README, with `kep.yaml` attached as metadata. The YAML is not a separately retrievable document. |
| `blog_post` | website blog |
| `governance_doc` | `community`, `sig-release` |
| `discussion` | GitHub issues, PRs, Discussions (Phase 2) |

### D2. Effective status

For any KEP or feature, compute `effective_stage`:

1. `observed_stage` for the release in question (from the feature-gate reference only, read from that release's own snapshot), else
2. `claimed_stage` from `kep.yaml`, with `status_confidence = low`, else
3. null: the stage is unknown.

Observations live in an `observed_lifecycle` table: one row per gate × minor release, named as that release names the gate. No range covers the release → no row. A KEP is observed through its `kep.yaml` gates: only when every gate it names has a row at the release, all high and giving one stage; otherwise step 2 (S09-R2).

A missing `claimed_stage` means **no claim**. That's a separate state from a low-confidence claim, and it never raises `claim_mismatch`. 76 KEP metadata versions have no stage (spike §7 R).

When `observed ≠ claimed`, emit a `claim_mismatch` flag. The conflict detector consumes it. The flag is never silently resolved in the index.

**The feature-gate reference is an observation that can be wrong.** Its two formats agree for 287 of the 293 gates they share, over their whole history. But the `EventedPLEG` revert appears only in the CHANGELOG, and later files rewrite earlier ranges (spike §6 O). So:
- the CHANGELOG is needed too, and a disagreement between the two is conflict evidence (D6). Deferred to S10: its conflict check adds the CHANGELOG, and how a claimed `disabled` compares (S09-R2)
- 2+ stages at R (a change at a patch release within R included), or an unparseable bound → no stage, `status_confidence = low`. One value outside the vocabulary → kept as written, low. The parser never picks one range.

### D3. Base authority tiers (1 = highest)

| Tier | Source |
|---|---|
| 1 | `docs_page` or `feature_gate_reference` |
| 2 | `release_record` |
| 3 | `kep`, where one of its gates has an observation at any release up to the target release, or its status is implemented |
| 4 | `governance_doc` |
| 5 | `kep`, otherwise |
| 6 | `blog_post`. Dated and time-bound. Authoritative for its date, not for "now". |
| 7 | `discussion` |
| — | `kep` that is withdrawn, rejected or replaced: kept, no tier, marked `superseded_proposal` |

Tiers go by source type, with a KEP's set by its gates and status (S09-R2). Validity stays separate: the filters in D4, and D4's CURRENT boost needs "valid at the latest release".

### D4. Mode-dependent adjustments

Multipliers apply after the reranker, on its probability: hits sort by sigmoid(score) × multiplier, ties in the reranker's order. Boost ×1.25, demote ×0.8, — = neutral; the values live in config. A separate `authority` retrieval mode (temporal + multipliers) applies them (S09-R2).

| Mode | Boost | Demote | Filter |
|---|---|---|---|
| CURRENT | Tiers 1–2 valid at the latest release | Blog | Prefer versions valid at the latest release; keep superseded ones only as conflict evidence |
| HISTORY | — (validity matters more than tier) | — | Hard filter on the validity window, with a small slack of ±1 release |
| CHANGE | `release_record` | — | Retrieve per window end, then merge. Deferred: no filter until a golden question names a window (S09-R1) |
| WHY | `kep` Motivation/Alternatives sections, blog, governance | `feature_gate_reference` | No temporal filter by default |
| UNANSWERABLE | (detected by the evidence grader, not by routing) | — | — |

### D5. Status vocabularies

| Field | Values |
|---|---|
| `version_status` (per document version) | `current` / `superseded` / `removed` (absent from the latest snapshot) |
| `lifecycle_stage` (per feature × minor release) | `alpha` / `beta` / `stable` / `deprecated` / `removed`. A stage change at a patch release isn't keyed separately; it sets `status_confidence = low` (D2). |
| `claimed_stage` (KEP) | `alpha` / `beta` / `stable` / `deprecated` / `disabled` / `removed`: the KEP template's six values, which the enhancements validator also accepts. Null = no claim. |
| `claimed_status` (KEP) | provisional / implementable / implemented / deferred / rejected / withdrawn / replaced. All values in the spike were in vocabulary (spike §7 R). |
| Flags | `claim_mismatch`, `status_confidence` (high/low), `superseded_proposal` |

**Synonyms and unknown values:** `GA` → `stable` is the only synonym, applied to both KEP claims and the feature-gate tables. Any other unknown value is stored as written and flagged, not mapped. Examples: the table typos `Derecated` and `True` (spike §6 N).

### D6. Precedence for conflicting claims (input to §16)

1. Observed beats claimed.
2. Within the same validity window, a lower tier number wins.
3. Across windows, the version valid for the question's target time wins. Other versions become `historical_context`.
4. If two sources of the same tier and the same window disagree, the conflict is **unresolved**. Surface it; never pick one.

## Consequences

- The multipliers and the synonym list live in config so ablations can vary them. Tiers are a fixed rule by source type (D3).
- Two golden-set metrics get defined inputs from this ADR:
  - `authority_selection_accuracy` (defined in the S09-R2 change table)
  - `stale_result_rate`
- The four gate conflict cases seed the §16 conflict test set: KEP-2572, `versioning.md`, KEP-2579 `replaces: []`, KEP-4858.
- **Known limit:** keying `lifecycle_stage` by minor release can't say "beta in 1.28.0–1.28.5, alpha from 1.28.6" (`EventedPLEG`). It only flags that the release is ambiguous.
- **Deferred to S10** (S09-R2 sitting): how the CHANGELOG's release notes become `observed_stage` values, and how a claimed `disabled` compares with an observed stage. S10's conflict check adds both.

## Open (resolve during Stage 6, not blocking now)

- ~~Does the feature-gates page give a reliable stage-per-version table for every gate in scope?~~ **Answered by the spike:** yes, every gate has stage ranges in every release, and the two formats agree for 98% of the gates they share. It's an observation to check, not ground truth (D2; spike §6).
- Should blog tier rank above `governance_doc` for date-bounded questions? Test this empirically (S09).

## Changes from the S02 spike (2026-10-01)

Each change was decided by the developer in S02-T6.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D1 `feature_gate_reference` | "Verify its format" | Two formats, parsed into stage ranges | spike §6 N |
| D2 | Observed, else claimed | Observed from R's own snapshot, else claimed, else unknown. No claim ≠ low confidence. Ambiguous or patch-level ranges set low confidence. | spike §6 O, §7 R |
| D5 `claimed_stage` | (no row) | The template's six values, including `disabled` | KEP-4004 uses `disabled`, valid under the template and validator (spike §7 R) |
| D5 synonyms | "normalized from typos" | `GA` → `stable` only; other unknown values flagged | KEP-1611's `GA` at 7 snapshots; the feature-gate tables use `GA` (spike §6 N, §7 R) |
| D5 `lifecycle_stage` | per feature × release | per feature × minor release; patch changes flagged | `EventedPLEG`, `DisableNodeKubeProxyVersion` (spike §6 N–O) |
| Open question 1 | open | answered | spike §6 |

## Changes from the S09-R1 sitting (2026-10-09)

Decided by the developer in the S09-R1 sitting; the evidence is in `docs/slices/S09-temporal-authority.md`, run S09-R1.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D4 CHANGE filter | Retrieve per window end, then merge | The same, deferred: CHANGE gets no filter until a golden question names a window (a proposed addition) | None of v0's 9 CHANGE questions names a release or year, so the plan can't be measured |

## Changes from the S09-R2 sitting (2026-10-10)

Decided by the developer in the S09-R2 sitting; the evidence is in `docs/slices/S09-temporal-authority.md`, run S09-R2. Three devil's-advocate reviews argued against the recommendations first.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D2 observation | "`observed_stage` for the release in question (from the CHANGELOG or the feature-gate reference, read from that release's own snapshot)" | From the feature-gate reference only, in an `observed_lifecycle` table: one row per gate × minor release, from that release's own snapshot, named as that release names the gate. No range covers the release → no row. 2+ stages, or an unparseable bound → no stage, `status_confidence = low`. One value outside the vocabulary → kept as written, low | 3,295 rows over 1.20–1.37, 35 of them low |
| D2 CHANGELOG, and a claimed `disabled` | S09 decides how the release notes become `observed_stage`, and how `disabled` compares | Deferred to S10: its conflict check adds the CHANGELOG (e.g. the `EventedPLEG` revert) and the `disabled` comparison | The reference covers every gate at every release (spike §6 N); release notes are free text |
| D2 effective stage | Observed, else claimed (low), else unknown | The same, for a KEP through its `kep.yaml` gates: observed only when every gate it names has a row at the release, all high and giving one stage; otherwise the claim, low | Gates disagree in 25 of 1,918 KEP × release pairs; "every gate it names has a row": resume decision R3d |
| D3 tiers 1–2 | Tier 1 "valid for the target release"; tier 2 "for the target release" | Tier by source type: docs page and feature-gate reference 1, release record 2, governance doc 4, blog 6. Validity stays separate: the filters (D4), and D4's CURRENT boost needs "valid at the latest release" | Same ranking on v0 as tiers that depend on validity; every citation gets a tier (AC1) |
| D3 KEP tiers | Tier 3: "`effective_stage` has shipped, or status is implemented and consistent"; tier 5 otherwise | Tier 3 when one of its gates has an observation at any release up to the target release, or its status is implemented; tier 5 otherwise. Withdrawn, rejected or replaced: no tier, "superseded proposal" | 42 of 65 gated KEPs have no observation at 1.37 (gates removed after GA), so "observed at the target" would demote shipped KEPs. With only the reference observed, "consistent" can't fail when nothing is observed |
| D4 placement | Multipliers "applied after RRF" | After the reranker, on its probability: sort by sigmoid(score) × multiplier, ties in the reranker's order; a separate `authority` retrieval mode (temporal + multipliers) | The reranker re-sorts the whole fused pool, so multipliers after RRF do nothing; its raw scores can be negative |
| D4 values | "Starting multipliers, to be tuned" (no numbers) | Boost ×1.25, demote ×0.8, in config. Rows used: CURRENT (boost tiers 1–2 valid at the latest release; demote blogs), CHANGE (boost release records), WHY (boost KEP Motivation/Alternatives sections, blogs, governance; demote the feature-gate reference); HISTORY none | v0 prototype: MRR 0.759 → 0.813, Recall@10 0.560 → 0.552; ×1.5 gives the same; +2 on the raw score gives MRR 0.783. Devil's advocate: strong (66 of 228 reorderings jump more than 2 logits) and set on v0 |
| Consequences: `authority_selection_accuracy` | Named | Over the golden CURRENT questions whose labeled documents span 2+ tiers, the share whose first labeled top-10 hit has the best label tier; CURRENT-question MRR is reported beside it, because the same tier code drives the weights and the metric | Flipped tiers lift the metric 3 → 6 of 9 but lower CURRENT MRR (0.637 → 0.628); real tiers: 5 → 9 of 9, 0.783 |
| Consequences, config | "Tiers and multipliers live in config so ablations can vary them. So does the synonym list." | The multipliers and the synonym list live in config so ablations can vary them; tiers are a fixed rule by source type (D3) | resume decision R3b |
