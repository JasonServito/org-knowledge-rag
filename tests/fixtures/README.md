# Test fixtures

Small real files from the Kubernetes corpus, copied byte-exact at pinned commits (the SHAs in `config/corpus_manifest.lock.yaml`). Don't edit them: the tests' expected values were read from these bytes by hand.

| Folder | Source | Pinned at |
|---|---|---|
| `website_s04/<page>/1.N.md` | [kubernetes/website](https://github.com/kubernetes/website), `content/en/docs/concepts/security/<page>.md` | `release-1.N` in the lock (`website_releases`); the file is the first release from 1.24 on with those bytes |
| `website_s04/rbac/excerpt-1.37.md` | kubernetes/website, `content/en/docs/reference/access-authn-authz/rbac.md`, lines 1–14 | `256a1f49` (1.37) |
| `website_s04/authorization/excerpt-1.37.md` | kubernetes/website, `.../access-authn-authz/authorization.md`, lines 204–339 | `256a1f49` (1.37) |
| `website_s04/authentication/excerpt-1.32.md` | kubernetes/website, `.../access-authn-authz/authentication.md`, lines 332–499 | `a6b9d383` (1.32) |
| `website_s05/release-notes/excerpt-1.20.md` | kubernetes/website, `content/en/docs/setup/release/notes.md`, lines 1–18 | `2886f437` (1.20) |
| `website_s05/release-notes/1.N.md` | kubernetes/website, `content/en/releases/notes.md` (where the page moved at 1.21) | `release-1.N` in the lock: `7ed77d72` (1.21), `80b4524c` (1.22) |
| `website_s05/redirects/excerpt-1.21.txt` | kubernetes/website, `static/_redirects`, lines 495–498 | `7ed77d72` (1.21) |
| `website_s05/feature-gates/<gate>/1.N.md` | kubernetes/website, `content/en/docs/reference/command-line-tools-reference/feature-gates/<gate>.md`, whole file: `StrictIPCIDRValidation` (1.37), `APIServingWithRoute` (1.32), `APIServingWithRoutine` (1.33), `PodInfoAPI` (1.36), `InPlacePodVerticalScalingMemoryBackedVolumes` (1.37) | The lock's website SHA for 1.N (`website_releases`): `a6b9d383` (1.32), `b9ab6105` (1.33), `1de955eb` (1.36), `256a1f49` (1.37, `main`). Each file's `git hash-object` equals the blob at that commit |
| `kep_2579/1.N.kep.yaml` | [kubernetes/enhancements](https://github.com/kubernetes/enhancements), `keps/sig-auth/2579-psp-replacement/kep.yaml` | `master` on the 1.N release date in the lock (`release_date_snapshots`) |
| `kubernetes/CHANGELOG-1.22-excerpt.md` | [kubernetes/kubernetes](https://github.com/kubernetes/kubernetes), `CHANGELOG/CHANGELOG-1.22.md`, lines 3082–3193 | `7c596ad7` |

## License

- `website_s04/` and `website_s05/`: Kubernetes documentation, © The Kubernetes Authors, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `kep_2579/` and `kubernetes/`: © The Kubernetes Authors, licensed [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), the license of the enhancements and kubernetes repos.
