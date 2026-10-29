# Corpus Validation Gate — Results & Decision

*Blueprint v2 §5.3 / Stage 0 · Run 2026-09-22 · Finalists: GitLab, Kubernetes, GOV.UK (GDS)*

## 1. Decision

**Recommended corpus: Kubernetes.**

- **Chain tracing:** all three finalists passed. Each reached 4/4 complete chains, with ≥5 of 6 steps found and 0 steps missing out of 24.
- **Why GitLab is not the pick:** by the link-explicitness rule agreed earlier, GitLab would win. It **failed a precondition that rule did not include: a usable content license.**
  - The handbook repository's LICENSE grants MIT only "With regard to the GitLab Software".
  - Handbook pages carry "© 2026 GitLab All Rights Reserved".
  - No open content license for the handbook was found.
- **Why Kubernetes over GOV.UK:** Kubernetes has the clean license, the most real conflicts (3 of 4), public rationale for every chain, and the strongest machine-readable link keys.
- **What the choice costs:** enterprise resemblance, R1. See §5 for how to reframe that.

**GitLab can be reinstated only if** GitLab confirms in writing that its handbook content may be reused. Even then, Kubernetes remains the stronger fit for the version, conflict and provenance thesis. The case for GitLab would be enterprise look-and-feel only.

## 2. Method

- **Changes traced:** 4 per finalist.
  - 2 best-case, at least one of them organizational or process.
  - 2 chosen at random: `random.seed(2026)` over a documented list; picks were not swapped after selection.
- **Steps:** each change was traced through the 6 §5.3 steps.
- **Per step, we recorded:**
  - FOUND-EXPLICIT, FOUND-INFERRED or MISSING
  - URL and date
  - whether the link could be extracted by a machine
- **Per change, we also recorded:** stale or conflict cases, whether the rationale is public, and 5 golden-set seed questions (CURRENT / HISTORY / CHANGE / WHY / UNANSWERABLE).
- **Random sampling frames** (not like-for-like; see §4 caveat):

| Corpus | Sampled from | Pool size | Picks |
|---|---|---|---|
| Kubernetes | Implemented KEPs, milestone ≥ v1.25 | 149 | KEP-2799 (legacy SA tokens), KEP-4858 (IP/CIDR validation) |
| GOV.UK | Accepted RFCs numbered ≥ 100 | 38 | RFC-117 (container runtime), RFC-145 (unarchive admin template) |
| GitLab | Handbook sitemap pages | 3,584 | Advanced CI/CD Lab 4; engineering development-onboarding |

## 3. Results

| Metric | GitLab | Kubernetes | GOV.UK |
|---|---|---|---|
| Complete chains (≥5/6 steps found) | 4/4 | 4/4 | 4/4 |
| Steps explicitly linked | **22/24** | 20/24 | 19/24 |
| Chains with ≥5 explicit steps | **4/4** | 2/4 | 2/4 |
| Missing steps | 0/24 | 0/24 | 0/24 |
| Changes with a real conflict or stale case | 1/4 (+2 mild) | **3/4** | 2/4 |
| Public WHY (full rationale) | 2/4 (1 "after careful consideration", 1 partial) | **4/4** | 4/4 (1 pivot unexplained) |
| Random picks that were real decisions | 0/2 (lab reorder; stub-page move) | **2/2** | **2/2** |
| Content license | ❌ Not openly licensed (see §1) | ✅ CC BY 4.0 docs; Apache-2.0 KEPs/code | ⚠️ OGL v3 / MIT, but `govuk-rfcs` has no licence file |
| Enterprise resemblance (R1) | **Best** | Weakest | Middle |
| Machine link keys | Commit→MR API, `merged_by`, "Relates to" regex | **KEP dir # = issue #; PRR yaml; CHANGELOG PR refs; feature-gate name = docs filename** | RFC file → merge commit → PR; CHANGELOG PR refs |
| Automation effort | Medium | **Low–medium** | Medium |
| Access in development | Browser/API partly anonymous; `/notes` 401; release posts before 16.x gone | GitHub clone (token needed for API) | GitHub clone (token needed for API) |

### Findings that matter for the build (verified by spot-check)

- **Kubernetes `kep.yaml` status is unreliable. That is useful as conflict material, but bad as a filter.**
  - KEP-2572 (release cadence) still says `status: implementable, stage: alpha, latest-milestone: v1.22`, yet the policy has been live since 2021.
  - KEP-4858 says `implemented / stable / v1.38`. CHANGELOG-1.38 does not exist yet, and the docs still say beta.
  - KEP-2579 (Pod Security Admission) has `replaces: []`, even though it replaced PodSecurityPolicy.
  - **Implication:** derive `valid_from` and `status` from release CHANGELOGs and docs, not from `kep.yaml` alone. Treat `kep.yaml` as a *claim* that the conflict detector checks.
