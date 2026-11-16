from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.database import AuditLog, Base, SessionLocal, engine
from app.security import Principal, _decode_oidc_token, require_roles
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request


def request(path: str = "/api/v1/audit") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


def principal(*roles: str) -> Principal:
    return Principal("subject-1", "analyst", None, None, frozenset(roles), "oidc")


def test_oidc_claims_are_mapped_to_supported_roles() -> None:
    claims = {
        "sub": "subject-1",
        "preferred_username": "analyst",
        "realm_access": {"roles": ["viewer", "analyst", "unknown-role"]},
    }
    jwk = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key="key"))
    with patch("app.security._jwk_client", return_value=jwk), patch(
        "app.security.jwt.decode", return_value=claims
    ) as decode:
        result = _decode_oidc_token("token")
    assert result.roles == frozenset({"viewer", "analyst"})
    assert decode.call_args.kwargs["audience"] == "osl-api"
    assert decode.call_args.kwargs["issuer"].endswith("/realms/osl")


def test_rbac_denies_and_audits_missing_role() -> None:
    Base.metadata.create_all(bind=engine)
    dependency = require_roles("admin")
    with pytest.raises(HTTPException) as error:
        dependency(request(), principal("analyst"))
    assert error.value.status_code == 403
    with SessionLocal() as db:
        entry = db.scalar(select(AuditLog).order_by(AuditLog.created_at.desc()))
    assert entry is not None
    assert entry.outcome == "denied"
    assert entry.resource == "/api/v1/audit"


def test_admin_bypasses_specific_role_requirement() -> None:
    dependency = require_roles("ingestor")
    result = dependency(request("/api/v1/ingestion/batches"), principal("admin"))
    assert result.username == "analyst"


def test_unknown_role_in_route_configuration_fails_fast() -> None:
    with pytest.raises(ValueError):
        require_roles("superuser")
