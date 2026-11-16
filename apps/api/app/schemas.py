from datetime import datetime
from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class IngestionRequest(BaseModel):
    batch_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    events: list[dict[str, Any]] = Field(min_length=1)

    @field_validator("events")
    @classmethod
    def reject_non_objects(cls, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("every event must be a JSON object")
        return events


class IngestionResponse(BaseModel):
    batch_id: str
    source: str
    status: str
    idempotent_replay: bool = False
    received_count: int
    accepted_count: int
    rejected_count: int
    raw_object_key: str | None = None
    normalized_object_key: str | None = None
    quarantine_object_key: str | None = None


class BatchStatusResponse(IngestionResponse):
    created_at: str
    completed_at: str | None = None


class InvestigationRequest(BaseModel):
    src_ip: str | None = None
    source: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    start_time: datetime | None = None
    end_time: datetime | None = None
    min_severity: int | None = Field(default=None, ge=0, le=6)
    max_severity: int | None = Field(default=None, ge=0, le=6)
    limit: int = Field(default=100, ge=1, le=1000)

    @field_validator("src_ip")
    @classmethod
    def validate_src_ip(cls, value: str | None) -> str | None:
        if value is not None:
            ip_address(value)
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("investigation timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("start_time must be before or equal to end_time")
        if (
            self.min_severity is not None
            and self.max_severity is not None
            and self.min_severity > self.max_severity
        ):
            raise ValueError("min_severity must be less than or equal to max_severity")
        return self


class InvestigationResponse(BaseModel):
    query_engine: str
    scanned_objects: int
    returned_count: int
    duration_ms: float
    events: list[dict[str, Any]]


class DetectionRuleResponse(BaseModel):
    id: str
    title: str
    description: str
    severity: str
    enabled: bool
    schedule_minutes: int
    threshold: int
    query: InvestigationRequest


class DetectionRunResponse(BaseModel):
    run_id: str
    rule_id: str
    status: str
    matched_count: int
    alert_created: bool
    duration_ms: float
    completed_at: str | None = None


class AlertResponse(BaseModel):
    alert_id: str
    rule_id: str
    title: str
    severity: str
    status: str
    event_count: int
    evidence_object_key: str
    created_at: str


class DashboardSummary(BaseModel):
    milestone: str
    platform_status: str
    ingestion_batches: int
    accepted_events: int
    quarantined_events: int
    detection_rules: int
    open_alerts: int
    detection_runs: int
    latest_alerts: list[AlertResponse]


class UserResponse(BaseModel):
    subject: str
    username: str
    email: str | None
    display_name: str | None
    roles: list[str]
    auth_method: str


class AuditLogResponse(BaseModel):
    audit_id: str
    actor_subject: str
    actor_username: str
    action: str
    resource: str
    outcome: str
    details: dict[str, Any]
    client_ip: str | None
    created_at: str


class AuthConfigResponse(BaseModel):
    mode: str
    issuer_url: str
    client_id: str
