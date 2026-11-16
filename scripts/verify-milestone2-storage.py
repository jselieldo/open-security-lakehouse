#!/usr/bin/env python3
import io

import pyarrow.parquet as pq

from app.config import get_settings
from app.storage import get_s3_client


def main() -> None:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    keys = [
        item["Key"]
        for item in client.list_objects_v2(Bucket=bucket).get("Contents", [])
        if "smoke-" in item["Key"]
    ]
    if not keys:
        raise SystemExit("No Milestone 2 smoke-test objects found")

    for key in sorted(keys):
        print(key)

    parquet_key = next((key for key in keys if key.endswith(".parquet")), None)
    if parquet_key is None:
        raise SystemExit("No normalized Parquet object found")
    body = client.get_object(Bucket=bucket, Key=parquet_key)["Body"].read()
    table = pq.read_table(io.BytesIO(body))
    print(f"PARQUET_ROWS={table.num_rows}")
    print(f"PARQUET_COLUMNS={','.join(table.column_names)}")


if __name__ == "__main__":
    main()
