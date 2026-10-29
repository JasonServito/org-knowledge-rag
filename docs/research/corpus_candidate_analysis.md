# Corpus Candidate Analysis — Beyond GitLab & Kubernetes

> **Update 2026-09-22:** the validation gate has been run. See `corpus_validation_gate.md`.
>
> - **Decision:** Kubernetes.
> - **GitLab license correction:** the handbook LICENSE is MIT scoped to "the GitLab Software" only, and the handbook pages say "All Rights Reserved". This supersedes the "believed CC BY-SA" note below.

*Organizational Knowledge & Decision Intelligence RAG · Blueprint v2 §5 / Stage 0 · Research date: 2026-09-22*

## 1. Bottom line

- **One new candidate is as good as the front-runners: GOV.UK / Government Digital Service (GDS).**
  - It is the only candidate that scores **≥7 on every criterion**.
  - It stays in the **top 4 under all three weightings** tested.
  - Two decision chains were traced end-to-end with real links.
- **PostHog ties GitLab** on overall score and matches it on enterprise feel.
  - Advantages: a cleaner license (MIT) and GitHub-hosted history.
  - Weakness: its product/engineering RFCs are **private**, so Phase 2 decision provenance is weaker.
- **Nothing clearly beats Kubernetes on versioning and provenance.** Swift Evolution and Fedora match or beat it on decision chains, but they are less enterprise-like.
- **Recommendation:** add **GOV.UK as a third finalist** in the §5.3 validation gate: GitLab vs Kubernetes vs GOV.UK. If the chain trace holds up on 3–5 more changes, GOV.UK is the best-balanced choice. Everything else is secondary or reference only.

## 2. Criteria derived from Blueprint v2

| # | Criterion | Blueprint source | Weight |
|---|---|---|---|
| R1 | Enterprise/workplace resemblance | §1, §5.2 "primary product direction" | 15 |
| R2 | Git-native Markdown/HTML + version history (SHA, dates → valid_from/until) | §10, §13 | 12 |
| R3 | Heterogeneous sources with derivable authority tiers | §15 | 10 |
| R4 | Real supersession, stale content, conflicts | §16, query modes HISTORY/CHANGE | 12 |
| R5 | Traceable decision chains (problem → discussion → proposal → decision → implementation → current docs) | §3.2, §5.3 gate | 15 |
| R6 | API access to discussion artifacts | §10, §22 | 6 |
| R7 | License permits reuse with attribution | §6 | 10 |
| R8 | Fits small RDS / ≤$50/mo (subset OK) | §27 | 5 |
| R9 | Public and stable in 2026, no history breaks | §10 incremental ingestion | 8 |
| R10 | Recognizable to engineers | §31 | 7 |

The weights are my judgement from the blueprint's stated priorities. Sensitivity checks are in §4.

## 3. Scorecard (1–10 per criterion; weighted total out of 100)

| Candidate | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Kubernetes *(current)* | 5 | 10 | 9 | 10 | 8 | 8 | 9 | 7 | 10 | 9 | **84.1** |
| **GOV.UK / GDS** | 7 | 8 | 9 | 9 | 8 | 8 | 8 | 8 | 9 | 7 | **80.8** |
| **PostHog** | 9 | 9 | 6 | 8 | 6 | 9 | 9 | 7 | 9 | 8 | **79.6** |
| GitLab *(current)* | 10 | 8 | 8 | 8 | 7 | 6 | 7 | 7 | 8 | 9 | **79.5** |
| Swift Evolution | 3 | 9 | 8 | 7 | 10 | 8 | 9 | 10 | 9 | 6 | 76.9 |
| Fedora | 6 | 5 | 9 | 9 | 10 | 5 | 8 | 8 | 6 | 7 | 74.5 |
| Wikipedia policy/RfC | 5 | 3 | 9 | 10 | 8 | 9 | 8 | 7 | 10 | 6 | 73.2 |
| CNCF TOC | 6 | 9 | 7 | 7 | 8 | 8 | 4 | 10 | 9 | 6 | 72.4 |
| GSA-TTS (18F) handbook | 9 | 9 | 5 | 7 | 4 | 7 | 10 | 9 | 6 | 7 | 72.1 |
| Apache Software Foundation | 7 | 6 | 8 | 6 | 6 | 8 | 8 | 8 | 9 | 6 | 70.1 |
| IETF | 3 | 3 | 9 | 10 | 9 | 9 | 4 | 8 | 10 | 6 | 68.2 |
| Debian | 4 | 7 | 8 | 8 | 7 | 4 | 6 | 9 | 9 | 5 | 66.1 |
| Sourcegraph (archived) | 9 | 8 | 5 | 6 | 3 | 7 | 9 | 8 | 5 | 6 | 65.2 |
| GitHub docs/site-policy | 5 | 7 | 6 | 8 | 3 | 8 | 6 | 6 | 7 | 8 | 61.0 |
| Mattermost | 8 | 5 | 4 | 5 | 3 | 6 | 3 | 9 | 6 | 5 | 51.9 |
| Oxide RFDs | — | — | — | — | — | — | — | — | — | — | excluded |

