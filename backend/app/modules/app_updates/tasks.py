from app.core.db import new_session
from app.modules.app_updates import github
from app.worker import celery


@celery.task(name="app_updates.import_github")
def import_github() -> bool:
    """The repository's latest GitHub release as a draft, when «تحديث التطبيق» asks for it (off by default)."""
    with new_session() as db:
        return github.auto_import(db)
