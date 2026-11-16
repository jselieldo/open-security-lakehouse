from unittest.mock import MagicMock, patch

from app.storage import lake_storage_stats


def test_lake_storage_stats_groups_objects_by_area() -> None:
    client = MagicMock()
    paginator = client.get_paginator.return_value
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "raw/linux/a.json", "Size": 100},
                {"Key": "normalized/source=linux/a.parquet", "Size": 300},
                {"Key": "quarantine/invalid/a.json", "Size": 50},
                {"Key": "artifacts/evidence/a.json", "Size": 75},
                {"Key": "future/a", "Size": 25},
            ]
        }
    ]
    with patch("app.storage.get_s3_client", return_value=client):
        stats = lake_storage_stats()
    assert stats["raw"] == (1, 100)
    assert stats["normalized"] == (1, 300)
    assert stats["quarantine"] == (1, 50)
    assert stats["artifacts"] == (1, 75)
    assert stats["other"] == (1, 25)
