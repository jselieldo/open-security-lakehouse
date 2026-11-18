#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


EXPECTED = {
    "ca": ("ca/ca.crt", "CN=OSL Collector CA"),
    "server": ("server/server.crt", "CN=server"),
    "homelab": ("clients/homelab/client.crt", "CN=homelab-client"),
    "windows": ("clients/windows/client.crt", "CN=windows-client"),
}
ALLOWED_CERTIFICATES = {
    "ca/ca.crt",
    "server/server.crt",
    "clients/homelab/ca.crt",
    "clients/homelab/client.crt",
    "clients/windows/ca.crt",
    "clients/windows/client.crt",
}


def openssl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["openssl", *arguments],
        check=check,
        capture_output=True,
        text=True,
    )


def inspect_certificate(root: Path, name: str, relative: str, expected_cn: str, days: int) -> dict:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"missing certificate: {relative}")
    ca = root / "ca/ca.crt"
    openssl("verify", "-CAfile", str(ca), str(path))
    details = openssl(
        "x509",
        "-in",
        str(path),
        "-noout",
        "-subject",
        "-issuer",
        "-serial",
        "-fingerprint",
        "-sha256",
        "-startdate",
        "-enddate",
        "-nameopt",
        "RFC2253",
    ).stdout.splitlines()
    fields = dict(line.split("=", 1) for line in details if "=" in line)
    subject = fields.get("subject", "")
    if expected_cn not in subject.split(","):
        raise ValueError(f"unexpected subject for {name}: {subject}")
    not_after_text = fields["notAfter"]
    not_after = datetime.strptime(not_after_text, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    remaining_seconds = max(0, int((not_after - datetime.now(UTC)).total_seconds()))
    threshold_ok = openssl(
        "x509", "-in", str(path), "-checkend", str(days * 86400), "-noout", check=False
    ).returncode == 0
    return {
        "name": name,
        "path": relative,
        "subject": subject,
        "issuer": fields.get("issuer"),
        "serial": fields.get("serial"),
        "sha256_fingerprint": fields.get("sha256 Fingerprint"),
        "not_before": fields.get("notBefore"),
        "not_after": not_after.isoformat(),
        "days_remaining": remaining_seconds // 86400,
        "valid_beyond_threshold": threshold_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the OSL mTLS certificate inventory")
    parser.add_argument("--root", type=Path, default=Path("data/mtls"))
    parser.add_argument("--warning-days", type=int, default=30)
    parser.add_argument("--emit-syslog", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.warning_days <= 365:
        parser.error("--warning-days must be between 1 and 365")

    root = arguments.root.resolve()
    errors: list[str] = []
    certificates: list[dict] = []
    try:
        observed = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*.crt")
            if "retired" not in path.parts
        }
        unexpected = sorted(observed - ALLOWED_CERTIFICATES)
        if unexpected:
            errors.append(f"unexpected certificates: {', '.join(unexpected)}")
        for name, (relative, expected_cn) in EXPECTED.items():
            try:
                item = inspect_certificate(
                    root, name, relative, expected_cn, arguments.warning_days
                )
                certificates.append(item)
                if not item["valid_beyond_threshold"]:
                    errors.append(
                        f"{name} expires within {arguments.warning_days} days"
                    )
            except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as error:
                errors.append(str(error))
    except OSError as error:
        errors.append(str(error))

    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "warning_days": arguments.warning_days,
        "status": "ok" if not errors else "error",
        "certificates": certificates,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if errors and arguments.emit_syslog:
        subprocess.run(
            [
                "logger",
                "-p",
                "authpriv.err",
                "-t",
                "osl-certificates",
                "OSL mTLS certificate check failed: " + "; ".join(errors),
            ],
            check=False,
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
