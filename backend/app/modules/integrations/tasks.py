from app.core.db import new_session
from app.modules.integrations import service
from app.worker import celery


@celery.task(name="integrations.relay_outbox")
def relay_outbox() -> int:
    total = 0
    with new_session() as db:
        while (n := service.relay_once(db)) > 0:
            total += n
    return total
