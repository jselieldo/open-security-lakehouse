from apscheduler.schedulers.background import BackgroundScheduler

from .config import get_settings
from .database import SessionLocal
from .detection import execute_rule, load_rules

scheduler = BackgroundScheduler(timezone="UTC")


def start_scheduler() -> None:
    if not get_settings().detection_scheduler_enabled or scheduler.running:
        return
    for rule in load_rules():
        if rule.enabled:
            scheduler.add_job(
                _run_scheduled_rule,
                "interval",
                minutes=rule.schedule_minutes,
                args=[rule.id],
                id=f"detection:{rule.id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _run_scheduled_rule(rule_id: str) -> None:
    rule = next((item for item in load_rules() if item.id == rule_id), None)
    if rule is None or not rule.enabled:
        return
    with SessionLocal() as db:
        execute_rule(rule, db)
