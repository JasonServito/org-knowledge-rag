# Slice brief: S02 Corpus spike

*Written by the coding agent in `/slice-retro`. The developer reads it before merging the retro PR.*

## What was built

S02 measured the public Kubernetes corpus before any schema was designed.
- A manifest (`config/corpus_manifest.yaml`) defines the Stage 1 subset.
- A fetch script pins 77 commit SHAs in a lock file, using partial clones.
- Six throwaway spike scripts measured versions, tokens and cost, renames, blog identity, and source formats. Each result was checked by hand and, where possible, graded against an independent source of truth: redirects, gate titles, Hugo URLs.

The evidence changed 12 rules in ADR-002 and ADR-003, and both are now Accepted. This matters to the project's thesis because explicit versions, authority and conflicts all rest on two definitions: what a version is, and what makes two files the same document. The spike replaced guesses about both with measured rules before a single migration was written.

## Decisions

| Decision | Alternative rejected | Why | Cost |
|---|---|---|---|
| Measure the corpus before designing the schema | Design tables from the blueprint | The schema depends on how many versions, renames and status mismatches exist | 9 PRs; 1,681 lines of throwaway spike code plus 578 lines of tests, to be rewritten in S04/S05 |
| Partial clones (`--filter=blob:none`) plus a SHA lock file | Full clones; the GitHub API | Reproducible and offline re-runs; a 138 MB cache | Git 2.43 lazily downloads missing objects, so reads run with `protocol.allow=never` to make a missing object an error |
| A version is a change in normalized content (ADR-002 D2) | Every commit is a version | Normalization removes only 5% of raw versions, so the rest is real change | A strip list to maintain in the manifest |
| Identity: the URL for rendered pages, a declared key for everything else (ADR-002 D4) | File path; `blog:<date>-<slug>` | Paths broke at the 1.29 page-bundle move, the 343 gate renames at 1.32 and the 909-file blog move. The URL keeps 415 of 416 blog histories whole. | Must mirror Hugo's URL rules |
| Renames: declared signals first, git similarity at 50% as the fallback | Similarity alone at 60% | Similarity found 4 of the 6 docs moves that redirects declare | Two mechanisms, plus the rule that a redirect's target must be new in that release |
| Blog `valid_from` = max(commit time, publication time); never-public versions not stored | Commit time | 317 of 416 posts were merged early, by up to 28.5 days | Relies on the unverified assumption that the site builds on every merge |
| CHANGELOGs are versioned like any source | "Sections never change" | 3 of 23 sampled sections were edited later, one a factual fix 13 months on | Text from before the first ingestion is lost |
| A feature's observed stage comes from release R's own snapshot, per minor release, and ambiguity is flagged | The latest file; per-patch keys | Later files rewrite history; patch-level changes are rare | Can't express "beta in 1.28.0–1.28.5, alpha after" |
| `GA` → `stable` is the only synonym; other unknown values are flagged | Map every "typo" | `GA` was the only real synonym; `disabled` turned out to be valid | A small synonym list in config |

## Likely interview questions

1. **Q: Why spend a slice measuring data instead of building?**
   **A:** The schema encodes what a version is and what a document is. Measuring first changed both rules.
   - Docs and blog identity moved from the file path to the URL, because 909 blog files and 343 feature-gate files moved while their URLs stayed the same.
   - Blog validity moved from commit time to publication time.
   - CHANGELOGs became versioned.

   Building first would have meant migrations designed on guesses, then rewritten.
2. **Q: How do you know two files are the same document?**
   **A:** For a page the website renders, I use the URL it's served at, because files move into folders or year directories without the URL changing. For structured sources I use a declared key: gate name, KEP number, CHANGELOG release. When a URL does change, I trust the site's own redirects and aliases first, and git's similarity score second.
3. **Q: How did you check that rename detection was correct?**
   **A:** I graded every rename git detected against an independent source of truth (an "oracle"): the site's redirect file and Hugo aliases for pages, and the gate title for feature gates. I also read a seeded sample by hand.
   - Precision: 351 of 351 renames at 50% or above were real.
   - Recall was the problem: similarity found only 4 of the 6 docs moves the redirects declare. So declared signals come first.
4. **Q: When is a document version "valid"?**
   **A:** Each version has a window on two clocks, releases and dates, bridged by a `releases` table. Docs are release-scoped: valid for the release whose branch they come from. Date-scoped sources use the commit date. The exception is the blog: valid from the later of the commit time and the publication time, because posts are often merged weeks before they go live.
5. **Q: What will embeddings cost, and how sure are you?**
   **A:** The realistic estimate is $0.42 with voyage-4 at 512-token chunks with a content-hash cache, and the worst case is $1.66. Both are far inside the 200M free tokens.
   - The estimate uses characters ÷ 4, which likely undercounts code and hex. Even doubling the worst case gives $3.33, inside the $5 budget.
   - S04 checks the estimate against Voyage's own token count.

## Numbers to remember

- **Corpus:** 1,745 documents and 3,862 versions; 3,281 versions are embeddable (the rest is KEP metadata). Releases 1.20–1.37; 77 locked SHAs.
- **Chunks at 512 tokens:** 26,588 (cached) to 55,821 (every version). 30–32% of sections are under 64 tokens.
- **Cost:** $0.42–$0.79 at voyage-4; worst row $1.66; budget $5.
- **Vector storage:** 109–229 MB at 1024 dimensions.
- **Renames:** 351 of 351 real at ≥50% similarity; similarity found 4 of 6 declared docs moves.
- **Blog:**
  - 417 in-scope posts
  - the URL keeps 413 of 416 published histories whole (415 with redirects and aliases)
  - 317 posts merged early (median 2.6 days, max 28.5)
  - 214 never-public versions dropped
- **Feature gates:** 287 of 293 agree across the 1.28 tables and the 1.37 files; 0–3% of gates per release are ambiguous.
- **CHANGELOG:** 371 sections in 18 files; 3 of 23 sampled sections edited after release.
- **Tests:** 74 spike unit tests, all running in CI without a corpus cache. Paid API calls: none.
