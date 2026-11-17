import io
import json
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import IngestionBatch
from .metrics import INGESTION_BATCHES, INGESTION_DURATION, INGESTION_EVENTS
from .normalization import normalize_events
from .schemas import BatchStatusResponse, IngestionRequest, IngestionResponse
from .sources import record_source_batch
from .storage import put_object


def ingest_batch(payload: IngestionRequest, db: Session) -> IngestionResponse:
    started = perf_counter()
    payload_hash = _payload_hash(payload)
    existing = db.get(IngestionBatch, payload.batch_id)
    if existing:
        if existing.source != payload.source or existing.payload_hash != payload_hash:
            raise BatchConflictError("batch_id was already used with different content")
        INGESTION_BATCHES.labels(source=payload.source, status="replayed").inc()
        return _response(existing, idempotent_replay=True)

    if len(payload.events) > get_settings().max_batch_events:
        raise BatchTooLargeError(get_settings().max_batch_events)

    now = datetime.now(UTC)
    prefix = f"year={now:%Y}/month={now:%m}/day={now:%d}"
    raw_key = f"raw/{payload.source}/{prefix}/batch={payload.batch_id}.json"
    normalized_key = f"normalized/source={payload.source}/{prefix}/batch={payload.batch_id}.parquet"
    quarantine_key = (
        f"quarantine/invalid-events/{payload.source}/{prefix}/batch={payload.batch_id}.json"
    )

    batch = IngestionBatch(
        batch_id=payload.batch_id,
        source=payload.source,
        payload_hash=payload_hash,
        status="processing",
        received_count=len(payload.events),
        raw_object_key=raw_key,
    )
    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.get(IngestionBatch, payload.batch_id)
        if (
            concurrent
            and concurrent.source == payload.source
            and concurrent.payload_hash == payload_hash
        ):
            return _response(concurrent, idempotent_replay=True)
        raise BatchConflictError("batch_id was already used with different content") from None

    raw_document = {
        "batch_id": payload.batch_id,
        "source": payload.source,
        "ingested_at": now.isoformat(),
        "events": payload.events,
    }

    try:
        put_object(raw_key, _json_bytes(raw_document), "application/json")
        normalized, rejected = normalize_events(payload.source, payload.events, now)

        if normalized:
            put_object(normalized_key, _parquet_bytes(normalized), "application/vnd.apache.parquet")
            batch.normalized_object_key = normalized_key
        if rejected:
            quarantine_document = {
                "batch_id": payload.batch_id,
                "source": payload.source,
                "rejected_at": now.isoformat(),
                "events": rejected,
            }
            put_object(quarantine_key, _json_bytes(quarantine_document), "application/json")
            batch.quarantine_object_key = quarantine_key

        batch.accepted_count = len(normalized)
        batch.rejected_count = len(rejected)
        batch.status = "completed" if normalized else "quarantined"
        batch.completed_at = datetime.now(UTC)
        record_source_batch(payload.source, payload.events, len(normalized), len(rejected), db)
        db.commit()
        db.refresh(batch)
        INGESTION_BATCHES.labels(source=payload.source, status=batch.status).inc()
        INGESTION_EVENTS.labels(source=payload.source, outcome="accepted").inc(len(normalized))
        INGESTION_EVENTS.labels(source=payload.source, outcome="quarantined").inc(len(rejected))
        INGESTION_DURATION.labels(source=payload.source).observe(perf_counter() - started)
        return _response(batch)
    except Exception as exc:
        batch.status = "failed"
        batch.error_message = type(exc).__name__
        batch.completed_at = datetime.now(UTC)
        db.commit()
        INGESTION_BATCHES.labels(source=payload.source, status="failed").inc()
        INGESTION_DURATION.labels(source=payload.source).observe(perf_counter() - started)
        raise


def get_batch_status(batch_id: str, db: Session) -> BatchStatusResponse | None:
    batch = db.get(IngestionBatch, batch_id)
    if batch is None:
        return None
    base = _response(batch)
    return BatchStatusResponse(
        **base.model_dump(),
        created_at=batch.created_at.isoformat(),
        completed_at=batch.completed_at.isoformat() if batch.completed_at else None,
    )


def _response(batch: IngestionBatch, idempotent_replay: bool = False) -> IngestionResponse:
    return IngestionResponse(
        batch_id=batch.batch_id,
        source=batch.source,
        status=batch.status,
        idempotent_replay=idempotent_replay,
        received_count=batch.received_count,
        accepted_count=batch.accepted_count,
        rejected_count=batch.rejected_count,
        raw_object_key=batch.raw_object_key,
        normalized_object_key=batch.normalized_object_key,
        quarantine_object_key=batch.quarantine_object_key,
    )


def _json_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, separators=(",", ":"), default=str).encode()


def _payload_hash(payload: IngestionRequest) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode()).hexdigest()


def _parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


class BatchConflictError(Exception):
    pass


class BatchTooLargeError(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"batch exceeds limit of {limit} events")


def vector_events_to_request(body: bytes) -> IngestionRequest:
    events = _parse_vector_body(body)
    sources = {str(event.get("osl_source", "linux-syslog")) for event in events}
    if len(sources) != 1:
        raise ValueError("Vector batch must contain a single OSL source")
    source = sources.pop()
    canonical = json.dumps(events, separators=(",", ":"), sort_keys=True, default=str)
    batch_id = f"vector-{sha256(canonical.encode()).hexdigest()[:32]}"
    normalized_events = [_vector_event(event, index) for index, event in enumerate(events)]
    return IngestionRequest(
        batch_id=batch_id,
        source=source,
        events=normalized_events,
    )


