# Decision-chain completeness (S13-T4)

Gold: eval/golden_set/chains-v0.yaml (chains-v0, sha256 50323a244638dd154abf7839ab20b5894e27d4a56e6ce0da6f583d75df9e3068).
Control: authority mode, mode WHY (no router call), top 10, the best-ranked hit per step by the lookup table. Made by `make eval-chain`.

## kep:2572 (built-on)

Question: Why did Kubernetes move to three releases per year?
Chain built: 2026-10-13 22:05:11 UTC

| step | gold | built | right | right with date | control's pick | control right |
|---|---|---|---|---|---|---|
| problem | 2 texts, 2020-10-14 | gh:sig-release/discussions/1290 › Opening post · @justaugustus · 2020-10-14 > What would you like to be added:, 2020-10-14, template_field | yes | yes | no hit | no |
| discussion | 1 text, 2020-10-14 | gh:sig-release/discussions/1290 › Comments > @markjacksonfishing · 2020-10-14, 2020-10-14, template_field | yes | yes | #5 gh:sig-release/discussions/1290 › Comments > @johnbelamaric · 2020-10-15 | yes |
| proposal | 2 texts, 2021-03-12 | kep:2572 › KEP-2572: Defining the Kubernetes Release Cadence > Summary, 2021-03-12, seed | yes | yes | #10 kep:2572 › KEP-2572: Defining the Kubernetes Release Cadence > Proposal > User Stories > SIG Release members | yes |
| decision | 7 texts, 2021-04-23 | gh:enhancements/pull/2567 › Comments > @dchen1107 · 2021-04-22, 2021-04-23, merge_event | yes | yes | no hit | no |
| implementation | 4 texts, 2021-08-04 | web:/blog/2021/07/20/new-kubernetes-release-cadence/ › Where you can find out more, 2021-07-20, linking_text | yes | no | #1 web:/blog/2021/07/20/new-kubernetes-release-cadence/ › Why we decided to change the release cadence | yes |
| current_docs | 3 texts | web:/releases/release/ › The Release Cycle, 2024-12-11, similarity | yes | n/a | no hit | no |

- steps right: 6 of 6
- right with the same UTC day: 4 of 5
- control steps right: 3 of 6
- builder 6, control 3: beats

## kep:3015 (held-out)

Question: Why did Kubernetes add the PreferSameZone and PreferSameNode traffic distribution options for Services?
Chain built: 2026-10-13 22:05:11 UTC

| step | gold | built | right | right with date | control's pick | control right |
|---|---|---|---|---|---|---|
| problem | 3 texts, 2021-10-14 | gh:enhancements/pull/3010 › Opening post · @danwinship · 2021-10-14, 2021-10-14, template_field | yes | yes | no hit | no |
| discussion | 1 text, 2021-10-14 | gh:enhancements/pull/3010 › Comments > @aojea · 2021-10-14, 2021-10-14, template_field | yes | yes | no hit | no |
| proposal | 2 texts, 2025-02-06 | kep:3015 › KEP-3015 PreferSameZone and PreferSameNode Traffic Distribution > Summary, 2025-01-23, seed | yes | no | #3 kep:4444 › KEP-4444: Traffic Distribution for Services > Alternatives > An alternative definition of `PreferClose` | no |
| decision | not_stored | missing: no_link | no | n/a | no hit | no |
| implementation | 4 texts, 2025-04-23 | web:/blog/2025/07/28/kubernetes-v1-34-sneak-peek/ › Featured enhancements of Kubernetes v1.34 > `PreferSameZone` and `PreferSameNode` traffic distribution for Services, 2025-07-28, linking_text | yes | no | #1 web:/blog/2025/12/17/kubernetes-v1-35-release/ › Features graduating to Stable > PreferSameNode traffic distribution | yes |
| current_docs | 3 texts | web:/docs/concepts/services-networking/service/ › Virtual IP addressing mechanism > Traffic distribution control, 2026-08-26, similarity | yes | n/a | no hit | no |

- steps right: 5 of 6
- right with the same UTC day: 2 of 4
- control steps right: 1 of 6
- builder 5, control 1: beats
