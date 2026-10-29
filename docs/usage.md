# Usage

How to set up, load the corpus, ask questions, run the API and the ingestion worker, and run the evals. The overview and results are in the [README](../README.md).


## Prerequisites

- **Windows:** WSL2 with Ubuntu. Run every command below in the Ubuntu shell, not in PowerShell. Native Windows is not supported (ADR-004).
- **macOS:** Apple Silicon only (macOS 14+). PyTorch, which the reranker needs, has no Intel Mac build (ADR-004).
- **Docker Desktop** as the only Docker engine, with WSL integration enabled for the Ubuntu distro (Docker Desktop → Settings → Resources → WSL integration). Don't also install Docker Engine inside Ubuntu.
- **make:** `sudo apt install make` (or `sudo apt install build-essential`).
- **uv:** `curl -LsSf https://astral.sh/uv/install.sh | sh`. uv also manages Python: `uv sync` installs Python 3.12 (from `.python-version`) if it's missing, so there's no separate Python install.
- **gh** (GitHub CLI): optional. Only needed to open PRs or watch CI from the terminal.

## Run it

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
make fetch-github           # the decision chains' 5 GitHub items into the cache; needs GITHUB_TOKEN (make ingest stops without them)
make ingest                 # read the scope at the locked SHAs, store one version per content change, chunk new versions, rebuild the observed lifecycle (safe to re-run); ends with the ingestion report
make lifecycle              # rebuild only the observed lifecycle: each feature gate's stage at each release, from that release's own feature-gate reference (free; a re-run stores the same rows)
make ingest-report          # print the report's database part alone: counts per source type and per release, chunk ids, and a fingerprint of every stored corpus value except generated ids (equal fingerprints = identical data)
make embed                  # embed each chunk text with no vector yet; paid, needs VOYAGE_API_KEY (a re-run sends 0 requests)
```

`make embed` refuses to start, and sends nothing, when its texts come to more than `EMBED_MAX_TOKENS_PER_RUN` estimated tokens (characters / 4; default 2,000,000). The full corpus from empty is about 5.7M estimated tokens, so raise the cap for that one command only and keep the default:

```bash
EMBED_MAX_TOKENS_PER_RUN=6000000 make embed   # full-corpus embed, one time
```

Then ask a question. Each ask is paid and needs `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY`: in the default `authority` mode (and in `temporal`), one Voyage call and 2 Claude calls, the router and the answer; in `rerank`, `hybrid` and `dense`, one Voyage call and one Claude call:

```bash
uv run orgknow ask "What enforces pod security standards in-tree?"
```

`RETRIEVAL_MODE` picks the retrieval: `authority` (the default) and `temporal` (both below), `rerank` (hybrid's whole merged list, about 21 texts, scored by a local cross-encoder model that reads the question next to each text, keeping the 10 best by that score), `hybrid` (the 20 nearest texts and the 20 best word matches from Postgres full-text search, merged with Reciprocal Rank Fusion, keeping the best 10) or `dense` (the 10 texts whose vectors are nearest the question's). For example, `RETRIEVAL_MODE=hybrid uv run orgknow ask "..."` skips the model. Authority became the default when its eval passed the improvement rule against rerank (S09-T8), rerank before it against hybrid, and hybrid against dense (`docs/evaluation.md`).

`temporal` is rerank with a time filter. One more Claude call (the query router, ADR-009) first sorts the question into CURRENT, HISTORY, CHANGE or WHY and copies the release or year it names; code turns that into releases through the release-dates table. Both searches then keep only matching texts: a "now" (CURRENT) question gets text a current version still holds, and a "back then" (HISTORY) question that names a release or year gets texts valid in it, ±1 release (`HISTORY_WINDOW_SLACK`). CHANGE, WHY and undated HISTORY questions are unfiltered. Before the JSON, `ask` prints the route on stderr, e.g. `Route: HISTORY, releases until 1.27 (searched until 1.28)`.

`authority` is temporal plus source-authority weights (ADR-003 D4). Every retrieved text has a trust tier, from 1 (docs pages and the feature-gate reference) to 6 (blog posts). After the reranker, each text's probability of answering the question (0 to 1) is multiplied by `AUTHORITY_BOOST` (1.25) when the question's kind trusts its source, by `AUTHORITY_DEMOTE` (0.8) when it doesn't, and by 1 otherwise, and the texts are reordered by that product before the best 10 are kept. A "now" question boosts docs, feature-gate and release-note text still valid in the latest release, and demotes blog posts; a "how did it change" question boosts release notes; a "why" question boosts a KEP's Motivation and Alternatives sections, blog posts and governance docs, and demotes the feature-gate reference; a "back then" question is unweighted. It routes and prints the route line as temporal does.

`rerank` runs `BAAI/bge-reranker-base` on the CPU with PyTorch (the CPU-only build, pinned in `uv.lock`). The first rerank command downloads the model once (1.1 GB, at the revision pinned in `RERANK_REVISION`) into the Hugging Face cache (`~/.cache/huggingface`), outside this repo; later runs load it from there (about 7.5 s, including importing PyTorch). Each command loads it once, so every `orgknow ask` in rerank, temporal or authority mode (the default) pays that load; the API (below) loads it once per server process.

It prints one line of JSON: `answered` with citations (each with its release windows and a GitHub link at the snapshot commit), or `insufficient_evidence` with a reason. Both carry `conflicts`, after the evidence (ADR-010): places where the evidence disagrees, each with its kind, who found it, the chunk ids, a one-sentence summary and how it was settled. Code finds two kinds in stored facts before the answer: `claim_mismatch` (a KEP claims a stage that the feature-gate reference doesn't show at the asked-about release) and `history_date` (a KEP's history gives a release date more than `HISTORY_DATE_TOLERANCE_DAYS`, default 7, from the official one). The answer model adds pairs of texts that disagree (`contradiction` between sources, `supersession` between an old and a new version of one section), and code settles each by ADR-003 D6: the text valid at the asked-about release wins, else the more trusted tier, else it stays `unresolved`. With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` set, each ask also leaves one Langfuse trace, whose id is the JSON's `trace_id`. Without them, it prints "tracing off" and still answers. Exit codes: 0 when an answer prints, 1 on an error, 2 on bad usage.

