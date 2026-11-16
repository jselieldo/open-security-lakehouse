#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${OSL_API_PORT:-8000}}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:${PROMETHEUS_PORT:-9090}}"
GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:${GRAFANA_PORT:-3000}}"
: "${GRAFANA_ADMIN_USER:?Set GRAFANA_ADMIN_USER}"
: "${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD}"

api_metrics=$(curl --fail --silent --show-error "$API_URL/metrics")
targets=$(curl --fail --silent --show-error "$PROMETHEUS_URL/api/v1/targets")
rules=$(curl --fail --silent --show-error "$PROMETHEUS_URL/api/v1/rules")
dashboard=$(curl --fail --silent --show-error \
  --user "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD" \
  "$GRAFANA_URL/api/dashboards/uid/osl-operations")

API_METRICS="$api_metrics" TARGETS="$targets" RULES="$rules" DASHBOARD="$dashboard" python3 - <<'PY'
import json
import os

metrics = os.environ["API_METRICS"]
targets = json.loads(os.environ["TARGETS"])["data"]["activeTargets"]
rules = json.loads(os.environ["RULES"])["data"]["groups"]
dashboard = json.loads(os.environ["DASHBOARD"])["dashboard"]

assert "osl_ingestion_events_total" in metrics
assert "osl_lake_bytes" in metrics
health = {item["labels"]["job"]: item["health"] for item in targets}
assert health.get("osl-api") == "up", health
assert health.get("vector") == "up", health
alert_names = {
    rule["name"]
    for group in rules
    for rule in group["rules"]
    if rule["type"] == "alerting"
}
assert {"OSLComponentDown", "OSLIngestionFailure", "VectorDroppedEvents"} <= alert_names
assert dashboard["uid"] == "osl-operations"
assert len(dashboard["panels"]) >= 10
print(
    f"Milestone 8 smoke test passed: {len(health)} targets, "
    f"{len(alert_names)} alert rules and {len(dashboard['panels'])} dashboard panels."
)
PY
