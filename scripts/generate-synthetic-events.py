#!/usr/bin/env python3
import argparse
import json
import uuid
from datetime import UTC, datetime, timedelta


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic OSL security event batch")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--source", default="synthetic-linux")
    parser.add_argument("--batch-id", default=f"synthetic-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--invalid", type=int, default=1, help="number of invalid events")
    args = parser.parse_args()
    if args.count < 1 or args.invalid < 0 or args.invalid > args.count:
        parser.error("require count >= 1 and 0 <= invalid <= count")

    now = datetime.now(UTC)
    valid_count = args.count - args.invalid
    events = [
        {
            "event_id": f"evt-{uuid.uuid4().hex}",
            "event_time": (now - timedelta(seconds=index)).isoformat(),
            "severity_id": (index % 5) + 1,
            "class_uid": 4002,
            "src_endpoint": {"ip": f"198.51.100.{(index % 250) + 1}"},
            "message": "synthetic authentication event",
        }
        for index in range(valid_count)
    ]
    events.extend(
        {"event_id": f"invalid-{index}", "severity_id": 99} for index in range(args.invalid)
    )
    print(json.dumps({"batch_id": args.batch_id, "source": args.source, "events": events}))


if __name__ == "__main__":
    main()