## The API

`make serve` starts the API on `http://127.0.0.1:8000` (uvicorn, ADR-004). `POST /query` answers through the same pipeline as `orgknow ask` and returns the same JSON. Each request is paid like an ask, and needs `make up` and both API keys.

```bash
make serve                  # in a second terminal; Ctrl-C stops it
curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question": "What enforces pod security standards in-tree?"}'
```

- **Startup builds the clients once** and, in rerank, temporal and authority modes, loads the reranker once, so a request skips the ~7.5 s load. A missing `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` stops startup.
- **Tracing:** with both Langfuse keys set, each request leaves one trace named `ask`, whose id is the JSON's `trace_id` (null when tracing is off).
- **Errors:** an empty question is a 422; a failed model or embedding call, a 502 with one line; a database that can't be reached, a 503.
- **`http://127.0.0.1:8000/docs`** is FastAPI's built-in page: it lists the endpoints and can send a request. `GET /health` (liveness) and `GET /ready` (readiness, pings the database) are there too.
- **Known limit:** concurrent requests share one reranker. Fine for a local dev server.

**Ingestion jobs** (ADR-013): the API can also queue a rebuild of the corpus, which `make worker` runs: ingest → lifecycle → embed → chains, through the same functions as the `make` targets above, with each step's progress saved in the job.

```bash
make worker                 # in a third terminal: runs the queued job, polling every 5 s; needs INGEST_SCOPE=full (the default) and VOYAGE_API_KEY; Ctrl-C stops it
curl -s -X POST localhost:8000/ingestion-jobs   # 202 with the new job (its id, status queued, 4 pending steps); 200 with the job already queued or running
curl -s localhost:8000/ingestion-jobs/1         # the job with the id the POST returned: its status, attempts, error, and each step's status, times and counts
```

- **One job at a time:** a repeated POST returns the active job, so it's safe to send twice. An error fails the job (POST again); a job left running by a killed or stopped worker resumes when the worker starts again, at most 3 attempts.
- **One corpus writer at a time:** while a job runs, `make ingest`, `make lifecycle`, `make embed`, `make chains` and `make seed` stop with a message, and the worker waits while one of them runs. `make reset-corpus` is outside this lock.
- **Cost:** the embed step sends only texts with no vector yet (none at the current corpus lock once `make embed` has run), capped by `EMBED_MAX_TOKENS_PER_RUN`: above the cap the step fails before any request, so the first full-corpus embed stays a hand-run `make embed`.
- **Details:** each field, status and the worker's log lines are in [`docs/interfaces.md`](interfaces.md).

