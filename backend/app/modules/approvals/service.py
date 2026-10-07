"""Approval workflows (BRD FR-WFL-01..05). Each module asks `gate` before it approves or refuses a document: with no
workflow for the process its own permission decides, as before; with one, the document goes through the steps that
apply to its amount, each decided by its role or person (or a delegate while away, or the escalation role once the step
waited too long), one person at most one step, a refusal always with its reason, every decision kept.

A request opens when the document is sent for approval (`submitted`), so it shows at once in its first approvers'
inbox, or at the first decision for a document sent before the workflow existed. It closes with the last step, with a
refusal, or as cancelled when the document is withdrawn or its amount changes (what was approved is what is applied)."""

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.approvals.models import PROCESSES, Decision, Delegation, Request, Step, Workflow
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications

# ------------------------------------------------------------------ the workflows (FR-WFL-01)


def _steps_out(db: Session, steps: list[Step]) -> list[dict]:
    roles = identity.role_refs(db, {x for s in steps for x in (s.role_id, s.escalate_role_id)})
    users = identity.user_refs(db, {s.user_id for s in steps})
    holders = identity.holders(db, {s.role_id for s in steps if s.role_id})
    return [
        {
            "position": s.position,
            "name": s.name,
            "role": roles.get(s.role_id),
            "user": users.get(s.user_id),
            "holders": len(holders[s.role_id]) if s.role_id else 1,  # a role nobody holds stops every request there
            "min_amount": s.min_amount,
            "escalate_after_hours": s.escalate_after_hours,
            "escalate_role": roles.get(s.escalate_role_id),
        }
        for s in steps
    ]


def list_workflows(db: Session) -> list[dict]:
    """Every process the workflows apply to, with its steps (none, or switched off: the permission alone decides)."""
    flows = {w.process: w for w in db.scalars(select(Workflow))}
    steps: dict[str, list[Step]] = {p: [] for p in PROCESSES}
    for s in db.scalars(select(Step).order_by(Step.process, Step.position)):
        steps[s.process].append(s)
    pending: dict[str, int] = {p: 0 for p in PROCESSES}
    for p in db.scalars(select(Request.process).where(Request.status == "pending")):
        pending[p] += 1
    return [
        {
            "process": p,
            "active": bool(p in flows and flows[p].active and steps[p]),
            "version": flows[p].version if p in flows else 0,
            "updated_at": flows[p].updated_at if p in flows else None,
            "pending": pending[p],
            "steps": _steps_out(db, steps[p]),
        }
        for p in PROCESSES
    ]


def _workflow(db: Session, process: str) -> dict:
    return next(w for w in list_workflows(db) if w["process"] == process)


def _cancel_pending(db: Session, q, note: str) -> int:
    n = 0
    for req in db.scalars(q.where(Request.status == "pending").with_for_update()):
        req.status, req.closed_at, req.cancel_note = "cancelled", utcnow(), note
        n += 1
    db.flush()
    return n


def set_workflow(
    db: Session, process: str, *, active: bool, steps: list[dict], version: int, actor_user_id: int
) -> dict:
    """The process's steps replaced as given, in order. Requests under way keep the steps they started with; switched
    off (or left without steps), the requests under way are cancelled and the permission decides again."""
    if process not in PROCESSES:
        raise AppError(404, "process_not_found")
    flow = db.get(Workflow, process, with_for_update=True)
    if (flow.version if flow else 0) != version:
        raise AppError(409, "version_conflict")
    rows = []
    for n, s in enumerate(steps, start=1):
        if bool(s.get("role")) == bool(s.get("user_id")):
            raise AppError(422, "step_needs_one_approver", position=n)
        if bool(s.get("escalate_after_hours")) != bool(s.get("escalate_role")):
            raise AppError(422, "step_escalation_incomplete", position=n)
        if identity.PORTAL_ROLE in (s.get("role"), s.get("escalate_role")):
            raise AppError(422, "step_role_not_allowed", position=n)  # a center never approves its own quote
        rows.append(
            Step(
                process=process,
                position=n,
                name=s["name"],
                role_id=identity.role_id_by_code(db, s["role"]) if s.get("role") else None,
                user_id=identity.user_id(db, s["user_id"]) if s.get("user_id") else None,
                min_amount=s.get("min_amount") or Decimal(0),
                escalate_after_hours=s.get("escalate_after_hours") or None,
                escalate_role_id=identity.role_id_by_code(db, s["escalate_role"]) if s.get("escalate_role") else None,
            )
        )
    before = _workflow(db, process)
    if flow is None:
        flow = Workflow(process=process)
        db.add(flow)
    for old in db.scalars(select(Step).where(Step.process == process)):
        db.delete(old)
    db.flush()
    db.add_all(rows)
    flow.active, flow.updated_by, flow.updated_at = active, actor_user_id, utcnow()
    flow.version = version + 1
    db.flush()
    if not (active and rows):
        _cancel_pending(db, select(Request).where(Request.process == process), "workflow_off")
    after = _workflow(db, process)
    audit.record(
        db,
        action="approvals.workflow_updated",
        entity_type="workflow",
        entity_id=process,
        actor_user_id=actor_user_id,
        before={"active": before["active"], "steps": before["steps"]},
        after={"active": after["active"], "steps": after["steps"]},
    )
    db.commit()
    return _workflow(db, process)


