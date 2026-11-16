from prometheus_client import Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "osl_http_requests_total",
    "HTTP requests handled by the OSL API",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "osl_http_request_duration_seconds",
    "OSL API request duration",
    ["method", "route"],
)
INGESTION_BATCHES = Counter(
    "osl_ingestion_batches_total",
    "Ingestion batch outcomes",
    ["source", "status"],
)
INGESTION_EVENTS = Counter(
    "osl_ingestion_events_total",
    "Events processed by ingestion",
    ["source", "outcome"],
)
INGESTION_DURATION = Histogram(
    "osl_ingestion_duration_seconds",
    "Time required to persist an ingestion batch",
    ["source"],
)
INVESTIGATION_DURATION = Histogram(
    "osl_investigation_duration_seconds",
    "DuckDB investigation duration",
)
DETECTION_RUNS = Counter(
    "osl_detection_runs_total",
    "Detection execution outcomes",
    ["rule_id", "status"],
)
DETECTION_DURATION = Histogram(
    "osl_detection_duration_seconds",
    "Detection execution duration",
    ["rule_id"],
)
DEPENDENCY_UP = Gauge(
    "osl_dependency_up",
    "Whether an API dependency is healthy",
    ["dependency"],
)
LAKE_OBJECTS = Gauge(
    "osl_lake_objects",
    "Objects stored in the security lake",
    ["area"],
)
LAKE_BYTES = Gauge(
    "osl_lake_bytes",
    "Bytes stored in the security lake",
    ["area"],
)
METRICS_REFRESH_FAILURES = Counter(
    "osl_metrics_refresh_failures_total",
    "Failures while refreshing storage metrics",
)


def render_metrics(storage_stats: dict[str, tuple[int, int]] | None = None) -> bytes:
    if storage_stats is not None:
        for area, (objects, size_bytes) in storage_stats.items():
            LAKE_OBJECTS.labels(area=area).set(objects)
            LAKE_BYTES.labels(area=area).set(size_bytes)
    return generate_latest()