## Evaluate

To evaluate the pipeline on the golden set (`EVAL_GOLDEN_PATH`, default `eval/golden_set/v0.yaml`; format in ADR-007):

```bash
make eval-check             # validate the golden file and count the stored texts each label matches (free)
make eval-sections DOC=gate:LegacyServiceAccountTokenCleanUp   # a document's sections, as labels write them (free)
make eval-retrieval         # retrieval scores alone (Recall@10, Hit@10, MRR, nDCG@10, stale-result rate, temporal accuracy, authority selection and the "now" questions' MRR; router accuracy in temporal and authority modes), the rule-found conflicts and retrieve time (p50, p95) in RETRIEVAL_MODE, from the stored question vectors and routes (free; writes nothing)
make eval-conflicts         # check the conflict set (EVAL_CONFLICTS_PATH) and score the rule-found conflicts against it: how many conflicts and seeds search retrieved, precision, recall (free; writes nothing)
make eval-routes            # route every golden and conflict-set question with no stored route, for temporal and authority modes, and embed the conflict set's new questions (paid: one Claude call per question, one Voyage request; a re-run makes 0)
make eval-smoke             # the smoke questions end to end (paid: one Claude call per question)
make eval                   # every question (paid; run only when asked)
make eval-table             # rebuild eval/results/ablation.md from every results folder (free)
make eval-resummarize       # rebuild every results folder's summary.json from its saved rows (free; then make eval-table)
```

A run stops before any paid call if a label matches no stored text. It embeds only the questions with no stored vector (`eval/question_vectors/<model>.json`, one Voyage request; a re-run makes 0), so retrieval is exactly repeatable. Each run writes `eval/results/<name>-<UTC time>/` (`run.json`, one `questions.jsonl` row per question with its hits, answer, metrics and checks, and `summary.json`), then rebuilds the ablation table. A failed ask is a row with its error, not a crash. Besides the metrics, the summary and the table report the p95 latency, the retrieval step's own p95 and the cost per question (at `GENERATION_PRICE_INPUT_USD_PER_MTOK` / `GENERATION_PRICE_OUTPUT_USD_PER_MTOK`). After a new summary field, `make eval-resummarize` refills older folders from their `questions.jsonl` with no paid call. `uv run python -m orgknow.eval run --name NAME` names the pipeline (default: the retrieval mode, `dense`, `hybrid`, `rerank`, `temporal` or `authority`; with `--smoke`, `<mode>-smoke`, so smoke runs get their own table row). In temporal and authority modes, each question's route is stored like its vector (`eval/question_routes/<model>.json`): a run routes only the questions with none, and `make eval-retrieval` never calls the router. Compare the modes for free with `RETRIEVAL_MODE=dense make eval-retrieval`, `RETRIEVAL_MODE=hybrid make eval-retrieval`, `RETRIEVAL_MODE=rerank make eval-retrieval`, `RETRIEVAL_MODE=temporal make eval-retrieval` and `RETRIEVAL_MODE=authority make eval-retrieval` before a paid run.

The conflict set (`EVAL_CONFLICTS_PATH`, default `eval/golden_set/conflicts-v0.yaml`; format in ADR-007 D4) lists every disagreement among each eval question's 10 results, 4 of them seed cases, and may add its own questions. With it, `make eval` also runs those questions (rows in `conflict_questions.jsonl`) and scores every answer's `conflicts` against it: precision, recall and AC4, in the summary and the table. Without it, `make eval` says so and runs. Try `make eval-conflicts` on the demo sample: `EVAL_CONFLICTS_PATH=tests/fixtures/conflicts/demo-sample.yaml make eval-conflicts`.

The metrics, the dense baseline and how to read a result are in `docs/evaluation.md`; the ablation table is `eval/results/ablation.md`.

Postgres listens on host port **5433** (not the default 5432), bound to localhost, so it doesn't clash with another Postgres on your machine. `make down` stops it; the data is kept in a named Docker volume.

## Decision provenance

`uv run orgknow chain kep:2572` prints a stored decision chain; `GET /decisions/kep:2572` returns it as JSON ([ADR-012](decisions/ADR-012-decision-provenance.md)).

To build the chains: `make fetch-github` (needs `GITHUB_TOKEN`), `make ingest`, `make embed` (paid), then `make chains` (free).
