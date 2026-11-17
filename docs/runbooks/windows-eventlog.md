# Windows Event Log collector

The first Windows source uses Vector `0.61.0` (MPL-2.0) and its native
`windows_event_log` source. The version matches the server-side Vector image and
is intentionally pinned. Vector keeps checkpoints and its durable buffer below
`C:\ProgramData\OpenSecurityLakehouse\vector-data`.

## Security boundary

The OSL API remains loopback-only. Windows sends RFC 5424-compatible records to
the existing TCP syslog listener on `192.168.3.120:5514`; Vector on the homelab
then authenticates to the internal ingestion API with its ingestion-only token.
The listener is CIDR-restricted and must never be exposed to the Internet.

This initial LAN transport is not encrypted. Use it only on the trusted homelab
segment. Do not onboard laptops on untrusted Wi-Fi. A future mTLS transport is
required before using this collector across routed, shared or hostile networks.

## Install and validate

1. Download the pinned MSI from the official Vector repository:
   `https://install.datadoghq.com/vector/0.61.0/vector-0.61.0-x64.msi`.
2. Verify its SHA-256 before installation. The expected value for the 0.61.0
   x64 MSI is
   `3ac167f226204e141d164c6218ae54a2df77dda1b3322bef4b565d4066c4cfad`.
   The MSI does not carry an Authenticode signature, so a matching published
   checksum is mandatory.
3. Run the MSI as an administrator; the package rejects non-elevated installs.
4. Verify that the installed binary reports `vector 0.61.0`.
5. Copy `infrastructure/vector-windows/vector.yaml` to
   `C:\Program Files\Vector\config\vector.yaml` as an administrator.
6. Confirm that `192.168.3.120` is still the homelab address and restrict
   `SYSLOG_ALLOWED_CIDR` in the homelab `.env` to `192.168.3.0/24`.
7. Validate and run the configuration:

   ```powershell
   & 'C:\Program Files\Vector\bin\vector.exe' validate `
     'C:\Program Files\Vector\config\vector.yaml'
   & 'C:\Program Files\Vector\bin\vector.exe' --config `
     'C:\Program Files\Vector\config\vector.yaml'
   ```

Reading the Security channel requires an account with permission to read it. Do
not grant local administrator access solely for Vector; prefer the built-in Event
Log Readers group where it is sufficient. The initial start reads at most the
previous hour and then resumes from durable per-channel checkpoints. Event-data
fields are limited to 4096 bytes and raw XML is disabled.

## Register and verify the source

Register it from the homelab with an administrator access token:

```bash
curl --fail -X POST http://127.0.0.1:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"source_id":"windows-workstation","source":"windows-eventlog","kind":"windows","hostname":"WINDOWS-HOSTNAME","display_name":"Windows workstation","expected_interval_minutes":60}'
```

Generate or locate a harmless Application event, then filter the OSL console by
source `windows-eventlog`, hostname and event type. Raw Windows fields remain in
the immutable raw object and in the normalized row's `raw_event_json`.

## Data minimization

Windows logs can contain usernames, process command lines, file paths and IP
addresses. Access them only through OSL roles, keep the API private, and apply a
retention policy before expanding collection to additional channels.
