"""The filters every report takes (BRD FR-RPT-08): company, branch, driver, vehicle, besides its period.

The company narrows the user's own scope (never widens it); a driver or a vehicle is looked up within that scope, so a
filter can't reach another company's records. Each report applies the branch, the driver and the vehicle where its
records have them.
"""

import uuid
from dataclasses import dataclass

from fastapi import Query
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.fleet import service as fleet
from app.modules.org import service as org
from app.modules.people import service as people


@dataclass(frozen=True)
class Filters:
    branch_id: int | None = None
    driver_id: int | None = None  # internal ids, found within the scope
    vehicle_id: int | None = None


@dataclass(frozen=True)
class FilterParams:
    company_id: int | None
    branch_id: int | None
    driver_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None


def params(
    company_id: int | None = Query(None),
    branch_id: int | None = Query(None),
    driver_id: uuid.UUID | None = Query(None),
    vehicle_id: uuid.UUID | None = Query(None),
) -> FilterParams:
    return FilterParams(company_id, branch_id, driver_id, vehicle_id)


def resolve(db: Session, p: FilterParams, *, all_companies: bool, company_ids) -> tuple[dict, Filters]:
    """The scope narrowed to the company asked for, and the other filters as internal ids."""
    scope = {"all_companies": all_companies, "company_ids": list(company_ids)}
    if p.company_id is not None:
        if not all_companies and p.company_id not in scope["company_ids"]:
            raise AppError(403, "company_out_of_scope")
        scope = {"all_companies": False, "company_ids": [p.company_id]}
    if p.branch_id is not None and p.branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")
    driver = people.ref_by_public_id(db, p.driver_id, **scope).id if p.driver_id else None
    vehicle = fleet.vehicle_ref_by_public_id(db, p.vehicle_id, **scope).id if p.vehicle_id else None
    return scope, Filters(p.branch_id, driver, vehicle)
