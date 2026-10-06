### API Change

- A new score extension for NodeResourcesFit plugin that merges the functionality of NodeResourcesLeastAllocated,NodeResourcesMostAllocated,RequestedToCapacityRatio plugins, which are marked as deprecated as of v1beta2. In v1beta1, the three plugins can still be used in v1beta1 but not at the same time with the score extension of NodeResourcesFit
  ```
  
  #### Additional documentation e.g., KEPs (Kubernetes Enhancement Proposals), usage docs, etc.:
  
  <!--
  This section can be blank if this pull request does not require a release note.
  
  When adding links which point to resources within git repositories, like
  KEPs or supporting documentation, please reference a specific commit and avoid
  linking directly to the master branch. This ensures that links reference a
  specific point in time, rather than a document that may change over time.
  
  See here for guidance on getting permanent links to files: https://help.github.com/en/articles/getting-permanent-links-to-files
  
  Please use the following format for linking documentation:
  - [KEP]: <link>
  - [Usage]: <link>
  - [Other doc]: <link>
  --> ([#101822](https://github.com/kubernetes/kubernetes/pull/101822), [@yuzhiquan](https://github.com/yuzhiquan)) [SIG API Machinery, Apps, Auth, Cloud Provider, Instrumentation, Node, Scheduling, Storage and Testing]
- Add DataSourceRef alpha field to PVC spec, which allows contents other than PVCs and VolumeSnapshots to be data sources. ([#103276](https://github.com/kubernetes/kubernetes/pull/103276), [@bswartz](https://github.com/bswartz)) [SIG API Machinery, Apps and Storage]
- Add PersistentVolumeClaimDeletePoilcy to StatefulSet API. ([#99378](https://github.com/kubernetes/kubernetes/pull/99378), [@mattcary](https://github.com/mattcary)) [SIG API Machinery and Apps]
- Add distributed tracing to the kube-apiserver.  It is can be enabled with the feature gate: APIServerTracing=true ([#94942](https://github.com/kubernetes/kubernetes/pull/94942), [@dashpole](https://github.com/dashpole)) [SIG API Machinery, CLI, Cloud Provider, Cluster Lifecycle, Instrumentation, Node, Storage and Testing]
- Added new kubelet alpha feature `SeccompDefault`. This feature enables falling back to
  the `RuntimeDefault` (former `runtime/default`) seccomp profile if nothing else is specified
  in the pod/container `SecurityContext` or the pod annotation level. To use the feature, enable
  the feature gate as well as set the kubelet configuration option `SeccompDefault`
  (`--seccomp-default`) to `true`. ([#101943](https://github.com/kubernetes/kubernetes/pull/101943), [@saschagrunert](https://github.com/saschagrunert)) [SIG Node]
- Adds the ReadWriteOncePod access mode for PersistentVolumes and PersistentVolumeClaims. Restricts volume access to a single pod on a single node. ([#102028](https://github.com/kubernetes/kubernetes/pull/102028), [@chrishenzie](https://github.com/chrishenzie)) [SIG Apps, CLI, Node, Scheduling and Storage]
- Alpha swap support can now be enabled on Kubernetes nodes with the NodeSwapEnabled feature flag. See <website link> for details. ([#102823](https://github.com/kubernetes/kubernetes/pull/102823), [@ehashman](https://github.com/ehashman)) [SIG Node]
- CSIServiceAccountToken is GA. ([#103001](https://github.com/kubernetes/kubernetes/pull/103001), [@zshihang](https://github.com/zshihang)) [SIG Auth and Storage]
- Enforce the ReadWriteOncePod PVC access mode during scheduling ([#103082](https://github.com/kubernetes/kubernetes/pull/103082), [@chrishenzie](https://github.com/chrishenzie)) [SIG Apps, CLI, Node, Scheduling and Storage]
- Improved parsing of label selectors ([#102188](https://github.com/kubernetes/kubernetes/pull/102188), [@alculquicondor](https://github.com/alculquicondor)) [SIG API Machinery]
- Kube API server accepts Impersonate-Uid header to impersonate a user with a specific UID, in the same way that you can currently use Impersonate-User, Impersonate-Group and Impersonate-Extra ([#99961](https://github.com/kubernetes/kubernetes/pull/99961), [@margocrawf](https://github.com/margocrawf)) [SIG API Machinery, Auth and Testing]
- Kube-scheduler: a plugin enabled in a v1beta2 configuration file takes precedence over the default configuration for that plugin; this simplifies enabling default plugins with custom configuration without needing to explicitly disable those default plugins. ([#99582](https://github.com/kubernetes/kubernetes/pull/99582), [@chendave](https://github.com/chendave)) [SIG Scheduling]
- Scheduler could be configured  to consider new resources beside CPU and memory,  GPU for example, for the score plugin of `NodeResourcesBalancedAllocation`. ([#101946](https://github.com/kubernetes/kubernetes/pull/101946), [@chendave](https://github.com/chendave)) [SIG Scheduling]
- Suspend Job feature graduated to beta
  Added the "action" label to Job controller sync metrics job_sync_total and job_sync_duration_seconds ([#102022](https://github.com/kubernetes/kubernetes/pull/102022), [@adtac](https://github.com/adtac)) [SIG Apps, Instrumentation and Testing]
- TerminationGracePeriodSeconds on pod specs and container probes should not be negative.
  Negative values of TerminationGracePeriodSeconds will be treated as the value `1s` on the delete path.
  Immutable field validation will be relaxed in order to update negative values. 
  In a future release, negative values will not be permitted. ([#98866](https://github.com/kubernetes/kubernetes/pull/98866), [@wzshiming](https://github.com/wzshiming)) [SIG API Machinery, Apps and Node]
- The API documentation for the DaemonSet's spec.updateStrategy.rollingUpdate.maxUnavailable field was corrected to state that the value is rounded up. ([#101296](https://github.com/kubernetes/kubernetes/pull/101296), [@Miciah](https://github.com/Miciah)) [SIG Apps and CLI]
- The CertificateSigningRequest.certificates.k8s.io API supports an optional expirationSeconds field to allow the client to request a particular duration for the issued certificate.  The default signer implementations provided by the Kubernetes controller manager will honor this field as long as it does not exceed the --cluster-signing-duration flag. ([#99494](https://github.com/kubernetes/kubernetes/pull/99494), [@enj](https://github.com/enj)) [SIG API Machinery, Apps, Auth, CLI, Instrumentation, Node, Security and Testing]
- The ServiceAppProtocol feature gate has been removed. It reached GA in Kubernetes 1.20. ([#103190](https://github.com/kubernetes/kubernetes/pull/103190), [@robscott](https://github.com/robscott)) [SIG Network]

### Feature

- (alpha feature) If the CSI driver supports the NodeServiceCapability `VOLUME_MOUNT_GROUP` and the `DelegateFSGroupToCSIDriver` feature gate is enabled, kubelet will delegate applying FSGroup to the driver by passing it to NodeStageVolume and NodePublishVolume, regardless of what other FSGroup policies are set. ([#103244](https://github.com/kubernetes/kubernetes/pull/103244), [@verult](https://github.com/verult)) [SIG Apps and Storage]
- API Server tracing can now trace re-entrant api requests. ([#103218](https://github.com/kubernetes/kubernetes/pull/103218), [@dashpole](https://github.com/dashpole)) [SIG API Machinery, CLI, Cloud Provider, Cluster Lifecycle and Instrumentation]
- Add unified map on CRI to support cgroup v2. Refer to https://github.com/opencontainers/runtime-spec/blob/master/config-linux.md#unified. ([#102578](https://github.com/kubernetes/kubernetes/pull/102578), [@payall4u](https://github.com/payall4u)) [SIG Node]
- Added field-selector option for `kubectl top pod` ([#102155](https://github.com/kubernetes/kubernetes/pull/102155), [@lauchokyip](https://github.com/lauchokyip)) [SIG CLI]
- Added new metrics about API Priority and Fairness.  Each one has a label `priority_level`.  The last two also have a label `bound` taking values `min` and `max.
  - apiserver_flowcontrol_current_r: R(the time of the last change in state of the queues)
  - apiserver_flowcontrol_dispatch_r: R(the time of the latest request dispatch)
  - apiserver_flowcontrol_latest_s: S(the request last dispatched) = R(when that request starts executing in the virtual world)
  - apiserver_flowcontrol_next_s_bounds: min and max next S among non-empty queues
  - apiserver_flowcontrol_next_discounted_s_bounds: min and max next S - (sum [over requests executing] width * estimatedDuration) among non-empty queues ([#102859](https://github.com/kubernetes/kubernetes/pull/102859), [@MikeSpreitzer](https://github.com/MikeSpreitzer)) [SIG API Machinery and Instrumentation]
- Adding `--restart-kubelet` flag on E2E Node test suite ([#97028](https://github.com/kubernetes/kubernetes/pull/97028), [@knabben](https://github.com/knabben)) [SIG Node and Testing]
- Adds feature gate `KubeletInUserNamespace` which enables support for running kubelet in a user namespace.
  
  The user namespace has to be created before running kubelet.
  All the node components such as CRI need to be running in the same user namespace.
  
  When the feature gate is enabled, kubelet ignores errors that happens during setting the following sysctl values: `vm.overcommit_memory`, `vm.panic_on_oom`, `kernel.panic`, `kernel.panic_on_oops`, `kernel.keys.root_maxkeys`, `kernel.keys.root_maxbytes`. (These sysctl values for the host, not for the containers)
  
  kubelet also ignores an error during opening `/dev/kmsg`.
  This feature gate also allows kube-proxy to ignore an error during setting `RLIMIT_NOFILE`.
  
  This feature gate is especially useful for running Kubernetes inside Rootless Docker/Podman with `kind` or `minikube`. ([#92863](https://github.com/kubernetes/kubernetes/pull/92863), [@AkihiroSuda](https://github.com/AkihiroSuda)) [SIG Network, Node and Testing]
- Adds metrics for the delegated authenticator used by extension APIs that delegate authentication logic to the Kube API server. ([#99364](https://github.com/kubernetes/kubernetes/pull/99364), [@p0lyn0mial](https://github.com/p0lyn0mial)) [SIG API Machinery, Auth, Instrumentation and Node]
- Adds metrics for the delegated authorizer used by extension APIs that delegate authorization logic to the Kube API server. ([#100339](https://github.com/kubernetes/kubernetes/pull/100339), [@p0lyn0mial](https://github.com/p0lyn0mial)) [SIG API Machinery, Auth, Instrumentation and Node]
- Client-go credential plugins are now GA ([#102890](https://github.com/kubernetes/kubernetes/pull/102890), [@ankeesler](https://github.com/ankeesler)) [SIG API Machinery, Auth and Testing]
- Deprecated warning message for igonre-errors flag. ([#102677](https://github.com/kubernetes/kubernetes/pull/102677), [@yuzhiquan](https://github.com/yuzhiquan)) [SIG CLI]
- Endpoints that have more than 1000 endpoints will be truncated and the `endpoints.kubernetes.io/over-capacity` annotation on the Endpoints resource will be set to `truncated`. ([#103520](https://github.com/kubernetes/kubernetes/pull/103520), [@swetharepakula](https://github.com/swetharepakula)) [SIG Apps and Network]
- Expose `/debug/flags/v` to allow dynamically setting log level for kube-proxy. ([#98306](https://github.com/kubernetes/kubernetes/pull/98306), [@borgerli](https://github.com/borgerli)) [SIG Network]
- Expose container start time as container_start_time_seconds in kubelet /metrics/resource endpoint ([#102444](https://github.com/kubernetes/kubernetes/pull/102444), [@sanwishe](https://github.com/sanwishe)) [SIG Instrumentation, Node and Testing]
- Extended resources defined in LeastAllocated, MostAllocated and RequestedToCapacityRatio plugin argument are bypassed by the scheduler if the incoming Pod doesn't request them in the pod spec. ([#103169](https://github.com/kubernetes/kubernetes/pull/103169), [@Huang-Wei](https://github.com/Huang-Wei)) [SIG Scheduling]
- Features gates `EndpointSliceProxying` & `WindowsEndpointSliceProxying` are now GA and cannot be disabled. Kube-proxy will use EndpointSlices for endpoint information. ([#103451](https://github.com/kubernetes/kubernetes/pull/103451), [@swetharepakula](https://github.com/swetharepakula)) [SIG Network]
- IngressClassNamespacedParams feature gate has graduated to beta and is enabled by default. This means IngressClass resource will now have two new fields - `spec.paramters.namespace` and `spec.parameters.scope`. ([#101711](https://github.com/kubernetes/kubernetes/pull/101711), [@hbagdi](https://github.com/hbagdi)) [SIG Network]
- JSON logging format is no longer available by default in non-core Kubernetes Components and require owners to opt in. ([#102869](https://github.com/kubernetes/kubernetes/pull/102869), [@mengjiao-liu](https://github.com/mengjiao-liu)) [SIG API Machinery, Cluster Lifecycle and Instrumentation]
- Kube-apiserver: the alpha PodSecurity feature can be enabled by passing `--feature-gates=PodSecurity=true`, and enables controlling allowed pods using namespace labels. See https://git.k8s.io/enhancements/keps/sig-auth/2579-psp-replacement for more details. ([#103099](https://github.com/kubernetes/kubernetes/pull/103099), [@liggitt](https://github.com/liggitt)) [SIG API Machinery, Auth, Instrumentation, Release, Security and Testing]
- Kube-proxy uses V1 EndpointSlices. ([#103306](https://github.com/kubernetes/kubernetes/pull/103306), [@swetharepakula](https://github.com/swetharepakula)) [SIG Network]
- LogarithmicScaleDown is now Beta and enabled by default ([#101767](https://github.com/kubernetes/kubernetes/pull/101767), [@damemi](https://github.com/damemi)) [SIG Apps and Instrumentation]
- Make kubectl command headers default for beta. ([#103238](https://github.com/kubernetes/kubernetes/pull/103238), [@seans3](https://github.com/seans3)) [SIG CLI]
- Mark net.ipv4.ip_unprivileged_port_start as safe sysctl ([#103326](https://github.com/kubernetes/kubernetes/pull/103326), [@pacoxu](https://github.com/pacoxu)) [SIG Auth, Network, Node and Security]
- Move the memory manager feature to the beta that will make it enabled by default with the None policy. ([#101947](https://github.com/kubernetes/kubernetes/pull/101947), [@cynepco3hahue](https://github.com/cynepco3hahue)) [SIG Node and Testing]
- Promote the ServiceInternalTrafficPolicy feature to beta, which enables the internalTrafficPolicy field of Service by default. ([#103462](https://github.com/kubernetes/kubernetes/pull/103462), [@andrewsykim](https://github.com/andrewsykim)) [SIG Apps and Network]
- Promote the feature ServiceLBNodePortControl to Beta ([#100412](https://github.com/kubernetes/kubernetes/pull/100412), [@hanlins](https://github.com/hanlins)) [SIG API Machinery, Apps, Architecture, Network and Testing]
- Scheduler nows provides an option for plugin developers to move Pods to activeQ proactively. ([#103383](https://github.com/kubernetes/kubernetes/pull/103383), [@Huang-Wei](https://github.com/Huang-Wei)) [SIG Scheduling and Testing]
- Services with `externalTrafficPolicy: Local` now support graceful termination when using
  the iptables or ipvs mode of kube-proxy with EndpointSlices enabled. Specifically, if a
  connection for such a service arrives on a node when there are no "Ready" endpoints
  for the service, but there is at least one Terminating pod for that service on the node,
  then kube-proxy will send the traffic to the Terminating pod rather than dropping it. This
  patches up a race condition between when a pod is killed and when the external load
  balancer notices that it has been killed. ([#97238](https://github.com/kubernetes/kubernetes/pull/97238), [@andrewsykim](https://github.com/andrewsykim)) [SIG Network, Scalability and Windows]
- Shell completion has been migrated to Cobra's go solution.  `kubectl` is now smarter about disabling file completion when it does not apply.  Furthermore, completion for the `cp` command does not show all files unless the user has started typing something. ([#96087](https://github.com/kubernetes/kubernetes/pull/96087), [@marckhouzam](https://github.com/marckhouzam)) [SIG CLI]
- The `HugePageStorageMediumSize` feature has been promoted to GA, allowing unconditional usage of multiple sizes huge page resources on a container level. ([#99144](https://github.com/kubernetes/kubernetes/pull/99144), [@bart0sh](https://github.com/bart0sh)) [SIG Apps, Node and Storage]
- Update the system-validators library to v1.5.0. Includes validation for seccomp and fixes a stdout/stderr problem in the Docker validator. ([#103390](https://github.com/kubernetes/kubernetes/pull/103390), [@ironyman](https://github.com/ironyman)) [SIG Cluster Lifecycle]
- Updates the following images to pick up CVE fixes:
  - `debian` to v1.8.0
  - `debian-iptables` to v1.6.5
  - `setcap` to v2.0.3 ([#103235](https://github.com/kubernetes/kubernetes/pull/103235), [@thejoycekung](https://github.com/thejoycekung)) [SIG API Machinery, Release and Testing]
- `kubectl debug` is able to create ephemeral containers in pre-1.22 clusters with the `EphemeralContainers` feature enabled. Note that versions of kubectl prior to 1.22 are unable to create ephemeral containers in clusters version 1.22 and greater due to an API change. ([#103292](https://github.com/kubernetes/kubernetes/pull/103292), [@verb](https://github.com/verb)) [SIG CLI]

### Documentation

- `kubectl debug` will now print a warning message when using the `--target` option since many container runtimes do not support this yet. ([#101074](https://github.com/kubernetes/kubernetes/pull/101074), [@verb](https://github.com/verb)) [SIG CLI]

