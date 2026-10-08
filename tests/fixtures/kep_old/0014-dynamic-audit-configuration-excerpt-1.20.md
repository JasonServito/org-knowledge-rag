---
title: Dynamic Audit Configuration
authors:
  - "@pbarker"
owning-sig: sig-auth
participating-sigs:
  - sig-api-machinery
reviewers:
  - "@tallclair"
  - "@yliaog"
  - "@caesarxuchao"
  - "@liggitt"
approvers:
  - "@tallclair"
  - "@liggitt"
  - "@yliaog"
editor: TBD
creation-date: 2018-05-18
last-updated: 2018-07-31
status: implementable
---

# Dynamic Audit Control

## Table of Contents

<!-- toc -->
- [Summary](#summary)
- [Motivation](#motivation)
  - [Goals](#goals)
  - [Non-Goals](#non-goals)
- [Proposal](#proposal)
  - [Dynamic Configuration](#dynamic-configuration)
    - [Cluster Scoped Configuration](#cluster-scoped-configuration)
  - [User Stories](#user-stories)
    - [Story 1](#story-1)
    - [Story 2](#story-2)
    - [Story 3](#story-3)
    - [Story 4](#story-4)
  - [Implementation Details/Notes/Constraints](#implementation-detailsnotesconstraints)
    - [Feature Gating](#feature-gating)
    - [Policy Enforcement](#policy-enforcement)
    - [Aggregated Servers](#aggregated-servers)
  - [Risks and Mitigations](#risks-and-mitigations)
    - [Privilege Escalation](#privilege-escalation)
    - [Leaked Resources](#leaked-resources)
    - [Webhook Authentication](#webhook-authentication)
    - [Performance](#performance)
- [Test Plan](#test-plan)
- [Graduation Criteria](#graduation-criteria)
- [Implementation History](#implementation-history)
- [Alternatives](#alternatives)
  - [Generalized Dynamic Configuration](#generalized-dynamic-configuration)
  - [Policy Override](#policy-override)
<!-- /toc -->

## Summary

We want to allow the advanced auditing features to be dynamically configured. Following in the same vein as 
[Dynamic Admission Control](https://kubernetes.io/docs/admin/extensible-admission-controllers/) we would like to provide 
a means of configuring the auditing features post cluster provisioning.
