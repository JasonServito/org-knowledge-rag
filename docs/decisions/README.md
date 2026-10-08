# Architecture Decision Records

An ADR records **one decision**, why it was made, and what it costs. ADRs are the project's highest source of truth (see `CLAUDE.md`). They are also interview material: each one answers the question "why did you do it that way?"

## Index

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-corpus-kubernetes.md) | Corpus is Kubernetes | Accepted |
| [002](ADR-002-versioning-and-identity.md) | Versioning and document identity | Accepted (amended in S02 and S05-R2) |
| [003](ADR-003-authority-and-status.md) | Source types, authority tiers, status taxonomy | Accepted (amended in S02 and S05-R2) |
| [004](ADR-004-toolchain.md) | Development toolchain | Accepted (amended through S04) |
| [005](ADR-005-data-access.md) | Data access approach | Accepted |
| [006](ADR-006-generation-and-tracing.md) | Generation model, structured output, tracing | Accepted |

The queue of upcoming ADRs is in `docs/backlog.md`.

## Rules

- **When to write one:** new dependency or service; schema shape; a retrieval or eval method; anything that is hard to reverse; anything you'd be asked "why?" about.
- **Statuses:** Proposed → Accepted → (Superseded by ADR-NNN). Never edit an accepted decision silently: change it as below.
- **Amendments:** an accepted ADR may get a dated `## Amendment YYYY-MM-DD` section at the end, for clarifications that add no new decision (e.g. naming a library the decision already implies). Each bullet says what, why, and the alternative rejected. The original text stays unchanged.
- **Changing one sub-decision** (a `Dn`): decided by the developer in a sitting, with its evidence (and a devil's advocate when the decision protocol calls for one). The sub-decision's text is updated in place, so the ADR reads as the current rule, and the change is logged in a dated `## Changes from <sitting> (YYYY-MM-DD)` table: Where / Was / Now / Evidence. The status line names the sitting. (S05-R3 sitting, decision 6: this is how S02 and S05-R2 changed ADR-002 and ADR-003.)
- **Superseding:** a new ADR that supersedes the old one is needed only when the ADR's main decision (its title) changes.
- **Keep it short:** about one page. If it needs more, the decision is probably two decisions.
- **Who writes it:** the agent may draft an ADR. The developer decides in the sitting. Claude commits the ADR as Accepted in the run PR, and the developer's merge confirms it.
- **Greptile context:** add each new ADR to `.greptile/files.json`, so the PR reviewer reads it. Greptile can't take a folder.

## Template

```markdown
# ADR-NNN: <decision title>

- **Status:** Proposed | Accepted | Superseded by ADR-NNN
- **Date:** YYYY-MM-DD
- **Blueprint/spec refs:**

## Context
What forces this decision? What facts (with evidence) constrain it?

## Decision
What we will do, stated precisely enough to implement and test.

## Alternatives considered
| Option | Why not |
|---|---|

## Consequences
What gets easier, what gets harder, what we deferred, what we must now verify.
```
