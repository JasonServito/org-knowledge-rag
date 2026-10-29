# S04 seed results (S04-T8)

Seeds #6–#10 from `docs/research/corpus_validation_gate.md` Appendix A, asked once each with `orgknow ask`.

- **Run:** 2026-10-07, at `main` 884ac96. One ask per seed, no re-runs.
- **Settings (defaults, no overrides):** `claude-opus-5-5`, effort `medium`, `max_tokens` 16,000; top-k 10; `voyage-4-large`.
- **Corpus:** S04 scope only. That is SIG Auth docs at 1.24–1.37 (43 pages, 216 versions) plus KEP-2579 (4 versions): 4,967 chunks, 1,583 distinct texts.
- **Verdicts:** drafted by an LLM, confirmed by the author (2026-10-07).

## Summary

| Seed | Class | Status | Verdict | Failure categories | Citations |
|---|---|---|---|---|---|
| #6 | CURRENT | answered | pass | — | 9 |
| #7 | HISTORY | answered | pass | — | 6 |
| #8 | CHANGE | answered | partial | `retrieval_miss`, `source_conflict` | 7 |
| #9 | WHY | answered | partial | `out_of_scope` | 2 |
| #10 | UNANSWERABLE | insufficient_evidence | pass | — | 0 |

- **Verdict scale:**
  - `pass`: every key fact of the expected answer, each supported by a citation
  - `partial`: a key fact missing, or one wrong
  - `fail`: a wrong or unsupported answer, or an answer to an unanswerable question
- **Failure categories:**
  - `retrieval_miss`: the needed text is stored but missed the top 10
  - `out_of_scope`: the needed source isn't ingested in S04
  - `source_conflict`: a cited source is wrong, and nothing flags it (S10)
  - `temporal_confusion`: a fact from the wrong release, or releases mixed (S09)
  - `unsupported_claim`: a claim not in its cited chunk
  - `generation_miss`: the right text was retrieved, but the answer is still wrong or incomplete
- **Faithfulness:** every claim in the 4 answers was checked against its cited chunk text, and 0 were unsupported.

## Per seed

### #6 CURRENT: What enforces pod security standards in-tree?

- **Expected:** PodSecurity admission, GA since v1.25.
- **Got:** the built-in PodSecurity admission controller; built in as of v1.22, beta in v1.23, stable since v1.25; replaced PodSecurityPolicy (PSP).
- **Claims check:**
  - "stable since v1.25": the `feature-state v1.25 stable` lines in chunks 546 and 4639
  - "beta in v1.23": chunk 4633
  - "as of v1.22": chunk 4648
  - "replaced PSP": chunks 1293, 1446 and 1813
- **Temporal:** it scoped the stale "enable the `PodSecurity` feature gate" prerequisite to 1.24 and 1.25, its chunk's windows (chunk 4649).
- **Retrieval:** 10 hits, but only 6 distinct sections. The same admission-controller section appears 3 times (1.26, 1.27–1.30, 1.31+), differing by one line.
- **Verdict:** pass.

### #7 HISTORY: What did Pod Security Admission replace, and when was that removed?

- **Expected:** PodSecurityPolicy: deprecated v1.21, removed v1.25.
- **Got:** PodSecurityPolicy, deprecated in v1.21 and removed in v1.25. It adds: PSA alpha 1.22, beta 1.23, stable 1.25.
- **Claims check:**
  - "deprecated v1.21, removed v1.25": chunk 585, the PSP page at 1.25+, which says "removed from Kubernetes in v1.25"
  - "alpha 1.22, beta 1.23": chunk 4974
  - "stable 1.25": chunk 1242
- **Temporal:** the evidence also held the 1.24 texts saying PSP "will be removed in v1.25" (chunks 555 and 511). The answer used the 1.25+ wording.
- **Sources:** Appendix A lists CHANGELOG-1.21 and CHANGELOG-1.25 (S05). The docs pages carry the same facts, so S04's scope was enough.
- **Verdict:** pass.

### #8 CHANGE: What were Pod Security Admission's graduation stages?

- **Expected:** alpha 1.22, beta 1.23, GA 1.25.
- **Got:**
  - alpha v1.22, "released on 2021-08-04"
  - beta v1.23, "released on 2021-11-03"
  - GA: "an earlier, unresolved version of the KEP targeted v1.24 … the later version targets GA in v1.25". It adds that the evidence "gives no actual GA release date".
