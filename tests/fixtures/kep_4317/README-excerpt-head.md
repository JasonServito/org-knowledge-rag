### Graduation Criteria

For Alpha:
* The feature will be gated behind feature flags and alpha API enablement.
* Interested users can experiment with the feature using a local Kubernetes
  distribution such as kind.
* Interested platform providers can experiment with integrating the feature into
  their environment.

For Beta:
* Add e2e test to exercise the feature end-to-end
* Implement out-of-tree signers for several scenarios to prove that the feature
  is sufficient for real use cases. These scenarios should include issuing of:
  - serving certificates
  - issuing client certificates
  - SPIFFE certificates (?)
  [mesh-examples](https://github.com/ahmedtd/mesh-example).
* Migrate kubelet implementation to use the beta API.
* Deprecate and remove the alpha API.

For GA:
* The `PKIXPublicKey` and `ProofOfPossession` fields, which have been marked as
  deprecated in beta, will not be promoted to v1. They will remain on the
  v1beta1 API until it is removed.
* Allow time for feedback (wait at least two releases in Beta) with no major
  bugs or regressions reported.
* Ensure all e2e tests related to the feature are stable and flake-free, and
  promote the e2e tests (`test/e2e/auth/projected_podcertificate.go`) to
  conformance.
* Official user-facing documentation is updated to reflect GA status.

<!--
**Note:** *Not required until targeted at a release.*

Define graduation milestones.

These may be defined in terms of API maturity, [feature gate] graduations, or as
something else. The KEP should keep this high-level with a focus on what
signals will be looked at to determine graduation.

Consider the following in developing the graduation criteria for this enhancement:
- [Maturity levels (`alpha`, `beta`, `stable`)][maturity-levels]
- [Feature gate][feature gate] lifecycle
- [Deprecation policy][deprecation-policy]

Clearly define what graduation means by either linking to the [API doc
definition](https://kubernetes.io/docs/concepts/overview/kubernetes-api/#api-versioning)
or by redefining what graduation means.

In general we try to use the same stages (alpha, beta, GA), regardless of how the
functionality is accessed.

[feature gate]: https://git.k8s.io/community/contributors/devel/sig-architecture/feature-gates.md
[maturity-levels]: https://git.k8s.io/community/contributors/devel/sig-architecture/api_changes.md#alpha-beta-and-stable-versions
[deprecation-policy]: https://kubernetes.io/docs/reference/using-api/deprecation-policy/

Below are some examples to consider, in addition to the aforementioned [maturity levels][maturity-levels].

#### Alpha

- Feature implemented behind a feature flag
- Initial e2e tests completed and enabled

#### Beta

- Gather feedback from developers and surveys
- Complete features A, B, C
- Additional tests are in Testgrid and linked in KEP

#### GA

- N examples of real-world usage
- N installs
- More rigorous forms of testing—e.g., downgrade tests and scalability tests
- Allowing time for feedback

**Note:** Generally we also wait at least two releases between beta and
GA/stable, because there's no opportunity for user feedback, or even bug reports,
in back-to-back releases.

**For non-optional features moving to GA, the graduation criteria must include
[conformance tests].**

[conformance tests]: https://git.k8s.io/community/contributors/devel/sig-architecture/conformance-tests.md

#### Deprecation

- Announce deprecation and support policy of the existing flag
- Two versions passed since introducing the functionality that deprecates the flag (to address version skew)
- Address feedback on usage/changed behavior, provided on GitHub issues
- Deprecate the flag
-->

### Upgrade / Downgrade Strategy
