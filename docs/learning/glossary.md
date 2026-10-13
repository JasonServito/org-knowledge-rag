# Glossary

One line per term; alphabetical within each section. The agent appends a term only if an interviewer would plausibly use it (see the PR brief rules in `CLAUDE.md`). Edit any definition you'd phrase differently.

## Project-specific

| Term | Meaning |
|---|---|
| **Authority tier** | Rank of how much a source should be trusted for a claim (ADR-003 D3). It is adjusted per query mode. |
| **`canonical_id`** | A stable identity for a document across versions, renames and branches (ADR-002 D4). |
| **`claimed_status` / `claimed_stage`** | What a KEP's `kep.yaml` *says* its status or stage is. Stored as a claim, because it's often stale. |
| **Claim mismatch** | A conflict where the claimed status disagrees with the observed stage. Surfaced, never silently resolved. |
| **Conflict detection** | Finding where retrieved evidence disagrees and recording it in the answer's `conflicts[]` instead of leaving it to the model's prose (ADR-010). Code compares stored facts (`claim_mismatch`, `history_date`); the answer model flags texts that disagree; code settles each by fixed rules (ADR-003 D6) or marks it unresolved. |
| **Content hash** | A hash of normalized document content. The same hash means no new version (ADR-002 D2). |
| **Effective stage** | Observed stage if known, otherwise claimed stage with low confidence, otherwise unknown (ADR-003 D2). |
| **Feature gate** | A named on/off switch for a Kubernetes feature, with a lifecycle stage per release (alpha, beta, stable, deprecated). The feature-gate reference lists each gate's stage ranges; `observed_lifecycle` keeps the stage each release's own reference gives (S09). |
| **KEP** | Kubernetes Enhancement Proposal: a design + decision + tracking document per feature or process change. |
| **Manifest** | `config/corpus_manifest.yaml`. It defines which repos, paths and releases are in the corpus. |
| **Normalization** | Stripping meaning-free differences (whitespace, reviewer lists) before hashing. |
| **Observed stage** | A feature's lifecycle stage per release, as that release's own feature-gate reference shows it (`observed_lifecycle`, S09). The CHANGELOG isn't a second source in Phase 1 (ADR-003, changed in the S10-R1 sitting). |
| **Query mode** | CURRENT, HISTORY, CHANGE or WHY. Determines filters and authority adjustments. |
| **Release-aligned snapshot** | The state of each in-scope file captured once per Kubernetes release (ADR-002 D1). |
| **Rename detection (similarity threshold)** | git pairs a deleted file with an added file when their contents are at least N% similar (`R081` means 81%). A lower threshold finds more renames but also pairs unrelated files. Declared signals, such as a site's redirects, are an alternative. |
| **Supersession** | A conflict between an older and a newer version of the same section of one document. The version valid at the asked-about release wins (ADR-010 D2). |
| **Temporal confusion** | An answer that mixes facts from different releases, or states an old release's fact as current. Retrieval that ignores release windows invites it (S09). |
| **Validity window** | The release range and date range during which a document version was the live version. |

## Retrieval and evaluation

