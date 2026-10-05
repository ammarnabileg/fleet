"""Initial data import from the onboarding workbook: vehicles, then employees and drivers.

One code path for both modes: every row runs through the real services inside its own savepoint, so a check run
finds exactly the errors an import would hit (row by row, with the column), and the whole transaction is rolled
back. An import applies only a file without errors, all at once. Rows are matched to what exists (vehicles by
plate or VIN, employees by civil ID or phone), so the same file can be imported again: it updates, never
duplicates. Documents are added only when the expiry date changed.
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError
from app.core.types import iban_ok
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.documents import service as documents
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.imports import sheets
from app.modules.imports import workbook as wb
from app.modules.imports.workbook import OPENING, PEOPLE, VEHICLES, Issue, Row
from app.modules.org import service as org
from app.modules.people import service as people

PEOPLE_FIELDS = (
    "employee_number",
    "name",
    "civil_id",
    "company_id",
    "branch_id",
    "department",
    "job_title",
    "is_driver",
    "phone",
    "basic_salary",
)


class _RowError(Exception):
    def __init__(self, code: str, **params):
        self.code, self.params = code, params


def _required(row: Row, column: str) -> str:
    value = wb.text(row, column)
    if not value:
        raise _RowError("field_required", field=column.rstrip(" *"))
    return value


def _lookup(value: str | None, column: str, found):
    if found is None:
        raise _RowError("unknown_value", field=column.rstrip(" *"), value=value)
    return found


def _date(row: Row, column: str):
    raw = _required(row, column)
    parsed = wb.parse_date(row.values[column])
    if parsed is None:
        raise _RowError("invalid_date", field=column.rstrip(" *"), value=raw)
    return parsed


def _localized(db: Session, value: str) -> dict:
    default = i18n.default_language(db).code
    out = {default: value}
    if value.isascii() and "en" in {lang.code for lang in i18n.list_languages(db)}:
        out["en"] = value  # a name written in Latin letters reads the same in English
    return out


def _document(db: Session, owner: documents.Owner, type_code: str, expiry, actor_user_id: int) -> int:
    exists, current = documents.current_expiry(db, type_code, owner.type, owner.id)
    if exists and current == expiry:
        return 0
    documents.add(
        db,
        owner,
        {"type_code": type_code, "expiry_date": expiry, "notes": "import"},
        actor_user_id=actor_user_id,
        commit=False,
    )
    return 1


def _duplicates(rows: list[Row], key) -> dict[int, str]:
    values = {r.number: key(r) for r in rows}
    counts = Counter(v for v in values.values() if v)
    return {n: v for n, v in values.items() if v and counts[v] > 1}


def _vehicle(db: Session, row: Row, *, actor_user_id: int, scope: dict) -> tuple[str, int]:
    c = wb.VEHICLE_COLUMNS
    plate = _required(row, c[1])
    year_raw = _required(row, c[4])
    if not year_raw.isdigit() or not 1980 <= int(year_raw) <= 2100:
        raise _RowError("invalid_number", field=c[4].rstrip(" *"), value=year_raw)
    company = _required(row, c[7])
    branch = _required(row, c[8])
    data = {
        "plate_number": plate,
        "make": _required(row, c[2]),
        "model": _required(row, c[3]),
        "year": int(year_raw),
        "color": _required(row, c[5]),
        "vin": _required(row, c[6]).upper(),
        "company_id": _lookup(company, c[7], org.company_id_by_name(db, company)),
        "branch_id": _lookup(branch, c[8], org.branch_id_by_name(db, branch)),
    }
    insurance, registration = _date(row, c[9]), _date(row, c[10])
    existing = fleet.vehicle_by_plate(db, plate) or fleet.vehicle_by_vin(db, data["vin"])
    if existing:
        out = fleet.update_vehicle(
            db,
            existing.public_id,
            version=fleet.vehicle_version(db, existing.id),
            changes=data,
            actor_user_id=actor_user_id,
            commit=False,
            **scope,
        )
        action, vehicle = "updated", existing
    else:
        out = fleet.create_vehicle(db, data, actor_user_id=actor_user_id, commit=False, **scope)
        action, vehicle = "created", fleet.vehicle_by_plate(db, plate)
    owner = documents.Owner("vehicle", vehicle.id, out["id"], out["company_id"], out["plate_number"])
    docs = _document(db, owner, "insurance", insurance, actor_user_id)
    docs += _document(db, owner, "registration", registration, actor_user_id)
    return action, docs


def _person(
    db: Session,
    row: Row,
    *,
    actor_user_id: int,
    can_set_salary: bool,
    numbers: list[int],
    warnings: list,
    scope: dict,
) -> tuple[str, int]:
    c = wb.PEOPLE_COLUMNS
    name, role = _required(row, c[1]), _required(row, c[2])
    phone_raw = _required(row, c[4])
    phone = wb.parse_phone(row.values[c[4]])
    if phone is None:
        raise _RowError("invalid_phone", value=phone_raw)
    status_label = _required(row, c[9])
    status = _lookup(status_label, c[9], people.status_by_name(db, status_label))
    civil_id = wb.text(row, c[3]).replace(" ", "")
    if civil_id and (not civil_id.isdigit() or len(civil_id) != 12):
        raise _RowError("invalid_civil_id", value=civil_id)
    if not civil_id and status != "under_visa":  # only someone whose visa is in process may have none yet
        raise _RowError("field_required", field=c[3].rstrip(" *"))
    company, branch = _required(row, c[5]), _required(row, c[6])
    salary = None
    if wb.text(row, c[10]):
        salary = wb.parse_decimal(row.values[c[10]])
        if salary is None:
            raise _RowError("invalid_number", field=c[10].rstrip(" *"), value=wb.text(row, c[10]))
        if not can_set_salary:
            warnings.append(Issue(row.sheet, row.number, "salary_skipped"))
            salary = None
    residence = _date(row, c[11]) if wb.text(row, c[11]) else None
    data = {
        "name": _localized(db, name),
        "civil_id": civil_id or None,
        "company_id": _lookup(company, c[5], org.company_id_by_name(db, company)),
        "branch_id": _lookup(branch, c[6], org.branch_id_by_name(db, branch)),
        "department": _required(row, c[7]),
        "job_title": _required(row, c[8]),
        "is_driver": role == wb.DRIVER_ROLE,
        "phone": phone,
    }
    if salary is not None:
        data["basic_salary"] = salary
    existing = people.find(db, civil_id=civil_id or None, phone=phone)
    if existing:
        people.update_employee(
            db,
            existing.public_id,
            version=people.get_version(db, existing.id),
            changes=data,
            can_set_salary=can_set_salary,
            actor_user_id=actor_user_id,
            commit=False,
            **scope,
        )
        if existing.status_code != status:
            people.change_status(
                db,
                existing.public_id,
                status_code=status,
                note="import",
                actor_user_id=actor_user_id,
                commit=False,
                **scope,
            )
        action = "updated"
    else:
        number = numbers[0]
        numbers[0] += 1
        people.create_employee(
            db,
            data | {"employee_number": f"E{number:05d}", "status_code": status},
            can_set_salary=can_set_salary,
            actor_user_id=actor_user_id,
            commit=False,
            **scope,
        )
        action = "created"
    employee = people.find(db, civil_id=civil_id or None, phone=phone)
    if employee.is_driver and not employee.is_terminal and employee.app_access == "none":
        people.set_app_access(
            db, employee.public_id, value="active", actor_user_id=actor_user_id, commit=False, **scope
        )
    docs = 0
    if residence:
        owner = documents.Owner("employee", employee.id, str(employee.public_id), employee.company_id, employee.name)
        docs = _document(db, owner, "residence", residence, actor_user_id)
    return action, docs


def _opening(db: Session, row: Row, *, actor_user_id: int, can_open: bool, scope: dict) -> tuple[str, int]:
    c = wb.OPENING_COLUMNS
    if not can_open:
        raise _RowError("permission_denied", permission="cash.adjust")
    civil_id = _required(row, c[2]).replace(" ", "")
    driver = people.find(db, civil_id=civil_id, phone=None)
    if driver is None or not driver.is_driver:
        raise _RowError("unknown_value", field=c[2].rstrip(" *"), value=civil_id)
    if not (scope["all_companies"] or driver.company_id in set(scope["company_ids"])):
        raise _RowError("company_out_of_scope")
    amount = wb.parse_decimal(row.values[c[3]], signed=True) if _required(row, c[3]) else None
    if amount is None:
        raise _RowError("invalid_number", field=c[3].rstrip(" *"), value=wb.text(row, c[3]))
    day = _date(row, c[4])
    approver = _required(row, c[5])
    created = cash.opening_balance(
        db, driver, amount=amount, business_date=day, approved_by=approver, actor_user_id=actor_user_id
    )
    return ("created" if created else "unchanged"), 0


def run(
    db: Session,
    data: bytes,
    *,
    apply: bool,
    actor_user_id: int,
    can_set_salary: bool,
    can_open: bool = False,
    **scope,
) -> dict:
    sheets = wb.read(data)
    errors: list[Issue] = []
    warnings: list[Issue] = []
    counts = {"vehicles": Counter(), "people": Counter(), "opening": Counter(), "documents": 0}
    dupes = {
        VEHICLES: _duplicates(
            sheets[VEHICLES], lambda r: fleet.normalize_plate(wb.text(r, wb.VEHICLE_COLUMNS[1])).replace(" ", "")
        ),
        PEOPLE: _duplicates(sheets[PEOPLE], lambda r: wb.parse_phone(r.values[wb.PEOPLE_COLUMNS[4]])),
    }
    dupes[PEOPLE] |= _duplicates(sheets[PEOPLE], lambda r: wb.text(r, wb.PEOPLE_COLUMNS[3]).replace(" ", ""))
    dupes[OPENING] = _duplicates(sheets[OPENING], lambda r: wb.text(r, wb.OPENING_COLUMNS[2]).replace(" ", ""))
    numbers = [people.next_employee_number(db)]
    for sheet, handler, bucket in (
        (VEHICLES, _vehicle, "vehicles"),
        (PEOPLE, _person, "people"),
        (OPENING, _opening, "opening"),
    ):
        for row in sheets[sheet]:
            if row.number in dupes[sheet]:
                errors.append(Issue(sheet, row.number, "duplicate_in_file", {"value": dupes[sheet][row.number]}))
                continue
            extra = {
                PEOPLE: {"can_set_salary": can_set_salary, "numbers": numbers, "warnings": warnings},
                OPENING: {"can_open": can_open},
            }.get(sheet, {})
            try:
                with db.begin_nested():
                    action, docs = handler(db, row, actor_user_id=actor_user_id, scope=scope, **extra)
                counts[bucket][action] += 1
                counts["documents"] += docs
            except _RowError as exc:
                errors.append(Issue(sheet, row.number, exc.code, exc.params))
            except AppError as exc:
                errors.append(Issue(sheet, row.number, exc.code, exc.params))
    applied = apply and not errors
    if applied:
        audit.record(
            db,
            action="import.applied",
            entity_type="import",
            actor_user_id=actor_user_id,
            after={
                "vehicles": dict(counts["vehicles"]),
                "people": dict(counts["people"]),
                "opening_balances": counts["opening"]["created"],
                "documents": counts["documents"],
            },
        )
        db.commit()
    else:
        db.rollback()
    return {
        "applied": applied,
        "vehicles": {"created": counts["vehicles"]["created"], "updated": counts["vehicles"]["updated"]},
        "people": {"created": counts["people"]["created"], "updated": counts["people"]["updated"]},
        "documents": counts["documents"],
        "opening_balances": counts["opening"]["created"],
        "errors": [vars(e) for e in errors],
        "warnings": [vars(w) for w in warnings],
    }


# ------------------------------------------------------------------ a client's own workbook (any layout)


def _cell(row: dict, field: str) -> str:
    return wb._text(row.get(field))


def _optional_date(row: dict, field: str, label: str):
    raw = _cell(row, field)
    if not raw:
        return None
    parsed = wb.parse_date(row[field])
    if parsed is None:
        raise _RowError("invalid_date", field=label, value=raw)
    return parsed


def _expired(warnings: list, sheet: str, number: int, code: str, expiry) -> None:
    if expiry and expiry < today():
        warnings.append(Issue(sheet, number, code, {"date": expiry.strftime("%d/%m/%Y")}))


def _mapped_vehicle(db: Session, sheet: str, number: int, row: dict, ctx: dict) -> tuple[str, int]:
    plate = _cell(row, "plate_number")
    if not plate:
        raise _RowError("field_required", field="plate_number")
    data = {"plate_number": plate, "company_id": ctx["company_id"], "branch_id": ctx["branch_id"]}
    for f in ("make", "model", "color"):
        if _cell(row, f):
            data[f] = _cell(row, f)
    if _cell(row, "year"):
        year = _cell(row, "year")
        if not year.isdigit() or not 1980 <= int(year) <= 2100:
            raise _RowError("invalid_number", field="year", value=year)
        data["year"] = int(year)
    if _cell(row, "vin"):
        data["vin"] = _cell(row, "vin").upper()
    registration = _optional_date(row, "registration_expiry", "registration_expiry")
    insurance = _optional_date(row, "insurance_expiry", "insurance_expiry")
    actor, scope = ctx["actor_user_id"], ctx["scope"]
    existing = fleet.vehicle_by_plate(db, plate) or (data.get("vin") and fleet.vehicle_by_vin(db, data["vin"]))
    if existing:
        version = fleet.vehicle_version(db, existing.id)
        out = fleet.update_vehicle(
            db, existing.public_id, version=version, changes=data, actor_user_id=actor, commit=False, **scope
        )
        action, vehicle = "updated", existing
    else:
        out = fleet.create_vehicle(db, data, actor_user_id=actor, commit=False, **scope)
        action, vehicle = "created", fleet.vehicle_by_plate(db, plate)
    owner = documents.Owner("vehicle", vehicle.id, out["id"], out["company_id"], out["plate_number"])
    docs = 0
    if registration:
        docs += _document(db, owner, "registration", registration, actor)
        _expired(ctx["warnings"], sheet, number, "registration_expired", registration)
    if insurance:
        docs += _document(db, owner, "insurance", insurance, actor)
        _expired(ctx["warnings"], sheet, number, "insurance_expired", insurance)
    return action, docs


def _civil_id_ok(civil_id: str) -> bool:
    """The check digit of a Kuwaiti civil ID."""
    weights = (2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    return 11 - sum(int(d) * w for d, w in zip(civil_id, weights, strict=False)) % 11 == int(civil_id[11])


def _mapped_person(db: Session, sheet: str, number: int, row: dict, ctx: dict) -> tuple[str, int]:
    civil_id, name = _cell(row, "civil_id").replace(" ", ""), _cell(row, "name")
    if not civil_id:
        raise _RowError("field_required", field="civil_id")
    if not civil_id.isdigit() or len(civil_id) != 12:
        raise _RowError("invalid_civil_id", value=civil_id)
    if not name:
        raise _RowError("field_required", field="name")
    if not _civil_id_ok(civil_id):
        ctx["warnings"].append(Issue(sheet, number, "civil_id_check_digit", {"value": civil_id}))
    job = _cell(row, "job_title") or None
    data = {
        "name": _localized(db, name),
        "civil_id": civil_id,
        "company_id": ctx["company_id"],
        "branch_id": ctx["branch_id"],
        "is_driver": bool(job) and any(k in sheets.norm(job) for k in ctx["keywords"]),
    }
    if job:
        data["job_title"] = job
    if _cell(row, "nationality"):
        data["nationality"] = _cell(row, "nationality")
    phone = None
    if _cell(row, "phone"):
        phone = wb.parse_phone(row["phone"])
        if phone is None:
            raise _RowError("invalid_phone", value=_cell(row, "phone"))
        data["phone"] = phone
    if _cell(row, "iban"):
        iban = _cell(row, "iban").replace(" ", "").upper()
        if not iban_ok(iban):
            raise _RowError("invalid_iban", value=iban)
        if ctx["can_set_salary"]:
            data["iban"] = iban
        else:
            ctx["warnings"].append(Issue(sheet, number, "salary_skipped"))
    actor, scope = ctx["actor_user_id"], ctx["scope"]
    existing = people.find(db, civil_id=civil_id, phone=phone)
    if existing:
        people.update_employee(
            db,
            existing.public_id,
            version=people.get_version(db, existing.id),
            changes=data,
            can_set_salary=ctx["can_set_salary"],
            actor_user_id=actor,
            commit=False,
            **scope,
        )
        action = "updated"
    else:
        n = ctx["numbers"][0]
        ctx["numbers"][0] += 1
        people.create_employee(
            db,
            data | {"employee_number": f"E{n:05d}"},
            can_set_salary=ctx["can_set_salary"],
            actor_user_id=actor,
            commit=False,
            **scope,
        )
        action = "created"
    employee = people.find(db, civil_id=civil_id, phone=None)
    if employee.is_driver and not employee.phone:
        ctx["warnings"].append(Issue(sheet, number, "driver_without_phone"))
        ctx["no_phone"].append(employee)
    elif employee.is_driver and not employee.is_terminal and employee.app_access == "none":
        people.set_app_access(db, employee.public_id, value="active", actor_user_id=actor, commit=False, **scope)
    return action, 0


def _row_key(field: str, value: str) -> str:
    value = value.replace(" ", "")
    return fleet.normalize_plate(value) if field == "plate_number" else value


def run_mapped(
    db: Session,
    data: bytes,
    plan: dict,
    *,
    apply: bool,
    actor_user_id: int,
    can_set_salary: bool,
    **scope,
) -> dict:
    """Imports the sheets of a client's own workbook as the plan says (from the preview, checked by the user)."""
    found = {s.name: s for s in sheets.read(data)}
    if not org.company_ids_exist(db, [plan["company_id"]]):
        raise AppError(422, "company_not_found")
    branch_id = plan.get("branch_id") or org.default_branch_id(db)
    errors: list[Issue] = []
    warnings: list[Issue] = []
    counts = {"vehicles": Counter(), "people": Counter(), "documents": 0}
    ctx = {
        "company_id": plan["company_id"],
        "branch_id": branch_id,
        "keywords": [sheets.norm(k) for k in plan["driver_keywords"]],
        "numbers": [people.next_employee_number(db)],
        "can_set_salary": can_set_salary,
        "actor_user_id": actor_user_id,
        "scope": scope,
        "warnings": warnings,
        "no_phone": [],
    }
    for sp in plan["sheets"]:
        sheet = found.get(sp["name"])
        if sheet is None:
            raise AppError(422, "import_sheet_missing", sheet=sp["name"])
        known = {f.key: f for f in sheets.FIELDS[sp["kind"]]}
        unknown = sorted(set(sp["columns"]) - set(known))
        missing = [k for k, f in known.items() if f.required and k not in sp["columns"]]
        bad = [c for c in sp["columns"].values() if not 0 <= c < len(sheet.headers)]
        if unknown or missing or bad:
            raise AppError(422, "import_bad_mapping", sheet=sp["name"], fields=", ".join(unknown + missing) or "?")
        handler, bucket = (_mapped_vehicle, "vehicles") if sp["kind"] == "vehicles" else (_mapped_person, "people")
        cols = sp["columns"]
        rows = [(n, {f: v[c] for f, c in cols.items()}) for n, v in sheet.all_rows if n >= sp["first_row"]]
        field = "plate_number" if sp["kind"] == "vehicles" else "civil_id"
        keys = {n: _row_key(field, _cell(r, field)) for n, r in rows}
        seen = Counter(k for k in keys.values() if k)
        for number, row in rows:
            if keys[number] and seen[keys[number]] > 1:
                errors.append(Issue(sheet.name, number, "duplicate_in_file", {"value": _cell(row, field)}))
                continue
            try:
                with db.begin_nested():
                    action, docs = handler(db, sheet.name, number, row, ctx)
                counts[bucket][action] += 1
                counts["documents"] += docs
            except (_RowError, AppError) as exc:
                errors.append(Issue(sheet.name, number, exc.code, exc.params))
    claims = 0
    if plan.get("claim_password") and ctx["no_phone"] and not errors:
        claims = identity.set_claims(
            db, ctx["no_phone"], password=plan["claim_password"], days=plan["claim_days"], actor_user_id=actor_user_id
        )["set"]
    applied = apply and not errors
    if applied:
        audit.record(
            db,
            action="import.applied",
            entity_type="import",
            actor_user_id=actor_user_id,
            after={
                "vehicles": dict(counts["vehicles"]),
                "people": dict(counts["people"]),
                "documents": counts["documents"],
                "claims": claims,
            },
        )
        db.commit()
    else:
        db.rollback()
    return {
        "applied": applied,
        "vehicles": {"created": counts["vehicles"]["created"], "updated": counts["vehicles"]["updated"]},
        "people": {"created": counts["people"]["created"], "updated": counts["people"]["updated"]},
        "documents": counts["documents"],
        "opening_balances": 0,
        "claims": claims,
        "errors": [vars(e) for e in errors],
        "warnings": [vars(w) for w in warnings],
    }
