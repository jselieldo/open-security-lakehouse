import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import get_settings
from .database import AuditLog, SessionLocal, User

bearer = HTTPBearer(auto_error=False)
SUPPORTED_ROLES = frozenset({"viewer", "ingestor", "analyst", "admin"})


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    email: str | None
    display_name: str | None
    roles: frozenset[str]
    auth_method: str


def _unauthorized(detail: str = "Invalid or missing bearer token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def _legacy_principal(token: str) -> Principal | None:
    settings = get_settings()
    if settings.auth_mode not in {"static", "hybrid"}:
        return None
    expected = settings.osl_api_token.get_secret_value()
    if not hmac.compare_digest(token, expected):
        return None
    return Principal(
        subject="legacy-static-token",
        username="legacy-admin",
        email=None,
        display_name="Legacy administrator",
        roles=SUPPORTED_ROLES,
        auth_method="static",
    )


def _collector_principal(token: str) -> Principal | None:
    configured = get_settings().collector_api_token
    if configured is None or not hmac.compare_digest(token, configured.get_secret_value()):
        return None
    return Principal(
        subject="collector:vector-linux-syslog",
        username="vector-linux-syslog",
        email=None,
        display_name="Vector Linux/syslog collector",
        roles=frozenset({"ingestor"}),
        auth_method="collector_token",
    )


def _decode_oidc_token(token: str) -> Principal:
    settings = get_settings()
    if settings.auth_mode not in {"oidc", "hybrid"}:
        raise _unauthorized()
    try:
        signing_key = _jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    roles = frozenset(claims.get("realm_access", {}).get("roles", [])) & SUPPORTED_ROLES
    return Principal(
        subject=str(claims["sub"]),
        username=str(claims.get("preferred_username", claims["sub"])),
        email=claims.get("email"),
        display_name=claims.get("name"),
        roles=roles,
        auth_method="oidc",
    )


def _record_access(
    principal: Principal,
    request: Request,
    outcome: str,
    details: dict | None = None,
) -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = db.get(User, principal.subject)
        if user is None:
            user = User(
                subject=principal.subject,
                username=principal.username,
                email=principal.email,
                display_name=principal.display_name,
                roles_json=json.dumps(sorted(principal.roles)),
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(user)
        else:
            user.username = principal.username
            user.email = principal.email
            user.display_name = principal.display_name
            user.roles_json = json.dumps(sorted(principal.roles))
            user.last_seen_at = now
        db.add(
            AuditLog(
                audit_id=str(uuid4()),
                actor_subject=principal.subject,
                actor_username=principal.username,
                action=request.method,
                resource=request.url.path,
                outcome=outcome,
                details_json=json.dumps(details or {}, sort_keys=True),
                client_ip=request.client.host if request.client else None,
                created_at=now,
            )
        )
        db.commit()


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    token = credentials.credentials
    principal = _legacy_principal(token)
    if principal is None:
        principal = _collector_principal(token)
    if principal is None:
        principal = _decode_oidc_token(token)
    _record_access(principal, request, "allowed")
    return principal


def require_roles(*required_roles: str):
    invalid = set(required_roles) - SUPPORTED_ROLES
    if invalid:
        raise ValueError(f"Unsupported roles: {sorted(invalid)}")

    def dependency(
        request: Request,
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if "admin" not in principal.roles and not principal.roles.intersection(required_roles):
            _record_access(
                principal,
                request,
                "denied",
                {"required_roles": sorted(required_roles)},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency


def require_api_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    supplied = (
        credentials.credentials
        if credentials and credentials.scheme.lower() == "bearer"
        else ""
    )
    if _legacy_principal(supplied) is None:
        raise _unauthorized()