| Term | Meaning |
|---|---|
| **Ablation** | Measuring the system with and without one component, to prove that component's contribution. |
| **Authority-selection accuracy** | Over "now" questions whose correct sources span 2+ trust tiers, the share where the first correct result has the most trusted tier among them (S09). It leans toward the tier weights it measures, so "now"-question MRR is reported beside it. |
| **Bi-encoder** | Embeds query and document separately, then compares the vectors. Fast; used for dense retrieval. |
| **BM25** | The standard ranking for word search: a rare word (high IDF, inverse document frequency) counts more than a common one, and repeating a word helps less each time. Postgres's built-in `ts_rank` has neither; BM25 needs an extension. |
| **Chunking (structure-aware)** | Splitting documents into retrievable pieces at their headings, so each chunk is one section with its heading path. Code blocks and HTML tables are never cut; an oversize list or pipe table is cut between items or rows (S05). |
| **Citation validation** | A plain-code check that every chunk id the model cites was retrieved for this question. One bad id rejects the answer (ADR-006). |
| **Conflict set** | The answer key for conflict detection: every disagreement among each eval question's fixed top-10 results, written before the runs, with 4 seed cases (ADR-007 D4). Precision = flagged conflicts that are in it; recall = its conflicts that search retrieved and the system flagged. |
| **Corrective RAG** | Checking the search results before answering: a grader judges them, and when they fall short, the system searches again with a changed query, a bounded number of times. Tested in S11 and not adopted (ADR-011). |
| **Cosine distance** | 1 − the cosine similarity of two vectors: 0 = same direction, 1 = unrelated, 2 = opposite. pgvector's `<=>` operator. |
| **Cross-encoder (reranker)** | Scores a query and document *together*. More accurate but slower; used on a small candidate set. |
| **Dense retrieval** | Finding chunks whose embedding vectors are close to the query's embedding. |
| **Embedding** | A fixed-length vector representing text meaning, produced by a model (here, Voyage). |
| **Embedding cache (content-hash)** | Reuses a stored vector when a chunk's embedded text hashes the same as text already embedded, so an unchanged section is paid for once across versions. It only works if the embedded text holds no per-version fields. |
| **Evidence grader** | A model call that reads a question's retrieved results and judges whether they're enough to answer it. S11's Haiku grader said "enough" even when no correct source was in the 10 (ADR-011). |
| **Faithfulness / groundedness** | Whether every claim in the answer is supported by the retrieved evidence. |
| **False refusal** | The system answers "insufficient evidence" to a question that has an answer in the corpus. The cost of being too cautious; AC3 measures the opposite case. |
| **Golden set** | A fixed, human-verified set of questions with expected answers and sources, used to evaluate changes. |
| **Hit@K (hit rate)** | 1 if any relevant item is in the top K results, else 0, averaged over questions. Unlike Recall@K, it asks "was one good source found?", not "how many?". |
| **HNSW** | Hierarchical Navigable Small World: a graph-based approximate nearest-neighbour index (supported by pgvector). Its search width (`hnsw.ef_search`) is how many candidates a search keeps: wider is slower but closer to an exact scan, and a scan returns at most that many rows. |
| **Hybrid retrieval** | Running dense and lexical retrieval for the same question and merging their ranked lists (here with RRF), so a text found by meaning or by exact words can rank high. |
| **Inter-annotator agreement** | How often independent labelers give the same labels. Low agreement means the answer key itself is uncertain, so scores against it are provisional. S10's 3 labeling passes split on 0.526 of conflicts, so precision is reported raw and judged. |
| **Lexical / full-text retrieval** | Matching on words or terms. In Postgres this uses `tsvector`/`tsquery` ranking. This is *not* BM25. |
| **LLM tracing (observability)** | Recording each step of one request (retrieve, generate, validate) with its inputs, outputs, tokens and latency, so a bad answer can be debugged later. Here: Langfuse, one trace per ask. |
| **MRR** | Mean Reciprocal Rank: the average of 1 / (rank of the first relevant result). |
| **nDCG** | Normalized Discounted Cumulative Gain: a rank-quality score that rewards relevant results appearing higher. |
| **Negative control** | A baseline that shouldn't pass a check, run to prove the check can tell systems apart. S12 picked AC5's and AC6's rules so that the time-blind dense baseline scores low on them (2 of 10, 6 of 9) and the time-aware pipeline higher (8 of 10, 8 of 9). |
| **Oracle (for grading)** | An independent source of truth used to check a heuristic's output. S02 graded git's rename guesses against the site's redirects, Hugo aliases and gate titles. |
| **Query rewriting** | Having a model rewrite the user's question into a search query in the corpus's own words (full names, not slang), then searching with it, usually beside the original. A proposed addition after S11, for informally worded questions. |
| **Query router** | A step before search that sorts a question by what it asks for (here an LLM call returning a query mode and the release or year it names), so retrieval can pick a plan per kind of question. Code, not the model, turns the release or year into a release window (ADR-009). |
| **RAG** | Retrieval-Augmented Generation: retrieve evidence, then have an LLM answer from that evidence. |
| **Recall@K** | The fraction of relevant items that appear in the top K results. |
| **Stale-result rate** | The share of top-K results for "now" questions whose text a later edit replaced: no current version still holds it (S09). Lower is better. |
| **RRF** | Reciprocal Rank Fusion: combine ranked lists with score = Σ 1/(k + rank), where k is often 60. |
| **Structured output** | Making the LLM return JSON that matches a given schema (here a Pydantic model), instead of free text that has to be parsed. |
| **Temporal accuracy** | For questions about a dated past ("in 1.22", "before 2021"), the share of top-K results valid inside the asked-for release window (S09). |

