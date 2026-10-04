"""Employees on the papers of a company (legal entity), their employment status and its history.

Salary and IBAN are visible and settable only with employees.view_salary, and never written to the audit log
(which other roles can read): the log records only that they changed.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import like_pattern, violated_constraint
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.org import service as org
from app.modules.people.models import Employee, EmploymentStatus, ExternalRef, StatusHistory

FIELDS = (
    "employee_number",
    "name",
    "civil_id",
    "nationality",
    "company_id",
    "branch_id",
    "department",
    "job_title",
    "is_driver",
    "phone",
    "hire_date",
)
SALARY_FIELDS = ("basic_salary", "iban")
REQUIRED = ("employee_number", "name", "company_id", "branch_id", "is_driver")
UNIQUE_ERRORS = {
    "employees_employee_number_key": "employee_number_taken",
    "employees_civil_id_key": "civil_id_taken",
    "employees_phone_idx": "phone_taken",
}


@dataclass(frozen=True)
class EmployeeRef:
    """What other modules need to know about an employee."""

    id: int
    public_id: uuid.UUID
    name: dict
    company_id: int
    is_driver: bool
    phone: str | None
    status_code: str
    is_working: bool
    is_terminal: bool
    app_access: str

    @property
    def can_use_app(self) -> bool:
        return self.is_driver and self.app_access == "active" and not self.is_terminal


# ------------------------------------------------------------------ statuses (configurable)


def _status_out(s: EmploymentStatus) -> dict:
    return {
        "code": s.code,
        "name": s.name,
        "is_working": s.is_working,
        "is_terminal": s.is_terminal,
        "is_active": s.is_active,
        "sort_order": s.sort_order,
    }


def list_statuses(db: Session) -> list[dict]:
    q = select(EmploymentStatus).order_by(EmploymentStatus.sort_order, EmploymentStatus.code)
    return [_status_out(s) for s in db.scalars(q)]


def create_status(db: Session, data: dict, *, actor_user_id: int) -> dict:
    if db.get(EmploymentStatus, data["code"]):
        raise AppError(409, "status_exists")
    status = EmploymentStatus(**{**data, "name": i18n.validate_localized(db, data["name"])}, is_active=True)
    db.add(status)
    db.flush()
    out = _status_out(status)
    audit.record(
        db,
        action="employment_status.created",
        entity_type="employment_status",
        entity_id=status.code,
        actor_user_id=actor_user_id,
        after=out,
    )
    db.commit()
    return out


def update_status(db: Session, code: str, changes: dict, *, actor_user_id: int) -> dict:
    status = db.get(EmploymentStatus, code)
    if status is None:
        raise AppError(404, "status_not_found")
    before = _status_out(status)
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    for field in ("name", "is_working", "is_terminal", "is_active", "sort_order"):
        if field in changes:
            setattr(status, field, changes[field])
    db.flush()
    after = _status_out(status)
    audit.record(
        db,
        action="employment_status.updated",
        entity_type="employment_status",
        entity_id=code,
        actor_user_id=actor_user_id,
        before=before,
        after=after,
    )
    db.commit()
    return after


def _active_status(db: Session, code: str) -> EmploymentStatus:
    status = db.get(EmploymentStatus, code)
    if status is None or not status.is_active:
        raise AppError(422, "status_not_found")
    return status


# ------------------------------------------------------------------ employees


def _out(e: Employee, status: EmploymentStatus, show_salary: bool) -> dict:
    out = {
        "id": str(e.public_id),
        **{f: getattr(e, f) for f in FIELDS},
        "status_code": e.status_code,
        "status_name": status.name,
        "is_terminal": status.is_terminal,
        "app_access": e.app_access,
        "version": e.version,
    }
    out.update({f: getattr(e, f) for f in SALARY_FIELDS} if show_salary else dict.fromkeys(SALARY_FIELDS))
    return out


def _snapshot(e: Employee) -> dict:
    """For the audit log: never the salary fields themselves."""
    return {
        "id": str(e.public_id),
        **{f: getattr(e, f) for f in FIELDS},
        "status_code": e.status_code,
        "app_access": e.app_access,
        "version": e.version,
    }


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Employee.company_id.in_(list(company_ids)))


def _get(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int], lock: bool = False) -> Employee:
    q = _scoped(select(Employee).where(Employee.public_id == public_id), all_companies, company_ids)
    employee = db.scalar(q.with_for_update() if lock else q)
    if employee is None:
        raise AppError(404, "employee_not_found")
    return employee


def _check_company(db: Session, company_id: int, all_companies: bool, company_ids: Iterable[int]) -> None:
    if not org.company_ids_exist(db, [company_id]):
        raise AppError(422, "company_not_found")
    if not (all_companies or company_id in set(company_ids)):
        raise AppError(403, "company_out_of_scope")


def _check_branch(db: Session, branch_id: int) -> None:
    if branch_id not in {b["id"] for b in org.list_branches(db)}:
        raise AppError(422, "branch_not_found")


def _flush_unique(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        # no rollback here: the caller's transaction (or savepoint) decides
        code = UNIQUE_ERRORS.get(violated_constraint(exc))
        if code is None:
            raise
        raise AppError(409, code) from None


def list_employees(
    db: Session,
    *,
    all_companies: bool,
    company_ids: Iterable[int],
    show_salary: bool,
    company_id: int | None = None,
    status_code: str | None = None,
    is_driver: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query = _scoped(
        select(Employee, EmploymentStatus)
        .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
        .order_by(Employee.employee_number)
        .limit(min(limit, 200))
        .offset(offset),
        all_companies,
        company_ids,
    )
    if company_id is not None:
        query = query.where(Employee.company_id == company_id)
    if status_code:
        query = query.where(Employee.status_code == status_code)
    if is_driver is not None:
        query = query.where(Employee.is_driver.is_(is_driver))
    if q:
        pattern = like_pattern(q.strip())
        query = query.where(
            or_(
                Employee.employee_number.ilike(pattern),
                Employee.civil_id.ilike(pattern),
                Employee.phone.ilike(pattern),
                cast(Employee.name, Text).ilike(pattern),
            )
        )
    return [_out(e, s, show_salary) for e, s in db.execute(query)]


def get_employee(db: Session, public_id, *, show_salary: bool, **scope) -> dict:
    e = _get(db, public_id, **scope)
    return _out(e, db.get(EmploymentStatus, e.status_code), show_salary)


def create_employee(
    db: Session, data: dict, *, can_set_salary: bool, actor_user_id: int, commit: bool = True, **scope
) -> dict:
    if not can_set_salary and any(data.get(f) is not None for f in SALARY_FIELDS):
        raise AppError(403, "permission_denied", permission="employees.view_salary")
    _check_company(db, data["company_id"], **scope)
    data = {**data, "name": i18n.validate_localized(db, data["name"])}
    data["branch_id"] = data.get("branch_id") or org.default_branch_id(db)
    _check_branch(db, data["branch_id"])
    status = _active_status(db, data.get("status_code") or "active")
    if data["is_driver"] and not data.get("phone"):
        raise AppError(422, "driver_phone_required")
    employee = Employee(**{**data, "status_code": status.code}, app_access="none")
    db.add(employee)
    _flush_unique(db)
    db.refresh(employee)
    db.add(StatusHistory(employee_id=employee.id, status_code=status.code, changed_by=actor_user_id))
    audit.record(
        db,
        action="employee.created",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        after={**_snapshot(employee), "salary_set": any(data.get(f) is not None for f in SALARY_FIELDS)},
    )
    emit(
        db,
        "employee.created",
        employee.public_id,
        {"employee_id": str(employee.public_id), "company_id": employee.company_id},
    )
    if commit:
        db.commit()
    return _out(employee, status, can_set_salary)


def update_employee(
    db: Session,
    public_id,
    *,
    version: int,
    changes: dict,
    can_set_salary: bool,
    actor_user_id: int,
    commit: bool = True,
    **scope,
) -> dict:
    employee = _get(db, public_id, lock=True, **scope)
    if employee.version != version:
        raise AppError(409, "version_conflict")
    salary_changes = [f for f in SALARY_FIELDS if f in changes]
    if salary_changes and not can_set_salary:
        raise AppError(403, "permission_denied", permission="employees.view_salary")
    before = _snapshot(employee)
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    if "company_id" in changes and changes["company_id"] != employee.company_id:
        _check_company(db, changes["company_id"], **scope)
    if changes.get("branch_id") is not None and changes["branch_id"] != employee.branch_id:
        _check_branch(db, changes["branch_id"])
    for field in REQUIRED:
        if field in changes and changes[field] is None:
            raise AppError(422, "field_required", field=field)
    for field in (*FIELDS, *SALARY_FIELDS):
        if field in changes:
            setattr(employee, field, changes[field])
    if employee.is_driver and not employee.phone:
        raise AppError(422, "driver_phone_required")
    if not employee.is_driver and employee.app_access in ("active", "suspended"):
        employee.app_access = "none"  # no longer a driver: no driver app
    employee.version += 1
    employee.updated_at = func.now()
    _flush_unique(db)
    db.refresh(employee)
    audit.record(
        db,
        action="employee.updated",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        before=before,
        after={**_snapshot(employee), "salary_fields_changed": salary_changes},
    )
    emit(
        db,
        "employee.updated",
        employee.public_id,
        {"employee_id": str(employee.public_id), "company_id": employee.company_id},
    )
    if commit:
        db.commit()
    return _out(employee, db.get(EmploymentStatus, employee.status_code), can_set_salary)


def change_status(
    db: Session, public_id, *, status_code: str, note: str | None, actor_user_id: int, commit: bool = True, **scope
) -> tuple[EmployeeRef, bool]:
    """Returns the employee and whether the employment just ended (terminal status)."""
    employee = _get(db, public_id, lock=True, **scope)
    status = _active_status(db, status_code)
    previous = db.get(EmploymentStatus, employee.status_code)
    if status.code == employee.status_code:
        raise AppError(422, "status_unchanged")
    ended = status.is_terminal and not previous.is_terminal
    employee.status_code = status.code
    if status.is_terminal and (employee.is_driver or employee.app_access != "none"):
        employee.app_access = "disabled"  # resignation / end of service: the driver app stops working now
    employee.version += 1
    employee.updated_at = func.now()
    db.add(StatusHistory(employee_id=employee.id, status_code=status.code, changed_by=actor_user_id, note=note))
    audit.record(
        db,
        action="employee.status_changed",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        before={"status_code": previous.code},
        after={"status_code": status.code, "note": note},
    )
    emit(
        db,
        "employee.status_changed",
        employee.public_id,
        {
            "employee_id": str(employee.public_id),
            "status_code": status.code,
            "terminal": status.is_terminal,
        },
    )
    if commit:
        db.commit()
    return _ref(employee, status), ended


def set_app_access(db: Session, public_id, *, value: str, actor_user_id: int, commit: bool = True, **scope) -> dict:
    """Suspend or (re)activate the driver app. "disabled" comes only from a terminal status."""
    employee = _get(db, public_id, lock=True, **scope)
    status = db.get(EmploymentStatus, employee.status_code)
    if not employee.is_driver:
        raise AppError(422, "not_a_driver")
    if value == "active" and status.is_terminal:
        raise AppError(422, "employment_ended")
    before = employee.app_access
    employee.app_access = value
    employee.version += 1
    audit.record(
        db,
        action="employee.app_access_changed",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        before={"app_access": before},
        after={"app_access": value},
    )
    if commit:
        db.commit()
    return _out(employee, status, False)


def apply_self_registration(db: Session, employee_id: int, changes: dict, *, actor_user_id: int) -> None:
    """Civil ID and nationality from an approved self-registration, in the caller's transaction."""
    employee = db.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    before = _snapshot(employee)
    for field in ("civil_id", "nationality"):
        if changes.get(field):
            setattr(employee, field, changes[field])
    employee.version += 1
    employee.updated_at = func.now()
    _flush_unique(db)
    audit.record(
        db,
        action="employee.self_registration_applied",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        before=before,
        after=_snapshot(employee),
    )


