# Test fixtures

Small real files from the Kubernetes corpus, copied byte-exact at pinned commits (the SHAs in `config/corpus_manifest.lock.yaml`). Don't edit them: the tests' expected values were read from these bytes by hand.

| Folder | Source | Pinned at |
|---|---|---|
| `website_s04/<page>/1.N.md` | [kubernetes/website](https://github.com/kubernetes/website), `content/en/docs/concepts/security/<page>.md` | `release-1.N` in the lock (`website_releases`); the file is the first release from 1.24 on with those bytes |
| `website_s04/rbac/excerpt-1.37.md` | kubernetes/website, `content/en/docs/reference/access-authn-authz/rbac.md`, lines 1–14 | `256a1f49` (1.37) |
| `website_s04/rbac/table-excerpt-1.37.md` | kubernetes/website, `content/en/docs/reference/access-authn-authz/rbac.md`, lines 645–698: an HTML table with 3 blank lines inside its cells | `256a1f49` (1.37, the lock's website head) |
| `website_s04/authorization/excerpt-1.37.md` | kubernetes/website, `.../access-authn-authz/authorization.md`, lines 204–339 | `256a1f49` (1.37) |
| `website_s04/authentication/excerpt-1.32.md` | kubernetes/website, `.../access-authn-authz/authentication.md`, lines 332–499 | `a6b9d383` (1.32) |
| `website_s05/release-notes/excerpt-1.20.md` | kubernetes/website, `content/en/docs/setup/release/notes.md`, lines 1–18 | `2886f437` (1.20) |
| `website_s05/release-notes/1.N.md` | kubernetes/website, `content/en/releases/notes.md` (where the page moved at 1.21) | `release-1.N` in the lock: `7ed77d72` (1.21), `80b4524c` (1.22) |
| `website_s05/feature-gates-page/excerpt-1.28.md` | kubernetes/website, `content/en/docs/reference/command-line-tools-reference/feature-gates.md`, lines 52–63: the start of the first pipe table | `6b57c309` (1.28) |
| `website_s05/redirects/excerpt-1.21.txt` | kubernetes/website, `static/_redirects`, lines 495–498 | `7ed77d72` (1.21) |
| `website_s05/feature-gates/<gate>/1.N.md` | kubernetes/website, `content/en/docs/reference/command-line-tools-reference/feature-gates/<gate>.md`, whole file: `StrictIPCIDRValidation` (1.37), `APIServingWithRoute` (1.32), `APIServingWithRoutine` (1.33), `PodInfoAPI` (1.36), `InPlacePodVerticalScalingMemoryBackedVolumes` (1.37) | The lock's website SHA for 1.N (`website_releases`): `a6b9d383` (1.32), `b9ab6105` (1.33), `1de955eb` (1.36), `256a1f49` (1.37, `main`). Each file's `git hash-object` equals the blob at that commit |
| `kep_2579/1.N.kep.yaml` | [kubernetes/enhancements](https://github.com/kubernetes/enhancements), `keps/sig-auth/2579-psp-replacement/kep.yaml` | `master` on the 1.N release date in the lock (`release_date_snapshots`) |
| `kep_old/0014-dynamic-audit-configuration-excerpt-1.20.md` | kubernetes/enhancements, `keps/sig-auth/0014-dynamic-audit-configuration.md` (an old single-file KEP), lines 1–61 | `2df83383` (`master` on the 1.20 release date) |
| `kep_4317/README-excerpt-head.md` | kubernetes/enhancements, `keps/sig-auth/4317-pod-certificates/README.md`, lines 901–994, with the HTML comment block of lines 932–992 | `4be81e27` (the lock's enhancements head) |
| `sig_release/versioning/1.N.md` | [kubernetes/sig-release](https://github.com/kubernetes/sig-release), whole file: `release-engineering/versioning.md` at 1.36, `release-engineering/reference/versioning.md` at 1.37 (moved by PR #2984) | `master` on the 1.N release date in the lock (`release_date_snapshots`): `760d54e8` (1.36), `9ad626fd` (1.37). Each file's `git hash-object` equals the blob at that commit |
| `sig_release/go/1.36.md`, `sig_release/go-updates/1.37.md` | kubernetes/sig-release, whole file: `release-engineering/handbooks/go.md` at 1.36, renamed `handbooks/go-updates.md` at 1.37 (PR #2984) | `760d54e8` (1.36), `9ad626fd` (1.37). Same `git hash-object` check |
| `blog/<post>-excerpt.md` | kubernetes/website, `content/en/blog/_posts/<path>`, the first lines: `2018/kubernetes-1-11-release-interview.md` (1–9), `2020/introducing-podtopologyspread.md` (1–12), `2015/borg-predecessor-to-kubernetes.md` (1–6), `2022/psp-historical-context/index.md` (1–12), `2023/kubernetes-1.28-blog.md` (1–13), `2023/image-registry-change.md` (1–20), `2025/announcing-etcd-3-6/index.md` (1–11) | `256a1f49` (the lock's website head) |
| `blog/<post>/<commit>-excerpt.md` | kubernetes/website, the post's file as website commit `<commit>` (on `main`'s first-parent line) left it, the first lines: `validating-admission-policy-ga` (`3a358ed2`, `2de4371a`: 1–12), `ingress-nginx-retirement` (`35d8dfc2`, `2b1598fc`, `fe122837`: 1–12), `headlamp-karpenter-plugin` (`e5c44148`, `5eaca101`: 1–12), `ccm-metric-route-sync-total` (`02ab95c9`: 1–12; `73f7fa85`: 1–15), `kubernetes-1.23-release-interview` (`27d1959c`: 1–10) | The named commits, all before the lock's website head `256a1f49` |
| `blog/k8s-book-club/<commit>.md` | kubernetes/website, `content/en/blog/_posts/2024-02-22-k8s-book-club/index.md`, whole file, as commits `ccb153d2` (opens with `------`) and `2912b59c` (the fix) left it | Each file's `git hash-object` equals the blob at that commit (`74e2c4f7`, `11091f1b`) |
| `blog/kubernetes-configuration-best-practices/5b9bb69f.md` | kubernetes/website, `content/en/blog/_posts/2025-11-25-kubernetes-configuration-best-practices/index.md`, whole file (4 headings have a tab after `###`) | `5b9bb69f`; the file's `git hash-object` equals the blob at that commit (`ab02007a`) |
| `kubernetes/CHANGELOG-1.22-excerpt.md` | [kubernetes/kubernetes](https://github.com/kubernetes/kubernetes), `CHANGELOG/CHANGELOG-1.22.md`, lines 3082–3193 | `7c596ad7` |
| `kubernetes/CHANGELOG-1.22-beta.1-excerpt.md` | kubernetes/kubernetes, `CHANGELOG/CHANGELOG-1.22.md`, lines 3019–3303: the whole `v1.22.0-beta.1` section (its stray closing fence is the file's line 3085), then `v1.22.0-beta.0`'s download tables | `7c596ad7` |
| `kubernetes/CHANGELOG-1.27-excerpt.md` | kubernetes/kubernetes, `CHANGELOG/CHANGELOG-1.27.md`, lines 2450–2466: part of one list block that opens with an indented continuation line | `7c596ad7` |
| `kubernetes/CHANGELOG-1.37-excerpt.md` | kubernetes/kubernetes, `CHANGELOG/CHANGELOG-1.37.md`, lines 1–250: the generated TOC and the whole `v1.37.1` section | `7c596ad7` |

## License

- `website_s04/`, `website_s05/` and `blog/`: Kubernetes documentation and blog, © The Kubernetes Authors, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `kep_2579/`, `kep_4317/`, `kep_old/`, `kubernetes/` and `sig_release/`: © The Kubernetes Authors, licensed [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), the license of the enhancements, kubernetes and sig-release repos.
| `eval/demo.yaml` | Not a corpus file: 3 Appendix A seeds (#6, #13, #10) in the ADR-007 format, labeled in the S06-R1 sitting from the dev database and verified by the developer | The dev database at `main` 60bd146 (S05 corpus, fingerprint `sha256:458effad…`) |