- **GOV.UK has the same pattern.**
  - RFC-171 and RFC-186 were merged but still say `status: proposed`.
  - RFC-172 says `implementation: pending` while the feature is in production.
- **The Kubernetes discussion tier is partly gated.**
  - SIG and leads meeting notes, and early proposals such as PSP's "3-Tier" doc, are Google Docs behind sign-in.
  - **Implication:** the discussion tier comes from GitHub issues, PRs and Discussions, plus the blog. WHY questions whose answer lives only in those docs become UNANSWERABLE test cases.
- **GitLab history:**
  - The handbook repo history starts 2020-06-06; anything earlier is only in `www-gitlab-com`.
  - MR references span two projects.
  - Handbook redirects are deleted on a schedule, so old URLs end up at a sign-in page.

## 4. Caveats

- **The sampling frames differ.** GitLab was sampled from *pages*; Kubernetes and GOV.UK from *decision records*. This inflates the "random picks were real decisions" gap. The underlying point still holds: in GitLab, you have to find decisions; in Kubernetes, the KEP registry *is* a decision index.
- **The sample is small.** It is n=4 per corpus. The results show feasibility, not rates.
- **Tooling differences.** GitLab tracing needed the desktop browser, because the sandbox blocks gitlab.com. That is our tooling, not a corpus flaw.
- **Not legal advice.** The license reading is based on the LICENSE file and page footers. It is not a legal opinion; if GitLab matters to you, ask GitLab directly.

## 5. Consequences for the blueprint

1. **§5.2:** set the corpus to **Kubernetes**, with sources:
   - kubernetes/enhancements (KEPs + tracking issues)
   - kubernetes/website (docs per release branch + blog)
   - kubernetes/kubernetes CHANGELOGs
   - kubernetes/community (governance and process)
   - kubernetes/sig-release
2. **§31 positioning** (fixes the R1 gap): pitch it as "an organization of about 3k contributors with SIGs, a release team, formal policy and deprecation processes". Lead the demo with **organizational** chains (release cadence, deprecation policy, PRR process, registry move), not only API features.
3. **§15 authority tiers** (first draft):
   1. Current versioned docs on kubernetes.io
   2. KEP README, status `implemented`
   3. CHANGELOG / release notes / deprecation guide
   4. KEP README, status `implementable` or `provisional`
   5. Blog post
   6. Tracking issue / PR review
   7. Community issue
4. **§13 data model:**
   - Add `claimed_status` (from `kep.yaml`) separate from `observed_status` (from CHANGELOG and docs).
   - Add `release_version` as a first-class temporal key alongside commit dates.
5. **§19 golden set:** 20 Kubernetes seed questions are ready (Appendix A). They cover all 5 query classes, including 4 UNANSWERABLE questions grounded in gated Google Docs.
6. **Stage 1 subset:** 3 SIGs (Release, Auth, Network) × releases v1.20–v1.37 + the four traced KEPs. This keeps the first vertical slice small.
7. **Optional later:** add GOV.UK as a second organization, to test whether authority and temporal logic generalize. This is not MVP scope.

## Appendix A — Kubernetes golden-set seeds (from traced chains)