- **What's wrong:**
  1. **Wrong beta date.** The KEP's Implementation History (chunk 4974) says "2021-11-03: v1.23 Beta version released". v1.23 shipped on 2021-12-07 (the `releases` table, from the manifest). This is the known conflict case in Appendix A, repeated as fact. → `source_conflict`.
  2. **GA 1.25 only as a target.** All 10 hits were KEP chunks, and the KEP's history stops at the beta. The docs chunks stating "stable since v1.25" (546, 1293 and others) are stored but weren't retrieved. → `retrieval_miss`.
- **Temporal:** handled well. It told apart the KEP version that targeted GA in v1.24 (chunk 4830, `implementable/beta`) from the newer one that targets v1.25 (chunk 4955).
- **Retrieval:** 10 hits, only 6 distinct sections. 4 hits are older KEP versions of a section that is also present in its newer version.
- **Verdict:** partial.

### #9 WHY: Why replace PSP instead of fixing it?

- **Expected:** fixes would break compatibility; a confusing authorization model; it could not be on by default.
- **Got:** the KEP's 3 problems: the authorization model, rollout (PSP "can never be enabled by default"), and an inconsistent API; plus the goal of keeping a built-in guard. It adds that the evidence "doesn't explicitly compare fixing PSP in place with replacing it".
- **Claims check:** all claims match the Motivation chunks (4917, 4918).
- **What's missing:** "fixes would break compatibility". That reason is in the 2021 PSP deprecation blog post ("can't be addressed without making breaking changes", line 84). Blog posts come in S05. → `out_of_scope`. Appendix A also lists CHANGELOG-1.25, which wasn't checked.
- **Retrieval:** the weakest of the 5. Distances were 0.65–0.69, against 0.34–0.55 for the other seeds. The top hit (PRR "Troubleshooting") is irrelevant, and Motivation ranked 4th. The question uses the abbreviation "PSP".
- **Verdict:** partial.

### #10 UNANSWERABLE: What objections were raised in the "3-Tier Pod Security Proposal" doc comments?

- **Expected:** insufficient evidence (the doc is a gated Google Doc).
- **Got:** `insufficient_evidence`. The reason says that no chunk mentions the doc or its comments, and lists what the evidence does cover.
- **Verdict:** pass.

## Patterns

1. **No temporal confusion in 5 of 5.**
   - The answers used the release windows in the evidence: seeds #6, #7 and #8 each preferred or scoped versioned text correctly.
   - None of these seeds asks about a specific older release, which is S09's case.
   - One run per seed, so this is anecdotal; S06 measures run-to-run variance.
2. **Near-duplicate crowding.**
   - The top 10 held 6 distinct sections for seeds #6 and #8, 7 for #7, 8 for #9 and 9 for #10.
   - Versions of one section that differ by a line each take a slot. That may be why seed #8 missed the docs chunk it needed; not proven, since only the top 10 is stored (a hypothesis for S06/S09).
   - S09's release filter, or one hit per section, would free those slots.
