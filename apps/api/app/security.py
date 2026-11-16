import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

bearer = HTTPBearer(auto_error=False)


def require_api_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = get_settings().osl_api_token.get_secret_value()
    supplied = (
        credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    )
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
