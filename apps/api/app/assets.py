import json
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Asset
from .schemas import AssetResponse


def _asset_kind(source: str) -> str:
    if source == "windows-eventlog":
        return "windows"
    if source in {"docker-events", "docker-logs"}:
        return "docker-host"
    if source == "linux-syslog":
        return "linux"
    return "host"


def _identity(hostname: str | None, source_ip: str | None) -> tuple[str, str] | None:
    if hostname:
        return "hostname", hostname.strip().lower()
    if source_ip:
        return "ip", source_ip
    return None


def record_assets(source: str, events: list[dict], db: Session) -> None:
    """Persist only derived asset metadata; event bodies remain in object storage."""
    observations: dict[str, dict[str, object]] = {}
    for event in events:
        hostname = event.get("hostname") if isinstance(event.get("hostname"), str) else None
        source_ip = event.get("src_ip") if isinstance(event.get("src_ip"), str) else None
        identity = _identity(hostname, source_ip)
        if identity is None:
            continue
        identity_type, identity_value = identity
        asset_id = sha256(f"{identity_type}:{identity_value}".encode()).hexdigest()
        item = observations.setdefault(
            asset_id,
            {"hostname": hostname, "source_ip": source_ip, "count": 0},
        )
        item["count"] = int(item["count"]) + 1
        if source_ip:
            item["source_ip"] = source_ip

    now = datetime.now(UTC)
    for asset_id, observation in observations.items():
        asset = db.get(Asset, asset_id)
        hostname = observation["hostname"]
        source_ip = observation["source_ip"]
        if asset is None:
            asset = Asset(
                asset_id=asset_id,
                kind=_asset_kind(source),
                display_name=str(hostname or source_ip),
                hostname=str(hostname) if hostname else None,
                primary_ip=str(source_ip) if source_ip else None,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(asset)
        addresses = set(json.loads(asset.ip_addresses_json or "[]"))
        sources = set(json.loads(asset.sources_json or "[]"))
        if source_ip:
            addresses.add(str(source_ip))
            asset.primary_ip = str(source_ip)
        sources.add(source)
        asset.ip_addresses_json = json.dumps(sorted(addresses), separators=(",", ":"))
        asset.sources_json = json.dumps(sorted(sources), separators=(",", ":"))
        asset.event_count = (asset.event_count or 0) + int(observation["count"])
        asset.last_seen_at = now


def asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        asset_id=asset.asset_id,
        kind=asset.kind,
        display_name=asset.display_name,
        hostname=asset.hostname,
        primary_ip=asset.primary_ip,
        ip_addresses=json.loads(asset.ip_addresses_json),
        sources=json.loads(asset.sources_json),
        criticality=asset.criticality,
        event_count=asset.event_count,
        first_seen_at=asset.first_seen_at,
        last_seen_at=asset.last_seen_at,
    )


def list_assets(db: Session) -> list[AssetResponse]:
    return [
        asset_response(item)
        for item in db.scalars(select(Asset).order_by(Asset.last_seen_at.desc())).all()
    ]


def get_asset(asset_id: str, db: Session) -> AssetResponse | None:
    asset = db.get(Asset, asset_id)
    return asset_response(asset) if asset else None
