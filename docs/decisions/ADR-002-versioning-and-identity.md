# ADR-002: Versioning and document identity

- **Status:** Accepted (2026-10-01), amended on the S02 spike's evidence and in the S05-R2 sitting (2026-10-07). See the two "Changes" tables at the end.
- **Date:** 2026-09-22
- **Blueprint refs:** §10, §13, §15; readiness gaps #3 and #13
- **Evidence:** `docs/research/corpus-spike-report.md` (cited below as "spike §N")

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
| Docs (`kubernetes/website`, `content/en/docs/…`) | Head of branch `release-1.R` at ingestion time. This is the final published docs for that release. The latest release has no branch yet, so its docs come from `main`. |
| KEPs, `community`, `sig-release` | `main` as of R's release date, **plus a `head` snapshot at ingestion time**, so changes after the latest release are captured (spike §2, finding 4). |
| CHANGELOG | `CHANGELOG-1.R.md` from `kubernetes/kubernetes` `master` at ingestion time. **Sections can be edited after they're written** (spike §7 Q), so the file is versioned by D2 like any other source: each ingestion re-hashes it, and changed content gives a new version. The clone has no history, so text from before the first ingestion isn't reconstructed. |
| Blog | `main` only, with the full history of each post (D3). Never ingest blog copies found inside versioned doc snapshots; they are duplicates. |

### D2. A version is a content change, not a commit

Create a new `document_version` only when a file's **normalized content hash** differs from its previous snapshot. Normalization:

- Strip front-matter fields that don't change meaning (`reviewers`, `approvers`, `weight`, `card`, …).
- Collapse whitespace.
- Ignore link-target-only changes.

The list of stripped fields lives in `config/corpus_manifest.yaml` (`normalization`), with a `never_strip` list of identity, time and lifecycle keys.

### D3. Validity windows on both clocks

Each version stores `valid_from_release`, `valid_until_release`, `valid_from_date` and `valid_until_date`. Null `until` means current.

- **Release-scoped sources (docs):** the release window is authoritative. Dates are derived from the `releases` table.
- **Date-scoped sources (KEPs, blog, governance):**
  - The date window is authoritative. `valid_from_date` is the date of the **commit that introduced the change**, found with `git log` between the two snapshot SHAs, not the snapshot date. This means a change like `sig-release versioning.md` on 2026-02-13 gets its true date.
  - The release window is derived as "latest release on or before that date", but never before the scope's first release (D6). A version that started before 1.20 keeps its true date, and its release window starts at 20 (S05-R2).
  - Blog posts get one version per commit that changes the normalized content (D2). This captures in-place updates.
- **Blog: `valid_from` = max(commit time, publication time).** Publication is the first moment Hugo would render the post: the live version isn't `draft: true`, and its date has passed (the site config has `buildFuture` off and `timeZone` UTC). 317 of 416 posts were merged ahead of their date, by up to 28.5 days (spike §5 K).
  - A version superseded before publication gets an empty window, so it isn't stored. That drops 214 never-public versions (19% of blog versions).
- **CHANGELOG:** `valid_from_date` is the date of the ingestion snapshot that first saw the version, because the clone has no history (D1).

A `releases` table (`version`, `release_date`, `end_of_life_date`) is the bridge between the clocks. Query parsing resolves "before 2021" to a release range, and "v1.24" to a date range.

### D4. Canonical document identity

**General rule:** a page the website renders is identified by its **URL**; an embedded or structured source by a **declared key**. A `canonical_id` is assigned when the document is first ingested (first published, for the blog) and never changes. Later URLs or names go to `document_aliases`.

