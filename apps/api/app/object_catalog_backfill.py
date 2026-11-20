import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select

from .database import LakeObject, PlatformState, SessionLocal
from .investigation import _load_compaction_manifests, _select_query_objects
from .object_catalog import CATALOG_READY_KEY
from .storage import get_object_bytes, list_object_keys

SOURCE_PATTERN = re.compile(r"^normalized/source=([^/]+)/")


def _entry(key: str) -> dict[str, object]:
    bounds = json.loads(get_object_bytes(f"{key}.index.json"))
    match = SOURCE_PATTERN.match(key)
    if match is None or bounds.get("version") != 1:
        raise ValueError(f"invalid catalog source object: {key}")
    return {
        "object_key": key,
        "source": match.group(1),
        "min_event_time": datetime.fromisoformat(bounds["min_event_time"]),
        "max_event_time": datetime.fromisoformat(bounds["max_event_time"]),
    }


def rebuild_object_catalog(workers: int = 2) -> dict[str, int]:
    if workers < 1 or workers > 4:
        raise ValueError("workers must be between 1 and 4")
    with SessionLocal() as db:
        state = db.get(PlatformState, CATALOG_READY_KEY)
        if state is None:
            state = PlatformState(key=CATALOG_READY_KEY, value="0")
            db.add(state)
        else:
            state.value = "0"
        db.commit()

    keys = list_object_keys("normalized/")
    manifests = _load_compaction_manifests(keys)
    parquet = _select_query_objects(keys, manifests)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        entries = list(executor.map(_entry, parquet))

    with SessionLocal() as db:
        existing = {
            item.object_key: item for item in db.scalars(select(LakeObject)).all()
        }
        for entry in entries:
            key = str(entry["object_key"])
            item = existing.get(key)
            if item is None:
                item = LakeObject(object_key=key)
                db.add(item)
            item.source = str(entry["source"])
            item.min_event_time = entry["min_event_time"]
            item.max_event_time = entry["max_event_time"]
            item.active = True
        state = db.get(PlatformState, CATALOG_READY_KEY)
        if state is None:
            state = PlatformState(key=CATALOG_READY_KEY, value="1")
            db.add(state)
        else:
            state.value = "1"
        db.commit()
    return {
        "listed": len(keys),
        "cataloged": len(entries),
        "compacted_partitions": len(manifests),
    }


if __name__ == "__main__":
    print(json.dumps(rebuild_object_catalog(), sort_keys=True))
