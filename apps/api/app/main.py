from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import (
    Alert,
    DetectionRun,
    IngestionBatch,
    check_database,
    get_db,
    initialize_database,
)
from .detection import (
    execute_rule,
    get_alert_evidence,
    get_rule,
    list_alerts,
    load_rules,
)
from .ingestion import (
    BatchConflictError,
    BatchTooLargeError,
    get_batch_status,
    ingest_batch,
)
from .investigation import investigate
from .scheduler import start_scheduler, stop_scheduler
from .schemas import (
    AlertResponse,
    BatchStatusResponse,
    DashboardSummary,
    DetectionRuleResponse,
    DetectionRunResponse,
    IngestionRequest,
    IngestionResponse,
    InvestigationRequest,
    InvestigationResponse,
)
from .security import require_api_token
from .storage import check_storage, ensure_bucket


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    ensure_bucket()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Open Security Lakehouse API",
    version="0.5.0",
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
    return {"name": "Open Security Lakehouse", "milestone": "5", "version": "0.5.0"}


@app.post(
    "/api/v1/ingestion/batches",
    response_model=IngestionResponse,
    dependencies=[Depends(require_api_token)],
    tags=["ingestion"],
)
def create_ingestion_batch(
    payload: IngestionRequest, db: Session = Depends(get_db)
) -> IngestionResponse:
    try:
        return ingest_batch(payload, db)
    except BatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/v1/ingestion/batches/{batch_id}",
    response_model=BatchStatusResponse,
    dependencies=[Depends(require_api_token)],
    tags=["ingestion"],
)
def read_ingestion_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchStatusResponse:
    batch = get_batch_status(batch_id, db)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
    return batch


@app.post(
    "/api/v1/investigations/search",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_api_token)],
    tags=["investigations"],
)
def search_security_events(payload: InvestigationRequest) -> InvestigationResponse:
    return investigate(payload)


@app.get(
    "/api/v1/detections/rules",
    response_model=list[DetectionRuleResponse],
    dependencies=[Depends(require_api_token)],
    tags=["detections"],
)
def read_detection_rules() -> list[DetectionRuleResponse]:
    return [DetectionRuleResponse.model_validate(rule.model_dump()) for rule in load_rules()]


@app.post(
    "/api/v1/detections/rules/{rule_id}/run",
    response_model=DetectionRunResponse,
    dependencies=[Depends(require_api_token)],
    tags=["detections"],
)
def run_detection_rule(rule_id: str, db: Session = Depends(get_db)) -> DetectionRunResponse:
    rule = get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule not found")
    if not rule.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="rule is disabled")
    return execute_rule(rule, db)


@app.get(
    "/api/v1/alerts",
    response_model=list[AlertResponse],
    dependencies=[Depends(require_api_token)],
    tags=["alerts"],
)
def read_alerts(limit: int = 100, db: Session = Depends(get_db)) -> list[AlertResponse]:
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid limit"
        )
    return list_alerts(db, limit)


@app.get(
    "/api/v1/alerts/{alert_id}/evidence",
    dependencies=[Depends(require_api_token)],
    tags=["alerts"],
)
def read_alert_evidence(alert_id: str, db: Session = Depends(get_db)) -> dict:
    evidence = get_alert_evidence(alert_id, db)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    return evidence


@app.get(
    "/api/v1/dashboard/summary",
    response_model=DashboardSummary,
    dependencies=[Depends(require_api_token)],
    tags=["dashboard"],
)
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    batches = db.scalar(select(func.count()).select_from(IngestionBatch)) or 0
    accepted = db.scalar(select(func.coalesce(func.sum(IngestionBatch.accepted_count), 0))) or 0
    quarantined = db.scalar(select(func.coalesce(func.sum(IngestionBatch.rejected_count), 0))) or 0
    open_alerts = (
        db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open")) or 0
    )
    runs = db.scalar(select(func.count()).select_from(DetectionRun)) or 0
    return DashboardSummary(
        milestone="5",
        platform_status="operational",
        ingestion_batches=batches,
        accepted_events=accepted,
        quarantined_events=quarantined,
        detection_rules=len(load_rules()),
        open_alerts=open_alerts,
        detection_runs=runs,
        latest_alerts=list_alerts(db, 5),
    )


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/console/")


console_dir = Path("/app/console")
if not console_dir.exists():
    console_dir = Path(__file__).resolve().parents[2] / "console"
app.mount("/console", StaticFiles(directory=console_dir, html=True), name="console")
