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
