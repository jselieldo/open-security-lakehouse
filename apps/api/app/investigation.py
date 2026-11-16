import io
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
    "product_name": pa.array([], type=pa.string()),
    "raw_event_json": pa.array([], type=pa.string()),
}


def investigate(request: InvestigationRequest) -> InvestigationResponse:
    started = perf_counter()
    prefix = f"normalized/source={request.source}/" if request.source else "normalized/"
    keys = [key for key in list_object_keys(prefix) if key.endswith(".parquet")]
    table = _load_tables(keys)
    sql, parameters = _build_query(request)

    with duckdb.connect(":memory:") as connection:
        connection.register("security_events", table)
        result = connection.execute(sql, parameters).fetch_arrow_table()

    events = result.to_pylist()
    duration_ms = round((perf_counter() - started) * 1000, 3)
    INVESTIGATION_DURATION.observe(duration_ms / 1000)
    return InvestigationResponse(
        query_engine="duckdb",
        scanned_objects=len(keys),
        returned_count=len(events),
        duration_ms=duration_ms,
        events=events,
    )


def _load_tables(keys: list[str]) -> pa.Table:
    tables = [pq.read_table(io.BytesIO(get_object_bytes(key))) for key in keys]
    if not tables:
        return pa.table(EMPTY_COLUMNS)
    if len(tables) == 1:
        return tables[0]
    return pa.concat_tables(tables, promote_options="default")


def _build_query(request: InvestigationRequest) -> tuple[str, list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    for expression, value in (
        ("src_ip = ?", request.src_ip),
        ("source = ?", request.source),
        ("event_time >= ?", request.start_time),
        ("event_time <= ?", request.end_time),
        ("severity_id >= ?", request.min_severity),
        ("severity_id <= ?", request.max_severity),
    ):
        if value is not None:
            clauses.append(expression)
            parameters.append(value)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    parameters.append(request.limit)
    sql = (  # noqa: S608 -- clauses are selected above; values remain parameters.
        f"""
        SELECT event_id, source, event_time, ingested_at, schema_name, schema_version,
               class_uid, severity_id, src_ip, product_name, raw_event_json
        FROM security_events
        {where}
        ORDER BY event_time DESC
        LIMIT ?
    """
    )
    return sql, parameters