def status_history(db: Session, public_id, **scope) -> list[dict]:
    employee = _get(db, public_id, **scope)
    q = select(StatusHistory).where(StatusHistory.employee_id == employee.id).order_by(StatusHistory.id.desc())
    return [
        {"status_code": h.status_code, "changed_at": h.changed_at, "changed_by": h.changed_by, "note": h.note}
        for h in db.scalars(q)
    ]


def set_external_ref(db: Session, public_id, *, system: str, external_id: str, actor_user_id: int, **scope) -> None:
    """Matching key in another system (a future HR integration), one per system and employee."""
    employee = _get(db, public_id, **scope)
    db.execute(
        ExternalRef.__table__.delete().where(ExternalRef.system == system, ExternalRef.employee_id == employee.id)
    )
    db.add(ExternalRef(system=system, external_id=external_id, employee_id=employee.id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "external_ref_taken") from None
    audit.record(
        db,
        action="employee.external_ref_set",
        entity_type="employee",
        entity_id=employee.public_id,
        actor_user_id=actor_user_id,
        company_id=employee.company_id,
        after={"system": system, "external_id": external_id},
    )
    db.commit()


def external_refs(db: Session, employee_id: int) -> dict[str, str]:
    q = select(ExternalRef).where(ExternalRef.employee_id == employee_id)
    return {r.system: r.external_id for r in db.scalars(q)}


# ------------------------------------------------------------------ for other modules


def _ref(e: Employee, s: EmploymentStatus) -> EmployeeRef:
    return EmployeeRef(
        e.id,
        e.public_id,
        e.name,
        e.company_id,
        e.is_driver,
        e.phone,
        e.status_code,
        s.is_working,
        s.is_terminal,
        e.app_access,
    )


def ref(db: Session, employee_id: int) -> EmployeeRef | None:
    row = db.execute(
        select(Employee, EmploymentStatus)
        .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
        .where(Employee.id == employee_id)
    ).first()
    return None if row is None else _ref(*row)


def ref_by_public_id(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int]) -> EmployeeRef:
    e = _get(db, public_id, all_companies=all_companies, company_ids=company_ids)
    return _ref(e, db.get(EmploymentStatus, e.status_code))


