from app.core.db import new_session
from app.modules.finance import service
from app.worker import celery


@celery.task(name="finance.post_entries")
def post_entries() -> dict:
    """Draft entries for the last 45 days' documents without one: the accountant finds them in the morning."""
    with new_session() as db:
        result = service.auto_post(db)
        return {"created": result["created"], "stale": len(result["stale"]), "errors": len(result["errors"])}
