# ADR 0007: Mutual TLS for network collectors

## Status

Accepted.

## Decision

Expose a parallel RFC5425-style TLS syslog listener on TCP 6514. Vector presents a server
certificate issued by an OSL-local CA and requires every network collector to present a
valid client certificate from that CA. Linux and Windows receive distinct client keys.
Certificate metadata is retained in the raw event under `tls_client`.

The existing TCP 5514 listener remains temporarily available during migration. It stays
CIDR-restricted and must be removed after both collectors have been observed on 6514. Docker
collectors run on the same host over loopback and do not use this network trust path.

Private keys live under the ignored `data/mtls` directory, are mounted read-only, and are
included only in the encrypted platform backup. Certificate generation refuses to overwrite
an existing authority. Rotation creates a new authority or a deliberately signed replacement;
it is never performed implicitly during deployment.

The native Ubuntu sender uses `rsyslog-gnutls` pinned to `8.2512.0-1ubuntu4.2`, matching the
installed rsyslog core. Its upstream licensing is GPL-3.0+/Apache-2.0 (with LGPL-3.0+ and
BSD-3-Clause components). The package is installed explicitly by the operator; the collector
installer validates the exact version and does not mutate system packages.

## Consequences

Possession of a shared bearer token is no longer sufficient to inject network syslog. A
collector must also possess its own private key. Certificate expiry and revocation become
operator responsibilities. This initial CA has no online revocation service; compromise of a
client key requires issuing a replacement CA or deploying a CRL-aware follow-up.
