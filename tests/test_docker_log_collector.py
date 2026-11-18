import importlib.util
from datetime import UTC, datetime
from pathlib import Path


def load_collector():
    path = Path(__file__).parents[1] / "scripts" / "collect-docker-logs.py"
    spec = importlib.util.spec_from_file_location("collect_docker_logs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_log_parser_separates_stream_and_drops_inclusive_checkpoint() -> None:
    collector = load_collector()
    container = {"ID": "a" * 64, "Names": "example-api", "Image": "example:1"}
    text = (
        "2026-11-18T04:45:00.000000000Z replayed\n"
        "2026-11-18T04:45:01.000000000Z new message\n"
    )

    records, latest = collector.parse_log_lines(
        text,
        "stderr",
        container,
        "homelab",
        datetime(2026, 11, 18, 4, 45, tzinfo=UTC),
    )

    assert len(records) == 1
    assert records[0]["message"] == "new message"
    assert records[0]["stream"] == "stderr"
    assert latest == "2026-11-18T04:45:01.000000000Z"


def test_log_parser_truncates_oversized_messages() -> None:
    collector = load_collector()
    container = {"ID": "b" * 64, "Names": "worker", "Image": "worker:1"}
    records, _ = collector.parse_log_lines(
        f"2026-11-18T04:45:01Z {'x' * (collector.MAX_MESSAGE_LENGTH + 10)}",
        "stdout",
        container,
        "homelab",
    )
    assert len(records[0]["message"]) == collector.MAX_MESSAGE_LENGTH
    assert records[0]["truncated"] is True


def test_default_exclusion_prevents_osl_feedback_loop(monkeypatch) -> None:
    collector = load_collector()

    class Result:
        stdout = (
            '{"ID":"' + "a" * 64 + '","Names":"open-security-lakehouse-api-1",'
            '"Image":"osl-api"}\n'
            '{"ID":"' + "b" * 64 + '","Names":"business-api",'
            '"Image":"business:1"}\n'
        )

    monkeypatch.setattr(collector.subprocess, "run", lambda *_args, **_kwargs: Result())
    included = collector.re.compile(".*")
    excluded = collector.re.compile(r"^open-security-lakehouse-")
    containers = collector.list_containers(included, excluded)
    assert [item["Names"] for item in containers] == ["business-api"]
