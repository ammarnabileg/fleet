from app.core.db import new_session
from app.modules.cash import service
from app.worker import celery


@celery.task(name="cash.check_invariants")
def check_invariants() -> list[str]:
    with new_session() as db:
        return service.check_invariants(db)


@celery.task(name="cash.scan_treasury")
def scan_treasury(moment: str = "morning") -> int:
    """The treasury's deposit rule: the deposit-day alerts in the morning, closed at the end of the day."""
    with new_session() as db:
        return service.scan_treasury(db, moment=moment)
