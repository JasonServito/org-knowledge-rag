# Architecture Decision Records

An ADR records **one decision**, why it was made, and what it costs. ADRs are the project's highest source of truth (see `CLAUDE.md`). They are also interview material: each one answers the question "why did you do it that way?"

## Index

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-corpus-kubernetes.md) | Corpus is Kubernetes | Accepted |
| [002](ADR-002-versioning-and-identity.md) | Versioning and document identity | Proposed (accept in S02) |
| [003](ADR-003-authority-and-status.md) | Source types, authority tiers, status taxonomy | Proposed (accept in S02) |
| [004](ADR-004-toolchain.md) | Development toolchain | Accepted |

The queue of upcoming ADRs is in `docs/backlog.md`.

## Rules

- **When to write one:** new dependency or service; schema shape; a retrieval or eval method; anything that is hard to reverse; anything you'd be asked "why?" about.
- **Statuses:** Proposed → Accepted → (Superseded by ADR-NNN). Never edit an accepted decision silently. Write a new ADR that supersedes it.
- **Amendments:** an accepted ADR may get a dated `## Amendment YYYY-MM-DD` section at the end, for clarifications that add no new decision (e.g. naming a library the decision already implies). Each bullet says what, why, and the alternative rejected. The original text stays unchanged. A changed decision still needs a superseding ADR.
- **Keep it short:** about one page. If it needs more, the decision is probably two decisions.
- **Who writes it:** the agent may draft an ADR. Only the developer sets the status to **Accepted**.

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
