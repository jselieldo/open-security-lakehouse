import json
from datetime import UTC, datetime, timedelta

from app.database import Base, LakeObject, PlatformState
from app.object_catalog import CATALOG_READY_KEY, catalog_keys
from app.object_catalog_backfill import rebuild_object_catalog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_catalog_filters_by_source_and_event_time(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add(PlatformState(key=CATALOG_READY_KEY, value="1"))
        db.add_all([
            LakeObject(
                object_key="normalized/source=linux/batch=recent.parquet",
                source="linux",
                min_event_time=now - timedelta(hours=1),
                max_event_time=now,
                active=True,
            ),
            LakeObject(
                object_key="normalized/source=linux/batch=old.parquet",
                source="linux",
                min_event_time=now - timedelta(days=5),
                max_event_time=now - timedelta(days=4),
                active=True,
            ),
        ])
        db.commit()
    monkeypatch.setattr("app.object_catalog.SessionLocal", lambda: Session(engine))
    assert catalog_keys("linux", now - timedelta(days=1), now) == [
        "normalized/source=linux/batch=recent.parquet"
    ]


def test_catalog_backfill_isolated_and_marks_ready(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    parquet = "normalized/source=linux/year=2026/month=11/day=20/batch=a.parquet"
    index = {
        "version": 1,
        "min_event_time": "2026-11-20T12:00:00+00:00",
        "max_event_time": "2026-11-20T12:01:00+00:00",
    }
    monkeypatch.setattr("app.object_catalog_backfill.SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(
        "app.object_catalog_backfill.list_object_keys",
        lambda _prefix: [parquet, f"{parquet}.index.json"],
    )
    monkeypatch.setattr(
        "app.object_catalog_backfill.get_object_bytes",
        lambda _key: json.dumps(index).encode(),
    )
    result = rebuild_object_catalog(1)
    assert result == {"listed": 2, "cataloged": 1, "compacted_partitions": 0}
    with Session(engine) as db:
        assert db.get(PlatformState, CATALOG_READY_KEY).value == "1"
        assert db.get(LakeObject, parquet).source == "linux"


def test_catalog_backfill_limits_parallelism() -> None:
    try:
        rebuild_object_catalog(5)
    except ValueError as exc:
        assert "between 1 and 4" in str(exc)
    else:
        raise AssertionError("unsafe catalog backfill concurrency was accepted")
