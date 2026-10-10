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

### Prerequisites

- **Windows:** WSL2 with Ubuntu. Run every command below in the Ubuntu shell, not in PowerShell. Native Windows is not supported (ADR-004).
- **macOS:** Apple Silicon only (macOS 14+). PyTorch, which the reranker needs, has no Intel Mac build (ADR-004).
- **Docker Desktop** as the only Docker engine, with WSL integration enabled for the Ubuntu distro (Docker Desktop → Settings → Resources → WSL integration). Don't also install Docker Engine inside Ubuntu.
- **make:** `sudo apt install make` (or `sudo apt install build-essential`).
- **uv:** `curl -LsSf https://astral.sh/uv/install.sh | sh`. uv also manages Python: `uv sync` installs Python 3.12 (from `.python-version`) if it's missing, so there's no separate Python install.
- **gh** (GitHub CLI): optional. Only needed to open PRs or watch CI from the terminal.

### Run it

```bash
git clone https://github.com/JasonServito/org-knowledge-rag.git
cd org-knowledge-rag
cp .env.example .env        # local settings; the defaults match compose.yaml
uv sync                     # Python 3.12 + all dependencies, exactly as pinned in uv.lock
make up                     # start Postgres + pgvector, wait until it's healthy, create the test database
make migrate                # apply Alembic migrations (safe to re-run)
make check                  # format check, lint, mypy --strict, unit tests
make test-int               # integration tests against a separate test database (orgknow_test)
uv run pre-commit install   # run ruff on every commit
```

