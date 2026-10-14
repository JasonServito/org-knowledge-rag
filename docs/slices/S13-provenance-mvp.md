# S13: Phase 2 provenance MVP

- **Status:** ✅
- **Blueprint stage:** 9 (Phase-2 provenance MVP)
- **Started:** 2026-10-13
- **Finished:** 2026-10-13

## Outcome

`orgknow chain kep:2572` prints the release-cadence decision (4 → 3 releases a year) as a dated chain of 6 steps, each citing a stored text, built by rules from the corpus's links and dates. Decision-chain completeness is measured against human-labeled gold chains (this chain and one random held-out KEP), beside a plain-search negative control graded by the same rule.

## Why now

- Blueprint §3.2 and §29: a small, real provenance MVP comes before AWS and UI polish, because it is part of the project's thesis.
- S17's UI needs provenance data to show; S14–S16 harden and deploy what exists.
- It retires the Phase 2 unknown: whether a chain can be rebuilt from machine-readable links, or needs an LLM.

## Exit checks

- [x] The chains' GitHub items are stored as `discussion` documents, chunked and embedded; re-ingesting gives an identical fingerprint (AC8 still holds).
- [x] Phase 1's retrieval metrics on golden v0, with the new texts searchable: each within ±0.03 of S12's final row, or the change explained (`make eval-retrieval`, free).
- [x] `orgknow chain kep:2572` prints the chain; every step cites a stored chunk with its source URL, date and tier, or says why it's missing.
- [x] Decision-chain completeness for the builder and the negative control, on both gold chains, in `docs/evaluation.md`.
- [x] `make check` and `make test-int` green.
- [x] Retro done; slice brief written; backlog updated.

## Scope

