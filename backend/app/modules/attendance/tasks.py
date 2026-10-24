from app.core.db import new_session
from app.modules.attendance import service
from app.worker import celery


@celery.task(name="attendance.scan_followups")
def scan_followups() -> int:
    """Daily: the follow-up alert on the absence requests open for the settings' days (absence_followup_days)."""
    with new_session() as db:
        return service.scan_followups(db)
