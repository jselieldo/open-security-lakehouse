import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_windows_vector_configuration_is_bounded() -> None:
    config = yaml.safe_load(
        (ROOT / "infrastructure/vector-windows/vector.yaml").read_text(encoding="utf-8")
    )
    source = config["sources"]["windows_events"]
    assert source["read_existing_events"] is True
    assert source["max_event_age_secs"] == 3600
    assert source["events_per_second"] == 100
    assert source["include_xml"] is False
    assert source["max_event_data_length"] == 4096
    assert "Microsoft-Windows-PowerShell/Operational" in source["channels"]
    assert "Microsoft-Windows-Windows Defender/Operational" in source["channels"]
    sink = config["sinks"]["osl_syslog"]
    assert sink["address"] == "192.168.3.120:6514"
    assert sink["tls"]["enabled"] is True
    assert sink["tls"]["verify_certificate"] is True
    assert sink["tls"]["verify_hostname"] is True
    assert sink["tls"]["server_name"] == "osl-syslog"
    assert sink["tls"]["key_file"].endswith("client.key")
    assert config["sinks"]["osl_syslog"]["mode"] == "tcp"
    assert config["sinks"]["osl_syslog"]["buffer"]["type"] == "disk"


def test_server_vector_batches_events_before_object_storage() -> None:
    template = (ROOT / "infrastructure/vector/vector.toml.template").read_text(
        encoding="utf-8"
    )
    config = tomllib.loads(
        template.replace("__SYSLOG_ALLOWED_CIDR__", "192.168.3.0/24").replace(
            "__COLLECTOR_API_TOKEN__", "x" * 32
        )
    )
    mtls = config["sources"]["syslog_mtls"]
    assert mtls["address"] == "0.0.0.0:6514"
    assert mtls["tls"]["enabled"] is True
    assert mtls["tls"]["verify_certificate"] is True
    assert mtls["tls"]["client_metadata_key"] == "tls_client"
    assert config["transforms"]["tag_source"]["inputs"] == ["syslog_mtls"]
    assert "linux_syslog" not in config["sources"]
    assert "5514" not in (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "osl_api" not in config["sinks"]
    for sink_id in ("osl_api_windows", "osl_api_linux", "osl_api_test"):
        assert config["sinks"][sink_id]["batch"]["max_events"] == 100
        assert config["sinks"][sink_id]["batch"]["timeout_secs"] == 2
        assert config["sinks"][sink_id]["buffer"]["type"] == "disk"
    assert config["sinks"]["osl_api_windows"]["inputs"] == ["route_source.windows"]
    assert config["sinks"]["osl_api_linux"]["inputs"] == ["route_source.linux"]
    assert config["sinks"]["osl_api_test"]["inputs"] == ["route_source.test"]


def test_windows_installer_uses_least_privilege_service_account() -> None:
    installer = (ROOT / "scripts/install-windows-collector.ps1").read_text(encoding="utf-8")
    assert "#Requires -RunAsAdministrator" in installer
    assert "$expectedVersion = '0.61.0'" in installer
    assert "S-1-5-19" in installer
    assert "S-1-5-32-573" in installer
    assert "-UserId $localServiceSid" in installer
    assert "-RunLevel Limited" in installer
    assert "NT AUTHORITY\\SYSTEM" not in installer
    assert "Stop-ScheduledTask -TaskName $taskName" in installer
    assert "data\\mtls\\clients\\windows" in installer
    assert "client.key" in installer
    assert "(OI)(CI)R" in installer
    assert installer.index("Stop-ScheduledTask") < installer.index("Register-ScheduledTask")
