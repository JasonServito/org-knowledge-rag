# ADR-001: Corpus is Kubernetes

- **Status:** Accepted
- **Date:** 2026-09-22
- **Supersedes:** Blueprint v2 §5.2 ("GitLab vs. Kubernetes pending validation")
- **Evidence:** `docs/research/corpus_validation_gate.md`, `docs/research/corpus_candidate_analysis.md`

## Context

The §5.3 validation gate traced 4 changes each for GitLab, Kubernetes and GOV.UK. All three produced complete chains. GitLab's handbook failed a precondition: it has no open content license (pages are marked "All Rights Reserved"). Kubernetes had the most real conflicts (3/4), public rationale for all 4 chains, and the strongest machine-readable link keys.

## Decision

Use **Kubernetes** as the single Phase 1 corpus.

| Source | Content | License |
|---|---|---|
| `kubernetes/enhancements` | KEP READMEs, `kep.yaml`, PRR files | Apache-2.0 |
| `kubernetes/website` | English docs per `release-1.x` branch; blog from `main` | CC BY 4.0 (code samples Apache-2.0) |
| `kubernetes/kubernetes` | `CHANGELOG/CHANGELOG-1.x.md` | Apache-2.0 |
| `kubernetes/community` | Governance and process docs (in-scope SIGs only) | Apache-2.0 / CC BY 4.0 (verify per file) |
| `kubernetes/sig-release` | Release process docs | Apache-2.0 |

GitHub issues, PRs and Discussions are **Phase 2 only**. Ingest them only when a traced chain links to them.

## Consequences

- **Positioning (§31):** frame Kubernetes as "an organization of ~3k contributors with SIGs, a release team, and formal policy/deprecation processes". Lead demos with organizational chains (release cadence, PSP→PSA, legacy token cleanup) rather than API trivia.
- **Differentiation risk:** "RAG over Kubernetes docs" is a common demo. The README must lead with temporal, authority and provenance results, not with the domain.
- **Attribution:** every citation shows the source URL and release/date. The README carries license notices and a non-affiliation disclaimer.
- **Redistribution:** the corpus is **not** committed to the public repo. Commit only manifests (repos, paths, branches, SHAs) and ingestion code. Snapshots go in private S3.
- **Reinstating GitLab** requires written reuse permission from GitLab. A second organization (e.g., GOV.UK) is optional post-MVP work to test generalization.
