import io
import tarfile
from datetime import UTC, datetime
from types import SimpleNamespace

from app.backup import export_bucket, import_bucket


class FakePaginator:
    def paginate(self, **_kwargs):
        return [
            {
                "Contents": [
                    {
                        "Key": "raw/source/event.json",
                        "Size": 7,
                        "LastModified": datetime.now(UTC),
                    }
                ]
            }
        ]


class FakeClient:
    def __init__(self):
        self.uploaded = {}

    def get_paginator(self, _name):
        return FakePaginator()

    def get_object(self, **_kwargs):
        return {"Body": io.BytesIO(b'{"x":1}'), "ContentType": "application/json"}

    def list_buckets(self):
        return {"Buckets": []}

    def create_bucket(self, **_kwargs):
        return None

    def upload_fileobj(self, body, bucket, key, ExtraArgs):
        assert bucket == "test-bucket"
        self.uploaded[key] = (body.read(), ExtraArgs["ContentType"])


def test_object_backup_round_trip(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr("app.backup.get_s3_client", lambda: client)
    monkeypatch.setattr(
        "app.backup.get_settings", lambda: SimpleNamespace(s3_bucket="test-bucket")
    )
    archive = io.BytesIO()
    assert export_bucket(archive) == {"objects": 1, "bytes": 7}
    archive.seek(0)
    assert import_bucket(archive) == {"objects": 1, "bytes": 7}
    assert client.uploaded == {"raw/source/event.json": (b'{"x":1}', "application/json")}


def test_object_restore_rejects_unsafe_key(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr("app.backup.get_s3_client", lambda: client)
    monkeypatch.setattr(
        "app.backup.get_settings", lambda: SimpleNamespace(s3_bucket="test-bucket")
    )
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as output:
        info = tarfile.TarInfo("objects/../escape")
        info.size = 1
        output.addfile(info, io.BytesIO(b"x"))
    archive.seek(0)
    try:
        import_bucket(archive)
    except ValueError as exc:
        assert "unsafe object key" in str(exc)
    else:
        raise AssertionError("unsafe key was accepted")
