import signal

from apscheduler.schedulers.blocking import BlockingScheduler

from .database import SessionLocal
from .detection import execute_rule, load_rules
from .storage import ensure_bucket


def run_rule(rule_id: str) -> None:
    rule = next((item for item in load_rules() if item.id == rule_id), None)
    if rule is None or not rule.enabled:
        return
    with SessionLocal() as db:
        execute_rule(rule, db)


def main() -> None:
    ensure_bucket()
    scheduler = BlockingScheduler(timezone="UTC")
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
