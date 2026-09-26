# ADR-003: Source types, authority tiers, and status taxonomy

- **Status:** Proposed (draft v1). The tiers and weights are hypotheses to tune against the golden set.
- **Date:** 2026-09-22
- **Blueprint refs:** §15, §16; readiness gap #4
- **Builds on:** validation gate §5.3 (first-draft tiers), ADR-002

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
| `feature_gate_reference` | The feature-gates docs page, parsed as a structured table (stage per version). Verify its format. |
| `kep` | KEP README, with `kep.yaml` attached as metadata. The YAML is not a separately retrievable document. |
| `blog_post` | website blog |
| `governance_doc` | `community`, `sig-release` |
| `discussion` | GitHub issues, PRs, Discussions (Phase 2) |

### D2. Effective status

For any KEP or feature, compute `effective_stage`:

1. `observed_stage` for the release in question (from the CHANGELOG or the feature-gate reference), else
2. `claimed_stage` from `kep.yaml`, with `status_confidence = low`.

When `observed ≠ claimed`, emit a `claim_mismatch` flag. The conflict detector consumes it. The flag is never silently resolved in the index.

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
| `lifecycle_stage` (per feature × release) | `alpha` / `beta` / `stable` / `deprecated` / `removed` |
| `claimed_status` (KEP) | provisional / implementable / implemented / deferred / rejected / withdrawn / replaced, normalized from typos |
| Flags | `claim_mismatch`, `status_confidence` (high/low), `superseded_proposal` |

### D6. Precedence for conflicting claims (input to §16)

1. Observed beats claimed.
2. Within the same validity window, a lower tier number wins.
3. Across windows, the version valid for the question's target time wins. Other versions become `historical_context`.
4. If two sources of the same tier and the same window disagree, the conflict is **unresolved**. Surface it; never pick one.

## Consequences

- Tiers and multipliers live in config so ablations can vary them.
- Two golden-set metrics get defined inputs from this ADR:
  - `authority_selection_accuracy`
  - `stale_result_rate`
- The four gate conflict cases seed the §16 conflict test set: KEP-2572, `versioning.md`, KEP-2579 `replaces: []`, KEP-4858.

## Open (resolve during Stage 6, not blocking now)

- Does the feature-gates page give a reliable stage-per-version table for every gate in scope?
- Should blog tier rank above `governance_doc` for date-bounded questions? Test this empirically.
