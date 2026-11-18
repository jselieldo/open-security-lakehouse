from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import yaml
from app.database import Alert, Base
from app.detection import (
    DetectionRule,
    execute_rule,
    get_alert_evidence,
    list_alerts,
    load_rules,
)
from app.schemas import InvestigationRequest, InvestigationResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def rule() -> DetectionRule:
    return DetectionRule(
        id="high-events",
        title="High events",
        description="Test rule",
        severity="high",
        threshold=1,
        query=InvestigationRequest(min_severity=4),
    )


def investigation_result() -> InvestigationResponse:
    now = datetime.now(UTC)
    return InvestigationResponse(
        query_engine="duckdb",
        scanned_objects=1,
        returned_count=1,
        duration_ms=1.0,
        events=[
            {
                "event_id": "evt-high",
                "source": "linux",
                "event_time": now,
                "ingested_at": now,
                "severity_id": 5,
            }
        ],
    )


def test_rule_loader_reads_yaml(tmp_path, monkeypatch) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "rule.yaml").write_text(
        """
id: test-rule
title: Test rule
description: Test description
severity: medium
enabled: true
schedule_minutes: 5
threshold: 1
query:
  source: linux
  min_severity: 3
""".strip()
    )
    monkeypatch.setattr(
        "app.detection.get_settings",
        lambda: SimpleNamespace(detection_rules_dir=str(rules_dir)),
    )
    rules = load_rules()
    assert len(rules) == 1
    assert rules[0].id == "test-rule"
    assert rules[0].query.source == "linux"


def test_repository_detection_rules_are_valid_and_unique() -> None:
    rules_dir = Path(__file__).parents[1] / "detections" / "rules"
    rules = [
        DetectionRule.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in rules_dir.glob("*.yaml")
    ]
    ids = [item.id for item in rules]
    assert len(ids) == len(set(ids))
    windows = [item for item in rules if item.id.startswith("windows-")]
    assert len(windows) == 6
    assert all(item.query.source == "windows-eventlog" for item in windows)


def test_detection_creates_alert_and_evidence(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    objects = {}
    monkeypatch.setattr("app.detection.investigate", lambda _query: investigation_result())
    monkeypatch.setattr(
        "app.detection.put_object",
        lambda key, body, content_type: objects.update({key: (body, content_type)}),
    )
    with Session(engine, expire_on_commit=False) as db:
        result = execute_rule(rule(), db)
        alert = db.scalar(select(Alert))

    assert result.status == "completed"
    assert result.matched_count == 1
    assert result.alert_created is True
    assert alert is not None
    assert alert.evidence_object_key in objects
    assert objects[alert.evidence_object_key][1] == "application/json"


def test_detection_deduplicates_same_evidence(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.detection.investigate", lambda _query: investigation_result())
    monkeypatch.setattr("app.detection.put_object", lambda *_args: None)
    with Session(engine, expire_on_commit=False) as db:
        first = execute_rule(rule(), db)
        second = execute_rule(rule(), db)
        alerts = list_alerts(db)

    assert first.alert_created is True
    assert second.alert_created is False
    assert len(alerts) == 1


def test_detection_below_threshold_does_not_alert(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    empty = InvestigationResponse(
        query_engine="duckdb",
        scanned_objects=1,
        returned_count=0,
        duration_ms=1.0,
        events=[],
    )
    monkeypatch.setattr("app.detection.investigate", lambda _query: empty)
    with Session(engine, expire_on_commit=False) as db:
        result = execute_rule(rule(), db)
        alerts = list_alerts(db)

    assert result.alert_created is False
    assert alerts == []


def test_detection_applies_relative_lookback(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured = {}
    monkeypatch.setattr(
        "app.detection.investigate",
        lambda query: captured.update({"query": query}) or investigation_result(),
    )
    monkeypatch.setattr("app.detection.put_object", lambda *_args: None)
    before = datetime.now(UTC)
    with Session(engine) as db:
        execute_rule(rule(), db)
    query = captured["query"]
    assert query.start_time is not None
    assert query.start_time <= before
    assert query.start_time > before.replace(year=before.year - 1)


def test_alert_evidence_is_loaded_from_storage(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.detection.investigate", lambda _query: investigation_result())
    stored = {}

    def fake_put(key, body, _content_type) -> None:
        stored[key] = body

    monkeypatch.setattr("app.detection.put_object", fake_put)
    monkeypatch.setattr("app.detection.get_object_bytes", lambda key: stored[key])
    with Session(engine, expire_on_commit=False) as db:
        execute_rule(rule(), db)
        alert = db.scalar(select(Alert))
        evidence = get_alert_evidence(alert.alert_id, db)

    assert evidence is not None
    assert evidence["alert_id"] == alert.alert_id
    assert evidence["events"][0]["event_id"] == "evt-high"
