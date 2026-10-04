from app.core.db import new_session
from app.modules.cash import service
from app.worker import celery


@celery.task(name="cash.check_invariants")
def check_invariants() -> list[str]:
    with new_session() as db:
        return service.check_invariants(db)