DOCKER_ACTIONS = frozenset({"start", "stop", "die", "restart", "oom", "kill"})


def docker_events_to_request(body: bytes) -> IngestionRequest:
    events = _parse_vector_body(body)
    if len(events) != 1:
        raise ValueError("Docker endpoint expects exactly one event per request")
    raw = events[0]
    if raw.get("Type") != "container" or raw.get("Action") not in DOCKER_ACTIONS:
        raise ValueError("unsupported Docker container action")
    timestamp = raw.get("timeNano")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
        raise ValueError("Docker event requires timeNano")
    host = raw.get("osl_hostname")
    if not isinstance(host, str) or not host or len(host) > 255:
        raise ValueError("Docker event requires osl_hostname")
    actor = raw.get("Actor")
    if not isinstance(actor, dict) or not isinstance(actor.get("ID"), str):
        raise ValueError("Docker event requires Actor.ID")
    action = raw["Action"]
    attributes = actor.get("Attributes")
    labeled_test = isinstance(attributes, dict) and str(attributes.get("osl.test")).lower() in {
        "1",
        "true",
    }
    exit_code = attributes.get("exitCode") if isinstance(attributes, dict) else None
    failed = action == "oom" or (action == "die" and str(exit_code) != "0")
    canonical = json.dumps(raw, separators=(",", ":"), sort_keys=True)
    digest = sha256(canonical.encode()).hexdigest()
    event = {
        "event_id": f"docker-{digest[:32]}",
        "event_time": datetime.fromtimestamp(timestamp / 1_000_000_000, UTC).isoformat(),
        "severity_id": 4 if failed else 2,
        "class_uid": 4002,
        "hostname": host,
        "application": "docker",
        "event_type": f"container.{action}",
        "message": f"Docker container {action}",
        "docker": raw,
    }
    return IngestionRequest(
        batch_id=f"docker-{digest[:32]}",
        source="test-docker" if raw.get("osl_test") is True or labeled_test else "docker-events",
        events=[event],
    )


def _parse_vector_body(body: bytes) -> list[dict[str, Any]]:
    if not body.strip():
        raise ValueError("empty Vector payload")
    try:
        decoded = json.loads(body)
        items = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        items = [json.loads(line) for line in body.splitlines() if line.strip()]
    if not items or any(not isinstance(item, dict) for item in items):
        raise ValueError("Vector payload must contain JSON objects")
    return items


def _vector_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    if event.get("osl_source") == "windows-eventlog":
        return _windows_syslog_event(event, index)
    timestamp = event.get("timestamp") or datetime.now(UTC).isoformat()
    severity = str(event.get("severity", "info")).lower()
    severity_id = {
        "emerg": 6,
        "alert": 6,
        "crit": 5,
        "err": 4,
        "warning": 3,
        "notice": 2,
        "info": 1,
        "debug": 0,
    }.get(severity, 1)
    canonical = json.dumps(event, separators=(",", ":"), sort_keys=True, default=str)
    result: dict[str, Any] = {
        "event_id": f"syslog-{sha256(f'{index}:{canonical}'.encode()).hexdigest()[:32]}",
        "event_time": timestamp,
        "severity_id": severity_id,
        "class_uid": 4002,
        "message": event.get("message", ""),
        "hostname": event.get("hostname"),
        "application": event.get("appname"),
        "event_type": "syslog",
        "syslog": event,
    }
    source_ip = event.get("source_ip")
    if source_ip:
        result["src_endpoint"] = {"ip": source_ip}
    return result


def _windows_syslog_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    raw_windows: dict[str, Any] = {}
    message = event.get("message", "")
    if isinstance(message, str):
        try:
            decoded = json.loads(message)
            if isinstance(decoded, dict):
                raw_windows = decoded
        except json.JSONDecodeError:
            pass

    timestamp = (
        raw_windows.get("timestamp")
        or event.get("timestamp")
        or datetime.now(UTC).isoformat()
    )
    channel = str(raw_windows.get("channel") or "Unknown")
    provider = str(raw_windows.get("provider_name") or "Windows Event Log")
    windows_event_id = raw_windows.get("event_id")
    record_id = raw_windows.get("record_id")
    hostname = raw_windows.get("computer") or event.get("hostname")
    level = str(raw_windows.get("level") or event.get("severity") or "Information").lower()
    severity_id = {
        "critical": 5,
        "error": 4,
        "warning": 3,
        "information": 1,
        "verbose": 0,
    }.get(level, 1)
    canonical = json.dumps(
        raw_windows or event, separators=(",", ":"), sort_keys=True, default=str
    )
    identity = f"{hostname}:{channel}:{record_id}:{windows_event_id}:{index}:{canonical}"
    rendered_message = raw_windows.get("message")
    if not isinstance(rendered_message, str) or not rendered_message:
        rendered_message = f"Windows event {windows_event_id or 'unknown'} from {provider}"
    return {
        "event_id": f"windows-{sha256(identity.encode()).hexdigest()[:32]}",
        "event_time": timestamp,
        "severity_id": severity_id,
        "class_uid": 4002,
        "hostname": hostname,
        "application": provider,
        "event_type": (
            f"windows.{channel.lower().replace(' ', '_')}."
            f"{windows_event_id or 'unknown'}"
        ),
        "message": rendered_message,
        "windows": raw_windows or {"syslog": event},
    }
