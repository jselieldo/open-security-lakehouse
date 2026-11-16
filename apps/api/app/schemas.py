from typing import Any

from pydantic import BaseModel, Field, field_validator


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
