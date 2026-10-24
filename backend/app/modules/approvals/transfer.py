"""The approval workflows in a transfer file, by process. A step names its role by code and a person by username;
a workflow whose role or person is missing here is skipped whole (half a chain of approvals would approve wrongly)."""

from decimal import Decimal

from sqlalchemy import select

from app.core.clock import utcnow
from app.core.errors import AppError
from app.core.transfer import (
    CREATED,
    UNCHANGED,
    UPDATED,
    ExportContext,
    ImportContext,
    Report,
    Section,
    each,
    plain,
    same,
)
from app.modules.approvals.models import PROCESSES, Request, Step, Workflow
from app.modules.approvals.schemas import StepIn
from app.modules.approvals.service import _cancel_pending
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.identity import transfer as identity_transfer


def _steps(db, process: str) -> list[dict]:
    steps = list(db.scalars(select(Step).where(Step.process == process).order_by(Step.position)))
    roles = identity.role_refs(db, {x for s in steps for x in (s.role_id, s.escalate_role_id)})
    users = identity_transfer.usernames(db, {s.user_id for s in steps})
    return [
        {
            "name": s.name,
            "role": (roles.get(s.role_id) or {}).get("code"),
            "username": users.get(s.user_id),
            "min_amount": plain(s.min_amount),
            "escalate_after_hours": s.escalate_after_hours,
            "escalate_role": (roles.get(s.escalate_role_id) or {}).get("code"),
        }
        for s in steps
    ]


def _export(ctx: ExportContext) -> list[dict]:
    flows = {w.process: w for w in ctx.db.scalars(select(Workflow))}
    return [{"process": p, "active": flows[p].active, "steps": _steps(ctx.db, p)} for p in PROCESSES if p in flows]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        process = item["process"]
        if process not in PROCESSES:
            raise AppError(404, "process_not_found")
        active = bool(item.get("active", True))
        rows, wanted = [], []
        for n, s in enumerate(item.get("steps") or [], start=1):
            username = s.get("username")
            clean = StepIn.model_validate({k: v for k, v in s.items() if k != "username"}).model_dump()
            if bool(clean.get("role")) == bool(username):
                raise AppError(422, "step_needs_one_approver", position=n)
            if bool(clean.get("escalate_after_hours")) != bool(clean.get("escalate_role")):
                raise AppError(422, "step_escalation_incomplete", position=n)
            if identity.PORTAL_ROLE in (clean.get("role"), clean.get("escalate_role")):
                raise AppError(422, "step_role_not_allowed", position=n)
            name = i18n.validate_localized(db, clean["name"])
            rows.append(
                Step(
                    process=process,
                    position=n,
                    name=name,
                    role_id=identity.role_id_by_code(db, clean["role"]) if clean.get("role") else None,
                    user_id=identity_transfer.user_id_by_username(db, username) if username else None,
                    min_amount=clean.get("min_amount") or Decimal(0),
                    escalate_after_hours=clean.get("escalate_after_hours") or None,
                    escalate_role_id=(
                        identity.role_id_by_code(db, clean["escalate_role"]) if clean.get("escalate_role") else None
                    ),
                )
            )
            wanted.append(
                {
                    "name": name,
                    "role": clean.get("role"),
                    "username": username,
                    "min_amount": plain(clean.get("min_amount") or Decimal(0)),
                    "escalate_after_hours": clean.get("escalate_after_hours") or None,
                    "escalate_role": clean.get("escalate_role"),
                }
            )
        flow = db.get(Workflow, process, with_for_update=True)
        before = _steps(db, process)
        if flow is not None and flow.active == active and same(_lower(before), _lower(wanted)):
            return UNCHANGED
        if flow is None:
            flow = Workflow(process=process, version=0)
            db.add(flow)
        for old in db.scalars(select(Step).where(Step.process == process)):
            db.delete(old)
        db.flush()
        db.add_all(rows)
        flow.active, flow.updated_by, flow.updated_at = active, ctx.actor_user_id, utcnow()
        flow.version = (flow.version or 0) + 1
        db.flush()
        if not (active and rows):
            _cancel_pending(db, select(Request).where(Request.process == process), "workflow_off")
        audit.record(
            db,
            action="approvals.workflow_updated",
            entity_type="workflow",
            entity_id=process,
            actor_user_id=ctx.actor_user_id,
            before={"steps": before},
            after={"active": active, "steps": wanted},
            comment="config import",
        )
        return CREATED if flow.version == 1 else UPDATED

    each(db, report, data, lambda i: i.get("process"), one)


def _lower(steps: list[dict]) -> list[dict]:
    return [s | {"username": (s.get("username") or "").lower() or None} for s in steps]


SECTIONS_OUT = [
    Section("approval_workflows", {"ar": "مسارات الموافقات", "en": "Approval workflows"}, _export, _apply, order=50)
]
