# S02 Corpus spike report

*Slice: `docs/slices/S02-corpus-spike.md` · Status: in progress. T3–T5 add their sections; T6 writes the conclusion.*

## 1. Snapshot (S02-T2)

- **Fetched:** 2026-09-30T06:09:15Z, by `uv run python spikes/fetch.py`.
- **SHA record:** `config/corpus_manifest.lock.yaml`, added in commit `edc3730`. The lock file is the **single record** of the 77 corpus SHAs this spike measures:
  - the head of each repo's default branch
  - the website SHA per release (`release-1.R`, or `main` for 1.37)
  - the enhancements, community and sig-release SHA at each release date (the cutoff rule is written in the lock)

  This report doesn't copy them. Re-running the script with the lock present verifies them and leaves the lock unchanged.
- **Clones:** partial clones with `--filter=blob:none`, meaning commits and directory listings only, no file contents yet. They live in `CORPUS_CACHE_DIR`, outside the repo. The total size on disk is about 117 MB.

Default-branch heads at fetch time:

| Repo | Branch | Head | History | Size on disk |
|---|---|---|---|---|
| kubernetes/website | `main` | `256a1f49419171f6c7fbdb1857146da1c63eb533` | all branches, full | 87 MB |
| kubernetes/kubernetes | `master` | `7c596ad7938d030a4cab3c1e55b16b7f61cf7ca5` | depth 1 | 1.5 MB |
| kubernetes/enhancements | `master` | `4be81e27aef5d252972fd02b5a9479a18982dfe5` | full | 11 MB |
| kubernetes/community | `main` | `c591129c16bf6b57b6ef9d689f1f5175ace56634` | full | 13 MB |
| kubernetes/sig-release | `master` | `49d129fa10676ef91d821c006494bfddd5d1fcd2` | full | 4.0 MB |

The website `main` head is also the 1.37 docs snapshot, because 1.37 has no `release-1.37` branch yet. The fetch confirmed that the 4 traced KEP directories (2572, 2579, 2799, 4858) exist at the enhancements head.
