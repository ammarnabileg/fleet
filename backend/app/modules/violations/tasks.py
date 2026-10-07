from app.core.db import new_session
from app.modules.violations import service
from app.worker import celery


@celery.task(name="violations.finalize_due")
def finalize_due() -> int:
    with new_session() as db:
        return service.finalize_due(db)