| Source | `canonical_id` | Rename handling |
|---|---|---|
| Docs pages and website release records | `web:<URL path>`, from Hugo's path rules: drop `content/en` and `.md`; `index.md` and `_index.md` become their folder; lowercase. A move into a page bundle keeps the URL (spike §4 H). | **Declared signals first:** a redirect whose target was added in the same release (otherwise it's a removal), or a Hugo `aliases` entry. **Fallback:** `git diff --find-renames` between adjacent release branches at **50%** (git's default; spike §4 F). Log unmatched adds and deletes per release pair. |
| Feature gate (one file per gate, 1.29+) | `gate:<name>`, the front-matter `title`. These files have no URL (`_build: render: false`). | `former_titles` first, then git similarity at 50%. The pre-1.29 tables are part of the feature-gates docs page; their rows give stages under the same gate name. |
| KEP | `kep:<number>` (directory number = tracking issue number). An old single-file KEP, which has no number: `kep:<sig folder>/<file name>`, e.g. `kep:sig-auth/0014-dynamic-audit-configuration` (S05-R2) | Stable if a KEP moves SIG directory or its folder's slug changes |
| CHANGELOG | `changelog:1.R`; chunks anchored per patch section | Not needed |
| Blog | `web:<URL path>` at publication, from the site's permalink config (`/:section/:year/:month/:day/:slug/`, with the front-matter `url:` override and Hugo's date and slug fallbacks) | Not needed for file moves: the URL survived all 349 measured moves of the 2026 year-folder reorganization. A URL changed after publication is linked through a redirect or `aliases` (spike §5 J). |
| Governance | `community:<path>`, `sig-release:<path>`, from the first path | Same path, then git similarity ≥ 50% between adjacent snapshots, as for docs; later paths become aliases (S05-R2) |

### D5. Status is stored twice

- `claimed_status` and `claimed_stage` come from `kep.yaml` at each snapshot (or the front matter of an old single-file KEP). They are checked against ADR-003 D5's vocabularies: `GA` → `stable` is the only synonym, and any other unknown value is stored as written and flagged, not mapped.
- `observed_stage` comes per release from the CHANGELOG and the feature-gates reference, read from **that release's own snapshot**. Later files rewrite earlier stage history (spike §6 O).

A mismatch between the two is data for the conflict detector, not an error. The taxonomy is in ADR-003.

### D6. Scope (Stage 1 subset)

- English only.
- Releases v1.20 → latest. The spike confirmed 1.37 as the latest, with its docs on website `main` (spike §6 M). Ingestion takes the latest release from the manifest.
- SIGs: **Release, Auth, Network**, plus the four traced KEPs (2572, 2579, 2799, 4858).
- Docs are not organized by SIG, so scope is a **path allowlist manifest** (`config/corpus_manifest.yaml`) mapping each SIG to website paths. Example: Auth → `concepts/security/`, `reference/access-authn-authz/`; Network → `concepts/services-networking/`.

The manifest, not the code, defines the subset.

## Consequences