To load the corpus scope (the whole S05 manifest: the docs pages of SIG Auth, Network and Release, the website release records and the feature gates at every release 1.20 to 1.37; every KEP in those 3 SIGs' folders and the governance docs; the blog posts from 1.20; and the 18 CHANGELOGs), first create the partial clones of the corpus repos with `spikes/fetch.py` (set `CORPUS_CACHE_DIR`, outside this repo), then:

```bash
make seed                   # load the releases from the corpus manifest (safe to re-run)
# reset-corpus is needed after any chunker change (a stored version keeps its old chunks) or any change to how versions are dated (a re-ingest reports a history mismatch); otherwise it's optional, to rebuild from empty
make reset-corpus           # empty the dev database's documents, versions and chunks (ids restart at 1); keeps releases and vectors
make ingest                 # read the scope at the locked SHAs, store one version per content change, chunk new versions, rebuild the observed lifecycle (safe to re-run); ends with the ingestion report
make lifecycle              # rebuild only the observed lifecycle: each feature gate's stage at each release, from that release's own feature-gate reference (free; a re-run stores the same rows)
make ingest-report          # print the report's database part alone: counts per source type and per release, chunk ids, and a fingerprint of every stored corpus value except generated ids (equal fingerprints = identical data)
make embed                  # embed each chunk text with no vector yet; paid, needs VOYAGE_API_KEY (a re-run sends 0 requests)
```

`make embed` refuses to start, and sends nothing, when its texts come to more than `EMBED_MAX_TOKENS_PER_RUN` estimated tokens (characters / 4; default 2,000,000). The full corpus from empty is about 5.7M estimated tokens, so raise the cap for that one command only and keep the default:

```bash
EMBED_MAX_TOKENS_PER_RUN=6000000 make embed   # full-corpus embed, one time
```

Then ask a question. Each ask is paid (one Voyage call and one Claude call) and needs `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY`:

```bash
uv run orgknow ask "What enforces pod security standards in-tree?"
```

`RETRIEVAL_MODE` picks the retrieval: `rerank` (the default: hybrid's whole merged list, about 21 texts, scored by a local cross-encoder model that reads the question next to each text, keeping the 10 best by that score), `hybrid` (the 20 nearest texts and the 20 best word matches from Postgres full-text search, merged with Reciprocal Rank Fusion, keeping the best 10) or `dense` (the 10 texts whose vectors are nearest the question's). For example, `RETRIEVAL_MODE=hybrid uv run orgknow ask "..."` skips the model. Rerank became the default when it passed the improvement rule against hybrid, and hybrid before it against dense (`docs/evaluation.md`).

`temporal` is rerank with a time filter. One more Claude call (the query router, ADR-009) first sorts the question into CURRENT, HISTORY, CHANGE or WHY and copies the release or year it names; code turns that into releases through the release-dates table. Both searches then keep only matching texts: a "now" (CURRENT) question gets text a current version still holds, and a "back then" (HISTORY) question that names a release or year gets texts valid in it, ±1 release (`HISTORY_WINDOW_SLACK`). CHANGE, WHY and undated HISTORY questions are unfiltered. Before the JSON, `ask` prints the route on stderr, e.g. `Route: HISTORY, releases until 1.27 (searched until 1.28)`.

`rerank` runs `BAAI/bge-reranker-base` on the CPU with PyTorch (the CPU-only build, pinned in `uv.lock`). The first rerank command downloads the model once (1.1 GB, at the revision pinned in `RERANK_REVISION`) into the Hugging Face cache (`~/.cache/huggingface`), outside this repo; later runs load it from there (about 7.5 s, including importing PyTorch). Each command loads it once, so every `orgknow ask` in rerank mode (the default) or temporal mode pays that load.

It prints one line of JSON: `answered` with citations (each with its release windows and a GitHub link at the snapshot commit), or `insufficient_evidence` with a reason. With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` set, each ask also leaves one Langfuse trace, whose id is the JSON's `trace_id`. Without them, it prints "tracing off" and still answers. Exit codes: 0 when an answer prints, 1 on an error, 2 on bad usage.

To evaluate the pipeline on the golden set (`EVAL_GOLDEN_PATH`, default `eval/golden_set/v0.yaml`; format in ADR-007):

```bash
make eval-check             # validate the golden file and count the stored texts each label matches (free)
make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp   # a document's sections, as labels write them (free)
make eval-retrieval         # retrieval scores alone (Recall@10, Hit@10, MRR, nDCG@10, stale-result rate, temporal accuracy; router accuracy in temporal mode) and retrieve time (p50, p95) in RETRIEVAL_MODE, from the stored question vectors and routes (free; writes nothing)
make eval-routes            # route every golden question with no stored route, for temporal mode (paid: one Claude call per question; a re-run makes 0)
make eval-smoke             # the smoke questions end to end (paid: one Claude call per question)
make eval                   # every question (paid; run only when asked)
make eval-table             # rebuild eval/results/ablation.md from every results folder (free)
make eval-resummarize       # rebuild every results folder's summary.json from its saved rows (free; then make eval-table)
```

A run stops before any paid call if a label matches no stored text. It embeds only the questions with no stored vector (`eval/question_vectors/<model>.json`, one Voyage request; a re-run makes 0), so retrieval is exactly repeatable. Each run writes `eval/results/<name>-<UTC time>/` (`run.json`, one `questions.jsonl` row per question with its hits, answer, metrics and checks, and `summary.json`), then rebuilds the ablation table. A failed ask is a row with its error, not a crash. Besides the metrics, the summary and the table report the p95 latency, the retrieval step's own p95 and the cost per question (at `GENERATION_PRICE_INPUT_USD_PER_MTOK` / `GENERATION_PRICE_OUTPUT_USD_PER_MTOK`). After a new summary field, `make eval-resummarize` refills older folders from their `questions.jsonl` with no paid call. `uv run python -m orgknow.eval run --name NAME` names the pipeline (default: the retrieval mode, `dense`, `hybrid`, `rerank` or `temporal`; with `--smoke`, `<mode>-smoke`, so smoke runs get their own table row). In temporal mode, each question's route is stored like its vector (`eval/question_routes/<model>.json`): a run routes only the questions with none, and `make eval-retrieval` never calls the router. Compare the modes for free with `RETRIEVAL_MODE=dense make eval-retrieval`, `RETRIEVAL_MODE=hybrid make eval-retrieval`, `RETRIEVAL_MODE=rerank make eval-retrieval` and `RETRIEVAL_MODE=temporal make eval-retrieval` before a paid run.

The metrics, the dense baseline and how to read a result are in `docs/evaluation.md`; the ablation table is `eval/results/ablation.md`.

Postgres listens on host port **5433** (not the default 5432), bound to localhost, so it doesn't clash with another Postgres on your machine. `make down` stops it; the data is kept in a named Docker volume.

## Development environment

This is the setup the project is built and verified on:

- **WSL2 Ubuntu** on Windows. The repo lives in the Linux filesystem (e.g. `~/code/`), not under `/mnt/c/`.
- **Docker Desktop** provides the Docker engine to WSL.
- **uv-managed Python 3.12.** No system Python is used.
- **Claude Code Desktop**, running in a WSL session on this repo. See [`docs/ai-workflow.md`](docs/ai-workflow.md).

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/product-spec.md`](docs/product-spec.md) | Phase 1 scope, non-goals, acceptance criteria |
| [`docs/architecture.md`](docs/architecture.md) | What the code does today |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records |
| [`docs/backlog.md`](docs/backlog.md) | Ordered slices and tasks |
| [`docs/ai-workflow.md`](docs/ai-workflow.md) | How this project is built with AI assistance |
| [`CLAUDE.md`](CLAUDE.md) | Rules for the coding agent |
| [`docs/learning/`](docs/learning/) | Slice briefs and glossary |
| [`docs/research/`](docs/research/) | Corpus selection research |

## Data, licensing and attribution

- Kubernetes documentation is licensed CC BY 4.0. KEPs and code are Apache-2.0. Every answer cites its source URL and release.
- The corpus is **not** redistributed in this repository. Only ingestion code and source manifests are committed.
- This is an independent project. It is **not affiliated with or endorsed by** the Kubernetes project or the CNCF.
- Code license: [MIT](LICENSE). It covers the code in this repository, not the Kubernetes corpus.
