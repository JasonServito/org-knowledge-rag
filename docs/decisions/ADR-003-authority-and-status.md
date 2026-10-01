# ADR-003: Source types, authority tiers, and status taxonomy

- **Status:** Accepted (2026-10-01), amended on the S02 spike's evidence. See "Changes from the S02 spike". The tiers and weights are still hypotheses, to be tuned against the golden set (S09).
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

1. `observed_stage` for the release in question (from the CHANGELOG or the feature-gate reference, read from that release's own snapshot), else
2. `claimed_stage` from `kep.yaml`, with `status_confidence = low`, else
3. null: the stage is unknown.

A missing `claimed_stage` means **no claim**. That's a separate state from a low-confidence claim, and it never raises `claim_mismatch`. 76 KEP metadata versions have no stage (spike §7 R).

When `observed ≠ claimed`, emit a `claim_mismatch` flag. The conflict detector consumes it. The flag is never silently resolved in the index.

**The feature-gate reference is an observation that can be wrong.** Its two formats agree for 287 of the 293 gates they share, over their whole history. But the `EventedPLEG` revert appears only in the CHANGELOG, and later files rewrite earlier ranges (spike §6 O). So:
- the CHANGELOG is also a source of `observed_stage`, and a disagreement between the two is conflict evidence (D6)
- ranges that leave a release's stage undefined or ambiguous (0–3% of gates per release), or that change at a patch release within R, set `status_confidence = low`. The parser never picks one range.

### D3. Base authority tiers (1 = highest)

| Tier | Source |
|---|---|
| 1 | `docs_page` or `feature_gate_reference`, valid for the target release |
| 2 | `release_record` for the target release |
| 3 | `kep`, where `effective_stage` has shipped (alpha or later observed) or status is implemented and consistent |
| 4 | `governance_doc` (current version) |
| 5 | `kep`: provisional or implementable, or claim not confirmed |
| 6 | `blog_post`. Dated and time-bound. Authoritative for its date, not for "now". |
| 7 | `discussion` |
| — | `kep` that is withdrawn, rejected or replaced: kept, marked `superseded_proposal` |

### D4. Mode-dependent adjustments

The table shows starting multipliers applied after RRF, to be tuned (up = boost, down = demote, — = neutral).

| Mode | Boost | Demote | Filter |
|---|---|---|---|
| CURRENT | Tiers 1–2; latest release | Blog, superseded versions | Prefer versions valid at the latest release; keep superseded ones only as conflict evidence |
| HISTORY | — (validity matters more than tier) | Versions outside the requested window | Hard filter on the validity window, with a small slack of ±1 release |
| CHANGE | Versions at both ends of the window; `release_record` | — | Retrieve per window end, then merge |
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

- Tiers and multipliers live in config so ablations can vary them. So does the synonym list.
- Two golden-set metrics get defined inputs from this ADR:
  - `authority_selection_accuracy`
  - `stale_result_rate`
- The four gate conflict cases seed the §16 conflict test set: KEP-2572, `versioning.md`, KEP-2579 `replaces: []`, KEP-4858.
- **Known limit:** keying `lifecycle_stage` by minor release can't say "beta in 1.28.0–1.28.5, alpha from 1.28.6" (`EventedPLEG`). It only flags that the release is ambiguous.
- **Deferred to S09:** how the CHANGELOG's release notes become `observed_stage` values, and how a claimed `disabled` compares with an observed stage.

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
