# S06-T5 spot-check sheet

Generated from `eval/candidates/v0-draft.yaml` and the dev database. Each excerpt is copied
from the stored chunk text by a script (not retyped). Releases are `[from–until]`; blank until = still current.

For each question, check: (1) the question is clear, (2) the expected answer is right,
(3) the excerpts support it. Mark ✅ or write what's wrong.

## q40 · CURRENT

**Question:** Is kube-proxy's ipvs mode still supported, and what should I use instead?

**Expected answer:** It is deprecated (since v1.35). In v1.37 it still works behind the KubeProxyIPVS gate (on by default); it will be disabled by default in v1.40 and removed in v1.43. Use nftables mode (or iptables on kernels too old for nftables).

- `web:/docs/reference/networking/virtual-ips/` › `Proxy modes > IPVS proxy mode`
  - releases [37–]: …ion="v1.35" state="deprecated" >}} This proxy mode is only available on Linux nodes. The ipvs proxy mode is deprecated. Support for ipvs mode will be disabled by default from Kubernetes v1.40 (you can re-enable it with the KubeProxyIPVS [feature gate](/docs/reference/command-line-tools-reference/feature-gates/)); ipvs mode will be fully removed in Kubernetes v1.43. In ipvs mode…
- `gate:KubeProxyIPVS`
  - (comment paraphrases; the section's newest text) releases [37–]: stages: - stage: deprecated   defaultValue: true   fromVersion: '1.37'  Enable support for the deprecated [`ipvs` proxy mode](/docs/reference/networking/virtual-ips/#proxy-mode-ipvs) in kube-proxy.…
- `changelog:1.35` › `v1.35.0 > Changes by Kind > Deprecation`
  - releases [35–35]: …ed state. ([#134298](https://github.com/kubernetes/kubernetes/pull/134298), [@kannon92](https://github.com/kannon92)) - Marked ipvs mode in kube-proxy as deprecated, which will be removed in a future version of Kubernetes. Users are encouraged to migrate to nftables. ([#134539](https://github.com/kubernetes/kubernetes/pull/134539), [@adrianmoisey](https://github.com/adrianmoise…
- `web:/blog/2026/08/26/kubernetes-v1-37-release/` › `Deprecations, removals and community updates > Deprecating `kube-proxy`'s support for `ipvs` mode`
  - releases [37–]: …: ipvs in KubeProxyConfiguration) now log a deprecation warning on startup. The deprecation timeline looks like this: - By v1.40, ipvs mode for kube-proxy is expected to be disabled by default (still selectable via the feature gate) - By v1.43, support for ipvs mode would be removed entirely [KEP #5495, Graduation Criteria](https://github.com/kubernetes/enhancements/blob/master…
- `changelog:1.37` › `v1.37.0 > Changes by Kind > Deprecation`
  - releases [37–37]: …@yongruilin](https://github.com/yongruilin)) [SIG API Machinery] - kubeadm: Added a (delayed) warning that kube-proxy's ipvs mode is deprecated since v1.35 and users on newer Linux kernels should be using the nftables mode instead, which became GA in v1.33. For older kernel versions, users can use iptables, which is still the default. ([#139067](https://github.com/kubernetes/ku…
- `web:/blog/2025/12/17/kubernetes-v1-35-release/` › `Graduations, deprecations, and removals in v1.35 > Deprecations, removals and community updates > Deprecation of ipvs mode in kube-proxy`
  - releases [36–]: …th evolving networking requirements created too much technical debt and complexity. Because of this maintenance burden, Kubernetes v1.35 deprecates ipvs mode. Although the mode remains available in this release, kube-proxy will now emit a warning on startup when configured to use it. The goal is to streamline the codebase and focus on modern standards. For Linux nodes, you shou…
- `kep:5495` › `KEP-5495: Deprecate IPVS mode in kube-proxy > Design Details > Graduation Criteria > Stage 3 (1.40)`
  - (comment paraphrases; the section's newest text) releases [36–]: - The feature gate is flipped to `Default: false`, and the docs   updated. (If you try to run kube-proxy in `ipvs` mode without   overriding the feature gate, kube-proxy will exit with an error   listing the valid modes (`iptables` and `nftables`).)…
- `kep:5495` › `KEP-5495: Deprecate IPVS mode in kube-proxy > Design Details > Graduation Criteria > Stage 4 (1.43)`
  - (comment paraphrases; the section's newest text) releases [36–]: - The feature gate is flipped to `LockToDefault: false` and   `pkg/proxy/ipvs` is removed. Remaining mentions of IPVS mode in the   docs are removed.…

Your verdict: ✅ (developer, 2026-10-08)

---

## q24 · HISTORY

**Question:** Which container image registry did Kubernetes use by default before v1.25?

**Expected answer:** k8s.gcr.io. From v1.25 the default is registry.k8s.io, and the new default was backported to the 1.22-1.24 patch releases from December 2022.

**Release range asked about:** {'until': '1.24'}

- `web:/blog/2022/11/28/registry-k8s-io-faster-cheaper-ga/` › `(intro, before the first heading)`
  - releases [30–]: ….k8s.io: faster, cheaper and Generally Available (GA) Document: web:/blog/2022/11/28/registry-k8s-io-faster-cheaper-ga/ Starting with Kubernetes 1.25, our container image registry has changed from k8s.gcr.io to [registry.k8s.io](https://registry.k8s.io). This new registry spreads the load across multiple Cloud Providers & Regions, functioning as a sort of content delivery netwo…
- `kep:3720` › `KEP-3720: Freeze `k8s.gcr.io` image registry > Motivation`
  - releases [26–]: …cr.io to registry.k8s.io but it didn't [work out](https://kubernetes.slack.com/archives/CCK68P2Q2/p1666725317568709) so we backported the image registry defaults to 1.24, 1.23, and 1.22 so all the patch releases from December 2022 will using the new registry by default. We are currently exceeding our budget as it will take quite a while for end users to upgrade Kubernetes to v1…
- `changelog:1.24` › `v1.24.9 > Changes by Kind > Feature`
  - releases [24–24]: …Source: releaserecord Title: CHANGELOG-1.24 Document: changelog:1.24 Section: v1.24.9 > Changes by Kind > Feature - Kubeadm: use the image registry registry.k8s.io instead of k8s.gcr.io for new clusters. During upgrade, migrate users to registry.k8s.io if they were using the default of k8s.gcr.io. ([#113395](https://github.com/kubernetes/kubernetes/pull/113395), [@neolit123…
- `changelog:1.23` › `v1.23.15 > Changes by Kind > Feature`
  - (comment paraphrases; the section's newest text) releases [23–23]: - Kubeadm: use the image registry registry.k8s.io instead of k8s.gcr.io for new clusters. During upgrade, migrate users to registry.k8s.io if they were using the default of k8s.gcr.io. ([#113393](https://github.com/kubernetes/kubernetes/pull/113393), [@neolit123](https://github.com/neolit123)) [SIG Cluster Lifecycle]…
- `changelog:1.22` › `v1.22.17 > Changes by Kind > Feature`
  - (comment paraphrases; the section's newest text) releases [22–22]: - Kubeadm: use the image registry registry.k8s.io instead of k8s.gcr.io for new clusters. During upgrade, migrate users to registry.k8s.io if they were using the default of k8s.gcr.io. ([#113388](https://github.com/kubernetes/kubernetes/pull/113388), [@neolit123](https://github.com/neolit123)) [SIG Cluster Lifecycle]…
- `web:/blog/2022/11/28/registry-k8s-io-faster-cheaper-ga/` › `TL;DR: What you need to know about this change`
  - releases [30–]: …25</del> 1.27 onward are not published to k8s.gcr.io, only to registry.k8s.io. In the upcoming December patch releases, the new registry domain default will be backported to all branches still in support (1.22, 1.23, 1.24). If you run in a restricted environment and apply strict domain/IP address access policies limited to k8s.gcr.io, the image pulls will not function after the…
- `changelog:1.25` › `v1.25.0 > What's New (Major Themes) > Moved container registry service from k8s.gcr.io to registry.k8s.io`
  - (comment paraphrases; the section's newest text) releases [25–25]: [Moving container registry from k8s.gcr.io to registry.k8s.io](https://github.com/kubernetes/kubernetes/pull/109938) got merged. For more details, see the [wiki page](https://github.com/kubernetes/k8s.io/wiki/New-Registry-url-for-Kubernetes-\(registry.k8s.io\)), [announcement](https://groups.google.com/a/kubernetes.io/g/dev/c/DYZYNQ_A6_c/m/oD9_Q8Q9AAAJ) was sent to the kubernet…
- `web:/blog/2022/08/23/kubernetes-v1-25-release/` › `What's New (Major Themes) > Moved container registry service from k8s.gcr.io to registry.k8s.io`
  - (comment paraphrases; the section's newest text) releases [36–]: [Moving container registry from k8s.gcr.io to registry.k8s.io](https://github.com/kubernetes/kubernetes/pull/109938) got merged. For more details, see the [wiki page](https://github.com/kubernetes/k8s.io/wiki/New-Registry-url-for-Kubernetes-\(registry.k8s.io\)), [announcement](https://groups.google.com/a/kubernetes.io/g/dev/c/DYZYNQ_A6_c/m/oD9_Q8Q9AAAJ) was sent to the kubernet…

Your verdict: ✅ (developer, 2026-10-08)

---

## q18 · CHANGE

**Question:** What are the release stages of strict IP/CIDR validation (KEP-4858)?

**Expected answer:** Alpha in v1.33 (off by default), beta in v1.36 (on by default); still beta as of v1.37. Conflict: KEP-4858's latest version claims implemented/stable, but the gate and the KEP's Implementation History stop at beta.

- `kep:4858` › `KEP-4858: IP/CIDR Validation Improvements > Implementation History`
  - releases [37–]: …ovements > Implementation History - 2024-01-01: Proposed as a PR ([kubernetes #122550]) - 2024-10-02: Proposed as a KEP - 2025-04-25: Alpha in Kubernetes v1.33 - 2026-04-22: Beta in Kubernetes v1.36…
- `gate:StrictIPCIDRValidation`
  - releases [36–]: …Source: featuregatereference Title: StrictIPCIDRValidation Document: gate:StrictIPCIDRValidation stages: - stage: alpha defaultValue: false fromVersion: '1.33' toVersion: '1.35' - stage: beta defaultValue: true fromVersion: '1.36' Use stricter validation for fields containing IP addresses and CIDR values. In particular, with this feature gate enabled, octets within…
- `web:/blog/2026/04/22/kubernetes-v1-36-release/` › `New features in Beta > IP/CIDR validation improvements`
  - releases [36–]: …ocument: web:/blog/2026/04/22/kubernetes-v1-36-release/ Section: New features in Beta > IP/CIDR validation improvements In Kubernetes v1.36, the StrictIPCIDRValidation feature for API IP and CIDR fields graduates to beta, tightening validation to catch malformed addresses and prefixes that previously slipped through. This helps prevent subtle configuration bugs where Services, …
- `changelog:1.36` › `v1.36.0 > Changes by Kind > API Change`
  - releases [36–36]: …Source: releaserecord Title: CHANGELOG-1.36 Document: changelog:1.36 Section: v1.36.0 > Changes by Kind > API Change - The StrictIPCIDRValidation feature gate in kube-apiserver is enabled by default, meaning that API fields no longer allow IP or CIDR values with extraneous leading "0"s (e.g., 010.000.000.005 rather than 10.0.0.5) or CIDR subnet/mask values with ambiguous seman…

Your verdict: ✅ (developer, 2026-10-08)

---

## q19 · WHY

**Question:** Why did Kubernetes tighten validation of IP addresses and CIDRs in API fields?

**Expected answer:** Lax parsing accepted ambiguous strings (leading-zero IPv4 octets, IPv4-mapped IPv6, ambiguous CIDRs) that different components can read as different IPs, which can let values slip past IP-range checks (CVE-2021-29923). Go 1.17 changed its parsing to avoid that CVE, and Kubernetes made its API validation stricter too.

- `kep:4858` › `KEP-4858: IP/CIDR Validation Improvements > Summary`
  - releases [37–]: …cepting any string accepted by the underlying functions (net.ParseIP and net.ParseCIDR) even though in some cases these strings had ambiguous meanings that could lead to security problems. After [golang 1.17 changed the handling of IP addresses with leading "0"s] to avoid [CVE-2021-29923], there was consensus that we should eventually update API validation to be stricter as wel…
- `gate:StrictIPCIDRValidation`
  - releases [36–]: … addresses are not allowed to have any leading 0s, and IPv4-mapped IPv6 values (e.g. ::ffff:192.168.0.1) are forbidden. These sorts of values can potentially cause security problems when different components interpret the same string as referring to different IP addresses (as in CVE-2021-29923). This tightening applies only to fields in build-in API kinds, and not to custom res…
- `kep:4858` › `KEP-4858: IP/CIDR Validation Improvements > Proposal > Updated IP/CIDR validity criteria`
  - releases [37–]: …th this is that they parse these by simply ignoring the extra "0"s (i.e., parsing "012.000.001.002" as "12.0.1.2"), but most libc-based code treats the octets as octal in this case (i.e., parsing it as "10.0.1.2"). If such an IP address is validated in golang code but then the original string is passed to something libc-based, this may allow bypassing checks on the IP range by …
- `changelog:1.33` › `v1.33.0 > Changes by Kind > API Change`
  - releases [33–33]: …ally cause security problems when different components interpret the same string as referring to different IP addresses (as in CVE-2021-29923). This tightening applies only to fields in built-in API kinds, and not to custom resource kinds, values in Kubernetes configuration files, or command-line arguments. (When the feature gate is disabled, creating an object with such an inv…

Your verdict: ✅ (developer, 2026-10-08)

---

## q48 · UNANSWERABLE

**Question:** In which Kubernetes release will StrictIPCIDRValidation graduate to GA?

**Expected answer:** Insufficient evidence. The feature gate is beta (on by default) from v1.36; KEP-4858's latest version claims implemented/stable, but no stored text names the release where it goes GA.

**Labels:** none (should refuse). Why it's unanswerable, per the draft:

> Checked 2026-10-08: 0 chunks mention strict IP validation or 4858 together with 1.38/1.39.
> A trap: the KEP's claim line (seen by the model) says implemented/stable; only its milestone
> v1.38 (metadata) is unseen. The original research
> said "GA planned 1.38" from an unstored issue. Tests refusing to guess a future release.


Your verdict: ✅ (developer, 2026-10-08)

---

## q21 · CURRENT

**Question:** How long does a Kubernetes minor release receive patch support?

**Expected answer:** About 14 months: a 12-month standard period, then a 2-month maintenance mode (CVEs, dependency issues, critical core fixes only), then end of life.

- `web:/releases/patch-releases/` › `Support Period`
  - releases [31–]: …ses/ Section: Support Period In accordance with the [yearly support KEP][yearly-support], the Kubernetes Community will support active patch release series for a period of roughly fourteen (14) months. The first twelve months of this timeframe will be considered the standard period. Towards the end of the twelve month, the following will happen: - [Release Managers][release-man…
- `kep:1498` › `Kubernetes Yearly Support Period > Proposal`
  - releases [22–]: …s Yearly Support Period > Proposal The proposal is to extend the Kubernetes support cadence from 9 months to 14 months. The 14 months proposed here is essentially 12 months of support and 2 months of upgrade period. NOTE: This follows and formalizes today’s practice of retaining patch branch CI for 6-7 weeks beyond the 9 months intended support phase as a failsafe option if any…
- `sig-release:release-engineering/versioning.md` › `Kubernetes Release Versioning > Release versioning > Supported releases and component skew`
  - releases [36–]: …ve some time ago)". With minor releases happening approximately every four months (three releases per year), that means a minor release is supported for approximately fourteen months.…

Your verdict: ✅ (developer, 2026-10-08)

---
