"""A driver's objection to his payslip (docs/payroll-schemes.md section 9).

From the app the driver objects to an approved payslip of his, all of it or one of its lines (a scheme item, a sheet
column, an installment deduction), with his reason and, if he has one, a photo or a PDF from his phone (camera or
gallery). The office is alerted; who sees payroll (payroll.view) reads the objections, who prepares or approves it
answers them: in review, accepted or rejected (with the answer the driver reads), then closed. The driver is told at
every change of status.

An objection never edits the approved run. What is owed either way is settled for a later month through the existing
manual deduction flow, and that deduction is linked to the objection as the action taken.
"""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.payroll import service
from app.modules.payroll.columns import BY_CODE
from app.modules.payroll.models import Deduction, Line, LineDeduction, Objection, Run
from app.modules.people import service as people

log = logging.getLogger(__name__)

STATUSES = ("open", "in_review", "accepted", "rejected", "closed")
NEXT = {  # where an objection may go from each status
    "open": {"in_review", "accepted", "rejected", "closed"},
    "in_review": {"in_review", "accepted", "rejected", "closed"},
    "accepted": {"accepted", "closed"},  # the settlement linked afterwards
    "rejected": {"rejected", "closed"},
    "closed": set(),
}
DOCUMENTS = files.IMAGES | {"application/pdf"}


def _payslip(db: Session, employee_id: int, run_public_id) -> tuple[Run, Line]:
    """His line in an approved (or paid) run: a draft is not a payslip yet, and another driver's is not his."""
    row = db.execute(
        select(Run, Line)
        .join(Line, Line.run_id == Run.id)
        .where(Run.public_id == run_public_id, Line.employee_id == employee_id, Run.status != "draft")
    ).first()
    if row is None:
        raise AppError(404, "payslip_not_found")
    return row[0], row[1]


def _items(db: Session, line: Line) -> dict[str, Decimal | None]:
    """What a driver may object to on this payslip, with the amount the payslip shows for it."""
    out: dict[str, Decimal | None] = {}
    for code, value in (
        line.cells or {}
    ).items():  # the sheet's amounts on it (an empty column is nothing to object to)
        col = BY_CODE.get(code)
        if col is not None and col.kind == "money" and value not in (None, ""):
            if Decimal(str(value)) or code in ("gross", "net"):
                out[code] = Decimal(str(value))
    for b in line.breakdown or []:
        out[b["code"]] = Decimal(str(b["amount"]))
    for public_id, deducted in db.execute(
        select(Deduction.public_id, LineDeduction.deducted)
        .join(LineDeduction, LineDeduction.deduction_id == Deduction.id)
        .where(LineDeduction.line_id == line.id)
    ):
        out[f"deduction:{public_id}"] = deducted
    return out


def _check_attachment(db: Session, sha: str, device_id: int) -> None:
    info = files.get(db, sha)
    if info.uploaded_by_device != device_id:
        raise AppError(422, "file_not_yours")
    if info.content_type not in DOCUMENTS:
        raise AppError(422, "file_type_not_allowed")


def driver_create(db: Session, employee_id: int, *, device_id: int, run_public_id, data: dict) -> dict:
    run, line = _payslip(db, employee_id, run_public_id)
    code = data.get("item_code")
    amount = None
    if code is not None:
        items = _items(db, line)
        if code not in items:
            raise AppError(422, "objection_item_invalid", item=code)
        amount = items[code]
    if data.get("attachment_sha256"):
        _check_attachment(db, data["attachment_sha256"], device_id)
    o = Objection(
        run_id=run.id,
        employee_id=employee_id,
        company_id=run.company_id,
        month=run.month,
        item_code=code,
        item_amount=amount,
        reason=data["reason"],
        attachment_sha256=data.get("attachment_sha256"),
        client_ref=data["client_ref"],
        submitted_by_device=device_id,
    )
    db.add(o)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "objections_client_ref_key":
            raise
        raise AppError(409, "objection_exists") from None  # the app's retry of what already arrived
    db.refresh(o)
    driver = people.ref(db, employee_id)
    notifications.raise_alert(
        db,
        "payroll_objection",
        company_id=run.company_id,
        entity_type="payroll_objection",
        entity_id=o.public_id,
        params={"driver": driver.name, "month": run.month.strftime("%m-%Y")},
        dedupe_key=f"objection:{o.public_id}",
    )
    audit.record(
        db,
        action="objection.submitted",
        entity_type="payroll_objection",
        entity_id=o.public_id,
        actor_type="device",
        company_id=run.company_id,
        after={"month": run.month, "item": code, "amount": amount, "reason": o.reason, "file": o.attachment_sha256},
    )
    db.commit()
    return _driver_out(db, [o])[0]


