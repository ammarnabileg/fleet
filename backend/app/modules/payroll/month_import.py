"""A platform's month from Excel, checked before it is applied: the platform's partner report of orders by batch
(Rider ID, Batch No., Total Completed Deliveries; the rider found by the platform driver ID on his file), or a simple
template (the driver's civil ID or platform driver ID, the month, a column per monthly field).

The check lists what would happen: riders the system does not know, rows given twice, batch orders that differ from
the approved daily reports, months already paid. Applying replaces each driver's values for the month by the file's
(key: platform, month, driver, field, batch), so importing the same file again changes nothing and never adds up."""

import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.text import cell_text, norm
from app.modules.audit import service as audit
from app.modules.payroll import forms, month
from app.modules.payroll.month_models import MonthImport
from app.modules.payroll.service import month_start
from app.modules.people import service as people

PARTNER = {
    "rider": ("rider id", "rider", "رقم السائق", "driver id"),
    "batch": ("batch no.", "batch no", "batch", "الباتش", "رقم الباتش"),
    "orders": ("total completed deliveries", "completed deliveries", "deliveries", "الطلبات المكتمله", "عدد الطلبات"),
}
GENERIC_IDS = {
    "civil_id": ("civil_id", "civil id", "الرقم المدني"),
    "platform_driver_id": ("platform_driver_id", "platform driver id", "driver id", "rider id", "رقم السائق"),
    "month": ("month", "الشهر"),
    "batch": ("batch", "batch no.", "الباتش"),
    "batch_orders": ("batch_orders", "batch orders", "طلبات الباتش"),
}
MAX_ROWS = 5000


def _sheet_rows(data: bytes) -> list[list]:
    import openpyxl  # defusedxml makes openpyxl parse the XML safely

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)][: MAX_ROWS + 20]
    wb.close()
    return rows


def _header(rows: list[list], wanted: dict) -> tuple[int, dict]:
    """The first row naming at least two of the wanted columns: its index and where each column is."""
    names = {k: {norm(a) for a in v} for k, v in wanted.items()}
    for i, r in enumerate(rows[:20]):
        found = {}
        for j, c in enumerate(r):
            h = norm(c)
            for k, aliases in names.items():
                if h in aliases and k not in found:
                    found[k] = j
        if len(found) >= 2:
            return i, found
    raise AppError(422, "month_import_headers")


def _int(v) -> int:
    d = Decimal(cell_text(v))
    if d != d.to_integral_value() or d < 0:
        raise ValueError
    return int(d)


def _month_of(v) -> date | None:
    if isinstance(v, datetime):
        return month_start(v.date())
    if isinstance(v, date):
        return month_start(v)
    text = cell_text(v)
    if not text:
        return None
    try:
        y, m = text.replace("/", "-").split("-")[:2]
        return date(int(y), int(m), 1)
    except ValueError:
        raise ValueError from None


class _Parsed:
    def __init__(self):
        self.entries: dict[tuple, dict] = {}  # (driver id, key, sub) -> {"value", "row"}
        self.unknown: list[dict] = []
        self.duplicates: list[dict] = []
        self.invalid: list[dict] = []
        self.other_month: list[dict] = []
        self.rows = 0

    def add(self, profile: dict, key: str, sub: str, value: Decimal, row: int) -> None:
        k = (profile["id"], key, sub)
        if k in self.entries:
            same = self.entries[k]["value"] == value
            self.duplicates.append(
                {
                    "row": row,
                    "first_row": self.entries[k]["row"],
                    "employee": _who(profile),
                    "key": key,
                    "sub": sub,
                    "same": same,
                }  # fmt: skip
            )
            if same:
                return
        self.entries[k] = {"value": value, "row": row, "profile": profile}


def _who(p: dict) -> dict:
    return {"id": p["public_id"], "name": p["name"], "platform_driver_id": p["platform_driver_id"]}


def _drivers(db: Session, platform_id: int, scope: dict) -> tuple[dict, dict]:
    profiles = people.platform_profiles(db, platform_id, departed=True, **scope)
    profiles = [p for p in profiles if p["platform_id"] == platform_id]
    by_ref = {norm(p["platform_driver_id"]): p for p in profiles if p["platform_driver_id"]}
    by_civil = {norm(p["civil_id"]): p for p in profiles if p["civil_id"]}
    return by_ref, by_civil