**Caveat:** the scores are judgement calls informed by verified facts. Differences under about 5 points are within noise. The top four are effectively a tie on weighted score, and the decision should come from the §5.3 chain-trace gate, not this table.

## 4. Sensitivity (does the winner change with priorities?)

| Weighting | #1 | #2 | #3 | #4 |
|---|---|---|---|---|
| Base (above) | Kubernetes 84.1 | GOV.UK 80.8 | PostHog 79.6 | GitLab 79.5 |
| Enterprise-heavy (R1 = 25) | GitLab 82.0 | PostHog 81.3 | Kubernetes 80.1 | GOV.UK 79.4 |
| Provenance-heavy (R5 = 22) | Kubernetes 86.2 | GOV.UK 81.9 | Swift Evolution 81.8 | Fedora 78.3 |

**Reading:**
- **GitLab** wins only if enterprise resemblance dominates.
- **Kubernetes** wins whenever versioning and provenance dominate.
- **GOV.UK** never drops below #4 and has no weak criterion. That makes it the lowest-risk pick if you want *both* parts of the thesis.

## 5. Candidate analyses

### 5.1 GOV.UK / Government Digital Service — **new finalist**

**Sources (all public; about 8 repos plus one API)**
- **govuk-developer-docs**, which aggregates ADRs from publishing-api, govuk-infrastructure and the archived govuk-aws.
- **govuk-rfcs**:
  - YAML front-matter with `status`, `implementation` and `status_last_reviewed`.
  - Two-week review, merge on senior-tech approval.
- **gds-way**: an engineering "how we work" handbook.
- **Design System stack**: govuk-design-system, govuk-frontend releases/CHANGELOG, design-system-backlog, design-system-architecture (proposals and decision records).
- **Service Manual**: via the Content API, which gives `first_published_at`, `public_updated_at` and `change_history`.

**Authority tiers (derivable)**
1. Service Standard / Manual
2. GDS Way, Developer Docs, Design System guidance
3. Accepted RFC/ADR
4. Frontend release notes
5. PR review threads
6. Backlog/community issues

