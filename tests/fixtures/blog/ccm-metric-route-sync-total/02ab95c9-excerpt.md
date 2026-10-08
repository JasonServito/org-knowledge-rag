---
layout: blog
title: "Kubernetes v1.36: New Metric for Route Sync in the Cloud Controller Manager"
date: 2026-02-26
slug: ccm-new-metric-route-sync-total
author: >
  [Lukas Metzner](https://github.com/lukasmetzner) (Hetzner)
---

Kubernetes v1.36 introduces a new alpha counter metric `route_controller_route_sync_total`
to the Cloud Controller Manager (CCM) route controller implementation at
[`k8s.io/cloud-provider`](https://github.com/kubernetes/cloud-provider). This metric