## Engineering

| Term | Meaning |
|---|---|
| **ADR** | Architecture Decision Record: a short document capturing one decision, its context, and its consequences. |
| **ADR amendment vs. superseding ADR** | An amendment is a dated section that clarifies an accepted ADR without changing its decision. If the decision itself changes, a new ADR replaces (supersedes) the old one. |
| **Database driver** | The library that speaks Postgres's network protocol (here psycopg 3). Alembic and SQLAlchemy sit on top of it. |
| **Editable install** | Installing a package as a link to its source directory, so code edits take effect without reinstalling. `uv sync` does this for the project. |
| **Exclusion constraint** | A Postgres constraint that rejects a row if it "collides" with an existing one under given operators. Here: same document (`=`) and overlapping date ranges (`&&`) means no two versions are live at once. Needs the `btree_gist` extension to compare plain columns with `=`. |
| **Fingerprint (of a database)** | One hash over every stored value except generated ids, from sorted rows, so two databases with equal fingerprints hold identical data however they were built. S05 uses it to prove re-ingestion is reproducible (AC8). |
| **Half-open interval `[from, until)`** | Includes its start, excludes its end. Back-to-back windows then touch without overlapping, so an instant belongs to exactly one version. Release windows are inclusive `[from, until]` instead. |
| **Healthcheck** | A command Docker runs repeatedly inside a container to decide whether it is healthy (here, `pg_isready`). `docker compose up --wait` blocks on it. |
| **Idempotent** | Running an operation twice has the same effect as running it once. This is required for ingestion and queue workers. |
| **Liveness vs. readiness** | Liveness means "the process is up". Readiness means "it can serve traffic, because its dependencies are reachable". |
| **Lockfile** | A file (`uv.lock`) recording the exact version of every dependency, including indirect ones, so every machine installs the same set. |
| **Migration** | A versioned, ordered schema change applied by a tool (Alembic), so every environment has the same schema. |
| **Named volume** | Docker-managed storage that outlives the container, so `make down` / `make up` keep the database's data. |
| **p95 latency** | The time 95% of requests finish within: a tail measure, where a mean hides slow outliers. Here it's nearest rank: sort the times and take the ⌈0.95 n⌉-th (the 41st of 43). |
| **Partial clone** | `git clone --filter=blob:none`: download commits and directory listings but no file contents, then fetch only the files you need. S02's corpus cache is built this way. |
| **Permissive license (MIT)** | Lets anyone use, modify and redistribute the code, even in closed-source products, as long as they keep the copyright notice. It covers this repo's code, not the corpus. |
| **Pre-commit hook** | A script git runs before each commit. If it fails or modifies files, the commit stops so you can review. Here it runs ruff only. |
| **pytest marker** | A label on a test (e.g. `integration`). `pytest -m <expr>` selects or excludes tests by label. |
| **Savepoint** | A checkpoint inside a transaction (a nested `conn.transaction()` in psycopg). Rolling back to it undoes only the failed statement, so a test can expect an error and keep going. |
| **Service container** | A Docker container GitHub Actions starts next to a CI job (here Postgres) and waits on until healthy. CI's equivalent of `make up`. |
| **Spike** | A time-boxed, throwaway experiment that answers a question with evidence before committing to a design. Its code is rewritten, not reused. |
| **src layout** | Package code lives under `src/<package>/`, so tests import the *installed* package and catch packaging mistakes a root-level package would hide. |
| **Upsert** | Insert a row, or update it if its key already exists (`INSERT … ON CONFLICT … DO UPDATE`). Makes a seed idempotent. |