| # | Class | Question | Expected answer (short) | Sources |
|---|---|---|---|---|
| 1 | CURRENT | How many Kubernetes minor releases happen per year? | About 3 | kubernetes.io/releases/release/ |
| 2 | HISTORY | What was the release cadence before 2021? | About 4 per year (quarterly) | website release-1.21 `releases/release.md`; blog 2021-07-20 |
| 3 | CHANGE | When was the move to 3 releases/year decided, and which release first followed it? | KEP PR #2567 merged 2021-04-23; v1.22 used the 15-week cycle | KEP-2572; blog 2021-07-20 |
| 4 | WHY | Why move to 3 releases per year? | v1.19 slip, predictability, less upgrade churn for users and the release team | KEP-2572 Motivation; sig-release discussion #1290 |
| 5 | UNANSWERABLE | Which leads objected in the SIG Chair/TL meeting? | Insufficient evidence: the notes are in a gated Google Doc | — |
| 6 | CURRENT | What enforces pod security standards in-tree? | PodSecurity admission, GA since v1.25 | docs/concepts/security/pod-security-admission |
| 7 | HISTORY | What did Pod Security Admission replace, and when was that removed? | PodSecurityPolicy: deprecated v1.21, removed v1.25 | CHANGELOG-1.21, CHANGELOG-1.25 |
| 8 | CHANGE | What were Pod Security Admission's graduation stages? | Alpha 1.22, beta 1.23, GA 1.25 | KEP-2579; issue #2579 |
| 9 | WHY | Why replace PSP instead of fixing it? | Fixes would break compatibility; confusing authorization model; could not be on by default | KEP-2579 Motivation; CHANGELOG-1.25 |
| 10 | UNANSWERABLE | What objections were raised in the "3-Tier Pod Security Proposal" doc comments? | Insufficient evidence: gated doc | — |
| 11 | CURRENT | What happens to unused auto-generated ServiceAccount token Secrets? | Labelled invalid after 1 year unused, then deleted after a further period | docs service-accounts-admin |
| 12 | HISTORY | Did Kubernetes create a token Secret for every ServiceAccount? | Yes, before v1.24 | website release-1.23 service-accounts-admin |
| 13 | CHANGE | When did legacy token cleanup reach GA? | v1.30 (k/k #122635) | CHANGELOG-1.30 |
| 14 | WHY | Why stop auto-generating Secret-based tokens? | Bound TokenRequest tokens (GA 1.22) are more secure | KEP-2799; KEP-1205 |
| 15 | UNANSWERABLE | How many clusters had legacy tokens deleted after v1.30? | Insufficient evidence | — |
| 16 | CURRENT | Does the API server reject IPs with leading zeros by default? | Yes, since v1.36 (`StrictIPCIDRValidation`, beta, on by default) | CHANGELOG-1.36; feature-gates docs |
| 17 | HISTORY | How were leading-zero IPs in Services handled before? | Warning only, since v1.27 | k/k v1.31.1 `pkg/api/service/warnings.go`; KEP-4858 |
| 18 | CHANGE | What are the stages of strict IP/CIDR validation? | Alpha 1.33, beta 1.36, GA *planned* 1.38. This is a conflict case: `kep.yaml` claims implemented/stable | KEP-4858; issue #4858 |
| 19 | WHY | Why tighten IP/CIDR validation? | Ambiguous parsing (e.g., CVE-2021-29923) can bypass security controls | KEP-4858; k/k #108074 |
| 20 | UNANSWERABLE | How many production clusters store non-canonical IPs in etcd? | Insufficient evidence (KEP has no metrics) | — |

Conflict and stale cases for the §16 conflict test set:

- KEP-2572 `kep.yaml` (alpha / v1.22) vs policy in force.
- sig-release `versioning.md` said "every three months" until 2026-02-13.
- KEP-2579 `replaces: []` plus a wrong beta date in Implementation History.
- KEP-4858 status claims GA before release.

## Appendix B — Other finalists: notable traced chains (for reference)

- **GitLab**
  - Values rename "Spend company money like it's your own" → "responsibly": handbook !18811, merged 2026-07-02. The rationale is in the MR, and the finance page is still stale.
  - Runner registration-token removal pulled from 18.0: gitlab#525239 → gitlab!184721 / handbook!12436 / runner!5487. The docs conflict: the runner/register page says 20.0, while the blueprint says no milestone.
- **GOV.UK**
  - RFC process change: govuk-rfcs PR #173, 2024-05-15.
  - Header → Service navigation: govuk-frontend v5.6.0 → v5.9.0 deprecation → v6.0.0 removal.
  - RFC-117 container runtime: the ECS→EKS pivot is undocumented.
  - RFC-145 unarchive admin template: the dev-docs claim that "most admin apps use it" is stale.

## Sources

- [kubernetes/enhancements](https://github.com/kubernetes/enhancements): [KEP-2572](https://github.com/kubernetes/enhancements/tree/master/keps/sig-release/2572-release-cadence), [KEP-2579](https://github.com/kubernetes/enhancements/tree/master/keps/sig-auth/2579-psp-replacement), [KEP-2799](https://github.com/kubernetes/enhancements/tree/master/keps/sig-auth/2799-reduction-of-secret-based-service-account-token), [KEP-4858](https://github.com/kubernetes/enhancements/tree/master/keps/sig-network/4858-ip-cidr-validation)
- [sig-release discussion #1290](https://github.com/kubernetes/sig-release/discussions/1290) · [Release cadence blog](https://kubernetes.io/blog/2021/07/20/new-kubernetes-release-cadence/) · [Pod Security Admission docs](https://kubernetes.io/docs/concepts/security/pod-security-admission/) · [kubernetes/website LICENSE](https://github.com/kubernetes/website/blob/main/LICENSE)
- [GitLab handbook !18811](https://gitlab.com/gitlab-com/content-sites/handbook/-/merge_requests/18811) · [gitlab#525239](https://gitlab.com/gitlab-org/gitlab/-/issues/525239) · [www-gitlab-com #358 "Add creative commons license to all handbooks"](https://gitlab.com/gitlab-com/www-gitlab-com/-/work_items/358)
- [govuk-rfcs PR #173](https://github.com/alphagov/govuk-rfcs/pull/173) · [RFC-117](https://github.com/alphagov/govuk-rfcs/blob/main/rfc-117-container-runtime.md) · [govuk-frontend v5.3.0+ CHANGELOG](https://github.com/alphagov/govuk-frontend/blob/main/CHANGELOG.md)
