# ADR 0001: SeaweedFS for Milestone 1 object storage

- Status: accepted
- Date: 2026-11-15

## Context

The project requires self-hosted, open-source, S3-compatible storage with a modest footprint on a 16 GB Linux host. The application must remain portable to a distributed corporate deployment.

## Decision

Use SeaweedFS 3.80 for Milestone 1. SeaweedFS is distributed under Apache License 2.0. The API depends only on the S3 protocol, not SeaweedFS-specific APIs.

## Consequences

The local topology is intentionally single-host and is not highly available. Production evolution may use a multi-node SeaweedFS deployment or replace it with Ceph; compatibility, consistency, backup, access policy, and load testing remain required before production use.

