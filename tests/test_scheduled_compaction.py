from pathlib import Path

import yaml
from app.detection import DetectionRule

ROOT = Path(__file__).parents[1]


def test_scheduled_compaction_is_bounded_locked_and_observable() -> None:
    script = (ROOT / "scripts" / "auto-compact-lake.sh").read_text()
    service = (
        ROOT / "infrastructure" / "systemd" / "osl-lake-compaction.service.template"
    ).read_text()
    timer = (
        ROOT / "infrastructure" / "systemd" / "osl-lake-compaction.timer"
    ).read_text()
    assert "flock -n" in script
    assert "--memory" in script
    assert "--minimum-objects" in script
    assert "timeout --signal=TERM" in script
    assert "date -u -d tomorrow" in script
    assert "authpriv.err" in script
    assert "TimeoutStartSec=45min" in service
    assert "SupplementaryGroups=docker" in service
    assert "OnUnitActiveSec=1h" in timer
    assert "RandomizedDelaySec=5m" in timer
    assert "Persistent=true" in timer


def test_compaction_failure_rule_is_valid() -> None:
    document = yaml.safe_load(
        (ROOT / "detections" / "rules" / "lake-compaction-failures.yaml").read_text()
    )
    rule = DetectionRule.model_validate(document)
    assert rule.query.source == "linux-syslog"
    assert rule.query.message_contains == "OSL lake compaction failed"
    assert rule.severity == "high"
