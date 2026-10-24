from app.core.db import new_session
from app.modules.tracking import service
from app.worker import celery


@celery.task(name="tracking.scan_signal_loss")
def scan_signal_loss() -> int:
    with new_session() as db:
        return service.scan_signal_loss(db)


@celery.task(name="tracking.maintain_partitions")
def maintain_partitions() -> None:
    with new_session() as db:
        service.maintain_partitions(db)
