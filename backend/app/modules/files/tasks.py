from app.core.db import new_session
from app.modules.files import service
from app.worker import celery


@celery.task(name="files.sync")
def sync() -> dict[str, int]:
    """Every few minutes: a few minutes of copying, each way the control panel's choice asks."""
    with new_session() as db:
        return service.run_sync(db, 240)
