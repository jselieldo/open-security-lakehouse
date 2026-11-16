from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status

from .database import check_database, initialize_database
from .security import require_api_token
from .storage import check_storage, ensure_bucket


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    ensure_bucket()
    yield


app = FastAPI(
    title="Open Security Lakehouse API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready() -> dict[str, str]:
    failures: list[str] = []
    for name, check in (("database", check_database), ("object_storage", check_storage)):
        try:
            check()
        except Exception:
            failures.append(name)
    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "failed_dependencies": failures},
        )
    return {"status": "ready", "database": "ok", "object_storage": "ok"}


@app.get("/api/v1/system/info", dependencies=[Depends(require_api_token)], tags=["system"])
def system_info() -> dict[str, str]:
    return {"name": "Open Security Lakehouse", "milestone": "1", "version": "0.1.0"}
