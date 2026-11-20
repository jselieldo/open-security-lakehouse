#!/usr/bin/env python3
"""Poll application container stdout/stderr and forward bounded batches to OSL."""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

MAX_MESSAGE_LENGTH = 16_384
MAX_BATCH_SIZE = 100
DOCKER_BINARY = "/usr/bin/docker"


def parse_log_lines(
    text: str,
    stream: str,
    container: dict[str, str],
    hostname: str,
    after: datetime | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    records: list[dict[str, object]] = []
    latest: str | None = None
    for line in text.splitlines():
        timestamp, separator, message = line.partition(" ")
        if not separator or not message:
            continue
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            continue
        parsed = parsed.astimezone(UTC)
        if after is not None and parsed <= after:
            continue
        message = message[:MAX_MESSAGE_LENGTH]
        if not message:
            continue
        latest = max(latest or timestamp, timestamp)
        records.append(
            {
                "timestamp": timestamp,
                "stream": stream,
                "message": message,
                "truncated": len(line.partition(" ")[2]) > MAX_MESSAGE_LENGTH,
                "container_id": container["ID"],
                "container_name": container["Names"],
                "image": container["Image"],
                "osl_hostname": hostname,
            }
        )
    return records, latest


def list_containers(include: re.Pattern[str], exclude: re.Pattern[str]) -> list[dict[str, str]]:
    result = subprocess.run(  # noqa: S603 -- fixed Docker CLI without a shell.
        [DOCKER_BINARY, "ps", "--no-trunc", "--format", "{{json .}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    containers = [json.loads(line) for line in result.stdout.splitlines() if line]
    return [
        item
        for item in containers
        if include.search(str(item.get("Names", "")))
        and not exclude.search(str(item.get("Names", "")))
        and all(isinstance(item.get(key), str) and item[key] for key in ("ID", "Names", "Image"))
    ]


def collect_container(
    container: dict[str, str], since: str
) -> tuple[list[dict[str, object]], str | None]:
    result = subprocess.run(  # noqa: S603 -- fixed Docker CLI without a shell.
        [
            DOCKER_BINARY, "logs", "--timestamps", "--since", since,
            container["ID"],
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker logs failed for {container['Names']}")
    hostname = os.environ.get("OSL_DOCKER_HOSTNAME", socket.gethostname())
    after = datetime.fromisoformat(since.replace("Z", "+00:00")).astimezone(UTC)
    stdout, stdout_latest = parse_log_lines(
        result.stdout, "stdout", container, hostname, after
    )
    stderr, stderr_latest = parse_log_lines(
        result.stderr, "stderr", container, hostname, after
    )
    latest = max(item for item in (stdout_latest, stderr_latest) if item is not None) \
        if stdout_latest or stderr_latest else None
    return stdout + stderr, latest


def send_batches(endpoint: str, token: str, records: list[dict[str, object]]) -> None:
    for offset in range(0, len(records), MAX_BATCH_SIZE):
        body = json.dumps(records[offset : offset + MAX_BATCH_SIZE]).encode()
        request = urllib.request.Request(  # noqa: S310 -- endpoint scheme validated by main.
            endpoint,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            result = json.load(response)
        if result["status"] == "quarantined":
            print(
                "Docker log batch quarantined: "
                f"accepted={result.get('accepted_count', 0)} "
                f"rejected={result.get('rejected_count', 0)}",
                file=sys.stderr,
            )
            continue
        if result["status"] != "completed":
            raise RuntimeError("Docker log batch was not accepted")


def write_checkpoint(path: Path, checkpoints: dict[str, str]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(checkpoints, separators=(",", ":")))
    os.replace(temporary, path)


def main() -> None:
    token = os.environ["COLLECTOR_API_TOKEN"]
    endpoint = os.environ.get(
        "OSL_DOCKER_LOG_INGEST_URL", "http://127.0.0.1:8000/api/v1/ingestion/docker-logs"
    )
    if urlparse(endpoint).scheme not in {"http", "https"}:
        raise ValueError("OSL_DOCKER_LOG_INGEST_URL must use HTTP or HTTPS")
    include = re.compile(os.environ.get("OSL_DOCKER_LOG_INCLUDE", ".*"))
    exclude = re.compile(
        os.environ.get("OSL_DOCKER_LOG_EXCLUDE", r"^open-security-lakehouse-")
    )
    interval = int(os.environ.get("OSL_DOCKER_LOG_INTERVAL_SECONDS", "15"))
    if interval < 5 or interval > 3600:
        raise ValueError("OSL_DOCKER_LOG_INTERVAL_SECONDS must be between 5 and 3600")
    checkpoint = Path(
        os.environ.get(
            "OSL_DOCKER_LOG_CHECKPOINT",
            str(Path.home() / ".local/state/osl/docker-logs.checkpoint"),
        )
    )
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoints = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if not isinstance(checkpoints, dict):
        raise ValueError("invalid Docker log checkpoint")

    while True:
        for container in list_containers(include, exclude):
            container_id = container["ID"]
            since = checkpoints.get(
                container_id, (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            )
            records, latest = collect_container(container, str(since))
            if records:
                send_batches(endpoint, token, records)
            if latest:
                checkpoints[container_id] = latest
                write_checkpoint(checkpoint, checkpoints)
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, re.error) as exc:
        print(f"Docker log collection stopped: {type(exc).__name__}", file=sys.stderr)
        time.sleep(1)
        sys.exit(1)