def _labels(db: Session, key: str) -> dict:
    """A catalog text in every base language: picked in the driver's language when his notice is read."""
    return {lang: i18n.t(db, lang, key) for lang in ("ar", "en")}


def _run_ids(db: Session, rows: list[Objection]) -> dict[int, Run]:
    ids = {o.run_id for o in rows}
    return {r.id: r for r in db.scalars(select(Run).where(Run.id.in_(ids)))} if ids else {}


def _deductions(db: Session, rows: list[Objection]) -> dict[int, Deduction]:
    ids = {o.deduction_id for o in rows if o.deduction_id}
    return {d.id: d for d in db.scalars(select(Deduction).where(Deduction.id.in_(ids)))} if ids else {}


def _base(o: Objection, run: Run, deds: dict[int, Deduction]) -> dict:
    d = deds.get(o.deduction_id)
    return {
        "id": str(o.public_id),
        "run_id": str(run.public_id),
        "month": o.month,
        "item_code": o.item_code,
        "item_amount": o.item_amount,
        "reason": o.reason,
        "has_attachment": o.attachment_sha256 is not None,
        "status": o.status,
        "response": o.response,
        "action_taken": o.action_taken,
        "deduction": {"id": str(d.public_id), "total": d.total, "start_month": d.start_month, "status": d.status}
        if d
        else None,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
        "version": o.version,
    }


def _driver_out(db: Session, rows: list[Objection]) -> list[dict]:
    runs, deds = _run_ids(db, rows), _deductions(db, rows)
    return [_base(o, runs[o.run_id], deds) for o in rows]


def driver_list(db: Session, employee_id: int) -> list[dict]:
    rows = db.scalars(
        select(Objection).where(Objection.employee_id == employee_id).order_by(Objection.id.desc()).limit(100)
    )
    return _driver_out(db, list(rows))


def driver_attachment(db: Session, employee_id: int, public_id) -> files.FileInfo:
    o = db.scalar(select(Objection).where(Objection.public_id == public_id, Objection.employee_id == employee_id))
    if o is None or o.attachment_sha256 is None:
        raise AppError(404, "objection_not_found")
    return files.get(db, o.attachment_sha256)


# ------------------------------------------------------------------ the office


def _scoped(q, all_companies: bool, company_ids):
    return q if all_companies else q.where(Objection.company_id.in_(list(company_ids)))


def _office_out(db: Session, rows: list[Objection]) -> list[dict]:
    runs, deds = _run_ids(db, rows), _deductions(db, rows)
    names = people.names(db, {o.employee_id for o in rows})
    users = identity.user_names(db, {o.handled_by for o in rows if o.handled_by})
    return [
        _base(o, runs[o.run_id], deds)
        | {
            "employee": names.get(o.employee_id),
            "company_id": o.company_id,
            "run_status": runs[o.run_id].status,
            "handled_by": users.get(o.handled_by),
            "handled_at": o.handled_at,
        }
        for o in rows
    ]


