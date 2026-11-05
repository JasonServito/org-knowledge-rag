# ADR-016: The UI (a private Next.js app; browser-only components; a hand-written text formatter)

- **Status:** Accepted (S17-R1 design review, 2026-11-01)
- **Date:** 2026-11-01
- **Blueprint/spec refs:** §25.2 (final UI); §23 stage 13; ADR-014 (D1, the 2026-10-16 amendment); security review 3.1, 3.3 and section 7
- **Evidence:** the S17-R1 design review's probes and 2 devil's advocates (the S17-R1 plan)

## Context

- The system's differentiators (release windows, authority tiers, conflicts, decision chains) are visible today only as JSON: `/docs`, the CLI, Langfuse. S18 records the demo video and screenshots through a UI.
- The AWS environment exists only in windows and is torn down after S18 (ADR-014's amendment). The S17-R1 design review decided the UI stays **private**: it runs on the developer's laptop against a local `make serve`, or the Session Manager tunnel during a window. Nothing is ever public, so section 7's exposure controls (HTTPS, API keys, spending caps, rate limits) are dropped.
- The API has 6 routes, request IDs and one error envelope (`docs/interfaces.md`); no CORS. `POST /query` takes ~12 s on the laptop and ~54 s on the AWS server (S15-T6).
- 43 saved answers (`eval/results/conflict-20261012T171932Z/questions.jsonl`) have the API's `Answer` shape; 20 hold markdown: code spans (14), bullet lines (14), bold (8); 0 links, images, headings, tables or code fences. q42 holds `<IPv4 CIDR>` inside a code span.
- Model text can carry injected content from retrieved GitHub comments (security review 3.1); the review's fix for the UI is "never render model text as HTML" (3.3).
- 2 decision chains are stored (`kep:2572`, `kep:3015`); `GET /decisions/{canonical_id}` reads one; nothing lists them. No saved answer cites `kep:3015`.
- Node isn't installed in WSL; the repo has no JavaScript today.

## Decision

### D1. Next.js, every component in the browser, one forwarder

- A Next.js app (App Router, TypeScript) in `ui/`. Every component is a client component: no server components that fetch, no route handlers, no server actions.
- The browser calls `/api/*` on the UI's own address; Next's `rewrites` forward it to the API (`API_BASE_URL`, default `http://127.0.0.1:8000`), so the browser never needs CORS and the API doesn't change. The forwarder's timeout comes from `API_TIMEOUT_S` (default 120 s).
- Two pages: the answer page (`/`) and the Decisions pages (`/decisions`, `/decisions/[id]`), with Next's built-in routing.
- The UI runs on the laptop (`make ui`); it is not in the Docker image or on AWS.

### D2. Component tests on saved data, plus one browser smoke test

- Vitest with Testing Library (jsdom) renders the 43 saved answers and the 2 captured chains. Tests run with `TZ=America/Edmonton` so a local-time date bug fails.
- One Playwright file loads the answer page (q25) and a chain page (`kep:3015`) in Chromium, with the API answered from fixtures inside the browser; it fails on any page error and saves 2 screenshots.
- `make ui-check` (lint, typecheck, Vitest, `next build`) and `make ui-e2e` (Playwright) run in a `ui` CI job.

### D3. Model text through a hand-written formatter

- `answer` and conflict summaries go through a small pure function that recognises only code spans, `**bold**` and `-`/`*` bullet lines, and returns React elements. Everything else, including `<`, `>`, `[text](url)` and `![alt](url)`, is text.
- It never produces a link, an image or HTML: no `dangerouslySetInnerHTML`, no markdown library.
- The UI shows its own fixed message per error code with the response's `request_id`, never the API's `message` (security review 8.3's provider text).

### D4. `GET /decisions` lists the stored chains

- A free, read-only route: each stored chain's `seed`, `title` and `built_at`; 200 with an empty list when none. Its SQL lives in `db/decisions.py`.
- A Decisions page lists them. A citation whose document is a listed seed links to its chain; no other citation does. This closes the "attach the stored chain to WHY answers" item (S13-R1 decision 6) without changing the answer's pinned format.

### D5. Packages

- npm with a committed lockfile and exact versions. Direct packages: `next`, `react`, `react-dom`; dev: `typescript`, `@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `eslint-config-next`, `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/dom`, `@playwright/test`. Adding another needs an amendment.
- Plain CSS; ESLint (Next's config) is the UI's lint; no Tailwind, component library or Prettier.
- Node: the LTS version installed in WSL, pinned in `ui/.nvmrc` and `engines`.

## Alternatives considered

| Option | Why not |
|---|---|
| Next.js with server-side calls (route handlers or server components) | Its main reason, keeping the API address on the server, came from the public design that was dropped; Next's Vitest guide says async server components can't be unit-tested; a second timeout in the UI's server |
| Next.js static export, the browser calling the API directly | Needs CORS in FastAPI for a private tool |
| Vite + React | Smallest framework, but 2 pages need a router package or hand-written switching |
| Streamlit (blueprint §25.1's dev UI) | S12 managed with `/docs`, the CLI and Langfuse; S17 builds the real UI |
| Component tests only | No real-browser run until the developer's T6; no screenshots from the unattended run |
| Playwright only | Slow; timeline arithmetic is easier to check exactly in a unit test |
| Plain text | Raw `**` and backticks in 20 of 43 answers |
| react-markdown (links and images turned off) | 81 packages (deps.dev, 10.1.0) for 3 constructs; links and images on by default |
| Ask the model for plain text | A generation change; would need measuring on the golden set |
| The UI asks `GET /decisions/{id}` per cited KEP | Up to 9 calls per answer; no index, so `kep:3015` is reachable only by a typed address |
| A list of chains in the UI's config | Stale whenever `make chains` changes |
| Attach the chain to the answer | Changes the answer's pinned format; ~100–150 lines in the pipeline |
| A public UI (key, cap, rate limits, HTTPS) | The deployment lives one week; ~3 more tasks; S17-R1 design review decisions s1–s2 |

## Consequences

- A second language and toolchain (Node, npm) in a Python repo, kept to `ui/` and one CI job. `make check` stays Python-only.
- One small API addition (`GET /decisions`); no schema change; the answer format is unchanged.
- The formatter is our code: a new markdown construct in a future answer shows as raw text until it is added.
- **Not verified until a window:** the forwarder on a request longer than ~30 s.
- **Revisit triggers:** a public window (→ section 7's exposure controls and HTTPS); answers using links, tables or code blocks (→ the formatter, or a library with an amendment); a third page needing shared server state.
