  To activate this feature, users can set the `ENABLE_CLIENT_GO_WATCH_LIST_ALPHA` environmental variable.
  It is important to note that the server must support streaming for this feature to function properly.
  If streaming is not supported by the server, the reflector will revert to the previous method
  of obtaining data through LIST/WATCH semantics. ([#110772](https://github.com/kubernetes/kubernetes/pull/110772), [@p0lyn0mial](https://github.com/p0lyn0mial)) [SIG API Machinery]
- K8s.io/client-go/tools/record.EventBroadcaster: after Shutdown() is called, the broadcaster now gives up immediately after a failure to write an event to a sink. Previously it tried multiple times for 12 seconds in a goroutine. ([#115514](https://github.com/kubernetes/kubernetes/pull/115514), [@pohly](https://github.com/pohly)) [SIG API Machinery]
- K8s.io/component-base/logs: usage of the pflag values in a normal Go flag set led to panics when printing the help message ([#114680](https://github.com/kubernetes/kubernetes/pull/114680), [@pohly](https://github.com/pohly)) [SIG Instrumentation]
- Kubeadm: explicitly set `priority` for static pods with `priorityClassName: system-node-critical` ([#114338](https://github.com/kubernetes/kubernetes/pull/114338), [@champtar](https://github.com/champtar)) [SIG Cluster Lifecycle]
- Kubelet: a "maxParallelImagePulls" field can now be specified in the kubelet configuration file to control how many image pulls the kubelet can perform in parallel. ([#115220](https://github.com/kubernetes/kubernetes/pull/115220), [@ruiwen-zhao](https://github.com/ruiwen-zhao)) [SIG API Machinery, Node and Scalability]
- Kubelet: changed `MemoryThrottlingFactor` default value to `0.9` and formulas to calculate `memory.high` ([#115371](https://github.com/kubernetes/kubernetes/pull/115371), [@pacoxu](https://github.com/pacoxu))
- Kubernetes components that perform leader election now only support using `Leases` for this. ([#114055](https://github.com/kubernetes/kubernetes/pull/114055), [@aimuz](https://github.com/aimuz))
- Migrated the `DaemonSet` controller (within `kube-controller-manager`) to use [contextual logging](https://k8s.io/docs/concepts/cluster-administration/system-logs/#contextual-logging) ([#113622](https://github.com/kubernetes/kubernetes/pull/113622), [@249043822](https://github.com/249043822))
- New `service.kubernetes.io/topology-mode` annotation has been introduced as a replacement for the `service.kubernetes.io/topology-aware-hints` annotation.
  - `service.kubernetes.io/topology-aware-hints` annotation has been deprecated.
  - kube-proxy now accepts any value that is not "disabled" for these annotations, enabling custom implementation-specific and/or future built-in heuristics to be used. ([#116522](https://github.com/kubernetes/kubernetes/pull/116522), [@robscott](https://github.com/robscott)) [SIG Apps, Network and Testing]
- Pods owned by a Job now uses the labels `batch.kubernetes.io/job-name` and `batch.kubernetes.io/controller-uid`.
  The legacy labels `job-name` and `controller-uid` are still added for compatibility. ([#114930](https://github.com/kubernetes/kubernetes/pull/114930), [@kannon92](https://github.com/kannon92))
- Promoted `CronJobTimeZone` feature to GA ([#115904](https://github.com/kubernetes/kubernetes/pull/115904), [@soltysh](https://github.com/soltysh))
