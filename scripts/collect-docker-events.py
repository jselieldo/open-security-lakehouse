#!/usr/bin/env python3
"""Host-side Docker event forwarder; never mount docker.sock in the API or Vector."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> None:
    token = os.environ["COLLECTOR_API_TOKEN"]
    endpoint = os.environ.get(
        "OSL_DOCKER_INGEST_URL", "http://127.0.0.1:8000/api/v1/ingestion/docker"
    )
    host = os.environ.get("OSL_DOCKER_HOSTNAME", socket.gethostname())
    checkpoint = Path(
        os.environ.get(
            "OSL_DOCKER_CHECKPOINT",
            str(Path.home() / ".local/state/osl/docker-events.checkpoint"),
        )
    )
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    # Docker's --since is inclusive. Replays are safe because IDs derive from content.
    since = (
        datetime.fromtimestamp(int(checkpoint.read_text()) / 1_000_000_000, UTC)
        if checkpoint.exists()
        else datetime.now(UTC) - timedelta(minutes=1)
    )
    command = [
        "docker", "events", "--filter", "type=container",
        "--since", since.isoformat(), "--format", "{{json .}}",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            event = json.loads(line)
            if event.get("Action") not in {"start", "stop", "die", "restart", "oom", "kill"}:
                continue
            event["osl_hostname"] = host
            body = json.dumps(event).encode()
            request = urllib.request.Request(
                endpoint, data=body, method="POST",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            # On failure, exit without advancing the checkpoint; a supervisor can restart us.
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            if result["status"] != "completed":
                raise RuntimeError("Docker event was not accepted")
            stamp = int(event["timeNano"])
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(str(stamp))
            os.replace(temporary, checkpoint)
        if process.wait() != 0:
            raise RuntimeError("docker events exited with an error")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process.stdout is not None:
            process.stdout.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Docker collection stopped: {type(exc).__name__}", file=sys.stderr)
        time.sleep(1)
        sys.exit(1)
