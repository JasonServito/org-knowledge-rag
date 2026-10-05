# Slice brief: S03 Domain model + migrations

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → Ingest → **Store** → Chunk → Embed → Retrieve → Answer

## What was built

- **6 tables** for releases, documents, aliases, versions, chunks and vectors, created by one migration (a versioned schema change) that also undoes itself cleanly.
- **15 rules from the domain model, each enforced and each tested.** The database refuses 12 of them by itself (CHECK, UNIQUE, foreign keys, one exclusion constraint). 3 live in code because SQL can't express them.
- **The "one live version" rule is a single exclusion constraint:** no two versions of one document may have overlapping date windows, so at most one window is open.
- **10 data-access functions** that S04 ingestion will call: plain SQL through psycopg, with Pydantic models at the edge and the transaction left to the caller.
- **A releases seed** (`make seed`) that loads 18 releases from the manifest and can be re-run safely (an upsert).

This matters to the project's thesis because "which text was true when" is now a database guarantee, not something the LLM has to guess.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| psycopg 3 + hand-written SQL, only in `db/` (ADR-005) | SQLAlchemy Core; an ORM | SQL stays visible; Postgres features (ranges, pgvector) used as-is | 10 functions of hand-written SQL; revisit at S09 if queries multiply |
| Rules enforced by DB constraints wherever SQL can express them | Python-only checks; triggers | Any writer is refused, not just our code; one constraint gives R8 and R9 | Needs the `btree_gist` extension, checked locally only (RDS: S15) |
| Release windows inclusive `[from, until]`; date windows half-open `[from, until)` | Both half-open; both inclusive | Every release bound is a real release (foreign key); same-day edits fit | Two conventions to remember; both live in the 2 read functions only |
| `releases` keyed by `minor` (24) as `smallint` | Text key `'1.24'` | `'1.9' < '1.20'` is false as text | Assumes Kubernetes stays on major version 1 |
| One vector per chunk per model | One vector per unique text | Saves nothing while chunk headers hold per-version fields | Up to 229 MB of vectors (S02's upper bound); revisit in the S04 sitting |
| `make seed` upserts and never deletes | Insert-only; seeding inside a migration | 4 end-of-life dates (1.34–1.37) are planned and will change | A removed release must be deleted by hand |
| Superseding = close the old version, then insert the new one | Insert, then close | The exclusion constraint rejects the other order | The caller must keep the order; a test proves the wrong order fails |

## Likely interview questions

1. **Q: How do you guarantee a document never has two current versions?**
   - An exclusion constraint on (document, date range): two open windows overlap, so Postgres refuses the second.
   - A test removes the constraint, re-migrates, and shows the R8 and R9 tests fail.
2. **Q: Why enforce rules in the database instead of in Python?**
   - The database refuses bad rows from any writer: a script, a migration or a future service.
   - Only 3 of 15 rules are in code (an alias can't equal an id; close a window once; compute the hash), because SQL can't express them.
3. **Q: Why are date windows half-open but release windows inclusive?**
   - Half-open: back-to-back versions touch without overlapping, so an instant has exactly one version.
   - Inclusive: every bound is a real release, checked by a foreign key, with no fake "1.38".
4. **Q: How do you know the tests test anything?**
   - Each rule test asserts the exact error and constraint name.
   - 6 break-it checks: break the rule's code or constraint, watch the test fail, restore.
   - Expected values come from outside the code: the manifest, real corpus commits, and the FIPS SHA-256 test vector.
5. **Q (follow-up): Why plain SQL and not an ORM?**
   - The core queries (windows, vectors, full-text search later) are Postgres-specific, and I want to explain every line.
   - Revisit if retrieval needs more than about 4 combined query variants (S09).

## Numbers to remember

- 6 tables, 28 named constraints, 15 rules (12 in the database, 3 in code).
- 10 data-access functions; 396 lines of source plus a 161-line migration.
- 55 new tests (13 unit, 42 integration); totals 94 unit and 45 integration.
- 18 releases (1.20–1.37); 2 seed runs give the same checksum.
- 6 break-it checks, 6 failed as intended.
- Run size: about 1,425 reviewable lines, split into 2 PRs (about 495 and 931).
- Paid API calls: none.
