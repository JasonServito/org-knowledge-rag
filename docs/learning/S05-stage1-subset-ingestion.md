# Slice brief: S05 Stage 1 subset ingestion

*Written by Claude in `/slice-retro`. The developer reads it before saying "merge" on the retro.*

**Where this fits:** Sources → **Ingest** → **Store** → **Chunk** → **Embed** → Retrieve → Answer

## What was built

- **The whole manifest is ingested:**
  - 1,168 documents and 2,882 versions from 6 source types, from empty in 1 min 25 s. A re-run adds 0.
  - Sources: docs pages of 3 SIGs, release records and feature gates at 18 releases (1.20–1.37); every KEP in the 3 SIG folders and the governance docs at each release date plus `head` (the latest default-branch commit in the lock); blog posts from 1.20; 18 CHANGELOGs.
- **One document per thing, across moves:**
  - A moved page or renamed gate stays one document. Its first URL or name is its id; later ones become **aliases** (old names that still point to it).
  - The 6 known page moves are one document each, and 345 gate files renamed at 1.32 created 0 new documents.
- **Versions start when the text went live:**
  - KEPs and governance docs use their **merge time** (when the change landed on the main branch, not when it was written).
  - Blog posts start at publication, so 214 of 1,138 versions that were never public aren't stored.
- **Final chunk text, then one embed:**
  - Chunks lose `{#id}` anchors (custom heading ids written after a heading) and hidden HTML comments; HTML tables stay whole; oversize lists and tables are cut between items or rows.
  - 21,552 distinct texts each got one `voyage-4-large` vector. A second run makes 0 requests.
- **Proof that ingestion is reproducible (the spec's AC8, first part: re-ingesting gives identical version counts and hashes):**
  - Every ingest ends with a report and a **fingerprint**: one hash over every stored corpus value except generated ids.
  - Two from-empty ingests printed byte-identical reports.

This matters to the project's thesis because the corpus is now fixed and complete before S06 measures the first baseline. Every version carries an exact window, so later slices can test release-aware retrieval on real history.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Every KEP in the 3 SIG folders (113 at `head`) | The 4 traced KEPs | The manifest defines the subset; seed #14 cites KEP-1205 | 141 KEP documents, 472 versions to ingest and test |
| Feature gates in S05; a gate's chunk starts with its `stages` YAML | Defer to S09; one formatted line | Seed #16 needs "beta since 1.36, on by default"; the file's own YAML is lossless | 491 documents; stages read from the file because Postgres reorders JSON keys |
| Moves: redirect file, then `aliases` in front matter (the YAML block at a page's top), then git similarity ≥ 50% | git similarity alone | Declared signals first: of the 6 known moves, 5 link by redirect, 1 by alias, 0 by similarity | The id can be a URL the site no longer serves |
| `make reset-corpus` empties 4 tables and keeps releases and vectors | Recreate the database | Every task's demo rebuilt from empty; ids restart, so chunk ids repeat exactly | Dev database only |
| A KEP or governance version starts at its merge time (first-parent) | Commit time | The text became the project's when it merged: KEP-2579 2021-05-12, not 2021-05-11 | One `git log` per change |
| Versions older than 1.20 keep their true date; release window starts at 1.20 | Clamp the date; add releases 1.0–1.19 | The date window is authoritative for date-scoped sources; 67 documents affected | Their release window understates their age |
| Governance moves: same path, then similarity ≥ 50% (ADR-002 D4 amendment) | `git log --follow` | Finds all 8 real moves with tested code; devil's advocate run | An ADR amendment |
| 25 old single-file KEPs stay separate (`kep:<sig>/<name>`) | Link them to later folders by title | Unique by construction; keeps ADR-002's known limit | 24 of 25 could be linked; changing ids after S06 means relabeling |
| Blog id = URL at publication; a version from max(merge, publication) | Path identity; merge time only | 909 posts moved folders in 2026; drafts were never public | The slug rule of Hugo (the site generator behind kubernetes.io) is approximated |
| CHANGELOGs `[R, R]`, dated by the lock head commit; no TOC and no Downloads sections | The lock's fetch time; keep the hash tables | sha512 rows were 42% of 7.74M CHANGELOG characters | A lock refresh re-dates all 18 (S14) |
| Cut oversize lists between items and pipe tables (Markdown tables drawn with vertical bars) between rows, repeating the header | Keep blocks whole; cut code by lines | Texts over 1,024 tokens: 433 → 77; cut code misleads | 77 stay oversize (max 15,735 tokens) |
| Drop HTML comment blocks from chunk text (scanner rule 6) | Keep them; test in S06 | 10.9% of KEP lines were hidden template text, with 260 fake headings | 1 indented comment left; ~12 PR-link lines lost |
| Fingerprint over every stored corpus value except generated ids | Ids, version hashes and windows only | One definition of "identical" that covers chunk text, claims and metadata | 52,344 rows hashed per report |
| Full embed with a one-off 6M token cap; default stays 2M | Raise the default | The guard stays tight for later runs | 6% headroom for a rebuild from empty |

## Likely interview questions

1. **Q: How do you keep one identity when a page moves or a gate is renamed?**
   - Declared signals first (the site's redirect file, the page's `aliases`); git similarity ≥ 50% only as a fallback. The id is the first URL.
   - Results: 6 known moves → 6 documents; 345 gate renames → 0 new documents; a 40% pair stays two.
2. **Q: How do you prove re-ingesting gives identical data?**
   - A sha256 over every stored corpus value except generated ids, rows sorted so order doesn't matter.
   - Two from-empty ingests printed byte-identical reports; an independent script reproduced the hash over 52,344 rows.
3. **Q: When does a version start, for a KEP and for a blog post?**
   - KEP: the last first-parent commit touching it, i.e. the merge. Blog: max(merge, publication), since Hugo hides a post until its date.
   - Follow-up, "why does it matter?": a question about 1.22 must not see text that went live after it.
4. **Q: Why fix the chunker before embedding the whole corpus?**
   - S06 labels relevance by section name, and vectors are paid once. Changing chunk text later means relabeling and re-embedding.
   - Numbers: anchors in 1,269 texts → 0; texts over 1,024 tokens 433 → 77; cost 5.61M Voyage tokens, free tier.
5. **Q: Your counts differ from your spike's. Why trust them?**
   - Each difference has a cause, e.g. the spike used file paths as ids (842 gate paths → 491 gates) and counted never-public versions (1,138 → 924).
   - Expected values came from the spike's code and git in the sittings, never from the code under test.

## Numbers to remember

- 1,168 documents, 2,882 versions, 21 aliases (spike: 1,745 / 3,862 by file path).
- 48,273 chunks, 21,552 distinct texts: 55% of chunks repeat a text.
- From empty: 1 min 25 s; a re-run: 34 s, 0 new rows.
- Fingerprint over 52,344 rows; skip lines 331 → 26.
- Texts over 1,024 tokens: 433 → 77 (max 15,735).
- Embedding: 162 requests, 5.61M Voyage tokens, 3 min 44 s; Voyage / estimate = 1.045 (S04: 0.95).
- Paid calls: Voyage only, inside the 200M free tier; 0 Anthropic calls.
- 390 unit and 93 integration tests (from 224 and 80).
- 4 PRs (#27–#29 and R3's). #27–#29 were ~1,510, ~1,050 and ~3,330 reviewable lines, all over the ~800-line alarm and accepted in their sittings.
