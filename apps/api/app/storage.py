import boto3
from botocore.client import BaseClient
from botocore.config import Config

from .config import get_settings


def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def check_storage() -> None:
    get_s3_client().head_bucket(Bucket=get_settings().s3_bucket)


def put_object(key: str, body: bytes, content_type: str) -> None:
    get_s3_client().put_object(
        Bucket=get_settings().s3_bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )


def list_object_keys(prefix: str) -> list[str]:
    client = get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=get_settings().s3_bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def lake_storage_stats() -> dict[str, tuple[int, int]]:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    stats: dict[str, list[int]] = {
        "raw": [0, 0],
        "normalized": [0, 0],
        "quarantine": [0, 0],
        "artifacts": [0, 0],
        "other": [0, 0],
    }
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            area = item["Key"].split("/", 1)[0]
            target = stats.get(area, stats["other"])
            target[0] += 1
            target[1] += int(item.get("Size", 0))
    return {area: (values[0], values[1]) for area, values in stats.items()}


def get_object_bytes(key: str) -> bytes:
    response = get_s3_client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    return response["Body"].read()
