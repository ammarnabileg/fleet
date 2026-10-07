"""Payroll (BRD FR-RPT-07): by month and company, the installments by their source, and what was carried forward.

Each payroll run in the months asked for, with its lines totalled (a draft is shown as such: it can still change).
An installment due in a month that the monthly cap left undeducted is carried to the next month, where it is due again:
what is carried is therefore read month by month and never added up across months (it would count twice).
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.org import service as org
from app.modules.payroll.models import SOURCES, Deduction, Line, LineDeduction, Run
from app.modules.people.models import Employee
from app.modules.reports.filters import Filters
from app.modules.reports.service import _people

ZERO = Decimal("0.000")
MAX_MONTHS = 24
CARRIED_LIMIT = 500


def _months(month_from: date, month_to: date) -> tuple[date, date]:
    first, last = month_from.replace(day=1), month_to.replace(day=1)
    if last < first:
        raise AppError(422, "invalid_range")
    if (last.year - first.year) * 12 + last.month - first.month >= MAX_MONTHS:
        raise AppError(422, "range_too_long_months", months=MAX_MONTHS)
    return first, last


def _lines(q, filters: Filters):
    if filters.branch_id is not None:
        q = q.where(Employee.branch_id == filters.branch_id)
    if filters.driver_id is not None:
        q = q.where(Employee.id == filters.driver_id)
    return q


def _source(s: dict) -> dict:
    return {
        "due": s["due"].quantize(ZERO),
        "deducted": s["deducted"].quantize(ZERO),
        "carried": (s["due"] - s["deducted"]).quantize(ZERO),
    }


def payroll_report(
    db: Session, *, month_from: date, month_to: date, filters: Filters, all_companies: bool, company_ids
) -> dict:
    first, last = _months(month_from, month_to)
    q = select(Run).where(Run.month.between(first, last))
    if not all_companies:
        q = q.where(Run.company_id.in_(list(company_ids)))
    runs = list(db.scalars(q.order_by(Run.month, Run.company_id)))
    ids = [r.id for r in runs]
    companies = {c["id"]: c for c in org.list_companies(db, all_companies=True, company_ids=())}

    sums = {}
    by_source: dict[int, dict] = defaultdict(dict)
    carried_rows = []
    if ids:
        q = (
            select(
                Line.run_id,
                func.count(),
                func.coalesce(func.sum(Line.gross), 0),
                func.coalesce(func.sum(Line.deductions), 0),
                func.coalesce(func.sum(Line.net), 0),
            )
            .join(Employee, Employee.id == Line.employee_id)
            .where(Line.run_id.in_(ids))
            .group_by(Line.run_id)
        )
        sums = {r[0]: r[1:] for r in db.execute(_lines(q, filters))}
        q = (
            select(
                Line.run_id,
                Deduction.source_type,
                func.sum(LineDeduction.due),
                func.sum(LineDeduction.deducted),
            )
            .join(LineDeduction, LineDeduction.line_id == Line.id)
            .join(Deduction, Deduction.id == LineDeduction.deduction_id)
            .join(Employee, Employee.id == Line.employee_id)
            .where(Line.run_id.in_(ids))
            .group_by(Line.run_id, Deduction.source_type)
        )
        for run_id, source, due, deducted in db.execute(_lines(q, filters)):
            by_source[run_id][source] = {"due": Decimal(due), "deducted": Decimal(deducted)}
        q = (
            select(Line.run_id, Line.employee_id, Deduction, LineDeduction.due, LineDeduction.deducted)
            .join(LineDeduction, LineDeduction.line_id == Line.id)
            .join(Deduction, Deduction.id == LineDeduction.deduction_id)
            .join(Employee, Employee.id == Line.employee_id)
            .where(Line.run_id.in_(ids), LineDeduction.due > LineDeduction.deducted)
            .order_by(Line.run_id, (LineDeduction.due - LineDeduction.deducted).desc())
            .limit(CARRIED_LIMIT)
        )
        carried_rows = list(db.execute(_lines(q, filters)))

    by_run = {}
    out_runs = []
    for r in runs:
        count, gross, deductions, net = sums.get(r.id, (0, ZERO, ZERO, ZERO))
        sources = by_source.get(r.id, {})
        due = sum((s["due"] for s in sources.values()), ZERO)
        deducted = sum((s["deducted"] for s in sources.values()), ZERO)
        row = {
            "id": str(r.public_id),
            "month": r.month,
            "company": {"id": r.company_id, "name": companies.get(r.company_id, {}).get("name")},
            "status": r.status,
            "lines": count,
            "gross": Decimal(gross).quantize(ZERO),
            "deductions": Decimal(deductions).quantize(ZERO),
            "net": Decimal(net).quantize(ZERO),
            "installments_due": due.quantize(ZERO),
            "installments_deducted": deducted.quantize(ZERO),
            "carried": (due - deducted).quantize(ZERO),
            "by_source": {s: _source(sources[s]) for s in SOURCES if s in sources},
        }
        by_run[r.id] = row
        out_runs.append(row)

    names = _people(db, {e for _, e, _, _, _ in carried_rows})
    carried = [
        {
            "run_id": by_run[run_id]["id"],
            "month": by_run[run_id]["month"],
            "employee": names.get(employee_id),
            "source_type": d.source_type,
            "reason": d.reason,
            "due": Decimal(due).quantize(ZERO),
            "deducted": Decimal(deducted).quantize(ZERO),
            "carried": (Decimal(due) - Decimal(deducted)).quantize(ZERO),
        }
        for run_id, employee_id, d, due, deducted in carried_rows
    ]
    totals = {k: sum((r[k] for r in out_runs), ZERO) for k in ("gross", "deductions", "net", "installments_deducted")}
    totals["lines"] = sum(r["lines"] for r in out_runs)
    return {"from": first, "to": last, "runs": out_runs, "totals": totals, "carried": carried}