def options(db: Session) -> dict:
    """The roles and the people a step may name."""
    return {"roles": identity.role_options(db), "users": identity.user_options(db)}


# ------------------------------------------------------------------ who may decide a step (FR-WFL-05)


def _delegators(db: Session, delegate_id: int) -> set[int]:
    """Whose approvals this user makes today, while they are away."""
    d = today()
    return set(
        db.scalars(
            select(Delegation.user_id).where(
                Delegation.delegate_id == delegate_id,
                Delegation.cancelled_at.is_(None),
                Delegation.date_from <= d,
                Delegation.date_to >= d,
            )
        )
    )


def _approvers(step: dict, escalated: bool, holders: dict[int, set[int]]) -> set[int]:
    people = {step["user_id"]} if step.get("user_id") else set(holders.get(step.get("role_id"), set()))
    if escalated and step.get("escalate_role_id"):
        people |= holders.get(step["escalate_role_id"], set())
    return people


def _step_roles(steps: Iterable[dict]) -> set[int]:
    return {x for s in steps for x in (s.get("role_id"), s.get("escalate_role_id")) if x}


def _authorize(db: Session, req: Request, actor_user_id: int) -> int | None:
    """The approver this user decides for: None when the step is theirs, the delegator's id when standing in; 403
    otherwise."""
    step = req.steps[req.current]
    approvers = _approvers(step, req.escalated, identity.holders(db, _step_roles([step])))
    if actor_user_id in approvers:
        return None
    standing_in = _delegators(db, actor_user_id) & approvers
    if standing_in:
        return min(standing_in)
    raise AppError(403, "not_your_step", step=step["name"])


# ------------------------------------------------------------------ what the modules call


def _open(db: Session, process: str, *, document_id, document_key, document_ref, company_id, amount, actor_user_id):
    steps = [
        {
            "position": s.position,
            "name": s.name,
            "role_id": s.role_id,
            "user_id": s.user_id,
            "escalate_after_hours": s.escalate_after_hours,
            "escalate_role_id": s.escalate_role_id,
        }
        for s in db.scalars(select(Step).where(Step.process == process).order_by(Step.position))
        if Decimal(amount or 0) >= s.min_amount
    ]
    if not steps:
        return None  # no step for this amount: the permission alone decides
    req = Request(
        process=process,
        document_id=document_id,
        document_key=str(document_key),
        document_ref=document_ref,
        company_id=company_id,
        amount=amount or 0,
        steps=steps,
        created_by=actor_user_id,
    )
    db.add(req)
    db.flush()
    return req


def _active(db: Session, process: str) -> bool:
    flow = db.get(Workflow, process)
    return flow is not None and flow.active


def submitted(
    db: Session,
    process: str,
    *,
    document_id: int,
    document_key,
    document_ref: str,
    company_id: int | None,
    amount: Decimal,
    actor_user_id: int | None = None,
    note: str = "resubmitted",
) -> None:
    """A document sent for approval: with a workflow, its request opens now and waits in its first approvers' inbox.
    A document sent again (corrected after a refusal, recomputed) starts over."""
    if not _active(db, process):
        return
    _cancel_pending(db, select(Request).where(Request.process == process, Request.document_id == document_id), note)
    _open(
        db,
        process,
        document_id=document_id,
        document_key=document_key,
        document_ref=document_ref,
        company_id=company_id,
        amount=amount,
        actor_user_id=actor_user_id,
    )


