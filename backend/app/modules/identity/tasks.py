from app.core.db import new_session
from app.modules.identity import service
from app.worker import celery


@celery.task(name="identity.check_messaging_channel")
def check_messaging_channel() -> str:
    with new_session() as db:
        return service.check_messaging_channel(db)