def _partner(rows: list[list], by_ref: dict, out: _Parsed) -> None:
    at, cols = _header(rows, PARTNER)
    if set(cols) != set(PARTNER):
        raise AppError(422, "month_import_headers")
    for n, r in enumerate(rows[at + 1 :], start=at + 2):
        rider = cell_text(r[cols["rider"]] if cols["rider"] < len(r) else None)
        if not rider and not any(cell_text(c) for c in r):
            continue
        out.rows += 1
        try:
            batch, orders = _int(r[cols["batch"]]), _int(r[cols["orders"]])
        except (ValueError, InvalidOperation, IndexError):
            out.invalid.append({"row": n, "rider": rider})
            continue
        p = by_ref.get(norm(rider))
        if p is None:
            out.unknown.append({"row": n, "rider": rider})
            continue
        out.add(p, "batch_orders", str(batch), Decimal(orders), n)


def _generic(db: Session, rows: list[list], platform_id: int, the_month: date, refs: tuple, out: _Parsed) -> None:
    by_ref, by_civil = refs
    kinds = month.monthly_kinds(db, platform_id)
    fields = forms.get(db, platform_id)["monthly"]
    wanted = dict(GENERIC_IDS)
    for key, kind in kinds.items():
        if kind in ("batch_orders", "choice"):
            continue
        labels = [it["label"] for it in fields if it["key"] == key]
        wanted.setdefault(key, (key, *(x for lab in labels for x in lab.values())))
    tasks = {}
    for it in fields:
        if it["type"] == "task_counts":
            for o in it["options"]:
                tasks[o["value"]] = (o["value"], *o["label"].values())
    for task, aliases in tasks.items():
        wanted[f"task:{task}"] = aliases
    at, cols = _header(rows, wanted)
    if "civil_id" not in cols and "platform_driver_id" not in cols:
        raise AppError(422, "month_import_headers")
    for n, r in enumerate(rows[at + 1 :], start=at + 2):
        if not any(cell_text(c) for c in r):
            continue
        out.rows += 1

        def cell(k, r=r):
            j = cols.get(k)
            return r[j] if j is not None and j < len(r) else None

        ref, civil = cell_text(cell("platform_driver_id")), cell_text(cell("civil_id"))
        p = (by_ref.get(norm(ref)) if ref else None) or (by_civil.get(norm(civil)) if civil else None)
        if p is None:
            out.unknown.append({"row": n, "rider": ref or civil})
            continue
        try:
            m = _month_of(cell("month"))
            if m is not None and m != the_month:
                out.other_month.append({"row": n, "employee": _who(p), "month": m.isoformat()})
                continue
            if cell_text(cell("batch")):
                out.add(p, "batch_orders", str(_int(cell("batch"))), Decimal(_int(cell("batch_orders"))), n)
            for key, kind in kinds.items():
                if key in cols and kind not in ("batch_orders", "task_counts", "choice") and cell_text(cell(key)):
                    raw = cell(key)
                    if kind == "bool":
                        raw = norm(raw) in ("1", "yes", "true", "نعم", "x", "✓")
                    out.add(p, key, "", month._number(kind, raw), n)
            for task in tasks:
                if cell_text(cell(f"task:{task}")):
                    out.add(p, "task_counts", task, Decimal(_int(cell(f"task:{task}"))), n)
        except (ValueError, InvalidOperation, TypeError):
            out.invalid.append({"row": n, "rider": ref or civil})


def _parse(db: Session, *, platform_id: int, the_month: date, fmt: str, data: bytes, scope: dict) -> _Parsed:
    rows = _sheet_rows(data)
    out = _Parsed()
    refs = _drivers(db, platform_id, scope)
    if fmt == "partner_batches":
        _partner(rows, refs[0], out)
    else:
        _generic(db, rows, platform_id, the_month, refs, out)
    return out


