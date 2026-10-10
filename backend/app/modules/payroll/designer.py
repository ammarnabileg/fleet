"""What the rules designer does with a block list besides storing it: tries it on sample figures («جرّب»), and
describes each line for the payslip and the panel."""

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.payroll import forms
from app.modules.payroll.rules.engine import Facts, MonthException, needs, run, validate

SAMPLE_INTS = ("orders", "valid_days", "working_days", "attendance_marks", "late_count", "absent_days", "batch_level")


def _sample(month: dict) -> Facts:
    try:
        ints = {k: int(month[k]) for k in SAMPLE_INTS if month.get(k) not in (None, "")}
        if any(v < 0 for v in ints.values()):
            raise ValueError
        star = month.get("star_day_failed")
        batches = tuple((int(b["batch"]), int(b["orders"])) for b in month.get("batches") or [] if b.get("batch"))
        tasks = {str(k): int(v) for k, v in (month.get("tasks") or {}).items()} or None
        fields = {}
        for k, v in (month.get("fields") or {}).items():
            fields[str(k)] = v if isinstance(v, bool) else Decimal(str(v))
        exceptions = tuple(
            MonthException(e["kind"], int(e.get("days") or 0), dict(e.get("corrections") or {}))
            for e in month.get("exceptions") or []
        )

        def money(k):
            return Decimal(str(month[k])) if month.get(k) not in (None, "") else None

        return Facts(
            **{k: v for k, v in ints.items() if k != "batch_level"},
            batch_level=ints.get("batch_level"),
            hours=money("hours"),
            star_day_failed=None if star is None else bool(star),
            batches=batches or None,
            tasks=tasks,
            basic_salary=money("basic_salary"),
            personal_rate=money("personal_rate"),
            fields=fields,
            exceptions=exceptions,
        )
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise AppError(422, "rule_sample_invalid") from None


def line_out(item) -> dict:
    return {
        "code": item.code,
        "amount": str(item.amount),
        "why": item.why,
        "formula": getattr(item, "formula", "") or "",
        "block": getattr(item, "block", None),
        "type": getattr(item, "type", None),
    }


def preview(db: Session, data: dict) -> dict:
    sources = forms.sources(db, data.get("platform_id")) if data.get("platform_id") else None
    blocks = validate(data["blocks"], sources=sources)
    facts = _sample(data.get("month") or {})
    out = run(blocks, facts, floor_at_zero=data.get("floor_at_zero", True))
    return {
        "blocks": blocks,
        "lines": [line_out(i) for i in out.items],
        "trace": out.trace,
        "pay": str(out.pay),
        "penalties": str(out.penalties),
        "uncovered": str(out.uncovered),
        "net": str(out.pay - out.penalties),
        "needs": needs(blocks, facts),
    }


# ------------------------------------------------------------------ the month's six stages


def _state(problem: bool, done: bool) -> str:
    return "problem" if problem else "done" if done else "todo"


def month_status(db: Session, *, month, all_companies: bool, company_ids) -> dict:
    """Where the month stands, stage by stage, with live counts: data collected, checked, each driver's policy, the
    engine run, review and approval, the month closed. Counts only, in the user's companies; the panel says them."""
    from sqlalchemy import func, select

    from app.modules.org import service as org
    from app.modules.payroll import month as months
    from app.modules.payroll import platforms
    from app.modules.payroll.models import Line, Objection, Run, Statement, Uncollected
    from app.modules.payroll.month_models import MonthImport
    from app.modules.payroll.service import month_start

    month = month_start(month)
    scope = {"all_companies": all_companies, "company_ids": company_ids}
    totals = {k: 0 for k in ("drivers", "values_missing", "daily_pending", "orders_conflict", "driver_id_missing")}
    totals["scheme_missing"] = 0
    used: set = set()
    for p in platforms.all_by_id(db).values():
        if not p.is_active:
            continue
        r = months.review(db, platform_id=p.id, month=month, **scope)
        totals["drivers"] += r["drivers"]
        for k in ("values_missing", "daily_pending", "orders_conflict", "driver_id_missing", "scheme_missing"):
            totals[k] += r["problems"].get(k, 0)
        used |= {x["scheme"]["id"] for x in r["rows"] if x["scheme"]}
    q = select(func.count()).select_from(Statement).where(Statement.month == month, Statement.status == "submitted")
    if not all_companies:
        q = q.where(Statement.company_id.in_(list(company_ids)))
    pending_statements = db.scalar(q)
    imports = db.scalar(select(func.count()).select_from(MonthImport).where(MonthImport.month == month))
    rq = select(Run).where(Run.month == month)
    if not all_companies:
        rq = rq.where(Run.company_id.in_(list(company_ids)))
    runs = list(db.scalars(rq))
    drafts = [r for r in runs if r.status == "draft"]
    blocking = sum(int((r.totals or {}).get("blocking", 0)) for r in drafts)
    missing_lines = 0
    if drafts:
        missing_lines = db.scalar(
            select(func.count())
            .select_from(Line)
            .where(Line.run_id.in_([r.id for r in drafts]), Line.flags.any("figures_missing"))
        )
    approved = [r for r in runs if r.status != "draft"]

    def scoped_count(model, *where):
        q = select(func.count()).select_from(model).where(model.month == month, *where)
        return db.scalar(q if all_companies else q.where(model.company_id.in_(list(company_ids))))

    objections = scoped_count(Objection, Objection.status.in_(("open", "in_review")))
    to_review = scoped_count(Uncollected, Uncollected.status == "review")
    gate_off = not org.get_section(db, "payroll").live_approval_enabled
    paid = [r for r in runs if r.status == "paid"]
    link_month = f"payroll?tab=month&month={month.isoformat()[:7]}"
    run_link = f"payroll/run/{runs[0].public_id}" if len(runs) == 1 else "payroll?tab=runs"
    return {
        "month": month,
        "collect": {
            "state": _state(bool(totals["values_missing"] or totals["daily_pending"]), totals["drivers"] > 0),
            "counts": {k: totals[k] for k in ("drivers", "values_missing", "daily_pending")} | {"imports": imports},
            "link": link_month,
        },
        "check": {
            "state": _state(bool(totals["orders_conflict"] or pending_statements), totals["drivers"] > 0),
            "counts": {
                "orders_conflict": totals["orders_conflict"],
                "statements_pending": pending_statements,
                "driver_id_missing": totals["driver_id_missing"],
            },
            "link": link_month,
        },
        "policy": {
            "state": _state(bool(totals["scheme_missing"]), totals["drivers"] > 0),
            "counts": {"scheme_missing": totals["scheme_missing"], "schemes": len(used)},
            "link": "payroll?tab=schemes",
        },
        "engine": {
            "state": _state(bool(missing_lines), bool(runs)),
            "counts": {"runs": len(runs), "drafts": len(drafts), "figures_missing": missing_lines},
            "link": run_link,
        },
        "review": {
            "state": _state(bool(blocking or (drafts and gate_off)), bool(runs) and not drafts),
            "counts": {
                "blocking": blocking,
                "approved": len(approved),
                "objections_open": objections,
                "gate_off": int(gate_off),
            },
            "link": run_link,
        },
        "close": {
            "state": _state(False, bool(runs) and len(approved) == len(runs)),
            "counts": {"approved": len(approved), "paid": len(paid), "uncollected": to_review},
            "link": run_link,
        },
    }
