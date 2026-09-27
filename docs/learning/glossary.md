# Glossary

One line per term; alphabetical within each section. The agent appends a term the first time it's introduced (see the explanation protocol in `CLAUDE.md`). Edit any definition you'd phrase differently.

## Project-specific

| Term | Meaning |
|---|---|
| **Authority tier** | Rank of how much a source should be trusted for a claim (ADR-003 D3). It is adjusted per query mode. |
| **`canonical_id`** | A stable identity for a document across versions, renames and branches (ADR-002 D4). |
| **`claimed_status` / `claimed_stage`** | What a KEP's `kep.yaml` *says* its status or stage is. Stored as a claim, because it's often stale. |
| **Claim mismatch** | A conflict where the claimed status disagrees with the observed stage. Surfaced, never silently resolved. |
| **Content hash** | A hash of normalized document content. The same hash means no new version (ADR-002 D2). |
| **Effective stage** | Observed stage if known, otherwise claimed stage with low confidence (ADR-003 D2). |
| **KEP** | Kubernetes Enhancement Proposal: a design + decision + tracking document per feature or process change. |
| **Manifest** | `config/corpus_manifest.yaml`. It defines which repos, paths and releases are in the corpus. |
| **Normalization** | Stripping meaning-free differences (whitespace, reviewer lists) before hashing. |
| **Observed stage** | A feature's lifecycle stage per release, as shown by the CHANGELOG or feature-gates docs. |
| **Query mode** | CURRENT, HISTORY, CHANGE or WHY. Determines filters and authority adjustments. |
| **Release-aligned snapshot** | The state of each in-scope file captured once per Kubernetes release (ADR-002 D1). |
| **Validity window** | The release range and date range during which a document version was the live version. |

## Retrieval and evaluation

| Term | Meaning |
|---|---|
| **Ablation** | Measuring the system with and without one component, to prove that component's contribution. |
| **Bi-encoder** | Embeds query and document separately, then compares the vectors. Fast; used for dense retrieval. |
| **Cross-encoder (reranker)** | Scores a query and document *together*. More accurate but slower; used on a small candidate set. |
| **Dense retrieval** | Finding chunks whose embedding vectors are close to the query's embedding. |
| **Embedding** | A fixed-length vector representing text meaning, produced by a model (here, Voyage). |
| **Faithfulness / groundedness** | Whether every claim in the answer is supported by the retrieved evidence. |
| **Golden set** | A fixed, human-verified set of questions with expected answers and sources, used to evaluate changes. |
| **HNSW** | Hierarchical Navigable Small World: a graph-based approximate nearest-neighbour index (supported by pgvector). |
| **Lexical / full-text retrieval** | Matching on words or terms. In Postgres this uses `tsvector`/`tsquery` ranking. This is *not* BM25. |
| **MRR** | Mean Reciprocal Rank: the average of 1 / (rank of the first relevant result). |
| **nDCG** | Normalized Discounted Cumulative Gain: a rank-quality score that rewards relevant results appearing higher. |
| **RAG** | Retrieval-Augmented Generation: retrieve evidence, then have an LLM answer from that evidence. |
| **Recall@K** | The fraction of relevant items that appear in the top K results. |
| **RRF** | Reciprocal Rank Fusion: combine ranked lists with score = Σ 1/(k + rank), where k is often 60. |

## Engineering

| Term | Meaning |
|---|---|
| **ADR** | Architecture Decision Record: a short document capturing one decision, its context, and its consequences. |
| **Editable install** | Installing a package as a link to its source directory, so code edits take effect without reinstalling. `uv sync` does this for the project. |
| **Healthcheck** | A command Docker runs repeatedly inside a container to decide whether it is healthy (here, `pg_isready`). `docker compose up --wait` blocks on it. |
| **Idempotent** | Running an operation twice has the same effect as running it once. This is required for ingestion and queue workers. |
| **Liveness vs. readiness** | Liveness means "the process is up". Readiness means "it can serve traffic, because its dependencies are reachable". |
| **Lockfile** | A file (`uv.lock`) recording the exact version of every dependency, including indirect ones, so every machine installs the same set. |
| **Migration** | A versioned, ordered schema change applied by a tool (Alembic), so every environment has the same schema. |
| **Named volume** | Docker-managed storage that outlives the container, so `make down` / `make up` keep the database's data. |
| **Pre-commit hook** | A script git runs before each commit. If it fails or modifies files, the commit stops so you can review. Here it runs ruff only. |
| **pytest marker** | A label on a test (e.g. `integration`). `pytest -m <expr>` selects or excludes tests by label. |
| **src layout** | Package code lives under `src/<package>/`, so tests import the *installed* package and catch packaging mistakes a root-level package would hide. |