def list_objections(
    db: Session, *, status: str | None, month: date | None, limit: int = 100, offset: int = 0, **scope
) -> list[dict]:
    q = _scoped(select(Objection), **scope)
    if status:
        q = q.where(Objection.status.in_(status.split(",")))
    if month is not None:
        q = q.where(Objection.month == service.month_start(month))
    q = q.order_by(Objection.created_at.desc(), Objection.id.desc()).limit(limit).offset(offset)
    return _office_out(db, list(db.scalars(q)))


def counts(db: Session, **scope) -> dict:
    q = _scoped(select(Objection.status, func.count()).group_by(Objection.status), **scope)
    found = dict(db.execute(q).all())
    return {s: found.get(s, 0) for s in STATUSES} | {"waiting": found.get("open", 0) + found.get("in_review", 0)}


def _row(db: Session, public_id, *, lock: bool = False, **scope) -> Objection:
    q = _scoped(select(Objection).where(Objection.public_id == public_id), **scope)
    o = db.scalar(q.with_for_update() if lock else q)
    if o is None:
        raise AppError(404, "objection_not_found")
    return o


def detail(db: Session, public_id, **scope) -> dict:
    """The objection with the payslip it is about: the line as approved, and the item's amount on it now."""
    o = _row(db, public_id, **scope)
    out = _office_out(db, [o])[0]
    line = db.scalar(select(Line).where(Line.run_id == o.run_id, Line.employee_id == o.employee_id))
    out["payslip"] = (
        {
            "gross": line.gross,
            "deductions": line.deductions,
            "net": line.net,
            "cells": line.cells,
            "breakdown": line.breakdown or [],
            "item_now": _items(db, line).get(o.item_code) if o.item_code else None,
        }
        if line
        else None
    )
    return out


def attachment(db: Session, public_id, **scope) -> files.FileInfo:
    o = _row(db, public_id, **scope)
    if o.attachment_sha256 is None:
        raise AppError(404, "file_not_found")
    return files.get(db, o.attachment_sha256)


def respond(db: Session, public_id, data: dict, *, actor_user_id: int, **scope) -> dict:
    """The office's answer: the status, what the driver reads, what was done (a settlement deduction for a later month
    linked here). The approved run is never touched."""
    o = _row(db, public_id, lock=True, **scope)
    if data.get("version") is not None and data["version"] != o.version:
        raise AppError(409, "version_conflict")
    status = data["status"]
    if status not in NEXT[o.status]:
        raise AppError(409, "objection_status_invalid", status=o.status)
    response = data.get("response") if data.get("response") is not None else o.response
    if status in ("accepted", "rejected") and not response:
        raise AppError(422, "field_required", field="response")
    before = {"status": o.status, "response": o.response, "action_taken": o.action_taken}
    if data.get("deduction_id"):
        d = db.scalar(select(Deduction).where(Deduction.public_id == data["deduction_id"]))
        if d is None or d.employee_id != o.employee_id:
            raise AppError(422, "objection_deduction_invalid")
        o.deduction_id = d.id
    changed = status != o.status
    o.status, o.response = status, response
    if data.get("action_taken") is not None:
        o.action_taken = data["action_taken"]
    o.handled_by, o.handled_at, o.updated_at = actor_user_id, utcnow(), utcnow()
    o.version += 1
    notifications.resolve(db, f"objection:{o.public_id}")  # someone took it up: the alert has done its work
    if changed:
        notifications.notify_driver(
            db,
            o.employee_id,
            "objection_updated",
            params={
                "month": o.month.strftime("%m-%Y"),
                "status": _labels(db, f"objection_status.{status}"),
                "response": response or "—",
            },
            entity_type="payroll_objection",
            entity_id=o.public_id,
        )
    audit.record(
        db,
        action="objection.answered",
        entity_type="payroll_objection",
        entity_id=o.public_id,
        actor_user_id=actor_user_id,
        company_id=o.company_id,
        before=before,
        after={
            "status": o.status,
            "response": o.response,
            "action_taken": o.action_taken,
            "deduction": str(data["deduction_id"]) if data.get("deduction_id") else None,
        },
    )
    db.commit()
    return detail(db, public_id, **scope)