def _report(db: Session, parsed: _Parsed, *, platform_id: int, the_month: date, digest: str) -> dict:
    from app.modules.payroll import statements

    by_driver: dict[int, dict] = defaultdict(lambda: {"batches": {}, "values": {}, "tasks": {}})
    for (emp, key, sub), e in parsed.entries.items():
        d = by_driver[emp]
        d["profile"] = e["profile"]
        if key == "batch_orders":
            d["batches"][int(sub)] = int(e["value"])
        elif key == "task_counts":
            d["tasks"][sub] = int(e["value"])
        else:
            d["values"][key] = str(e["value"])
    ids = list(by_driver)
    system = statements.system_counts(db, ids, the_month)
    current = month.load(db, dict.fromkeys(ids, platform_id), the_month)
    locked = statements.locked_months(db, {(d["profile"]["company_id"], the_month) for d in by_driver.values()})
    drivers, conflicts, paid = [], [], []
    for emp, d in by_driver.items():
        p = d["profile"]
        in_file = sum(d["batches"].values())
        daily = system[emp]["orders"]
        if d["batches"] and daily and in_file != daily:
            conflicts.append({"employee": _who(p), "file_orders": in_file, "daily_orders": daily})
        if (p["company_id"], the_month) in locked:
            paid.append(_who(p))
        had = current[emp]
        drivers.append(
            {
                "employee": _who(p),
                "batches": [{"batch": b, "orders": n} for b, n in sorted(d["batches"].items())],
                "values": d["values"],
                "tasks": d["tasks"],
                "daily_orders": daily,
                "replaces": bool(had.batches or had.values or had.tasks),
            }
        )
    again = db.scalar(
        select(MonthImport.id).where(
            MonthImport.platform_id == platform_id, MonthImport.month == the_month, MonthImport.file_sha256 == digest
        )
    )
    differing = [x for x in parsed.duplicates if not x["same"]]
    return {
        "platform_id": platform_id,
        "month": the_month,
        "rows": parsed.rows,
        "drivers": drivers,
        "unknown": parsed.unknown,
        "invalid": parsed.invalid,
        "duplicates": parsed.duplicates,
        "other_month": parsed.other_month,
        "conflicts": conflicts,
        "locked": paid,
        "imported_before": again is not None,
        # what stops it: two different figures for the same driver and batch, a paid month, nothing to apply
        "blocking": bool(differing or paid or not drivers),
    }


def check(db: Session, *, platform_id: int, month_: date, fmt: str, data: bytes, **scope) -> dict:
    the_month = month_start(month_)
    parsed = _parse(db, platform_id=platform_id, the_month=the_month, fmt=fmt, data=data, scope=scope)
    return _report(db, parsed, platform_id=platform_id, the_month=the_month, digest=hashlib.sha256(data).hexdigest())


def apply(
    db: Session, *, platform_id: int, month_: date, fmt: str, data: bytes, file_name: str | None, actor_user_id: int,
    **scope,
) -> dict:  # fmt: skip
    the_month = month_start(month_)
    digest = hashlib.sha256(data).hexdigest()
    parsed = _parse(db, platform_id=platform_id, the_month=the_month, fmt=fmt, data=data, scope=scope)
    report = _report(db, parsed, platform_id=platform_id, the_month=the_month, digest=digest)
    if report["blocking"]:
        raise AppError(409, "month_import_blocked")
    imp = MonthImport(
        platform_id=platform_id,
        month=the_month,
        format=fmt,
        file_sha256=digest,
        file_name=(file_name or "")[:200] or None,
        summary={"rows": report["rows"], "drivers": len(report["drivers"]), "unknown": len(report["unknown"])},
        created_by=actor_user_id,
    )
    db.add(imp)
    db.flush()
    grouped: dict[int, dict] = defaultdict(lambda: defaultdict(dict))
    profiles = {}
    for (emp, key, sub), e in parsed.entries.items():
        grouped[emp][key][sub] = e["value"]
        profiles[emp] = e["profile"]
    for emp, keys in grouped.items():
        ref = people.ref(db, emp)
        for key, subs in keys.items():
            if key in ("batch_orders", "task_counts"):  # the file's rows are the driver's rows for the month
                month._replace(db, ref, the_month, key, subs, actor_user_id, source="import", import_id=imp.id)
            else:
                month._put(db, ref, the_month, key, "", subs[""], source="import", actor_user_id=actor_user_id,
                           import_id=imp.id)  # fmt: skip
    db.flush()
    audit.record(
        db,
        action="payroll.month_imported",
        entity_type="month_import",
        entity_id=imp.public_id,
        actor_user_id=actor_user_id,
        after={
            "platform_id": platform_id,
            "month": the_month.isoformat(),
            "format": fmt,
            "drivers": len(grouped),
            "file_sha256": digest,
        },
    )
    db.commit()
    return report | {"import_id": str(imp.public_id), "applied": len(grouped)}


def template(db: Session, platform_id: int) -> bytes:
    """The simple template for a platform: who, the month, and a column per monthly field."""
    import openpyxl

    f = forms.get(db, platform_id)
    headers = ["platform_driver_id", "civil_id", "month"]
    for it in f["monthly"]:
        if it["type"] == "batch_orders":
            headers += ["batch", "batch_orders"]
        elif it["type"] == "task_counts":
            headers += [o["value"] for o in it["options"]]
        elif it["type"] != "choice":
            headers.append(it["key"])
    wb = openpyxl.Workbook()
    wb.active.title = "month"
    wb.active.append(headers)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