| In | Out (explicitly) |
|---|---|
| One chain built on: release cadence (KEP-2572); one random held-out KEP, scored only (S13-R1 decision 2) | Other chains' issues and PRs (ADR-001: only items a traced chain links to) |
| KEP-2572's 3 GitHub items: sig-release Discussion #1290, enhancements issue #2572 (tracking), enhancements PR #2567 (the KEP's PR); the held-out KEP's items its tracking issue links (public GitHub only) | The KEP's side links (#1494, #1495, #809, community #5240) and the blog's #1566: not on the chain |
| `discussion` source type (ADR-003 D1, tier 7) | Mailing lists, Slack, Google Docs (gated) |
| `decisions` and `decision_evidence` tables | A general link table; entities and entity mentions (blueprint §13); Neo4j |
| A rule-based chain builder and `orgknow chain` | An LLM that builds or narrates the chain (ADR-012) |
| Decision-chain completeness and its negative control | Attaching the chain to `ask` answers (S13-R1 decision 6: a note for S17's sitting) |
| `GET /decisions/{canonical_id}` (JSON for S17) | The provenance UI (S17); async ingestion (S14) |

## Metric to move

- **Decision-chain completeness** (new; blueprint §19.2): the share of a gold chain's steps the builder reconstructs. Its rule and negative control were fixed in the S13-R1 sitting, before any score (S12 retro; ADR-012 D4).
- **Phase 1 metrics:** hold. The new texts enter search, so v0's retrieval-only numbers are re-measured (free).

## Tasks

These mirror `docs/backlog.md`; details live here and in the run contract.

### S13-T1: Ingest the chains' GitHub items `[core]`

- **Goal:** the chains' GitHub items are stored as `discussion` documents, chunked and embedded, reproducibly.
- **Done when:**
  - The manifest lists each chain's items. A fetch writes each one's snapshot to the corpus cache, and the lock pins its hash.
  - `make ingest` stores each as a `discussion` document with its dates in metadata (created, closed, merged), bot comments dropped. Re-ingesting from the cached snapshots gives an identical fingerprint.
  - A migration adds `discussion` and the `gh:` prefix to the CHECKs.
  - `make embed` embeds the new texts (paid, < US$0.01). `make eval-retrieval` on v0 shows the effect on Phase 1 metrics.
  - Every gold-chain label matches a stored text (the chain label check).
  - Unit tests use synthetic, API-shaped JSON. No GitHub text is committed (ADR-001: the corpus isn't redistributed).
- **Notes / pointers:** ADR-012 D3; ADR-001 (Phase 2 only, chain-linked only); ADR-002 D2–D4; ADR-003 D1, D3 (`discussion`, tier 7). Discussions are only in GitHub's GraphQL API; issues and PRs are in REST. `httpx2` is already the project's HTTP client. The token comes from settings (`gh auth token` locally).
- **Deps:** none.

### S13-T2: Gold chains v0 `[human]`

- **Goal:** gold labels for both chains' steps, fixed before any system output.
- **Done when:** `eval/golden_set/chains-v0.yaml` holds both chains (steps, acceptable texts, dates; the held-out chain's WHY question), signed off and copied in by the developer, its hash recorded in the contract.
- **Notes / pointers:** a label sheet with excerpts a script copies from the source (`label_sheet.py`). Done in the S13-R1 sitting, after the contract commit and the held-out draw: drafted by Claude at the developer's request, reviewed in full and signed off by the developer (see the contract's "Gold chains v0").
- **Status:** ✅ done in the sitting (2026-10-13).
- **Deps:** the contract (rules frozen first).

### S13-T3: Decision tables and the chain builder `[core]`

- **Goal:** each chain is built by rules from stored links and dates, stored, and printed.
- **Done when:**
  - A migration adds `decisions` and `decision_evidence`.
  - `make chains` fills them: each step cites a stored chunk with its date and how it was found, or is missing with its reason. Re-running gives the same rows.
  - `orgknow chain kep:2572` prints the timeline with citations (source URL, date, tier).
- **Notes / pointers:** ADR-012 D1–D2; blueprint §13 ("start with PostgreSQL joins"); ADR-005 (SQL only in `db/`).
- **Deps:** T1.

### S13-T4: Decision-chain completeness `[core]`

- **Goal:** score each built chain against its gold chain, beside the negative control.
- **Done when:** `make eval-chain` (free after one question vector) prints both numbers for the builder and the headline for the control, per chain, by ADR-012 D4's rule. Unit tests use hand-computed fixtures. The results are committed.
- **Deps:** T2, T3.

### S13-T5: `GET /decisions/{canonical_id}` `[commodity]`

- **Goal:** the chain as JSON, for S17's provenance view.
- **Done when:** the endpoint returns the same chain as the CLI, and 404 for a chain that isn't stored; unit and integration tests.
- **Deps:** T3.

### S13-T6: Docs and the S13 retro `[commodity]`

- **Goal:** the domain model, architecture, evaluation, the README's Phase 2 line, the backlog; then `/slice-retro S13`.
- **Deps:** T4, T5.

## Risks & unknowns

- **Rules written on one chain.** Mitigated by a random held-out KEP drawn after the rules were committed (decision 2). Two chains still show feasibility, not a rate.
- **The new texts change Phase 1 search.** ~140 texts (plus the held-out chain's) join 21,552; they're tier 7, and WHY mode doesn't demote them. v0's labels can't credit them. Measured free with `make eval-retrieval`.
- **The "current documentation" step has no link.** Only the blog links KEP-2572. The similarity rule found a sensible page for 3 of 4 traced KEPs (`probe_rules.log`).
- **GitHub text isn't CC BY.** It stays in the local corpus cache, never in the repo; fixtures are synthetic.
- **Mutable sources.** A re-fetch can add comments, which makes a new version. Reproducibility comes from the cached snapshot pinned by hash.
- **The API needs a token.** About 10–20 calls per chain, against 5,000/hour.

## Decisions expected (ADRs)

- **ADR-012: Decision provenance:** Accepted in the S13-R1 sitting (2026-10-13). The deployment-topology ADR becomes ADR-013.
- **ADR-002 D4:** the `gh:` identity, logged in its "Changes from the S13-R1 sitting" table.

## Run contracts

Written by `/plan-run` in the sitting, and committed as the run branch's first commit. One block per run; `/run-bundle` builds from it.

### Run S13-R1: Provenance MVP

- **Status:** PR open
- **Tasks:** T1, T3, T4, T5, T6. T2 (`[human]`) is done in the sitting, before "go".
- **Goal (plain words):** bring in the release-cadence decision's GitHub discussion, issue and PR; rebuild the decision as 6 dated steps by following Kubernetes' own recorded links; store and show it; and score it, and a random held-out KEP's chain, against gold chains and against plain search.

#### Sitting evidence (2026-10-13)

The scripts and outputs are in `eval/results/s13-sitting/`; its `README.md` lists each one's command, cost and output. GitHub text stays in a scratch directory (`fetch_items.sh`), never the repo.

- **The chain's GitHub items** (`expected_posts.log`): Discussion #1290: 1 opening post + 88 comments and replies (1 bot); issue #2572: 1 opening + 2 comments (6 of 8 are bots); PR #2567: 1 opening + 46 comments (2 bots) + 4 non-empty review bodies (165 reviews, paged: page 1 holds 100).
- **Format traps** (sitting checks): the bots `k8s-ci-robot`, `k8s-triage-robot` and `fejta-bot` are typed "User"; 80 of 134 posts use CRLF; 1 of 134 posts holds markdown headings.
- **The decision** (`prow_order.log`): 4 `/approve`s (dims, derekwaynecarr, johnbelamaric, dchen1107, the last on 04-22) after dims's `/hold for all approvers to cast their vote/support`; the last Prow command is justaugustus's `/hold cancel`, 6 minutes before the merge (2021-04-23T15:38:03Z, by `k8s-ci-robot`).
- **Decision 1's rules on the gate's 4 traced KEPs** (`probe_rules.log`):

  | Step | 2572 | 2579 | 2799 | 4858 |
  |---|---|---|---|---|
  | Discussion (the "Discussion Link" field) | public Discussion #1290 | gated Google Doc | gated Google Doc | public k/k PR #122550 |
  | Proposal PR (the template fields) | #2567 | #2582 | none listed | #4899 |
  | Earliest stored text linking the KEP | blog 2021-07-20 | deprecation blog 2021-04-06 (before the change shipped) | 1.29 blog 2023-12-13 (the change began in 1.24) | none |
  | Nearest current text to the KEP's Summary vector (distance) | releases page "The Release Cycle" (0.201) | PSA concept page (0.113) | security checklist (0.191) | `gate:StrictIPCIDRValidation` (0.176) |

  CHANGELOG versions carry the lock refresh date (2026-09-30), so a CHANGELOG is dated by its release.
- **Re-run cost of a chain:** scanning all chunk texts for links to one KEP took 2.4 s; a naive nearest-text query took 8.0 s (sitting timing). A stored chain is read in milliseconds.
- **Three devil's-advocate reviews:**
  - **Build method:** argued for hand-curation now and an LLM later: only this chain's items are ingested, each rule fits what the sitting saw, the discussion link is public for 1 of 4 KEPs, and "last Prow command" cites `/hold cancel` (confirmed). Proposed the held-out test above, which led to fixes 1–2 and to decision 2.
  - **Tables:** argued for no tables (rebuild on demand): less code, no stale copy (`make reset-corpus` truncates with CASCADE), and "how found" as free text hides a link S17 would parse. Led to the structured "how found" and the "not built yet" answer.
  - **Metric:** argued that section matching collapses to document matching unless shared-document steps get different sections; dates should count; the control should be a lookup by source type, not a lenient top 10; and "beats" needs a margin. Led to decisions 4–5 as recorded.

#### Decisions (made in the sitting, 2026-10-13)

| # | Decision | Rejected | Why |
|---|---|---|---|
| Step 0 | Triage of S12-R1's 23 notes: K1–K4 kept (K1 one docs-fix item; K2 appended to "S09-R1 cleanup"; K3 its own item; K4 an S14 input); D1–D6 dropped | Keeping all; dropping all | K1–K4 are factual errors or real gaps; D1–D6 are intended behavior, can't happen, or style |
| Slice | The S13 slice doc approved (updated after decision 2 to add the held-out chain) | — | — |
| Run shape | 1 run, 1 PR; split after T1 (ingestion │ chain) only if the size alarm fires when the PR opens | 2 runs; 2 PRs up front | The developer's choice; estimate ~36 files, ~2,300 reviewable lines |
| 1 | **The chain is built by rules over the project's own links and dates**, with 3 fixes: the decision cites the last `/approve` before the merge; implementation is the earliest linking text on or after the decision; a step the rules can't fill is stored missing, with its reason | An LLM picks each step (cost, varies by run, can't read gated docs either, still needs the links' candidates); hand-curated (not a reconstruction; scoring it is circular) | Kubernetes records the links: KEP number = tracking issue; the template's 2 fields (4 of 4 sampled KEPs); `/approve` and the merge. Rules fail visibly, step by step |
| 2 | **A random, unseen held-out KEP**, drawn with a recorded seed after this contract's commit, from the 35 implemented KEPs in the 3 SIGs with a latest milestone ≥ v1.25, minus the 4 traced ones. Its items are ingested by T1's rule below; the developer labels its gold chain and writes its WHY question before run night | No held-out chain (the "6 rules, 1 chain, 100%" attack stands); reuse 2579 or 4858 (looked at in the sitting; fix 2 was written after seeing 2579) | The only clean test; the gate's own method (seeded random) |
| 3 | **2 tables with structured "how found"**: a fixed list of ways plus the text holding the link. Derived data like embeddings: rebuilt by `make chains`; `make reset-corpus` wipes it; the API answers "not built yet" | A general link table (no reader in S13: scaffolding); no tables, rebuild per request (seconds per request; nothing to inspect) | A rebuild costs seconds (2.4 s + 8.0 s naive); 6 stored rows are read in milliseconds |
| 4 | **Headline: a step counts when it's the right kind and cites an acceptable text** (by section where the label names one, ADR-007's prefix rule). Steps sharing a document must have different sections (the loader enforces it). A "not public" gold step counts only when the builder reports it missing as not public. **Beside it: right text and the same UTC day** (the 5 event steps; current docs is undated). Both fixed now | Date must match in the headline (mixes 2 failures; the proposal step has 2 defensible dates); document only (any chunk of PR #2567 would pass "decision"); any step (1 hit on #1290 credits 2 steps) | 2 pairs of steps share a document (#1290: problem, discussion; PR #2567: proposal, decision) |
| 5 | **The control: 1 WHY question per chain** (q04 for chain 1; the developer's question for the held-out chain), Phase 1's final mode with the mode set to WHY, top 10, after T1. A naive table assigns each hit a step by its source type; the best-ranked hit per step is graded by decision 4's headline rule. **The builder beats the control on a chain when it gets at least 1 more step right** | q04's top 10 graded leniently (chain 1 only; a different rule); q01–q04 merged, lenient (40 hits; chain 1 only) | Same test, same grader, both chains; it asks whether the links and dates beat "search plus a lookup by type" |
| 6 | **`ask` stays unchanged**; attaching the chain to answers → a proposed addition for S17's sitting | Attach the stored chain to WHY answers (bigger PR; the UI can call both endpoints); feed the chain to the LLM (changes Phase 1's answer path; paid re-evaluation) | The run is already over the size alarm; Phase 1's numbers can't move |
| Plan | The verification plan approved; paid calls: Voyage embeddings only, cap US$0.05 | — | — |

**Claude's calls** (reversible; confirmed at the read-back):
- a. **Document shape:** one document per item, id `gh:<repo key>/<issues|pull|discussions>/<number>`; rendering as pinned in T1. PR comments on diff lines are dropped (189 comments, 40.7k characters, that need the diff to read).
- b. **Windows:** ADR-002 D3's date-scoped rule, counted from the last kept post.
- c. **Search:** discussion texts are searchable in every mode, tier 7, no multiplier (ADR-003 D1, D3, D4 unchanged).
- d. **Fetching** is its own command; ingest reads only the cached snapshot, pinned by sha256 in the lock; the cache folder is `github/` (the cache's `gh/` holds 2 unused S02 files). `GITHUB_TOKEN` comes from `.env` and is checked at run start.
- e. **API path:** `GET /decisions/{canonical_id}`.
- f. **ADR numbers:** ADR-012 is provenance; deployment topology becomes ADR-013.
- g. **Sitting evidence** in `eval/results/s13-sitting/`, with no GitHub text.
- h. **Problem fallback:** the KEP's Motivation section when the discussion isn't stored or isn't public (every KEP has one by template).
- i. **Discussion step:** the discussion's first comment, dated by it.
- j. **Proposal step:** the KEP's Summary section, dated by the proposal PR's opening (the KEP's `creation-date` when there's no PR).
- k. **Current docs:** the nearest text to the KEP's first Summary chunk vector among texts valid at the latest release (docs pages, feature gates, release records other than CHANGELOGs, governance docs); ties by content hash.
- l. **Implementation candidates:** blog posts and release records linking the KEP; a CHANGELOG is dated by its release.
- m. **The control's lookup table** as pinned in T4; the control is scored on the headline only.
- n. **The manifest** lists each chain: its seed KEP and its GitHub items.

#### Pinned: T1 (the GitHub items)

- **Manifest:** a `decision_chains` section; each chain has `seed` (e.g. `kep:2572`) and `items`, each `{repo, kind, number}` with `repo` a key of `repos` and `kind` one of `issues`, `pull`, `discussions`. Chain 1: `{sig-release, discussions, 1290}`, `{enhancements, issues, 2572}`, `{enhancements, pull, 2567}`. The held-out chain's items are recorded below at the draw.
- **Which items a chain gets** (the rule used for the held-out chain): the tracking issue (`enhancements/issues/<KEP number>`); the proposal PR (the "Kubernetes Enhancement Proposal:" field when its first URL is an `enhancements` PR, else the first URL on the first "KEP (`k/enhancements`) update PR(s):" line); the first URL of the "Discussion Link:" field when it's an issue, PR or discussion in a manifest repo. Only full URLs count, as in T3's rule 2: a bare `#N` is not a link (S13-R1, after the draw, option A). Nothing else.
- **`make fetch-github`** (needs `GITHUB_TOKEN`, a `SecretStr` setting, never logged): REST for issues and PRs (the item, its comments, a PR's reviews), GraphQL for discussions (comments, replies). Every list is paged. Writes one JSON snapshot per item to `<corpus cache>/github/<repo>/<kind>/<number>.json` (only the fields the rendering uses) and records each snapshot's sha256 and fetch time in the lock (`github:` section). It refetches only when run.
- **`make ingest`** reads only the cached snapshots: a missing snapshot or a hash that differs from the lock stops it with a one-line error naming the item. No network.
- **Rendering (normalize, then hash):**
  - `# Opening post · @<author> · <YYYY-MM-DD>` then the item's body (a PR's description, an issue's or discussion's opening post).
  - `# Comments`, then one `## @<login> · <YYYY-MM-DD>` per kept post, in time order: comments, discussion replies (`## @<login> · <date> · reply`) and non-empty review bodies (`## @<login> · <date> · review`). Dates are UTC.
  - Kept: every post whose login doesn't end in `-robot`, `-bot` or `[bot]`. PR comments on diff lines are not fetched.
  - Headings inside a post are pushed below the post's heading (one level for the opening post, two for a comment; at most level 6).
  - CRLF and CR become LF before hashing.
  - The item's title is the document title (metadata), as for other sources' chunk headers.
- **Document:** `source_type` `discussion`; `canonical_id` `gh:<repo key>/<kind>/<number>`; metadata: `kind`, `number`, `url`, `title`, `author`, `created_at`, `closed_at`, `merged_at`, `merged_by` (the last two for PRs). One version per snapshot; ADR-002 D3's date-scoped windows from the last kept post's time; `claimed_status` null.
- **Migration `0007`:** `discussion` in the `source_type` CHECK; `gh:` in the `canonical_id` and alias prefix CHECKs. Downgrade restores both.
- **Tier and citations:** `discussion` is tier 7 (ADR-003 D3); a citation's source URL is the item's GitHub URL.
- **Ingestion report:** counts include `discussion`; the fingerprint covers the new documents.
- **`make embed`:** embeds the new texts (paid; the estimate prints first).
- **The chain label check** (`make eval-check` or a sibling target): every `texts` entry of `chains-v0.yaml` matches at least 1 stored chunk; a miss fails with the label named.
- **Tests:** synthetic JSON shaped like the API (no GitHub text): paging (2 pages), bots, CRLF, headings inside posts, replies and review bodies, line comments absent, the hash pin; `httpx2.MockTransport` for the fetcher; integration: the migration, ingesting fixture snapshots, an identical fingerprint on re-ingest.

#### Pinned: T3 (tables and the builder)

- **Migration `0008`:**
  - `decisions`: `id` bigint identity PK; `document_id` bigint NOT NULL UNIQUE → `documents` ON DELETE CASCADE (the seed KEP); `title` text NOT NULL; `built_at` timestamptz NOT NULL.
  - `decision_evidence`: `id` bigint identity PK; `decision_id` → `decisions` ON DELETE CASCADE; `step` text NOT NULL, CHECK one of `problem`, `discussion`, `proposal`, `decision`, `implementation`, `current_docs`; UNIQUE (`decision_id`, `step`); `chunk_id` bigint NULL → `chunks` ON DELETE CASCADE; `occurred_at` timestamptz NULL; `found_by` text NULL, CHECK one of `seed`, `template_field`, `merge_event`, `linking_text`, `similarity`; `via_chunk_id` bigint NULL → `chunks` ON DELETE CASCADE (the text holding the link that connects this step); `missing_reason` text NULL, CHECK one of `no_tracking_issue`, `no_link`, `not_public`, `not_ingested`, `not_merged`, `no_linking_text`; CHECK exactly one of `chunk_id` and `missing_reason` is set; CHECK `found_by` is set exactly when `chunk_id` is.
- **`make chains`** rebuilds every chain in the manifest, each in one transaction (delete the decision, insert it and its 6 rows). Needs `make ingest` and `make embed`. `orgknow chain <canonical_id>` prints the stored chain; it never builds.
- **The rules** (pure functions over rows the data-access layer returns; SQL only in `db/`):
  1. **Tracking issue:** `gh:enhancements/issues/<N>` for `kep:<N>`; the chunk holding a field is the `via` of the steps that field finds. Not stored → every step that needs a field is missing `no_tracking_issue`.
  2. **Template fields** in the tracking issue's opening post: the line holding `Kubernetes Enhancement Proposal:`, the first line holding `` KEP (`k/enhancements`) update PR(s): ``, and the line holding `Discussion Link:`; the first URL on each. A `github.com/kubernetes/<repo>/<issues|pull|discussions>/<n>` URL resolves to `gh:<repo key>/…`; stored → found; not stored → `not_ingested`; a non-GitHub URL (e.g. `docs.google.com`) → `not_public`; no URL → `no_link`.
  3. **problem:** the discussion's opening post (found_by `template_field`, via the tracking issue's field text), dated by its creation. Else the KEP's `Motivation` section (found_by `seed`), dated by the KEP's `creation-date`.
  4. **discussion:** the discussion's first comment (found_by `template_field`), dated by it; else the field's missing reason.
  5. **proposal:** the KEP's `Summary` section (first chunk; found_by `seed`, via the tracking issue's field text when a proposal PR is found), dated by the proposal PR's creation; else by the KEP's `creation-date`.
  6. **decision:** the proposal PR's last post holding a line starting `/approve` before `merged_at` (found_by `merge_event`, via the field text), dated `merged_at`. Not merged → `not_merged`; PR missing → the field's reason; merged with no `/approve` post → its opening post.
  7. **implementation:** the earliest stored blog post or release record holding a link to the KEP (its folder name, `enhancements/issues/<N>`, or `KEP-<N>` as a whole word), dated on or after the decision's date (the proposal's when the decision is missing); a blog by its version's date-window start, a CHANGELOG by its release date; the cited chunk is the one holding the link (found_by `linking_text`, via itself). None → `no_linking_text`.
  8. **current_docs:** the nearest text to the KEP's first `Summary` chunk vector among texts valid at the latest release in `docs_page`, `feature_gate_reference`, `release_record` (not `changelog:`), `governance_doc`; ties by content hash (found_by `similarity`), dated by its version's date-window start. Use the indexed vector search plus a filter in `db/`, not a full scan.
- **CLI output:** a header (seed, title, built time), then one line per step in step order: date, step, source URL, `canonical_id › heading path`, tier, found_by (and "via <canonical_id › heading path>"), or `missing: <reason>`. Exit 1 with a one-line message when the chain isn't stored.
- **Chain 1's expected picks** (from the sitting's checks, independent of the code): problem = #1290's opening post, 2020-10-14; discussion = #1290's first comment, 2020-10-14; proposal = KEP-2572's Summary, 2021-03-12; decision = PR #2567, `## @dchen1107 · 2021-04-22`, dated 2021-04-23; implementation = `web:/blog/2021/07/20/new-kubernetes-release-cadence/`, the chunk holding the KEP link, 2021-07-20; current docs = `web:/releases/release/ › The Release Cycle`.
- **Tests:** each rule on synthetic rows (written first); missing reasons; re-running gives identical rows (integration); `make reset-corpus` empties the tables (integration).

#### Pinned: T4 (completeness)

- **The gold file** `eval/golden_set/chains-v0.yaml` (human-owned; T2):
  ```yaml
  version: chains-v0
  chains:
    - seed: kep:2572
      role: built-on            # or held-out
      question: "Why did Kubernetes move to three releases per year?"
      steps:                    # each step has exactly one of texts / not_public / not_stored / none
        - step: problem
          date: 2020-10-14      # required for event steps with texts; absent for current_docs
          texts:                # "any of": {document, section?}, ADR-007 D2's section rule
            - {document: "gh:sig-release/discussions/1290", section: "Opening post · @justaugustus · 2020-10-14"}
        - step: discussion
          not_public: "<url>"   # the evidence exists but isn't public
        - step: implementation
          not_stored: "<url>"   # public, but not linked by the template fields, so not ingested
        - step: decision
          none: "<why>"         # the step has no record
  ```
- **The loader** rejects: an unknown step; a repeated step; a step with 0 or 2+ of the 4 forms; an event step with `texts` but no date; two steps whose `texts` share a document where either label is whole-document or one section is a prefix of the other's; a document that doesn't resolve (canonical id or alias).
- **Matching, per step kind:** `texts` → the built step cites a chunk of an acceptable document whose heading path matches the section (ADR-007 D2); `not_public` → the built step is missing with `not_public`; `none` → the built step is missing (any reason); `not_stored` → never.
- **Numbers per chain:** "steps right: k of n" (all gold steps); "right with the same UTC day: k of m" (gold event steps with `texts`). A 6-row table: step, gold, built (citation, date, found_by or missing reason), right, right with date, control's pick, control right.
- **The control:** the chain's `question`, retrieved in the `authority` mode with the mode set to WHY (no router call), top 10, after T1's ingest. The question vector: q04's stored vector for chain 1; the held-out question embedded once (Voyage) and stored beside the golden questions' vectors. Each hit gets a step from its document: a discussion's (`gh:*/discussions/*`) opening post → problem; any other post of a discussion or issue → discussion; a PR's post → decision; `kep` → proposal; `blog_post` or `changelog:` → implementation; `docs_page`, `feature_gate_reference`, other `release_record`, `governance_doc` valid at the latest release → current_docs; else none. The best-ranked hit per step fills it. Scored on the headline only.
- **Verdict line per chain:** "builder k, control j: beats" when k ≥ j + 1, else "does not beat".
- **`make eval-chain`** prints the tables and verdicts and writes `eval/results/s13-chains/chains.json` and `chains.md` (committed).
- **Tests:** hand-computed fixtures for every matching branch (section prefix, whole-document, `""`, the 4 forms, the same-day date, the loader's rejections, the control's lookup table).

#### Pinned: T5 (API)

- `GET /decisions/{canonical_id}` (e.g. `/decisions/kep:2572`) → 200 with the same model the CLI prints from (seed, title, built_at, steps with citation fields, found_by, via, missing_reason).
- 404 `{"detail": "no stored decision chain for <id>; chains are built by make chains"}`; database down → 503, as `/query`.
- One shared function returns the chain for the CLI and the API.

#### Pinned: T6 (docs and retro)

- `docs/domain-model.md`: the `discussion` source (identity, rendering, windows), the 2 tables and their rules, the new data-access functions.
- `docs/architecture.md`: the chain builder, `make fetch-github`, `make chains`, `GET /decisions/…`.
- `docs/evaluation.md`: "Decision provenance (S13)": the 2 chains' tables and verdicts, copied from `make eval-chain`; the Phase 1 re-check from `make eval-retrieval`; the n = 2 caveat.
- README: the status line adds Phase 2's MVP; `orgknow chain` and the result in at most ~8 lines.
- `docs/backlog.md`: S13 tasks ticked; the proposed additions recorded at the sitting.
- `.greptile/files.json` already lists ADR-012 (sitting commit).
- Then `/slice-retro S13` as the run's last commit.

#### Handoffs between tasks

- T1 → T3: `gh:` documents with the pinned rendering (post headings carry the author and date; the opening post holds the template fields); `merged_at` in metadata.
- T2 → T4: `chains-v0.yaml` in the golden set (copied in by the developer in the sitting).
- T3 → T4, T5: the stored rows and one shared function returning the chain model.
- T6 copies every number from `make eval-chain`, `make eval-retrieval` and the ingestion report.

#### Edge cases

- **Paging:** PR #2567's 165 reviews span 2 pages.
- **Bots typed "User":** dropped by login, never by account type.
- **A merge by a bot:** the merge comes from PR metadata, so it survives the bot filter.
- **Two posts by one author on one day:** they share a heading; both are kept, in order.
- **A "Discussion Link" to a gated doc:** the step is missing `not_public`, never an error.
- **CHANGELOG dates:** a CHANGELOG version carries the lock refresh date; date it by its release.
- **The held-out chain's discussion in a repo outside the manifest:** missing `not_ingested`; the gold labels it `not_stored`.
- **The reset:** `make reset-corpus` empties the chains (CASCADE); the API answers 404 with the "make chains" hint.

#### Files in scope

- Sitting commits: this slice doc, `docs/backlog.md`, `docs/decisions/ADR-012-decision-provenance.md`, `docs/decisions/ADR-002-versioning-and-identity.md` (Changes row), `docs/decisions/README.md`, `.greptile/files.json`, `eval/results/s13-sitting/`, `eval/candidates/` (the label drafts' ids and sections, no GitHub text), `eval/golden_set/chains-v0.yaml` (copied in by the developer).
- T1: `config/corpus_manifest.yaml`, `config/corpus_manifest.lock.yaml`, `src/orgknow/settings.py`, `.env.example`, a new `src/orgknow/ingestion/github.py` (fetch, render), `src/orgknow/ingestion/ingest.py`, `src/orgknow/ingestion/manifest.py`, `src/orgknow/db/migrations/versions/0007_*.py`, `src/orgknow/retrieval/authority.py` (tier 7), citation URL code if needed, `src/orgknow/eval/` (the chain label check), `Makefile`, `tests/unit/`, `tests/integration/`, `tests/fixtures/` (synthetic JSON).
- T3: `src/orgknow/db/migrations/versions/0008_*.py`, `src/orgknow/db/` (a new `decisions.py`), a new `src/orgknow/provenance/` module (rules, chain model), `src/orgknow/cli.py`, `Makefile`, tests.
- T4: `src/orgknow/eval/` (a new `chains.py` and its entry point), `Makefile`, `eval/question_vectors/` (the held-out question's vector), `eval/results/s13-chains/`, tests.
- T5: `src/orgknow/api/app.py`, tests.
- T6: `docs/domain-model.md`, `docs/architecture.md`, `docs/evaluation.md`, `README.md`, `docs/backlog.md`, `docs/learning/S13-*.md`, this slice doc.

#### Proof map

| Task | "Done when" | Proof | Expected values from |
|---|---|---|---|
| T1 | Paging, bots, CRLF, headings, replies, review bodies, the hash pin | Unit tests on synthetic JSON (written first) | Hand-written in the tests |
| T1 | The real items are stored | `make fetch-github && make ingest`; posts per item from the database | `expected_posts.log`: 89, 3 and 51 posts (1 + 88; 1 + 2; 1 + 46 + 4) |
| T1 | Reproducible | `make ingest-report` twice: identical fingerprint | — |
| T1 | Phase 1 search holds | `make eval-retrieval` (authority mode) | S12's final row: Recall@10 0.552, MRR 0.813, Hit@10 1.000, ±0.03 |
| T1 | Gold labels match stored texts | The chain label check | `chains-v0.yaml` |
| T3 | Each rule | Unit tests on synthetic rows (written first) | Hand-written |
| T3 | Chain 1 on real data | `make chains && uv run orgknow chain kep:2572` | "Chain 1's expected picks" above |
| T3 | Rebuild is stable; reset empties | Integration tests | — |
| T4 | Matching and the loader | Unit tests, hand-computed | Hand calculation |
| T4 | The scores | `make eval-chain` | None in advance: the measurement |
| T5 | Same JSON as the CLI; 404; 503 | Unit (`TestClient`) and integration tests | The CLI's model for the same rows |
| All | `make check`; `make test-int` | Both | — |
| T6 | The retro's exit checks | `/slice-retro`'s checklist | This slice doc |

#### Break-it rules

- **T1, bots:** remove the bot filter → the bot test fails. **Paging:** stop after page 1 → the 2-page test fails.
- **T3, decision:** cite the last Prow command instead of the last `/approve` → the decision test fails (its fixture ends with `/hold cancel`). **Implementation:** drop "on or after the decision" → the test with an earlier linking text fails.
- **T4, sections:** match by document only → the shared-document test fails.

#### Real-data demo

```bash
make fetch-github && make ingest && make embed && make chains
uv run orgknow chain kep:2572
make eval-chain
make serve   # second terminal
curl -s localhost:8000/decisions/kep:2572
```

#### Bundle-level check

- `make check`; `make test-int` (Postgres and `GITHUB_TOKEN` checked at the run's start).
- `make ingest-report` twice: identical fingerprint.
- `make eval-retrieval` within ±0.03 of S12's final row (or each change explained per question).
- `make eval-chain` for both chains.
- The demo above.

#### PR plan

- 1 PR (`s13-r1-provenance-mvp`). If the size alarm fires when it opens (> ~30 files or > ~800 reviewable lines), split after T1: PR 1 = T1 (ingestion), PR 2 = T3–T6 (the chain), stacked.
- Greptile: once, after the PR opens. Greptile: 18/50 at the sitting.

#### Paid calls allowed

- **Voyage embeddings only,** cap US$0.05 in all: `make embed` for the new texts (~140, plus the held-out chain's) and 1 question vector (the held-out chain's WHY question). Estimate < US$0.01.
- No Anthropic calls, so no credit check (`CLAUDE.md`, "Anthropic credit").

#### Gold chains v0 (T2, done in the sitting)

- **File:** `eval/golden_set/chains-v0.yaml`, sha256 `50323a244638dd154abf7839ab20b5894e27d4a56e6ce0da6f583d75df9e3068`; copied in by the developer (Ubuntu terminal), confirmed by `sha256sum` and `cmp` against the checked scratch file.
- **Who labeled it:** drafted by Claude at the developer's request (`eval/candidates/chains-v0-draft.yaml`, identical below the header). Claude knew the builder's rules while drafting; the brief states this. Principle: accept every text a careful person would cite; date each event step by when it happened; never pick by what the rules choose.
- **Sign-off rule:** the developer reviews all 12 steps (each with its one-line reason; 12 is small enough for a full review) and signs off. Signed off as is, with 3 calls flagged for review: chain 1's implementation date (1.22's release 2021-08-04, not the 2021-07-20 announcement), chain 2's proposal date (the accepted proposal 2025-02-06), chain 2's discussion (PR #3010's comments only).
- **Checks** (`check_gold_draft.py`, `check_gold.log`): 0 errors; every label matches a stored text or a post as T1 will render it. T1's label check repeats the GitHub half against the stored texts.
- **Shape:** chain 1 has 6 labeled steps; chain 2 has 5 labeled steps and a `not_stored` decision (PR #5140). The headline's best case is 6 of 6 and 5 of 6.
- **The held-out WHY question** (the control's query): "Why did Kubernetes add the PreferSameZone and PreferSameNode traffic distribution options for Services?"

#### The held-out chain

- **Drawn:** KEP-3015, "PreferSameZone and PreferSameNode Traffic Distribution" (sig-network, latest milestone v1.35), from 35 KEPs, seeded by this contract's commit SHA (`d6e7d9c`; `draw_heldout.log`, commit `e23e533`).
- **Its tracking issue's fields** (#3015): "Kubernetes Enhancement Proposal:" links the KEP folder (no PR); "Discussion Link:" lists PR #3010, PR #3016 and a bare `#4931`; the first "KEP (`k/enhancements`) update PR(s):" line holds a bare `#5140` (the PR merged 2025-02-11).
- **The wording conflict, decided after the draw:** T1 said "the first PR on the line", T3 "the first URL". **Decision (option A): only full URLs count**, the literal frozen rule; rejected: reading a bare `#N` as that repo's item (B), because it was chosen after seeing that it would find the decision. Expected effect: KEP-3015's decision step is missing `no_link`; reported with the score, not tuned.
- **Its items (T1's rule):** `{enhancements, issues, 3015}` (the tracking issue) and `{enhancements, pull, 3010}` (the first URL of "Discussion Link:"). PRs #3016, #4931 and #5140 are not ingested.
- **Its gold chain and WHY question:** labeled by the developer in the sitting (T2), in `eval/golden_set/chains-v0.yaml`.

## Retro

- **Shipped (with numbers):**
  - **S13-R1** (1 run, 5 tasks; T2 done in the sitting), split after T1 into 2 stacked PRs (ingestion │ chain): 66 files and ~6,000 reviewable lines against `main`, over the ~800 alarm.
    - **T1:** 5 GitHub items as `discussion` documents (tier 7): 210 chunks; stored posts 89, 3, 51 (chain 1, as `expected_posts.log`) and 49, 9 (held-out). Re-ingest fingerprint identical (`sha256:0f0ee078…`). 210 texts embedded (Voyage 39,143 tokens). The chain label check: 32 of 32 labels match.
    - **T3:** migration `0008` (`decisions`, `decision_evidence`); `make chains` rebuilds 2 chains, 12 rows, identical on a re-run; `orgknow chain`. Chain 1 matches all 6 of the sitting's expected picks.
    - **T4:** `make eval-chain`: builder 6 of 6 vs. control 3 of 6 (chain 1); 5 of 6 vs. 1 of 6 (held-out KEP-3015). Both "beats".
    - **T5:** `GET /decisions/{canonical_id}`: 200 equals the CLI's model; 404 with the `make chains` hint; 503 when the database is down.
    - **T6:** the domain model, architecture, evaluation ("Decision provenance (S13)") and README; this retro and the slice brief.
  - **Metric:** decision-chain completeness (new), above. Same UTC day: 4 of 5 and 2 of 4.
  - **Phase 1 re-check:** Recall@10 0.552 → 0.522, Hit@10 1.000 → 0.972, MRR 0.813 → 0.781 (−0.032, just outside ±0.03). Explained per question (`eval/results/s13-chains/per_question.log`): 5 of 36 questions' scores change, all through discussion texts; with them removed (rolled back), all 36 match the earlier run exactly.
  - **Tests:** 1,061 unit (896 at S12's close), 214 integration (189).
  - **Reviews:** 0 must-fix in T1, T3, T5; 2 in T4 (a duplicated opening-post check; the backlog tick); 6 in T6 (an unsourced timing, wrong per-question counts, a sources overclaim, the Quickstart's missing `make fetch-github`). All fixed.
  - **Paid in S13-R1:** Voyage only, ~US$0.007 (210 texts, 39,143 tokens, at an assumed list price) plus 1 question vector; cap US$0.05. No Anthropic calls. Greptile 18/50 before the PRs.
- **Surprises:**
  - **Discussion comments outrank the docs for "now" questions:** their windows never close, so they pass CURRENT's filter. q01 loses all 4 of its labeled hits (Recall@10 0.571 → 0.000) to Discussion #1290's comments.
  - **Post headings repeat:** two adjacent posts by one author on one day share a heading, and #1290's opening post has no text before its first subheading. Chunks are matched by heading-path prefix, never an exact path.
  - **Dates are the weaker half:** 3 steps cite the right text on a different day than the gold (chain 1's implementation: the 07-20 blog vs. 1.22's release 08-04), the gold calls flagged in the sitting.
  - **Plain search fills neither the problem nor the decision step** on either chain: no WHY-question top 10 holds a discussion's opening post or a PR's post (`chains.md`).
- **What didn't work / negative results:**
  - **KEP-3015's decision step is missing (`no_link`):** its update PR is a bare `#5140`, and the frozen rule reads full URLs only. Reported, not tuned (a proposed addition tests the fix on a fresh held-out chain).
  - **Phase 1's MRR moved 0.032**, outside ±0.03. No scoring was changed: whether to demote or filter discussions in CURRENT mode is the developer's call.
  - **Post times are stored by day only,** so rule 6's "before the merge" compares days; an `/approve` posted on the merge day after the merge would still be cited (neither chain has one).
- **Do differently next slice:**
  - Probe a new source's effect on Phase 1, per question, in the sitting (free): open windows passing CURRENT's filter was predictable before the run.
  - Estimate reviewable lines per task with tests included: the sitting estimated ~2,300; the run's tasks came to ~7,100 changed lines, ~3,300 of them tests.
  - In a docs task, name the command behind every number as it is written: the T6 review found 6 sourcing and wording errors.
- **Slice brief:** `docs/learning/S13-provenance-mvp.md`
