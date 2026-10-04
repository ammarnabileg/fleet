from app.core.db import new_session
from app.modules.identity import link_queue, service
from app.worker import celery


@celery.task(name="identity.send_queued_link")
def send_queued_link() -> str:
    with new_session() as db:
        return link_queue.send_next(db)


@celery.task(name="identity.check_messaging_channel")
def check_messaging_channel() -> str:
    with new_session() as db:
        return service.check_messaging_channel(db)
