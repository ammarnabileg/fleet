from app.core.db import new_session
from app.modules.maintenance import service
from app.worker import celery


@celery.task(name="maintenance.scan_due")
def scan_due() -> int:
    """Daily: periodic schedules due or overdue, and repairs late at the center (escalated as the settings say)."""
    with new_session() as db:
        return service.scan_due(db)