**Chain A: GraphQL for GOV.UK (engineering decision)**
1. Problem + proposal: [RFC-172](https://github.com/alphagov/govuk-rfcs/blob/main/rfc-172-graphql-for-govuk.md).
2. Discussion/decision: [PR #172](https://github.com/alphagov/govuk-rfcs/pull/172), merged 2024-06-03.
3. Implementation ADRs: [ADR-008](https://docs.publishing.service.gov.uk/repos/publishing-api/arch/adr-008-typing-for-graphql-editions.html) and [ADR-013](https://docs.publishing.service.gov.uk/repos/publishing-api/arch/adr-013-grahql-draft-content.html).
4. Current docs: [manual/graphql](https://docs.publishing.service.gov.uk/manual/graphql.html).
5. **Built-in conflict:** the RFC front-matter still reads `implementation: pending` (verified 2026-09-22), while the current docs describe GraphQL in production. This is a ready-made stale-vs-current eval case.
6. **Gap:** the ADRs don't link back to the RFC. That link has to be inferred from topic and dates.

**Chain B: Password input component**
1. Community need: [backlog #240](https://github.com/alphagov/govuk-design-system-backlog/issues/240), 2021.
2. Epic: [frontend #4063](https://github.com/alphagov/govuk-frontend/issues/4063).
3. Guidance draft: [design-system #3352](https://github.com/alphagov/govuk-design-system/issues/3352).
4. Implementation: [PR #4442](https://github.com/alphagov/govuk-frontend/pull/4442).
5. Release: [v5.3.0](https://github.com/alphagov/govuk-frontend/releases/tag/v5.3.0).
6. Current guidance: the [component page](https://design-system.service.gov.uk/components/password-input/).
7. **Built-in conflict:** epic #4063 is closed as "not planned" even though the component shipped, and #240 is still open.

**Supersession examples**
- govuk-aws was archived in Feb 2025 in favour of govuk-infrastructure.
- Password guidance moved from a *pattern* page to a *component* page.

**License:** Open Government Licence v3.0 (© Crown copyright) for docs, and MIT for code. Issue and PR comments fall under GitHub's ToS, not the OGL. Store author and URL for each comment. Some repos (e.g., the backlog) have no LICENSE file.

**Risks**
- Public sector, not a company, so R1 = 7 not 10.
- Less recognizable to North American engineers.
- The Service Manual is not in git.
- Chains span several repos, so relationship extraction takes real work (this is also a good engineering challenge).
- A GitHub token is required: the unauthenticated limit is 60/hr.

### 5.2 PostHog — **strong enterprise alternative to GitLab**

**Sources**
- `contents/handbook` in [PostHog/posthog.com](https://github.com/PostHog/posthog.com): Markdown, full history, active in Sept 2026.
- [requests-for-comments-public](https://github.com/PostHog/requests-for-comments-public) (MIT).
- Linked PRs in PostHog/posthog.

**License (verified):** `/contents/` is **MIT**. Everything outside `/contents/` is *all rights reserved*, so ingest only `contents/`.

**Chain: PostHog for Startups**
1. Issue [#5415](https://github.com/PostHog/posthog.com/issues/5415).
2. PR [#5451](https://github.com/PostHog/posthog.com/pull/5451).
3. RFC [#116](https://github.com/PostHog/requests-for-comments-public/issues/116).
4. Implementation [posthog#16672](https://github.com/PostHog/posthog/pull/16672).
5. Current [handbook page](https://posthog.com/handbook/marketing/startups).
6. **Real supersession:** the credit changed from $38k to $50k, and an AI-tools exclusion applies from 2026-09-14.
7. **Gaps:** the PR behind the $38k → $50k change was not found, and the file path moved.

**Useful for rejected-proposal cases:** stale/auto-closed handbook PRs (e.g., [#19806](https://github.com/PostHog/posthog.com/pull/19806)) serve as "proposal not adopted" examples.

**Main weakness:** product and engineering RFCs live in private repos (`requests-for-comments-internal`, `product-internal`). The WHY questions for product decisions will often be unanswerable. That exercises refusal, but it weakens Phase 2.

**vs GitLab**
- About equal on R1.
- Better on license (MIT vs share-alike), API (GitHub, no gitlab.com robots/rate-limit risk) and history continuity.
- Worse on decision-artifact depth. GitLab has design documents and public epics.

### 5.3 Kubernetes and GitLab — re-verified risks (new findings)

**Kubernetes**
- 655 `kep.yaml` files with `status`, `stage`, milestones, `replaces` and `superseded-by`.
  - The status values are messy (e.g., "imlpemented", "superseded"), so normalise them.
  - Only 46 KEPs use `replaces` and 13 use `superseded-by`.
- Docs are CC BY 4.0, with release branches 1.4–1.36.
- **SIG meeting notes are Google Docs gated behind dev@kubernetes.io membership.** They are not usable. The "discussion" tier must come from GitHub issues/PRs.

**GitLab**
- The handbook moved to `content-sites/handbook` in 2023, and GitLab says 12 years of history came with it.
- Design documents moved from docs.gitlab.com to the handbook in 2024. Their earlier history stays in gitlab-org/gitlab, so this is a **history break** to handle.
- A separate internal handbook exists (how much content moved there is unquantified).
- **The handbook license was not verified this session.** Docs are CC BY-SA 4.0, and the handbook is believed to be the same. Confirm the LICENSE file manually. Share-alike applies to any redistributed corpus.
- gitlab.com rate limits:
  - Currently 500 req/min unauthenticated.
  - A proposed tier change would cut unauthenticated traffic to 60 req/hr.
  - Mitigation: git clone for content, plus a token for MRs/issues/epics.
  - Snapshot early.

### 5.4 Strong on provenance, weak on enterprise feel

- **Swift Evolution**
  - The cleanest decision chains of any candidate: proposal header → review thread → "Returned for revision"/"Accepted" post → implementation → Swift book.
  - Apache 2.0 covers forum posts too.
  - Verified chain: SE-0302 Sendable.
  - Reads as language design (R1 = 3). Good as a *secondary* tenant for decision-chain evaluation.
- **Fedora**
  - Change proposals are template-linked (owner, FESCo ticket, tracker bug, release-notes ticket).
  - Real supersession: DNF5 was dropped for F39 and re-accepted for F41. CC BY-SA 4.0.
  - Blockers:
    - Spread across wiki + Discourse + Forgejo + GitLab, so it is not git-native.
    - Anubis bot protection blocks automated fetches.
    - The Pagure → Forgejo migration is moving URLs.
- **Wikipedia policy + RfC**
  - Explicit authority templates (policy / guideline / essay) and formal RfC closures. Excellent supersession.
  - Not git-native, wikitext parsing is painful, and it is encyclopedic rather than organizational.
- **IETF**
  - Perfect `Obsoletes`/`Updates` metadata and an open Datatracker API.
  - The license (Trust Legal Provisions) **does not grant modification/derivative rights**, and it is not git-native. Avoid as the core corpus.
- **CNCF TOC**
  - Good governance process, and it overlaps Kubernetes.
  - **No LICENSE file** in the repo. Needs confirming before use.

### 5.5 Not recommended

| Candidate | Reason |
|---|---|
| GSA-TTS (18F) handbook | CC0 and a real HR/ops handbook, but archived 2026-06-09 after 18F's elimination, and discussion was in private Slack. Useful only as a stale-content test set. |
| Sourcegraph handbook | Archived 2024-07; content scrubbed before archive; RFCs were in Google Drive (dead links). |
| Mattermost handbook | CC BY-NC-SA 3.0 (non-commercial), noisy GitBook history, weak decision artifacts. |
| Oxide RFDs | Source repo is private; no content license; about 83 public RFDs. Use their state model (prediscussion → discussion → published → committed/abandoned) as a *taxonomy reference* only. |
| GitHub docs / site-policy / roadmap | Decisions are internal; the roadmap repo has been stale since 2024-10; licenses are mixed. |
| Debian, Apache, Go, Rust, Python | Good individual traits (Debian's policy upgrading checklist, Apache's VOTE API, the PEP `Superseded-By` header), but either less enterprise-like or weaker chain linkage than the finalists. |

## 6. Recommended next step (updates Stage 0 / §5.3)

1. **Expand the validation gate to three finalists:** GitLab, Kubernetes, GOV.UK. PostHog is an alternate if GitLab's license or API access fails.
2. **Trace 3–5 changes per finalist** and record, per step:
   - found / inferred / missing
   - link type (explicit link vs date/topic inference)
   - whether a real stale/conflict case exists
3. **Decision rule** (suggested):
   - Pick the corpus with the most **complete chains (≥5 of 6 steps with explicit links)**.
   - Tie-break on R1, because enterprise resemblance is the product direction.
4. **Before ingestion, whichever wins:**
   - confirm the LICENSE file by hand
   - get an API token
   - snapshot raw sources to S3 early (rate-limit and migration risk)

## 7. Confidence and gaps

- **Verified this session:**
  - PostHog LICENSE split
  - GOV.UK RFC-172 front-matter
  - Kubernetes KEP counts (from a local clone)
  - Swift Evolution counts
  - archive dates for TTS, Sourcegraph and govuk-aws
- **Not verified:**
  - GitLab handbook LICENSE
  - the size of GitLab's internal-handbook split
  - Fedora FESCo vote text (blocked)
  - CNCF docs license
  - some commit counts (they came from page summaries, so treat them as approximate)
- **Subjective:** all 1–10 scores are judgements. The chain traces carry more weight than the table.

## Sources

- [PostHog/posthog.com](https://github.com/PostHog/posthog.com) · [PostHog RFCs (public)](https://github.com/PostHog/requests-for-comments-public)
- [alphagov/govuk-rfcs](https://github.com/alphagov/govuk-rfcs) · [GOV.UK Developer Docs](https://docs.publishing.service.gov.uk) · [GOV.UK Design System](https://design-system.service.gov.uk)
- [GitLab handbook roadmap (migration)](https://handbook.gitlab.com/handbook/about/roadmap/) · [GitLab.com rate limits](https://docs.gitlab.com/user/gitlab_com/rate_limits/) · [GitLab docs legal](https://docs.gitlab.com/legal/)
- [kubernetes/enhancements](https://github.com/kubernetes/enhancements) · [kubernetes/website](https://github.com/kubernetes/website)
- [swiftlang/swift-evolution](https://github.com/swiftlang/swift-evolution) · [SE-0302 acceptance](https://forums.swift.org/t/accepted-se-0302-sendable-and-sendable-closures/45786)
- [Fedora Changes/SwitchToDnf5](https://fedoraproject.org/wiki/Changes/SwitchToDnf5) · [Fedora forge migration](https://communityblog.fedoraproject.org/the-forge-is-our-new-home/)
- [IETF Trust Legal Provisions 5.0](https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5) · [RFC 9846 datatracker](https://datatracker.ietf.org/doc/rfc9846/)
- [GSA-TTS/handbook](https://github.com/GSA-TTS/handbook) · [sourcegraph/handbook](https://github.com/sourcegraph/handbook) · [mattermost-handbook](https://github.com/mattermost/mattermost-handbook) · [Oxide RFD site](https://rfd.shared.oxide.computer)
- [cncf/toc](https://github.com/cncf/toc) · [Debian Policy upgrading checklist](https://www.debian.org/doc/debian-policy/upgrading-checklist.html)
