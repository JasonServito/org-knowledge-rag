# ADR-002: Versioning and document identity

- **Status:** Proposed. Accept after the size check in "Validation before accepting".
- **Date:** 2026-09-22
- **Blueprint refs:** §10, §13, §15; readiness gaps #3 and #13

## Context

Blueprint §13 has `document_versions` with `commit_sha`, `valid_from` and `valid_until`, but it never defines what counts as a version. For Kubernetes, taking every commit on every branch would be mostly noise: typo fixes, reviewer lists, link churn. It would also multiply embedding cost. Four facts about the corpus shape the policy:

1. **Docs are release-scoped.** `kubernetes/website` has a `release-1.x` branch per release. A docs page describes the behavior *of a release*.
2. **Other sources are date-scoped.** Blog posts, KEPs, `community` and `sig-release` live only on `main`. Blog posts are sometimes edited in place with dated "Update" notes.
3. **Two clocks exist.** Users ask "in v1.24" and "before 2021". Both must resolve to the same timeline.
4. **`kep.yaml` status is unreliable** (validation gate §3). It must be stored as a *claim*, not as truth.

## Decision

### D1. Release-aligned snapshots

For each release R in scope (v1.20 → latest; see D6), capture each in-scope file once:

| Source | Snapshot taken from |
|---|---|
| Docs (`kubernetes/website`, `content/en/docs/…`) | Head of branch `release-1.R` at ingestion time. This is the final published docs for that release. |
| KEPs, `community`, `sig-release` | `main` as of R's release date |
| CHANGELOG | `CHANGELOG-1.R.md` from `kubernetes/kubernetes` `master`. Sections are append-only per patch release, so each patch section is immutable and needs no versioning. |
| Blog | `main` only, with the full history of each post (D3). Never ingest blog copies found inside versioned doc snapshots; they are duplicates. |

### D2. A version is a content change, not a commit

Create a new `document_version` only when a file's **normalized content hash** differs from its previous snapshot. Normalization:

- Strip front-matter fields that don't change meaning (`reviewers`, `approvers`, `weight`, `card`, …).
- Collapse whitespace.
- Ignore link-target-only changes.

Keep the list of stripped fields in config so it can be tuned.

### D3. Validity windows on both clocks

Each version stores `valid_from_release`, `valid_until_release`, `valid_from_date` and `valid_until_date`. Null `until` means current.

- **Release-scoped sources (docs):** the release window is authoritative. Dates are derived from the `releases` table.
- **Date-scoped sources (KEPs, blog, governance):**
  - The date window is authoritative. `valid_from_date` is the date of the **commit that introduced the change**, found with `git log` between the two snapshot SHAs, not the snapshot date. This means a change like `sig-release versioning.md` on 2026-02-13 gets its true date.
  - The release window is derived as "latest release on or before that date".
  - Blog posts get one version per commit that changes the normalized body. This captures in-place updates.

A `releases` table (`version`, `release_date`, `end_of_life_date`) is the bridge between the clocks. Query parsing resolves "before 2021" to a release range, and "v1.24" to a date range.

### D4. Canonical document identity

| Source | `canonical_id` | Rename handling |
|---|---|---|
| Docs | `docs:<path under content/en/docs>` | Compare adjacent release branches with `git diff --find-renames` at a similarity threshold (start at 60%, tune). Store renames in `document_aliases`. Also read Hugo `aliases` front matter if present (verify). |
| KEP | `kep:<number>` (directory number = tracking issue number) | Stable if a KEP moves SIG directory |
| CHANGELOG | `changelog:1.R`; chunks anchored per patch section | Not needed |
| Blog | `blog:<YYYY-MM-DD>-<slug>` | Not needed. The URL date is part of the identity. |
| Governance | `community:<path>`, `sig-release:<path>` | `git log --follow` |

### D5. Status is stored twice

- `claimed_status` and `claimed_stage` come from `kep.yaml` at each snapshot, with typos normalized.
- `observed_stage` comes per release from the CHANGELOG and the feature-gates reference page.

A mismatch between the two is data for the conflict detector, not an error. The taxonomy is in ADR-003.

### D6. Scope (Stage 1 subset)

- English only.
- Releases v1.20 → latest. *Verify the latest release at ingestion time*: the gate doc references both 1.36 and 1.37 branches.
- SIGs: **Release, Auth, Network**, plus the four traced KEPs (2572, 2579, 2799, 4858).
- Docs are not organized by SIG, so scope is a **path allowlist manifest** (`config/corpus_manifest.yaml`) mapping each SIG to website paths. Example: Auth → `concepts/security/`, `reference/access-authn-authz/`; Network → `concepts/services-networking/`.

The manifest, not the code, defines the subset.

## Consequences

**Schema changes relative to blueprint §13.** These go into the domain model review (gap #3):
- New `releases` table.
- New `document_aliases` table.
- `document_versions` gains:
  - `content_hash`
  - `snapshot_ref` (repo, branch, SHA)
  - both validity windows
  - `claimed_status` / `claimed_stage`
- New `observed_lifecycle` table (feature/KEP × release → stage).
- Embeddings keyed by model name, so embedding ablations don't overwrite each other.

**Accepted tradeoffs:**
- **Docs changes within a release branch collapse into one version.** This is acceptable because docs describe a release.
- **Similarity-based rename detection will miss some restructures.** Log unmatched deletions and additions per snapshot pair, and review them for the traced chains.

## Alternatives rejected

- **Every commit is a version:** noise, cost, and meaningless CHANGE answers.
- **Current snapshot only:** removes HISTORY and CHANGE, which are core to the project's thesis.
- **Date-only validity:** misaligned with how Kubernetes docs are actually versioned.

## Validation before accepting

- [ ] Count in-scope files per release and distinct versions after dedup. Record the chunk estimate and embedding cost.
- [ ] Confirm `release-1.20` … `release-1.<latest>` branches exist and build paths match.
- [ ] Spot-check rename detection on one known move within the Auth or Network docs.
- [ ] Confirm the blog front matter has a date, and that in-place updates are visible in git history.