def driver_by_phone(db: Session, phone: str) -> EmployeeRef | None:
    row = db.execute(
        select(Employee, EmploymentStatus)
        .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
        .where(Employee.phone == phone, Employee.is_driver.is_(True))
    ).first()
    return None if row is None else _ref(*row)


def app_drivers(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> list[EmployeeRef]:
    """Drivers whose app access is active, in scope."""
    q = _scoped(
        select(Employee, EmploymentStatus)
        .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
        .where(Employee.is_driver.is_(True), Employee.app_access == "active", EmploymentStatus.is_terminal.is_(False))
        .order_by(Employee.employee_number),
        all_companies,
        company_ids,
    )
    return [_ref(e, s) for e, s in db.execute(q)]


def find(db: Session, *, civil_id: str | None, phone: str | None) -> EmployeeRef | None:
    """The existing employee for an imported row: by civil ID, or by phone when there is none."""
    for column, value in ((Employee.civil_id, civil_id), (Employee.phone, phone)):
        if value:
            row = db.execute(
                select(Employee, EmploymentStatus)
                .join(EmploymentStatus, EmploymentStatus.code == Employee.status_code)
                .where(column == value)
            ).first()
            if row:
                return _ref(*row)
    return None


def next_employee_number(db: Session) -> int:
    """For imported employees without a number: E00001, E00002..."""
    numbers = db.scalars(select(Employee.employee_number).where(Employee.employee_number.op("~")(r"^E[0-9]+$")))
    return max((int(n[1:]) for n in numbers), default=0) + 1


def status_by_name(db: Session, label: str) -> str | None:
    """An active status matched by its name in any language (imported files carry names, not codes)."""
    label = " ".join(label.split())
    for s in db.scalars(select(EmploymentStatus).where(EmploymentStatus.is_active.is_(True))):
        if label in {" ".join(v.split()) for v in s.name.values()} or label == s.code:
            return s.code
    return None


def get_version(db: Session, employee_id: int) -> int:
    return db.scalar(select(Employee.version).where(Employee.id == employee_id))


def names(db: Session, ids: Iterable[int]) -> dict[int, dict]:
    ids = set(ids)
    if not ids:
        return {}
    return {
        i: {"id": str(p), "name": n}
        for i, p, n in db.execute(select(Employee.id, Employee.public_id, Employee.name).where(Employee.id.in_(ids)))
    }
