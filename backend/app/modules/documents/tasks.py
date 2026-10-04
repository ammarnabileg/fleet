from app.core.db import new_session
from app.modules.documents import service
from app.modules.fleet import service as fleet
from app.modules.org import service as org
from app.modules.people import service as people
from app.worker import celery


def _label(db):
    def label_of(owner_type: str, owner_id: int):
        if owner_type == "employee":
            return people.names(db, [owner_id]).get(owner_id, {}).get("name", "")
        if owner_type == "vehicle":
            return fleet.plate_numbers(db, [owner_id]).get(owner_id, "")
        return next(
            (c["name"] for c in org.list_companies(db, all_companies=True, company_ids=()) if c["id"] == owner_id), ""
        )

    return label_of


@celery.task(name="documents.scan_expiring")
def scan_expiring() -> int:
    with new_session() as db:
        return service.scan_expiring(db, _label(db))
