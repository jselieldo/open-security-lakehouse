import io
import json
from time import perf_counter

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .metrics import INVESTIGATION_DURATION
from .schemas import InvestigationRequest, InvestigationResponse
from .storage import get_object_bytes, list_object_keys

EMPTY_COLUMNS = {
    "event_id": pa.array([], type=pa.string()),
    "source": pa.array([], type=pa.string()),
    "event_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
    "ingested_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
    "schema_name": pa.array([], type=pa.string()),
    "schema_version": pa.array([], type=pa.string()),
    "class_uid": pa.array([], type=pa.int64()),
    "severity_id": pa.array([], type=pa.int64()),
    "src_ip": pa.array([], type=pa.string()),
    "hostname": pa.array([], type=pa.string()),
    "application": pa.array([], type=pa.string()),
    "event_type": pa.array([], type=pa.string()),
    "product_name": pa.array([], type=pa.string()),
    "raw_event_json": pa.array([], type=pa.string()),
}


def investigate(request: InvestigationRequest) -> InvestigationResponse:
    started = perf_counter()
    prefix = f"normalized/source={request.source}/" if request.source else "normalized/"
    all_keys = list_object_keys(prefix)
    keys = _select_query_objects(all_keys, _load_compaction_manifests(all_keys))
    table = _load_tables(keys)
    sql, parameters = _build_query(request)
    count_sql, count_parameters = _build_count_query(request)

    with duckdb.connect(":memory:") as connection:
        connection.register("security_events", table)
        total_count = connection.execute(count_sql, count_parameters).fetchone()[0]
        result = connection.execute(sql, parameters).fetch_arrow_table()

    events = result.to_pylist()
    duration_ms = round((perf_counter() - started) * 1000, 3)
    INVESTIGATION_DURATION.observe(duration_ms / 1000)
    return InvestigationResponse(
        query_engine="duckdb",
        scanned_objects=len(keys),
        returned_count=len(events),
        total_count=total_count,
        limit=request.limit,
        offset=request.offset,
        duration_ms=duration_ms,
        events=events,
    )


def _load_compaction_manifests(keys: list[str]) -> dict[str, dict[str, object]]:
    manifests: dict[str, dict[str, object]] = {}
    for key in keys:
        if not key.endswith("/_compaction.json"):
            continue
        try:
            document = json.loads(get_object_bytes(key))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if isinstance(document, dict):
            manifests[key.rsplit("/", 1)[0]] = document
    return manifests


def _select_query_objects(
    keys: list[str], manifests: dict[str, dict[str, object]] | None = None
) -> list[str]:
    """Prefer completed compacted partitions while preserving legacy layouts."""
    manifests = manifests or {}
    parquet_by_partition: dict[str, list[str]] = {}
    for key in keys:
        if not key.endswith(".parquet"):
            continue
        parquet_by_partition.setdefault(key.rsplit("/", 1)[0], []).append(key)

    selected: list[str] = []
    for partition, objects in parquet_by_partition.items():
        manifest = manifests.get(partition, {})
        compacted = {
            str(key) for key in manifest.get("compact_objects", []) if isinstance(key, str)
        }
        sources = {
            str(key) for key in manifest.get("source_objects", []) if isinstance(key, str)
        }
        available = set(objects)
        verified_compacts = compacted & available
        if verified_compacts:
            selected.extend(verified_compacts)
            selected.extend(
                key
                for key in objects
                if "/compact=" not in key and key not in sources
            )
        else:
            selected.extend(key for key in objects if "/compact=" not in key)
    return sorted(selected)


def _load_tables(keys: list[str]) -> pa.Table:
    tables = []
    for key in keys:
        table = pq.read_table(io.BytesIO(get_object_bytes(key)))
        for name in EMPTY_COLUMNS:
            if name not in table.column_names:
                table = table.append_column(
                    name, pa.nulls(table.num_rows, type=EMPTY_COLUMNS[name].type)
                )
        tables.append(table)
    if not tables:
        return pa.table(EMPTY_COLUMNS)
    if len(tables) == 1:
        return tables[0]
    return pa.concat_tables(tables, promote_options="default")


def _build_query(request: InvestigationRequest) -> tuple[str, list[object]]:
    where, parameters = _build_filters(request)
    parameters.extend((request.limit, request.offset))
    sql = (  # noqa: S608 -- clauses are selected below; values remain parameters.
        f"""
        SELECT event_id, source, event_time, ingested_at, schema_name, schema_version,
               class_uid, severity_id, src_ip, hostname, application, event_type,
               product_name, raw_event_json
        FROM security_events
        {where}
        ORDER BY event_time DESC
        LIMIT ? OFFSET ?
    """
    )
    return sql, parameters


def _build_count_query(request: InvestigationRequest) -> tuple[str, list[object]]:
    where, parameters = _build_filters(request)
    return f"SELECT count(*) FROM security_events {where}", parameters  # noqa: S608


def _build_filters(request: InvestigationRequest) -> tuple[str, list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    for expression, value in (
        ("src_ip = ?", request.src_ip),
        ("hostname = ?", request.hostname),
        ("application = ?", request.application),
        ("event_type = ?", request.event_type),
        ("source = ?", request.source),
        ("event_time >= ?", request.start_time),
        ("event_time <= ?", request.end_time),
        ("severity_id >= ?", request.min_severity),
        ("severity_id <= ?", request.max_severity),
        (
            "raw_event_json ILIKE ?",
            f"%{request.message_contains}%" if request.message_contains else None,
        ),
    ):
        if value is not None:
            clauses.append(expression)
            parameters.append(value)

    if request.exclude_sources:
        placeholders = ", ".join("?" for _ in request.exclude_sources)
        clauses.append(f"source NOT IN ({placeholders})")
        parameters.extend(request.exclude_sources)

    if request.event_types:
        placeholders = ", ".join("?" for _ in request.event_types)
        clauses.append(f"event_type IN ({placeholders})")
        parameters.extend(request.event_types)

    if request.message_contains_any:
        clauses.append(
            "(" + " OR ".join("raw_event_json ILIKE ?" for _ in request.message_contains_any) + ")"
        )
        parameters.extend(f"%{pattern}%" for pattern in request.message_contains_any)

    if request.windows_channel and request.windows_event_id is not None:
        clauses.append("event_type = ?")
        parameters.append(
            f"windows.{request.windows_channel}.{request.windows_event_id}"
        )
    elif request.windows_channel:
        clauses.append("starts_with(event_type, ?)")
        parameters.append(f"windows.{request.windows_channel}.")
    elif request.windows_event_id is not None:
        clauses.append("starts_with(event_type, 'windows.') AND ends_with(event_type, ?)")
        parameters.append(f".{request.windows_event_id}")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, parameters
