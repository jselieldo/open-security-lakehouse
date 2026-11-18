from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_certificate_generator_keeps_keys_outside_git_and_refuses_overwrite() -> None:
    script = (ROOT / "scripts" / "generate-mtls-certs.sh").read_text()
    assert "data/mtls" in script
    assert "refusing to overwrite" in script
    assert "rsa_keygen_bits:3072" in script
    assert "serverAuth" in script
    assert "clientAuth" in script
    assert "chmod 600" in script
    assert "openssl verify" in script
    assert "data/" in (ROOT / ".gitignore").read_text()


def test_linux_forwarder_requires_named_mtls_peer_and_durable_queue() -> None:
    config = (ROOT / "infrastructure" / "rsyslog" / "60-osl.conf").read_text()
    assert 'port="6514"' in config
    assert 'StreamDriver="gtls"' in config
    assert 'StreamDriverMode="1"' in config
    assert 'StreamDriverAuthMode="x509/name"' in config
    assert 'StreamDriverPermittedPeers="osl-syslog"' in config
    assert 'queue.saveOnShutdown="on"' in config


def test_compose_exposes_parallel_mtls_listener_with_private_keys_read_only() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    assert "${SYSLOG_MTLS_PORT:-6514}:6514/tcp" in compose
    assert "./data/mtls/server/server.key:/etc/osl/mtls/server.key:ro" in compose
    assert "./data/mtls/ca/ca.crt:/etc/osl/mtls/ca.crt:ro" in compose


def test_encrypted_backup_includes_collector_authority() -> None:
    backup = (ROOT / "scripts" / "backup.sh").read_text()
    assert 'tar -C data/mtls -cf "$stage/mtls.tar" .' in backup
    assert "mtls.tar" in backup
