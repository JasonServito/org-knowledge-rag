# ADR-006: Generation model, structured output, and tracing

- **Status:** Accepted (2026-10-06, decided in the S04-R2 sitting)
- **Date:** 2026-10-06
- **Blueprint/spec refs:** §18, §20; product spec must-haves 7 and 10, AC1–AC3; ADR-004 (Tracing row)

## Context

- S04 builds the first answer path: embed the question → top-10 dense retrieval → **one LLM call** that returns a structured answer → a deterministic citation validator → JSON on stdout, with one trace per ask.
- Input is ~4–6K tokens per ask (10 chunks averaging ~302 tokens, plus the prompt); output ~500 tokens plus the model's reasoning. Volume: ~20 asks in S04, then roughly 300–600 eval asks across S06–S11.
- Every ablation row from S06 on is compared with the dense baseline, so the generation model is effectively frozen once the baseline runs.
- Unit tests make no network calls; external APIs sit behind small interfaces with fakes (`CLAUDE.md`).
- Langfuse's legacy ingestion API (`POST /api/public/ingestion`) is sunset on Langfuse Cloud on 2026-11-16. Its OpenTelemetry endpoint (`/api/public/otel/v1/traces`) is the supported path.
- A devil's advocate argued against each recommendation. Each held, with changes recorded in the Decision.

## Decision

### D1. Claude Opus 5.5 at `medium` effort

- Model id `claude-opus-5-5` ($4 / $20 per M tokens) and the effort level are settings (`GENERATION_MODEL`, `GENERATION_EFFORT`), with effort set explicitly. Thinking can't be disabled on this model, and its reasoning tokens are billed as output: ~$0.07–0.11 per ask (estimate).
- T8 logs `usage` per ask, including reasoning tokens. **The model is confirmed or switched in writing before the S06 baseline**, using those numbers.

### D2. The official `anthropic` SDK with structured outputs

- `client.messages.parse(..., output_format=<Pydantic model>)` constrains generation to the answer schema and returns a validated object.
- The call sits behind a small `Generator` protocol with a fake for tests.
- A refusal (`stop_reason: refusal`) or a cut-off answer (`max_tokens`) is a typed error, never a crash.
- A schema can't say "only ids from this query's retrieved set", so the citation validator stays as plain code (AC2).
- Voyage stays on `urllib` (S04-R1 decision 7).

### D3. Langfuse Cloud through the `langfuse` Python SDK (v4)

- One trace per `ask`: a retrieval span (question, chunk ids, distances) and a generation observation (model, prompt, output, token usage, validator result). `flush()` runs before the CLI exits.
- Without Langfuse keys, `ask` still runs and prints "tracing off" (tests, CI). Keys are never printed.
- The S04 demo proves a trace arrives. T8 saves each trace id with its output in `eval/results/s04/`, since the Hobby tier keeps traces for 30 days.

## Alternatives considered

| Option | Why not |
|---|---|
| Claude Sonnet 5.5 ($2 / $10) | Half the cost and easy to defend for a baseline. Kept as the candidate for the S06 freeze if T8's numbers show Opus isn't worth ~2× |
| Claude Haiku 4.5 | Cheapest, but the weakest at the judgement this step needs (when to say "insufficient evidence") |
| Raw HTTP via `urllib` for the LLM call | No dependency, but we would hand-maintain schema conversion, retries and error types that the SDK provides |
| Prompt for JSON, then parse and retry | Malformed output still happens, and retries cost money |
| Strict tool use | Forced `tool_choice` returns a 400 on Opus 5.5; structured outputs are the direct route to JSON |
| Anthropic's document "citations" feature | Incompatible with structured outputs, and our citations are chunk ids checked by our own validator |
| OTLP JSON posted with `urllib` | 0 packages, but ~80 lines of hand-built trace payloads, and S11's LangGraph integration needs the SDK anyway |
| Legacy Langfuse ingestion API | Sunset 2026-11-16 |
| Self-hosted Langfuse | ADR-004 (Tracing row) |

## Consequences

- New runtime dependencies (ADR-004 amendment 2026-10-06): `anthropic`, `httpx2` (dev-only until now), `langfuse`. The `langfuse` SDK brings 17 packages (OpenTelemetry, protobuf, `httpx`), so the process has three HTTP stacks: `urllib` (Voyage), `httpx2` (Anthropic) and `httpx` (Langfuse).
- Same question, different run: reasoning makes answers vary. S06 measures this before trusting small ablation deltas.
- Trace links in PR briefs expire after 30 days; outputs in `eval/results/` don't.
- Revisit triggers: the S06 baseline freeze (D1); the S11 LangGraph integration (D3); Langfuse pricing or retention changes.

## Amendment 2026-10-08

- **D1 confirmed for the S06 baseline (S06-R1 sitting, decision 5):** `claude-opus-5-5` at `medium` effort stays the answer model, frozen from the dense baseline on. Evidence: S04-T8's 5 traced asks cost $0.020–0.041 each with 0 reasoning tokens (`eval/results/s04/traces.json`), below this ADR's $0.07–0.11 estimate, so 3 baseline runs of 50 questions cost about $5. Rejected: Sonnet 5.5, which halves a small cost but is weaker at "insufficient evidence".
- **D2 kept (S06-R1 sitting, decision 6):** `messages.parse` stays. A cut-off or refused answer still loses its stop reason; the eval runner records it as an error row and continues. Rejected: `messages.create` with our own validation, which would change D2 for a path seen 0 times in S04.