3. **Unflagged source error (#8).** The KEP's wrong beta date passed through as fact. Our `releases` table holds the right date, but the model never sees it. This motivates S10 (conflicts).
4. **Missing sources (#9).** The "why" behind a decision can live in a blog post rather than the KEP. S05 adds blogs.
5. **KEP windows overlap in the output.** A KEP version's release window comes from dates, so consecutive versions share a release (e.g. `1.22–1.24`, then `1.24–1.25`). This is correct by ADR-002, but confusing to read.
6. **Retrieval isn't bit-reproducible.**
   - A second retrieval run for the same question shifted distances by up to 0.0044. That swapped near-ties: seed #6's 10th hit (554 in the ask, 547 in the second run) and seed #9's 8th and 9th.
   - The question's Voyage vector varies slightly between calls.
   - No cited chunk was affected. S06 should store query vectors (or accept the noise) before comparing small ablation deltas.

## Usage and cost

From each trace's `generate` step (`traces.json`). Output tokens include reasoning tokens.

| Seed | Input | Output | Reasoning | Stop reason | Ask latency (s) | Cost (USD) |
|---|---|---|---|---|---|---|
| #6 | 3,437 | 323 | 0 | `end_turn` | 6.6 | 0.0202 |
| #7 | 4,645 | 195 | 0 | `end_turn` | 13.2 | 0.0225 |
| #8 | 6,033 | 853 | 0 | `end_turn` | 8.7 | 0.0412 |
| #9 | 4,777 | 492 | 0 | `end_turn` | 15.7 | 0.0289 |
| #10 | 5,360 | 162 | 0 | `end_turn` | 4.6 | 0.0247 |
| **Total** | 24,252 | 2,025 | 0 | | | **0.1375** |

- **Cost:** input × $4/M + output × $20/M (ADR-006). It matches Langfuse's own figure for each seed.
- **Against ADR-006:** ~$0.03 per ask, against the $0.07–0.11 estimate. Reasoning was 0 on all 5 at `medium` effort, as on R2's 4 asks.
- **Model decision:** these numbers feed the written model decision due before the S06 baseline (ADR-006 D1).
- **Validation:** all 5 passed (0 rejected ids). The trace's `retrieve`, `generate` and `validate` steps are present on all 5.

## Files

- `seed-NN.json`: the `ask` stdout, byte for byte, with the trace id.
- `seed-NN.retrieval.txt`: a readable top 10 (document, section, windows), printed by `python -m orgknow.retrieval.dense`.
  - It is a **second** retrieval run, not the ask's own (pattern 6).
  - It matches the ask's ids and order for #7, #8 and #10. #6 differs at rank 10; #9 swaps ranks 8 and 9.
  - The section counts above use the ask's own hits; the swaps leave them unchanged.
- `traces.json`: selected fields of each trace, which are the exact record of each ask:
  - retrieved ids and distances
  - usage, stop reason and latency
  - the validation result
  - No raw observations: the Langfuse SDK adds the public key to their metadata.
  - Langfuse Hobby keeps traces for 30 days, until about 2026-11-06.
  - Traces took ~6 minutes to show in the Langfuse API after the asks.
- **Keys:** a check found no API key or Langfuse key in any file here.

## How to reproduce

Answers vary from run to run, so a re-run won't match byte for byte.

```bash
uv run orgknow ask "What enforces pod security standards in-tree?" > eval/results/s04/seed-06.json
uv run python -m orgknow.retrieval.dense "What enforces pod security standards in-tree?" > eval/results/s04/seed-06.retrieval.txt
```

The same pair applies to #7–#10, with the questions as written above.

`traces.json` comes from the Langfuse v2 observations endpoint. The legacy traces endpoint returns HTTP 410. Save the script below to a scratch file outside the repo, then run `uv run python <file> eval/results/s04 > eval/results/s04/traces.json`.

<details><summary>Trace fetch script</summary>

```python
"""Fetch selected fields of each seed's trace from Langfuse (v2 observations endpoint).

Writes only named fields, never raw observations: the SDK puts the Langfuse public key in
each observation's metadata (PR #24 question 2).
"""

import json
import sys
from pathlib import Path

from langfuse import Langfuse

from orgknow.settings import Settings

s = Settings()
assert s.langfuse_public_key and s.langfuse_secret_key
lf = Langfuse(
    public_key=s.langfuse_public_key.get_secret_value(),
    secret_key=s.langfuse_secret_key.get_secret_value(),
    base_url=s.langfuse_base_url,
)
out = {}
for path in sorted(Path(sys.argv[1]).glob("seed-*.json")):
    trace_id = json.loads(path.read_text())["trace_id"]
    rows = lf.api.observations.get_many(
        trace_id=trace_id, fields="basic,io,model,usage,metrics,metadata"
    ).data
    obs = {r.name: r for r in rows}
    gen = obs["generate"]
    out[path.stem] = {
        "trace_id": trace_id,
        "observations": sorted(obs),
        "ask_level": obs["ask"].level,
        "ask_latency_s": obs["ask"].latency,
        "retrieve_output": json.loads(obs["retrieve"].output),
        "generate": {
            "model": gen.model,
            "model_parameters": gen.model_parameters,
            "usage_details": gen.usage_details,
            "stop_reason": gen.metadata["stop_reason"],
            "langfuse_total_cost_usd": gen.total_cost,
            "latency_s": gen.latency,
        },
        "validate_output": json.loads(obs["validate"].output),
    }
print(json.dumps(out, indent=2))
```

</details>
