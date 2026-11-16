from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class SourceEndpoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    ip: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        ip_address(value)
        return value


class SecurityEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(min_length=1, max_length=200)
    event_time: datetime
    severity_id: int = Field(ge=0, le=6)
    class_uid: int = Field(default=4002, ge=1)
    src_endpoint: SourceEndpoint | None = None

    @field_validator("event_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event_time must include a timezone")
        return value.astimezone(UTC)


def normalize_events(
    source: str, events: list[dict[str, Any]], ingested_at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for index, raw_event in enumerate(events):
        try:
            event = SecurityEvent.model_validate(raw_event)
        except ValidationError as exc:
            rejected.append(
                {
                    "index": index,
                    "event": raw_event,
                    "errors": exc.errors(include_url=False, include_input=False),
                }
            )
            continue

        src_ip = event.src_endpoint.ip if event.src_endpoint else None
        normalized.append(
            {
                "event_id": event.event_id,
                "source": source,
                "event_time": event.event_time,
                "ingested_at": ingested_at,
                "schema_name": "ocsf",
                "schema_version": "1.3.0",
                "class_uid": event.class_uid,
                "severity_id": event.severity_id,
                "src_ip": src_ip,
                "product_name": source,
                "raw_event_json": _compact_json(raw_event),
            }
        )
    return normalized, rejected


def _compact_json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
