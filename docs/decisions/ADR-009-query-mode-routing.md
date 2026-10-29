# ADR-009: Query-mode routing

- **Status:** Accepted (2026-10-09, decided in the S09-R1 design review)
- **Date:** 2026-10-09
- **Blueprint/spec refs:** blueprint §4 (query modes), §14 (query-mode classification); product spec must-haves 4–5, router accuracy; ADR-003 D4 (mode plans); ADR-002 D3 (releases table); ADR-006 (generation model)

## Context

- **The mode picks the retrieval plan** (ADR-003 D4, S09-R1 decisions 2–3). CURRENT drops text a later edit replaced. HISTORY with a release window keeps texts valid in the window ±1 release. CHANGE, WHY and HISTORY with no window get no filter.
- **A wrong mode is costly in one direction.** Sending a HISTORY or CHANGE question to CURRENT drops the old text it needs.
- **Golden set v0** labels a mode for each of its 36 answerable questions, and a release window for 9 HISTORY questions. Only 7 of the 9 name a release or year; 2 imply it ("Did Kubernetes create a token Secret for every ServiceAccount?").
- **Retrieval in the eval repeats exactly** because question vectors are stored (`docs/evaluation.md`). A router must not break that.

### Design-review evidence (2026-10-09)

| Router | v0 (36) | Blind rewording (36) | HISTORY/CHANGE/WHY sent to CURRENT (v0 / reworded) | Windows exact (v0 / reworded, of 9) | Cost per question |
|---|---|---|---|---|---|
| Rules: 3 ordered regexes + a CURRENT default | 36 | **12** | 0 / 24 | 7 / 1 | $0 |
| LLM, `claude-haiku-5-5`, effort low | 33 | 34 | 2 / 0 | 7 / 7 | ~$0.0001 |
| **LLM, `claude-opus-5-5`, effort low** | **35** | **35** | **0 / 0** | **7 / 7** | **~$0.0043** |

- **The rules were written after reading v0,** so 36/36 is fitted. The blind rewording was written by a separate LLM session that never saw the rules: the same 36 questions in Slack style ("pre-1.28 kubelet/apiserver skew: how many minors behind could kubelet lag?"), same meaning and time scope, scored against v0's labels. It's kept in `eval/candidates/router-rewording-v0.yaml`.
- **Opus's one miss is q07** ("What did Pod Security Admission replace, and when was that removed?", labeled HISTORY, routed CHANGE). Both plans apply no filter, since q07 names no release, so its retrieval is unchanged.
- **Haiku's window misses were first 0/9 for "before" questions:** it wrote the value in the schema's `end` field. Re-scored with either field accepted, it gets 7/9. Its 2 mode misses on v0 (q12, q43) send HISTORY questions to CURRENT.
- **Cost:** 72 calls per model; Opus 63,376 input and 2,816 output tokens ($0.31), Haiku 63,376 and 3,567 ($0.008). Latency wasn't measured.
- **Devil's advocate** (fresh context) argued that the rules' 36/36 is fitted to the labeler's wording, that the CURRENT default is the most harmful fallback, and proposed rules first with the LLM only when no rule fires. Its concession test (rules ≥ 0.90 on a blind rewording) failed at 0.33. The LLM alone met that bar, so the simpler single mechanism was chosen.

## Decision

### D1. An LLM sorts each question into a mode

- One `claude-opus-5-5` call per question, effort `low`, structured output (`messages.parse`, as in ADR-006): `mode` (CURRENT / HISTORY / CHANGE / WHY) and `time_scope` (`kind`: none / before / in / after / since / between; `start`; `end`).
- The system prompt is fixed in the code. It defines the modes from ADR-003 D4 and the blueprint, not from golden-set questions, and is the design review's prompt word for word (run S09-R1).
- The router sits behind a small `Router` interface with a test fake, like the embedder and the reranker, so unit tests never call the API.
- The model, effort and token cap come from settings (`ROUTER_MODEL`, `ROUTER_EFFORT`, `ROUTER_MAX_TOKENS`).

### D2. Code, not the model, turns a time scope into releases

- The model only copies the release ("1.28") or year ("2021") the question names, with its relation. It never infers a release from an event.
- A pure function maps the time scope to a release window through the `releases` table (ADR-002 D3). Example: "before 2021" becomes "until the release in effect on 2020-12-31", which is 1.20.

### D3. The eval stores each question's route

- Like the question vectors, the eval stores each golden question's raw route, one file per router model, keyed by the question's hash.
- `make eval` and `make eval-smoke` fill in missing routes, and so does a dedicated `make eval-routes`. `make eval-retrieval` never calls the API.
- The file records the prompt's hash. A changed prompt makes the stored routes an error, not a silent reuse.

## Alternatives considered

| Option | Why not |
|---|---|
| Rules (ordered regexes) | 36/36 on v0 but 12/36 on the blind rewording; every miss fell to CURRENT |
| `claude-haiku-5-5` | 40× cheaper, but sent 2 v0 HISTORY questions to CURRENT; the author kept Opus |
| Rules first, LLM when no rule fires | Two mechanisms to explain and test; on the rewording most questions would reach the LLM anyway |
| Jev (proposed addition) | Early access and a new dependency; the LLM already met the bar |
| The LLM also maps dates to releases | Models misdate releases (seed #8 repeated a wrong 1.23 date); the `releases` table is the source of truth |

## Consequences

- **Each live question costs one more call:** about $0.0043, +14% over rerank's $0.031 per question; the product spec's ceiling is $0.06.
- **Latency is added to live `ask` only.** Eval latency doesn't include routing, because routes are stored (the same known limit as the question embedding). The run measures the router's p50/p95 once, when filling the routes.
- **Router accuracy threshold: ≥ 0.90** (≥ 33 of 36) on v0, and on v1 when it exists. Revisit this ADR if router accuracy, the p95 ceiling (23 s) or the cost ceiling fails.
- **Retrieval stays exactly repeatable** in the eval, from the stored routes.
- **The router is non-deterministic live.** The same question could route differently on two asks; the stored routes make the eval immune to this.
- **Known limit:** implicit times ("before strict validation was on by default") get no window; the question routes HISTORY with no filter.
