import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import LakeObject, PlatformState, SessionLocal

SOURCE_PATTERN = re.compile(r"^normalized/source=([^/]+)/")
CATALOG_READY_KEY = "event_object_catalog_ready"


def catalog_ready(db: Session) -> bool:
    state = db.get(PlatformState, CATALOG_READY_KEY)
    return state is not None and state.value == "1"


def register_lake_object(
    object_key: str,
    source: str,
    minimum: datetime,
    maximum: datetime,
    db: Session,
    row_count: int | None = None,
) -> None:
    item = db.get(LakeObject, object_key)
    if item is None:
        item = LakeObject(object_key=object_key, source=source)
        db.add(item)
    item.min_event_time = minimum
    item.max_event_time = maximum
    item.row_count = row_count
    item.active = True


def replace_compacted_objects(
    source_objects: list[str], compact_objects: list[dict[str, object]], db: Session
) -> None:
    if source_objects:
        db.execute(
            update(LakeObject)
            .where(LakeObject.object_key.in_(source_objects))
            .values(active=False)
        )
    for item in compact_objects:
        match = SOURCE_PATTERN.match(str(item["object_key"]))
        if match is None:
            raise ValueError("compact object key has no source partition")
        register_lake_object(
            str(item["object_key"]),
            match.group(1),
            datetime.fromisoformat(str(item["min_event_time"])),
            datetime.fromisoformat(str(item["max_event_time"])),
            db,
            int(item["row_count"]),
        )


def catalog_keys(
    source: str | None, start: datetime | None, end: datetime | None
) -> list[str] | None:
    try:
        with SessionLocal() as db:
            if not catalog_ready(db):
                return None
            query = select(LakeObject.object_key).where(LakeObject.active.is_(True))
            if source:
                query = query.where(LakeObject.source == source)
            if start:
                query = query.where(LakeObject.max_event_time >= start)
            if end:
                query = query.where(LakeObject.min_event_time <= end)
            return list(db.scalars(query.order_by(LakeObject.object_key)).all())
    except SQLAlchemyError:
        return None


def catalog_status() -> dict[str, object]:
    with SessionLocal() as db:
        return {
            "ready": catalog_ready(db),
            "objects": len(db.scalars(select(LakeObject.object_key)).all()),
        }