**Schema changes relative to blueprint §13.** These go into the domain model review (gap #3):
- New `releases` table.
- New `document_aliases` table: old URL → document for pages, old name → document for feature gates.
- `document_versions` gains:
  - `content_hash`
  - `snapshot_ref` (repo, branch, SHA)
  - both validity windows
  - `claimed_status` / `claimed_stage`
- New `observed_lifecycle` table (feature/KEP × release → stage).
- Embeddings keyed by model name, so embedding ablations don't overwrite each other.

**Accepted tradeoffs:**
- **Docs changes within a release branch collapse into one version.** This is acceptable because docs describe a release.
- **A rename that the site doesn't declare and git doesn't pair at 50% is missed.** Log unmatched deletions and additions per snapshot pair, and review them for the traced chains.
- **Known identity splits:**
  - 1 blog post whose URL changed after publication with no redirect or alias (`ingress-nginx-retirement`, spike §5 I)
  - the 25 single-file KEPs at the 1.20 snapshot, which use an older numbering and are in KEP directories by 1.21, for example `0014-dynamic-audit-configuration.md` → `600-dynamic-audit-configuration/` (spike §7 R)
  - 2 gate names misspelled in the pre-1.29 tables (spike §6 O)
- **CHANGELOG history before the first ingestion is lost,** and a later edit is dated by the ingestion that sees it, not by its commit.
- **The blog publication time is approximate.** It assumes the site builds on every merge, which wasn't checked against the build config or logs.

## Alternatives rejected

- **Every commit is a version:** noise, cost, and meaningless CHANGE answers.
- **Current snapshot only:** removes HISTORY and CHANGE, which are core to the project's thesis.
- **Date-only validity:** misaligned with how Kubernetes docs are actually versioned.
- **File path as the identity of docs pages, feature gates and blog posts:** breaks on page-bundle moves (1.29), the per-gate file renames (343 at 1.32), and the 2026 blog move (909 files).
- **Front-matter `blog:<date>-<slug>`:** splits 10 of 416 published posts, and gives no id to the 4 interviews that have no `slug` (spike §5 J).
- **Git similarity alone for renames:** found 4 of the 6 docs moves that redirects declare (spike §4 G).
- **Commit time as a blog version's `valid_from`:** 317 versions would claim to be public before they were.

## Validation before accepting

- [x] Count in-scope files per release and distinct versions after dedup. Record the chunk estimate and embedding cost. *(spike §2 A–B, §3 C–D)*
- [x] Confirm `release-1.20` … `release-1.<latest>` branches exist and build paths match. *(`release-1.20`…`release-1.36`, plus 1.37 on `main`: spike §6 M; per-release file counts, with a `git ls-tree` hand check: spike §2)*
- [x] Spot-check rename detection on one known move within the Auth or Network docs. *(PSP page, 1.22→1.23, 81%, confirmed by its redirect: spike §4 E)*
- [x] Confirm the blog front matter has a date, and that in-place updates are visible in git history. *(all 412 in-scope posts have a date: spike §7 S; 508 versions after publication: spike §5 K)*

## Changes from the S02 spike (2026-10-01)

Each change was decided by the developer in S02-T6. The evidence is in the spike report.

| Where | Was | Now | Evidence |
|---|---|---|---|
| D1 KEPs, governance | Release-date snapshots only | Plus a `head` snapshot | 23 KEP and governance changes after 1.37 were invisible (spike §2, finding 4) |
| D1 CHANGELOG | Sections immutable, never versioned | Versioned by D2 at each ingestion | 3 of 23 sections in the sampled file were edited later, one a factual fix 13 months on (spike §7 Q) |
| D3 blog | `valid_from` = commit time | max(commit, publication); never-public versions not stored | spike §5 K |
| D3 CHANGELOG | (not covered) | Dated by the ingestion snapshot | follows from D1 |
| D4 docs | `docs:<path>`; similarity at 60% | `web:<URL>`; declared signals first, similarity at 50% as the fallback | spike §4 F–H |
| D4 feature gates | (no row) | `gate:<name>`; `former_titles`, then similarity | spike §2, finding 2; §6 O |
| D4 blog | `blog:<date>-<slug>` | `web:<URL>` at publication | spike §5 J |
| D5 | "typos normalized" | `GA` → `stable` only; other unknown values flagged; observed stage from R's own snapshot | spike §6 O, §7 R |
| D6 | "verify the latest release" | 1.37 confirmed | spike §6 M |

## Changes from the S05-R2 sitting (2026-10-07)

Decided by the developer in the S05-R2 sitting; the evidence was checked on the locked clones in the sitting (`docs/slices/S05-stage1-subset-ingestion.md`, run S05-R2).

| Where | Was | Now | Evidence |
|---|---|---|---|
| D3 release window of date-scoped sources | "Latest release on or before that date" | The same, but never before the scope's first release; the date stays true | 67 KEPs and governance docs start before 1.20's release date (the earliest 2019-06-29) |
| D4 governance renames | `git log --follow` (never run) | Same path, then git similarity ≥ 50% between adjacent snapshots; the first path is the id | The only moves in range: 8 files in sig-release PR #2984 (1.36 → 1.37), at 66–100%. The per-commit log shows the same 8 pairs and no edit before a move. A devil's advocate argued for `--follow`; its concession condition holds |
| D4 old single-file KEPs | No id (only the known limit) | `kep:<sig folder>/<file name>`; still separate documents | 25 files at the 1.20 snapshot, none with a KEP number |

