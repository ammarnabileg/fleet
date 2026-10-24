from app.core.db import new_session
from app.modules.accidents import service
from app.worker import celery


@celery.task(name="accidents.scan_police_reports")
def scan_police_reports() -> int:
    with new_session() as db:
        return service.scan_police_reports(db)
