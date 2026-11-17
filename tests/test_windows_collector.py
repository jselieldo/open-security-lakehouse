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
    assert config["sinks"]["osl_syslog"]["address"] == "192.168.3.120:5514"
    assert config["sinks"]["osl_syslog"]["mode"] == "tcp"
    assert config["sinks"]["osl_syslog"]["buffer"]["type"] == "disk"


def test_windows_installer_uses_least_privilege_service_account() -> None:
    installer = (ROOT / "scripts/install-windows-collector.ps1").read_text(encoding="utf-8")
    assert "#Requires -RunAsAdministrator" in installer
    assert "$expectedVersion = '0.61.0'" in installer
    assert "S-1-5-19" in installer
    assert "S-1-5-32-573" in installer
    assert "NT AUTHORITY\\LOCAL SERVICE" in installer
    assert "-RunLevel Limited" in installer
    assert "NT AUTHORITY\\SYSTEM" not in installer
