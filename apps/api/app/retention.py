"""Two-phase retention planning and application for the object lake."""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from .storage import (
    delete_object_keys,
    get_object_bytes,
    list_object_inventory,
)

ALLOWED_PREFIXES = ("raw/", "normalized/", "quarantine/", "artifacts/")
ALLOWED_REASONS = frozenset(
    {"raw_expired", "normalized_expired", "quarantine_expired", "artifact_expired", "superseded"}
)


@dataclass(frozen=True)
class RetentionPolicy:
    raw_days: int = 90
    normalized_days: int = 90
    quarantine_days: int = 90
    artifact_days: int = 365
    superseded_days: int = 14

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 1 or value > 3650:
                raise ValueError(f"{name} must be between 1 and 3650 days")


def create_plan(policy: RetentionPolicy, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    inventory = list_object_inventory()
    available = {str(item["Key"]) for item in inventory}
    manifests: dict[str, dict] = {}
    for key in available:
        if not key.endswith("/_compaction.json"):
            continue
        try:
            document = json.loads(get_object_bytes(key))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if isinstance(document, dict):
            manifests[key.rsplit("/", 1)[0]] = document
    candidates = _retention_candidates(inventory, manifests, available, policy, now)
    plan = {
        "version": 1,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "policy": asdict(policy),
        "candidate_count": len(candidates),
        "candidate_bytes": sum(item["size"] for item in candidates),
        "candidates": candidates,
    }
    plan["digest"] = _digest(plan)
    return plan


def _retention_candidates(
    inventory: list[dict],
    manifests: dict[str, dict],
    available: set[str],
    policy: RetentionPolicy,
    now: datetime,
) -> list[dict]:
    superseded: set[str] = set()
    for manifest in manifests.values():
        compact_objects = {
            str(key) for key in manifest.get("compact_objects", []) if isinstance(key, str)
        }
        if compact_objects and compact_objects.issubset(available):
            superseded.update(
                str(key) for key in manifest.get("source_objects", []) if isinstance(key, str)
            )

    candidates: list[dict] = []
    for item in inventory:
        key = str(item["Key"])
        modified = item["LastModified"]
        if modified.tzinfo is None:
            modified = modified.replace(tzinfo=UTC)
        age = now - modified.astimezone(UTC)
        reason = None
        if key in superseded and age >= timedelta(days=policy.superseded_days):
            reason = "superseded"
        elif key.startswith("raw/") and age >= timedelta(days=policy.raw_days):
            reason = "raw_expired"
        elif key.startswith("normalized/") and age >= timedelta(days=policy.normalized_days):
            reason = "normalized_expired"
        elif key.startswith("quarantine/") and age >= timedelta(days=policy.quarantine_days):
            reason = "quarantine_expired"
        elif key.startswith("artifacts/") and age >= timedelta(days=policy.artifact_days):
            reason = "artifact_expired"
        if reason:
            candidates.append(
                {
                    "key": key,
                    "reason": reason,
                    "size": int(item.get("Size", 0)),
                    "last_modified": modified.astimezone(UTC).isoformat(),
                }
            )
    return sorted(candidates, key=lambda item: item["key"])


def apply_plan(plan: dict, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    if plan.get("version") != 1 or plan.get("digest") != _digest(plan):
        raise ValueError("invalid or modified retention plan")
    expires_at = datetime.fromisoformat(str(plan["expires_at"]))
    if expires_at.tzinfo is None or now > expires_at.astimezone(UTC):
        raise ValueError("retention plan has expired")
    candidates = plan.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("retention plan candidates are invalid")
    keys: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("retention candidate is invalid")
        key = candidate.get("key")
        reason = candidate.get("reason")
        if (
            not isinstance(key, str)
            or not key.startswith(ALLOWED_PREFIXES)
            or reason not in ALLOWED_REASONS
        ):
            raise ValueError("retention candidate is outside the allowed scope")
        keys.append(key)
    deleted = delete_object_keys(keys) if keys else 0
    return {"planned": len(keys), "deleted": deleted}


def _digest(plan: dict) -> str:
    document = {key: value for key, value in plan.items() if key != "digest"}
    canonical = json.dumps(document, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--raw-days", type=int, default=90)
    parser.add_argument("--normalized-days", type=int, default=90)
    parser.add_argument("--quarantine-days", type=int, default=90)
    parser.add_argument("--artifact-days", type=int, default=365)
    parser.add_argument("--superseded-days", type=int, default=14)
    args = parser.parse_args()
    if args.command == "plan":
        policy = RetentionPolicy(
            raw_days=args.raw_days,
            normalized_days=args.normalized_days,
            quarantine_days=args.quarantine_days,
            artifact_days=args.artifact_days,
            superseded_days=args.superseded_days,
        )
        print(json.dumps(create_plan(policy), separators=(",", ":")))
        return
    plan = json.load(sys.stdin)
    print(json.dumps(apply_plan(plan), separators=(",", ":")))


if __name__ == "__main__":
    main()
