# ADR 0004: Prometheus and Grafana observability

## Status

Accepted for Milestone 8.

## Decision

Use Prometheus 3.13.0 LTS for metric collection, time-series retention, and operational rule evaluation. Use Grafana OSS 13.2.1 for visualization. The Python API uses the official Prometheus client 0.26.0, and Vector exposes its internal metrics through its Prometheus exporter sink.

Prometheus retains a maximum of 15 days or 2 GB to fit the 16 GB single-host homelab. Grafana datasource and dashboards, plus Prometheus scrape and alert rules, are provisioned from version-controlled files. Ports 9090 and 3000 bind to loopback and are reached remotely through SSH forwarding.

## Consequences

The platform can now measure throughput, quarantine, latency, health, event-flow failures, and lake growth. Prometheus rules expose pending and firing states but do not send notifications; Alertmanager and notification routing remain a separate concern. The `/metrics` endpoint is intentionally unauthenticated but reachable only inside the Compose network or through the loopback-bound API port.

## Licenses

- Prometheus 3.13.0 LTS: Apache License 2.0.
- Prometheus Python client 0.26.0: Apache-2.0 and BSD-2-Clause.
- Grafana OSS 13.2.1: GNU Affero General Public License v3.0.
