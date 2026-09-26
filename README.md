# Organizational Knowledge & Decision Intelligence RAG

A retrieval-augmented generation system that treats **time, source authority, and conflicting information** as first-class data rather than leaving them for the LLM to guess at.

It's evaluated on the public Kubernetes project: KEPs, versioned docs, release notes, and governance documents. The system answers four kinds of question, each with citations:

- what's true **now**
- what was true **before**
- **how** something changed
- **why** it changed

It refuses when the public record doesn't contain the answer.

> **Status:** pre-development. Foundation slice (S01) in progress. See [`docs/backlog.md`](docs/backlog.md).

## Why this is harder than "chat with your docs"

Organizational knowledge changes over time. Sources differ in authority, and documents contradict each other. For example, a KEP's metadata can claim a feature is GA before the release notes say it shipped. This project models versions, authority and conflicts explicitly, and measures every retrieval technique against a fixed, human-verified golden set.

## Quickstart

*Filled in and verified in S01-T8.*

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/product-spec.md`](docs/product-spec.md) | Phase 1 scope, non-goals, acceptance criteria |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records |
| [`docs/backlog.md`](docs/backlog.md) | Ordered slices and tasks |
| [`docs/ai-workflow.md`](docs/ai-workflow.md) | How this project is built with AI assistance |
| [`CLAUDE.md`](CLAUDE.md) | Rules for the coding agent |
| [`docs/learning/`](docs/learning/) | Learning notes and glossary |
| [`docs/research/`](docs/research/) | Corpus selection research |

## Data, licensing and attribution

- Kubernetes documentation is licensed CC BY 4.0. KEPs and code are Apache-2.0. Every answer cites its source URL and release.
- The corpus is **not** redistributed in this repository. Only ingestion code and source manifests are committed.
- This is an independent project. It is **not affiliated with or endorsed by** the Kubernetes project or the CNCF.
- Code license: *TBD in S01-T8.*
