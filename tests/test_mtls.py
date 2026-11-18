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
    assert "homelab-client" in script
    assert "windows-client" in script
    assert "data/" in (ROOT / ".gitignore").read_text()


def test_client_rotation_is_scoped_verified_and_recoverable() -> None:
    script = (ROOT / "scripts" / "rotate-mtls-client.sh").read_text()
    assert 'case "$client" in' in script
    assert "homelab|windows" in script
    assert "rsa_keygen_bits:3072" in script
    assert "extendedKeyUsage=clientAuth" in script
    assert 'openssl verify -CAfile "$root/ca/ca.crt"' in script
    assert '"/CN=$client-client/O=Open Security Lakehouse"' in script
    assert 'retired="$root/retired/$client-$timestamp"' in script
    assert 'install -m 0600 "$staging/client.key"' in script


def test_linux_forwarder_requires_named_mtls_peer_and_durable_queue() -> None:
    config = (ROOT / "infrastructure" / "rsyslog" / "60-osl.conf").read_text()
    assert 'port="6514"' in config
    assert 'StreamDriver="gtls"' in config
    assert 'StreamDriverMode="1"' in config
    assert 'StreamDriverAuthMode="x509/name"' in config
    assert 'StreamDriverPermittedPeers="osl-syslog"' in config
    assert 'queue.saveOnShutdown="on"' in config
    installer = (ROOT / "scripts" / "install-homelab-autocollection.sh").read_text()
    assert 'required_rsyslog_gnutls="8.2512.0-1ubuntu4.2"' in installer
    assert "dpkg-query" in installer
    assert 'certificate_target="/etc/rsyslog.d/osl-mtls"' in installer
    assert "chmod 0711 /etc/osl" not in installer
    assert "-g syslog -m 0750" in installer
    assert "-g syslog -m 0640" in installer
    assert "-m 0660" not in installer
    assert "/etc/rsyslog.d/osl-mtls/client.key" in config


def test_compose_exposes_parallel_mtls_listener_with_private_keys_read_only() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    assert "${SYSLOG_MTLS_PORT:-6514}:6514/tcp" in compose
    assert "./data/mtls/server/server.key:/etc/osl/mtls/server.key:ro" in compose
    assert "./data/mtls/ca/ca.crt:/etc/osl/mtls/ca.crt:ro" in compose


def test_seaweed_volume_capacity_is_configurable_with_safe_homelab_default() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    example_env = (ROOT / ".env.example").read_text()
    assert "-max=${SEAWEED_VOLUME_MAX:-64}" in compose
    assert "SEAWEED_VOLUME_MAX=64" in example_env


def test_encrypted_backup_includes_collector_authority() -> None:
    backup = (ROOT / "scripts" / "backup.sh").read_text()
    assert 'tar -C data/mtls -cf "$stage/mtls.tar" .' in backup
    assert "mtls.tar" in backup