def withdrawn(db: Session, process: str, document_ids: Iterable[int], *, note: str = "withdrawn") -> None:
    """Documents cancelled, or changed so that what was approved no longer holds: their requests stop."""
    ids = list(document_ids)
    if ids:
        _cancel_pending(db, select(Request).where(Request.process == process, Request.document_id.in_(ids)), note)


def gate(
    db: Session,
    process: str,
    *,
    document_id: int,
    document_key,
    document_ref: str,
    company_id: int | None,
    amount: Decimal,
    actor_user_id: int,
    approve: bool = True,
    reason: str | None = None,
) -> bool:
    """True when the module may now apply its own decision: no workflow applies, the last step was just approved, or
    the document was refused. False when the approval was recorded and another step follows. Added to the caller's
    transaction, which holds the document locked."""
    if not _active(db, process):
        return True
    req = db.scalar(
        select(Request)
        .where(Request.process == process, Request.document_id == document_id, Request.status == "pending")
        .with_for_update()
    )
    if req is not None and Decimal(req.amount) != Decimal(amount or 0):
        req.status, req.closed_at, req.cancel_note = "cancelled", utcnow(), "amount_changed"
        db.flush()  # approved for another amount: the steps for this one start over
        req = None
    if req is None:
        req = _open(
            db,
            process,
            document_id=document_id,
            document_key=document_key,
            document_ref=document_ref,
            company_id=company_id,
            amount=amount,
            actor_user_id=actor_user_id,
        )
        if req is None:
            return True
    on_behalf = _authorize(db, req, actor_user_id)
    if not approve:
        if not reason:
            raise AppError(422, "reason_required")
        db.add(
            Decision(
                request_id=req.id,
                step=req.current,
                decision="rejected",
                user_id=actor_user_id,
                on_behalf_of=on_behalf,
                reason=reason,
            )
        )
        req.status, req.closed_at = "rejected", utcnow()
        db.flush()
        return True
    decided: set[int] = set()
    for user, behalf in db.execute(
        select(Decision.user_id, Decision.on_behalf_of).where(
            Decision.request_id == req.id, Decision.decision == "approved"
        )
    ):
        decided |= {user, behalf} - {None}
    if actor_user_id in decided or on_behalf in decided:
        raise AppError(409, "approver_repeated")  # one person approves one step of a document at most
    db.add(
        Decision(
            request_id=req.id,
            step=req.current,
            decision="approved",
            user_id=actor_user_id,
            on_behalf_of=on_behalf,
            reason=reason,
        )
    )
    req.current += 1
    req.step_since, req.escalated = utcnow(), False
    if req.current >= len(req.steps):
        req.status, req.closed_at = "approved", utcnow()
    db.flush()
    return req.status == "approved"


# ------------------------------------------------------------------ deciding from the inbox


def _apply(db: Session, req: Request, *, approve: bool, reason: str | None, actor_user_id: int, scope: dict) -> None:
    """The module's own approve or refuse, which asks the gate in turn: the step's approver decides from the inbox
    without holding the module's permission, the workflow having named them."""
    key, by = req.document_key, {"actor_user_id": actor_user_id, **scope}
    if req.process == "daily_report":
        from app.modules.daily_ops import service as m

        if approve:
            m.approve(db, key, cash_amount=None, reason=reason, **by)
        else:
            m.reject(db, key, reason=reason or "", **by)
    elif req.process == "maintenance_request":
        from app.modules.maintenance import service as m

        if approve:
            m.approve(db, key, note=reason, **by)
        else:
            m.reject(db, key, reason=reason or "", **by)
    elif req.process == "maintenance_quote":
        from app.modules.maintenance import service as m

        m.decide_quote(db, key, approve=approve, reason=reason, **by)
    elif req.process == "maintenance_invoice":
        from app.modules.maintenance import service as m

        m.decide_invoice(db, key, approve=approve, reason=reason, **by)
    elif req.process == "accident_estimate":
        from app.modules.accidents import service as m

        m.decide_estimate(db, key, approve=approve, reason=reason, **by)
    elif req.process == "expense":
        from app.modules.finance import service as m

        m.decide_expense(db, key, approve=approve, note=reason, **by)
    elif req.process == "payroll_run":
        from app.modules.payroll import service as m

        if approve:
            m.approve_run(db, key, **by)
        else:
            m.send_back_run(db, key, reason=reason or "", **by)


