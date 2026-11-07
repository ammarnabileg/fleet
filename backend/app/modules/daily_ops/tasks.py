from app.core.db import new_session
from app.modules.daily_ops import service
from app.worker import celery


@celery.task(name="daily_ops.scan_overdue")
def scan_overdue() -> int:
    with new_session() as db:
        return service.scan_overdue(db)


@celery.task(name="daily_ops.scan_missing")
def scan_missing() -> int:
    """Late evening: who started the day and sent no report."""
    with new_session() as db:
        return service.scan_missing(db)
