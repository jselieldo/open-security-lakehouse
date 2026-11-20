import signal
from datetime import UTC, datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from .asset_monitor import process_asset_changes
from .config import get_settings
from .database import SessionLocal
from .detection import execute_rule, load_rules
from .source_health import check_source_health
from .storage import ensure_bucket


def run_rule(rule_id: str) -> None:
    rule = next((item for item in load_rules() if item.id == rule_id), None)
    if rule is None or not rule.enabled:
        return
    with SessionLocal() as db:
        execute_rule(rule, db)


def run_source_health() -> None:
    with SessionLocal() as db:
        check_source_health(db)


def run_asset_monitor() -> None:
    with SessionLocal() as db:
        process_asset_changes(db)


def main() -> None:
    ensure_bucket()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_source_health,
        "interval",
        minutes=get_settings().source_health_check_minutes,
        id="source-health",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        run_asset_monitor,
        "interval",
        minutes=get_settings().source_health_check_minutes,
        id="asset-monitor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC),
    )
    for rule in load_rules():
        if rule.enabled:
            scheduler.add_job(
                run_rule,
                "interval",
                minutes=rule.schedule_minutes,
                args=[rule.id],
                id=f"detection:{rule.id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
    signal.signal(signal.SIGTERM, lambda *_: scheduler.shutdown(wait=False))
    scheduler.start()


if __name__ == "__main__":
    main()
