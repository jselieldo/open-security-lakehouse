from datetime import UTC, datetime, timedelta

import pytest
from app.retention import RetentionPolicy, _retention_candidates, apply_plan, create_plan

NOW = datetime(2026, 11, 18, tzinfo=UTC)


def item(key: str, days_old: int, size: int = 10) -> dict:
    return {"Key": key, "LastModified": NOW - timedelta(days=days_old), "Size": size}


def test_retention_policy_selects_only_expired_known_areas() -> None:
    inventory = [
        item("raw/linux/old.json", 91),
        item("raw/linux/recent.json", 2),
        item("normalized/source=linux/old.parquet", 91),
        item("quarantine/invalid/old.json", 91),
        item("artifacts/detection-evidence/recent.json", 100),
        item("future/unknown.dat", 1000),
    ]
    candidates = _retention_candidates(
        inventory, {}, {entry["Key"] for entry in inventory}, RetentionPolicy(), NOW
    )
    assert {entry["key"] for entry in candidates} == {
        "raw/linux/old.json",
        "normalized/source=linux/old.parquet",
        "quarantine/invalid/old.json",
    }


def test_superseded_batches_require_verified_compact_object() -> None:
    partition = "normalized/source=linux/year=2026/month=10/day=01"
    batch = f"{partition}/batch=one.parquet"
    compact = f"{partition}/compact=one.parquet"
    inventory = [item(batch, 15), item(compact, 1)]
    manifest = {partition: {"source_objects": [batch], "compact_objects": [compact]}}
    candidates = _retention_candidates(
        inventory, manifest, {batch, compact}, RetentionPolicy(), NOW
    )
    assert [(entry["key"], entry["reason"]) for entry in candidates] == [
        (batch, "superseded")
    ]
    assert _retention_candidates(
        inventory, manifest, {batch}, RetentionPolicy(), NOW
    ) == []


def test_plan_is_deterministic_and_apply_rejects_tampering(monkeypatch) -> None:
    monkeypatch.setattr("app.retention.list_object_inventory", lambda: [item("raw/a", 91)])
    plan = create_plan(RetentionPolicy(), NOW)
    assert plan["candidate_count"] == 1
    plan["candidates"][0]["key"] = "future/unsafe"
    with pytest.raises(ValueError, match="modified"):
        apply_plan(plan, NOW)


def test_apply_rejects_expired_plan_and_reports_storage_failure(monkeypatch) -> None:
    monkeypatch.setattr("app.retention.list_object_inventory", lambda: [item("raw/a", 91)])
    plan = create_plan(RetentionPolicy(), NOW)
    with pytest.raises(ValueError, match="expired"):
        apply_plan(plan, NOW + timedelta(hours=25))

    monkeypatch.setattr(
        "app.retention.delete_object_keys",
        lambda _keys: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    with pytest.raises(RuntimeError, match="storage unavailable"):
        apply_plan(plan, NOW)


def test_apply_empty_plan_does_not_call_storage(monkeypatch) -> None:
    monkeypatch.setattr("app.retention.list_object_inventory", lambda: [])
    plan = create_plan(RetentionPolicy(), NOW)
    monkeypatch.setattr(
        "app.retention.delete_object_keys",
        lambda _keys: (_ for _ in ()).throw(AssertionError("must not delete")),
    )
    assert apply_plan(plan, NOW) == {"planned": 0, "deleted": 0}
