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
        "pay": out.pay,
        "penalties": out.penalties,
        "uncovered": out.uncovered,
        "net": out.pay - out.penalties,
        "needs": needs(blocks, facts),
    }
