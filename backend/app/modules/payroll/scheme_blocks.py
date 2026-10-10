"""A scheme's rules as blocks, edited in the rules designer: each save is a version «يسري من شهر» (the versions of
schemes.py), never a month an approved payroll paid on the scheme; a scheme nobody was paid on is simply redefined.
A scheme starts from a template (its blocks copied, every value editable) or from a single price per order."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.payroll import forms, rules, schemes
from app.modules.payroll.models import Platform, Scheme, SchemeVersion
from app.modules.payroll.rules.engine import validate
from app.modules.payroll.service import month_start

COVERS = {"maintenance": "maintenance", "housing": "housing", "gas": "gas", "phone": "sim"}
BLANK = [{"type": "per_order", "params": {"rate": "0.000", "source": "orders"}, "condition": [], "on_exception": "none",
          "group": None, "label": None}]  # fmt: skip


def covers_of(blocks: list[dict]) -> list[str]:
    """What the blocks put on the company (informational expenses), for the parts that ask (maintenance)."""
    out = []
    for b in blocks:
        if b["type"] == "expense" and b["params"].get("responsibility") == "company":
            c = COVERS.get(b["params"].get("kind"))
            if c and c not in out:
                out.append(c)
    return sorted(out)


def _sources(db: Session, platform_id: int) -> list[dict]:
    f = forms.get(db, platform_id)
    return [
        {"key": x["key"], "label": x["label"], "type": x["type"], "scope": scope}
        for scope in ("daily", "monthly")
        for x in f[scope]
        if not x.get("builtin") and x["type"] != "choice"
    ]


def _tasks(db: Session, platform_id: int) -> list[dict]:
    f = forms.get(db, platform_id)
    return next((x["options"] for x in f["monthly"] if x["type"] == "task_counts"), [])


def designer(db: Session, public_id) -> dict:
    s = schemes._by_public_id(db, public_id)
    p = db.get(Platform, s.platform_id)
    versions = schemes._versions(db, [s.id])[s.id]
    users = identity.user_names(db, {v.created_by for v in versions if v.created_by})
    return {
        "scheme": {
            "id": str(s.public_id),
            "code": s.code,
            "name": s.name,
            "platform_id": s.platform_id,
            "calculator": s.calculator,
            "is_active": s.is_active,
            "driver_selectable": s.driver_selectable,
            "version": s.version,
        },
        "platform": {"id": p.id, "name": p.name},
        "sources": _sources(db, p.id),
        "tasks": _tasks(db, p.id),
        "used": bool(schemes._used_ids(db, [s.id])),
        "change_from": schemes._change_from(versions, schemes._last_paid(db, [s.id]).get(s.id)),
        "versions": [
            {
                "version_no": v.version_no,
                "effective_month": v.effective_month,
                "blocks": v.blocks,
                "floor_at_zero": v.floor_at_zero,
                "terms": None if v.blocks is not None else schemes._terms(v),
                "note": v.note,
                "created_by": users.get(v.created_by),
                "created_at": v.created_at,
            }
            for v in reversed(versions)
        ],
    }


def _terms_from(latest: SchemeVersion | None, blocks: list[dict], floor: bool) -> dict:
    base = {k: getattr(latest, k) for k in schemes.TERMS_BY_VERSION} if latest else {
        "per_order": None, "target_orders": 420, "required_valid_days": 28, "missing_order_rate": None,
        "reduced_rate": None, "bonus_when_reduced": False, "marks_when_reduced": False, "floor_at_zero": True,
        "company_covers": [],
    }  # fmt: skip
    return base | {"floor_at_zero": floor, "company_covers": covers_of(blocks), "steps": []}


def _add(db, s, no, month, blocks, floor, latest, *, note, actor_user_id) -> SchemeVersion:
    v = schemes._new_version(
        db, s, no, month, _terms_from(latest, blocks, floor), note=note, actor_user_id=actor_user_id
    )
    v.blocks = blocks
    return v


def save(db: Session, public_id, *, version: int, data: dict, actor_user_id: int) -> dict:
    s = schemes._by_public_id(db, public_id, lock=True)
    if s.version != version:
        raise AppError(409, "version_conflict")
    blocks = validate(data["blocks"], sources={x["key"] for x in _sources(db, s.platform_id)})
    floor, note, month = data.get("floor_at_zero", True), data.get("note"), data.get("effective_month")
    versions = schemes._versions(db, [s.id])[s.id]
    latest = versions[-1] if versions else None
    used = bool(schemes._used_ids(db, [s.id]))
    before = {"version_no": latest.version_no if latest else None, "blocks": latest.blocks if latest else None}
    if not used and month is None:  # nobody was paid on it: redefined, one version from its first month
        target = versions[0].effective_month if versions else month_start(today())
        for v in versions:
            db.delete(v)
        db.flush()
        _add(db, s, 1, target, blocks, floor, latest, note=note, actor_user_id=actor_user_id)
        if s.calculator != "blocks":
            s.calculator = "blocks"
    else:
        if month is None:
            raise AppError(422, "field_required", field="effective_month")
        target = month_start(month)
        earliest = schemes._change_from(versions, schemes._last_paid(db, [s.id]).get(s.id))
        if target < earliest:
            raise AppError(409, "scheme_version_month", **{"from": earliest.isoformat()[:7]})
        no = latest.version_no + 1
        if target == latest.effective_month:  # the latest version, not paid on yet, is replaced
            no = latest.version_no
            db.delete(latest)
            db.flush()
        _add(db, s, no, target, blocks, floor, latest, note=note, actor_user_id=actor_user_id)
    db.flush()
    newest = schemes._versions(db, [s.id])[s.id][-1]
    schemes._mirror(db, s, schemes._terms(newest))
    s.version += 1
    db.flush()
    audit.record(
        db,
        action="scheme.rules_set",
        entity_type="scheme",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after={
            "from": target.isoformat(),
            "version_no": newest.version_no,
            "blocks": blocks,
            "floor_at_zero": floor,
            "note": note,
        },  # fmt: skip
    )
    db.commit()
    return designer(db, s.public_id)


def from_template(db: Session, data: dict, *, actor_user_id: int) -> dict:
    """A new scheme of a platform, its blocks copied from a template (or a single price per order to edit)."""
    p = db.get(Platform, data["platform_id"])
    if p is None:
        raise AppError(404, "platform_not_found")
    if data.get("template"):
        t = rules.template(data["template"])
        if t is None:
            raise AppError(404, "rule_template_not_found")
        blocks, description = t["blocks"], t["description"]
    else:
        blocks, description = validate(BLANK), None
    s = Scheme(
        platform_id=p.id,
        code=data["code"],
        name=i18n.validate_localized(db, data["name"]),
        description=description,
        calculator="blocks",
        driver_selectable=data.get("driver_selectable", True),
        company_covers=covers_of(blocks),
        created_by=actor_user_id,
    )
    db.add(s)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "schemes_platform_id_key":
            raise
        raise AppError(409, "scheme_code_taken") from None
    db.refresh(s)
    _add(db, s, 1, month_start(today()), blocks, True, None, note=None, actor_user_id=actor_user_id)
    db.flush()
    audit.record(
        db,
        action="scheme.created",
        entity_type="scheme",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        after={"platform_id": p.id, "code": s.code, "template": data.get("template"), "blocks": blocks},
    )
    db.commit()
    return schemes.get(db, s.public_id)