def decide(
    db: Session, public_id, *, approve: bool, reason: str | None, actor_user_id: int, all_companies: bool, company_ids
) -> dict:
    req = db.scalar(_scoped(select(Request).where(Request.public_id == public_id), all_companies, company_ids))
    if req is None:
        raise AppError(404, "approval_not_found")
    if req.status != "pending":
        raise AppError(409, "approval_closed", status=req.status)
    if not approve and not reason:
        raise AppError(422, "reason_required")
    _apply(
        db,
        req,
        approve=approve,
        reason=reason,
        actor_user_id=actor_user_id,
        scope={"all_companies": all_companies, "company_ids": company_ids},
    )
    db.expire_all()
    req = db.scalar(select(Request).where(Request.public_id == public_id))
    return _request_out(db, req, _decisions(db, [req.id])[req.id])


# ------------------------------------------------------------------ what the screens show (FR-WFL-04)


def _request_out(db: Session, req: Request, decisions: list[Decision]) -> dict:
    users = identity.user_refs(db, {x for d in decisions for x in (d.user_id, d.on_behalf_of)})
    roles = identity.role_refs(db, _step_roles(req.steps))
    step_users = identity.user_refs(db, {s.get("user_id") for s in req.steps})
    return {
        "id": str(req.public_id),
        "process": req.process,
        "document_id": req.document_key,
        "document_ref": req.document_ref,
        "company_id": req.company_id,
        "amount": req.amount,
        "status": req.status,
        "current": req.current,
        "escalated": req.escalated,
        "step_since": req.step_since,
        "created_at": req.created_at,
        "closed_at": req.closed_at,
        "cancel_note": req.cancel_note,
        "steps": [
            {
                "name": s["name"],
                "role": roles.get(s.get("role_id")),
                "user": step_users.get(s.get("user_id")),
                "escalate_role": roles.get(s.get("escalate_role_id")),
            }
            for s in req.steps
        ],
        "decisions": [
            {
                "step": d.step,
                "decision": d.decision,
                "by": users.get(d.user_id),
                "on_behalf_of": users.get(d.on_behalf_of),
                "reason": d.reason,
                "at": d.at,
            }
            for d in decisions
        ],
    }


def _decisions(db: Session, ids: Iterable[int]) -> dict[int, list[Decision]]:
    out: dict[int, list[Decision]] = {i: [] for i in ids}
    if out:
        for d in db.scalars(select(Decision).where(Decision.request_id.in_(list(out))).order_by(Decision.id)):
            out[d.request_id].append(d)
    return out


def _scoped(q, all_companies: bool, company_ids):
    if all_companies:
        return q
    return q.where(Request.company_id.is_(None) | Request.company_id.in_(list(company_ids)))


def history(db: Session, process: str, document_key, *, all_companies: bool, company_ids) -> list[dict]:
    """Every request a document went through, newest first, with each decision: who, when, what, why."""
    if process not in PROCESSES:
        raise AppError(404, "process_not_found")
    rows = list(
        db.scalars(
            _scoped(
                select(Request).where(Request.process == process, Request.document_key == str(document_key)),
                all_companies,
                company_ids,
            ).order_by(Request.id.desc())
        )
    )
    decisions = _decisions(db, [r.id for r in rows])
    return [_request_out(db, r, decisions[r.id]) for r in rows]


def inbox(db: Session, *, actor_user_id: int, all_companies: bool, company_ids) -> list[dict]:
    """The requests waiting for this user's decision, their own steps and those of whoever they stand in for, the
    longest waiting first."""
    pending = list(
        db.scalars(
            _scoped(select(Request).where(Request.status == "pending"), all_companies, company_ids).order_by(
                Request.step_since, Request.id
            )
        )
    )
    if not pending:
        return []
    holders = identity.holders(db, _step_roles(r.steps[r.current] for r in pending))
    me = {actor_user_id} | _delegators(db, actor_user_id)
    mine = [r for r in pending if _approvers(r.steps[r.current], r.escalated, holders) & me]
    decisions = _decisions(db, [r.id for r in mine])
    return [_request_out(db, r, decisions[r.id]) for r in mine]


