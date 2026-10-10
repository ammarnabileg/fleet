from app.core.db import new_session
from app.modules.notifications import service
from app.worker import celery


@celery.task(name="notifications.push")
def push() -> int:
    """The drivers' new notices to their phones, once push is set up in the control panel."""
    with new_session() as db:
        return service.push_pending(db)
