from app.core.db import new_session
from app.modules.approvals import service
from app.worker import celery


@celery.task(name="approvals.escalate")
def escalate() -> int:
    """Steps that waited longer than their workflow allows: opened to the escalation role, with an alert."""
    with new_session() as db:
        return service.escalate(db)