# ------------------------------------------------------------------ delegation while away (FR-WFL-05)


def _delegation_out(db: Session, rows: list[Delegation]) -> list[dict]:
    users = identity.user_refs(db, {x for d in rows for x in (d.user_id, d.delegate_id)})
    d0 = today()

    def status(d: Delegation) -> str:
        if d.cancelled_at:
            return "cancelled"
        if d.date_to < d0:
            return "ended"
        return "upcoming" if d.date_from > d0 else "active"

    return [
        {
            "id": str(d.public_id),
            "user": users.get(d.user_id),
            "delegate": users.get(d.delegate_id),
            "date_from": d.date_from,
            "date_to": d.date_to,
            "reason": d.reason,
            "status": status(d),
        }
        for d in rows
    ]


def list_delegations(db: Session, *, user_id: int | None) -> list[dict]:
    """Everyone's (who manages the workflows), or this user's: given and received."""
    q = select(Delegation).order_by(Delegation.date_from.desc(), Delegation.id.desc()).limit(300)
    if user_id is not None:
        q = q.where((Delegation.user_id == user_id) | (Delegation.delegate_id == user_id))
    return _delegation_out(db, list(db.scalars(q)))


def add_delegation(
    db: Session, *, user_id: int, delegate_public_id, date_from, date_to, reason: str | None, actor_user_id: int
) -> dict:
    delegate_id = identity.user_id(db, delegate_public_id)
    if delegate_id == user_id:
        raise AppError(422, "delegate_self")
    if date_to < date_from:
        raise AppError(422, "invalid_range")
    if date_to < today():
        raise AppError(422, "delegation_in_past")
    d = Delegation(
        user_id=user_id,
        delegate_id=delegate_id,
        date_from=date_from,
        date_to=date_to,
        reason=reason,
        created_by=actor_user_id,
    )
    db.add(d)
    db.flush()
    db.refresh(d)
    names = identity.user_refs(db, {user_id, delegate_id})
    audit.record(
        db,
        action="approvals.delegation_added",
        entity_type="delegation",
        entity_id=d.public_id,
        actor_user_id=actor_user_id,
        after={
            "user": names[user_id]["name"],
            "delegate": names[delegate_id]["name"],
            "from": date_from,
            "to": date_to,
            "reason": reason,
        },
    )
    db.commit()
    return _delegation_out(db, [d])[0]


def cancel_delegation(db: Session, public_id, *, actor_user_id: int, manager: bool) -> dict:
    d = db.scalar(select(Delegation).where(Delegation.public_id == public_id).with_for_update())
    if d is None or not (manager or d.user_id == actor_user_id):
        raise AppError(404, "delegation_not_found")
    if d.cancelled_at is None:
        d.cancelled_at = utcnow()
        audit.record(
            db,
            action="approvals.delegation_cancelled",
            entity_type="delegation",
            entity_id=d.public_id,
            actor_user_id=actor_user_id,
        )
        db.commit()
    return _delegation_out(db, [d])[0]


# ------------------------------------------------------------------ escalation after a time (FR-WFL-05)


def escalate(db: Session) -> int:
    """Steps that waited longer than their workflow allows open to the escalation role too, once per step, with an
    alert (beat, every quarter of an hour)."""
    now = utcnow()
    n = 0
    rows = db.scalars(
        select(Request)
        .where(Request.status == "pending", Request.escalated.is_(False))
        .with_for_update(skip_locked=True)
    )
    for req in rows:
        hours = req.steps[req.current].get("escalate_after_hours")
        if not hours or now - req.step_since < timedelta(hours=hours):
            continue
        req.escalated = True
        db.add(Decision(request_id=req.id, step=req.current, decision="escalated"))
        notifications.raise_alert(
            db,
            "approval_escalated",
            company_id=req.company_id,
            entity_type="approval",
            entity_id=req.public_id,
            params={"ref": req.document_ref, "hours": hours},
            dedupe_key=f"approval:{req.id}:{req.current}",
        )
        n += 1
    db.commit()
    return n
