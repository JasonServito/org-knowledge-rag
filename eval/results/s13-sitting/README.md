# S13-R1 sitting evidence (2026-10-13)

The checks behind the S13-R1 sitting's decisions (ADR-012):
- the release-cadence chain's GitHub items and their format traps;
- decision 1's rules on the gate's 4 traced KEPs (the held-out test the build-method devil's advocate asked for);
- which post the decision rule cites;
- the held-out KEP's draw (decision 2).

These are scratch scripts written during the sitting and committed verbatim, with their outputs. They are never imported by `src/` and are excluded from ruff (`pyproject.toml`).

**No GitHub text is committed** (it isn't CC BY; ADR-001). `fetch_items.sh` writes the raw API JSON to a scratch directory you name; the logs hold only counts, ids, dates, logins, Prow commands and template-field lines.

Run from the repo root, with `make up` and `gh auth login`.

| Script and command | Paid | Output | What it shows |
|---|---|---|---|
| `bash eval/results/s13-sitting/fetch_items.sh <scratch dir>` | no | the raw JSON, in `<scratch dir>` (not committed) | Discussion #1290 (GraphQL), issue #2572 and PR #2567 (REST, reviews paged); the held-out chain's issue #3015 and PR #3010 |
| `python3 eval/results/s13-sitting/expected_posts.py <scratch dir>` | no | `expected_posts.log` | Posts T1's rendering keeps per item: 1 + 88, 1 + 2, 1 + 46 + 4. T1's expected values |
| `cd eval/results/s13-sitting && python3 prow_order.py <scratch dir>` | no | `prow_order.log` | PR #2567's `/approve`s, `/hold` and approvals in time order: the last Prow command is `/hold cancel`, the last `/approve` is dchen1107's (decision 1, fix 1) |
| `bash eval/results/s13-sitting/probe_rules.sh > eval/results/s13-sitting/probe_rules.log` | no | `probe_rules.log` | Decision 1's rules on KEPs 2572, 2579, 2799, 4858: the template fields, the stored texts linking each KEP, the nearest current texts to each KEP's Summary vector |
| `python3 eval/results/s13-sitting/draw_heldout.py d6e7d9c5bcbfe2a787916294a30f87c8af3ddc46` | no | `draw_heldout.log` | Decision 2's draw, seeded by the contract commit's SHA: KEP-3015 from 35 |
| `python3 eval/results/s13-sitting/label_sheet.py <scratch dir> > <scratch>/sheet.md` | no | the label sheet (GitHub excerpts; not committed) | T2's candidates per step, each excerpt copied from its source, each GitHub post under the section name T1 will render. |
| `uv run python eval/results/s13-sitting/check_gold_draft.py eval/golden_set/chains-v0.yaml <scratch dir>` | no | `check_gold.log` | The contract's loader rules on the gold file: 0 errors; every label matches a stored text or a rendered post |

- **Sitting timings** (not scripted): scanning all chunk texts for links to KEP-2572 took 2.4 s; a naive nearest-text query took 8.0 s (decision 3).
- **Format checks** (not scripted; from the same JSON): the bots `k8s-ci-robot`, `k8s-triage-robot` and `fejta-bot` are typed "User"; 80 of 134 posts use CRLF; 1 of 134 holds markdown headings.
- The three devil's-advocate reviews (build method, tables, metric) are summarized in the S13 slice doc's run contract.
- **Total spent in the sitting:** US$0 (GitHub API reads and the local database only).
