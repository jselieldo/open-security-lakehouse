"""Streaming object-lake backup helpers used by the operator scripts."""

import argparse
import json
import sys
import tarfile

from .config import get_settings
from .storage import get_s3_client


def export_bucket(output=None) -> dict[str, int]:
    output = output or sys.stdout.buffer
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    count = 0
    total = 0
    with tarfile.open(fileobj=output, mode="w|") as archive:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                key = item["Key"]
                response = client.get_object(Bucket=bucket, Key=key)
                info = tarfile.TarInfo(f"objects/{key}")
                info.size = int(item["Size"])
                info.mtime = int(item["LastModified"].timestamp())
                info.pax_headers = {
                    "osl-content-type": response.get("ContentType", "application/octet-stream")
                }
                archive.addfile(info, response["Body"])
                count += 1
                total += info.size
    return {"objects": count, "bytes": total}


def import_bucket(input_file=None) -> dict[str, int]:
    input_file = input_file or sys.stdin.buffer
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
    count = 0
    total = 0
    with tarfile.open(fileobj=input_file, mode="r|") as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith("objects/"):
                continue
            key = member.name.removeprefix("objects/")
            if not key or key.startswith("/") or ".." in key.split("/"):
                raise ValueError("unsafe object key in backup")
            body = archive.extractfile(member)
            if body is None:
                raise ValueError(f"missing object body for {key}")
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentLength=member.size,
                ContentType=member.pax_headers.get(
                    "osl-content-type", "application/octet-stream"
                ),
            )
            count += 1
            total += member.size
    return {"objects": count, "bytes": total}


def bucket_stats() -> dict[str, int]:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    count = 0
    total = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            count += 1
            total += int(item.get("Size", 0))
    return {"objects": count, "bytes": total}


def purge_bucket() -> dict[str, int]:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted += len(objects)
    client.delete_bucket(Bucket=bucket)
    return {"deleted": deleted}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "import", "stats", "purge"))
    args = parser.parse_args()
    if args.command == "export":
        export_bucket()
        return
    result = {
        "import": import_bucket,
        "stats": bucket_stats,
        "purge": purge_bucket,
    }[args.command]()
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
