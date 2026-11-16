# Repository guidance

- Keep data-plane and control-plane contracts separate.
- Never commit `.env`, credentials, generated data, or test secrets used outside tests.
- PostgreSQL is for operational metadata; security telemetry belongs in object storage.
- New dependencies must have a documented license and a pinned version.
- Add tests for authentication, dependency failures, and every new public endpoint.

