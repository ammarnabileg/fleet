"""Cash (BRD FR-RPT-04): the drivers' balances and how old they are, the receipts by who collected them, and the
treasury's movement with its bank deposits.

How old a balance is: what a driver hands in pays off his oldest cash first, so what he still holds is the latest
of what he collected. Each approved amount on his account (a day's collection, an adjustment in his debit) is aged
from its business date; the amounts he handed in (receipts, credits) are taken off the oldest first. A reversed
receipt is cash he holds again from the day of the reversal. Unapproved collections are shown apart, not aged.

The treasury is per branch and shared by every company of the branch (as in the cash page), so the company filter does
not apply to it; it needs the treasury permission.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, BIGINT
from sqlalchemy.orm import Session

from app.core.clock import today
from app.modules.identity import service as identity
from app.modules.org import service as org
from app.modules.reports.filters import Filters
from app.modules.reports.service import _people, _period

ZERO = Decimal("0.000")
AGES = (("d0_1", 0, 1), ("d2_3", 2, 3), ("d4_7", 4, 7), ("d8_plus", 8, None))  # days since the business date

AGING = text("""
WITH drivers AS (
    SELECT e.id FROM people.employees e
    WHERE e.is_driver AND (:all_companies OR e.company_id = ANY(:company_ids))
      AND (CAST(:branch_id AS bigint) IS NULL OR e.branch_id = :branch_id)
      AND (CAST(:driver_id AS bigint) IS NULL OR e.id = :driver_id)
),
lines AS (
    SELECT a.driver_id, l.amount, j.business_date, j.id AS journal_id
    FROM cash.journal_lines l
    JOIN cash.journals j ON j.id = l.journal_id
    JOIN cash.accounts a ON a.id = l.account_id
    JOIN drivers d ON d.id = a.driver_id
    WHERE a.kind = 'driver' AND j.status = 'posted'
),
paid AS (SELECT driver_id, -sum(amount) AS paid FROM lines WHERE amount < 0 GROUP BY driver_id),
owed AS (
    SELECT driver_id, amount, business_date,
           sum(amount) OVER (PARTITION BY driver_id ORDER BY business_date, journal_id) AS upto
    FROM lines WHERE amount > 0
)
SELECT o.driver_id, o.business_date, LEAST(o.amount, GREATEST(o.upto - COALESCE(p.paid, 0), 0)) AS held
FROM owed o LEFT JOIN paid p USING (driver_id)
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))

BALANCES = text("""
WITH drivers AS (
    SELECT e.id FROM people.employees e
    WHERE e.is_driver AND (:all_companies OR e.company_id = ANY(:company_ids))
      AND (CAST(:branch_id AS bigint) IS NULL OR e.branch_id = :branch_id)
      AND (CAST(:driver_id AS bigint) IS NULL OR e.id = :driver_id)
)
SELECT a.driver_id, b.posted, b.pending
FROM cash.accounts a JOIN cash.balances b ON b.account_id = a.id JOIN drivers d ON d.id = a.driver_id
WHERE a.kind = 'driver'
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))

COLLECTORS = text("""
SELECT r.created_by,
       count(*) FILTER (WHERE NOT x.reversed) AS receipts,
       COALESCE(sum(r.amount) FILTER (WHERE NOT x.reversed), 0) AS amount,
       count(*) FILTER (WHERE NOT x.reversed AND r.driver_confirmed_at IS NOT NULL) AS confirmed,
       count(*) FILTER (WHERE x.reversed) AS reversed
FROM cash.receipts r
JOIN people.employees e ON e.id = r.driver_id
CROSS JOIN LATERAL (
    SELECT EXISTS (
        SELECT 1 FROM cash.journals j WHERE j.kind = 'reversal' AND j.source_type = 'receipt' AND j.source_id = r.id
    ) AS reversed
) x
WHERE r.created_at >= :start AND r.created_at < :end
  AND (:all_companies OR e.company_id = ANY(:company_ids))
  AND (CAST(:branch_id AS bigint) IS NULL OR r.branch_id = :branch_id)
  AND (CAST(:driver_id AS bigint) IS NULL OR r.driver_id = :driver_id)
GROUP BY r.created_by
ORDER BY amount DESC
""").bindparams(bindparam("company_ids", type_=ARRAY(BIGINT)))

TREASURY = text("""
SELECT a.branch_id,
       COALESCE(sum(l.amount) FILTER (WHERE j.business_date < :date_from), 0) AS opening,
       COALESCE(sum(l.amount) FILTER (WHERE j.business_date BETWEEN :date_from AND :date_to AND l.amount > 0), 0)
           AS received,
       COALESCE(sum(-l.amount) FILTER (WHERE j.business_date BETWEEN :date_from AND :date_to AND l.amount < 0), 0)
           AS paid_out,
       COALESCE(sum(l.amount) FILTER (WHERE j.business_date <= :date_to), 0) AS closing
FROM cash.journal_lines l
JOIN cash.journals j ON j.id = l.journal_id
JOIN cash.accounts a ON a.id = l.account_id
WHERE a.kind = 'treasury' AND j.status = 'posted'
  AND (CAST(:branch_id AS bigint) IS NULL OR a.branch_id = :branch_id)
GROUP BY a.branch_id
""")

DEPOSITS = text("""
SELECT j.public_id, j.business_date, j.reason, j.created_by, a.branch_id, l.amount,
       j.attachment_sha256 IS NOT NULL AS has_receipt,
       EXISTS (SELECT 1 FROM cash.journals x WHERE x.reverses_id = j.id) AS reversed
FROM cash.journals j
JOIN cash.journal_lines l ON l.journal_id = j.id
JOIN cash.accounts a ON a.id = l.account_id AND a.kind = 'bank'
WHERE j.kind = 'bank_deposit' AND j.status = 'posted' AND j.business_date BETWEEN :date_from AND :date_to
  AND (CAST(:branch_id AS bigint) IS NULL OR a.branch_id = :branch_id)
ORDER BY j.business_date DESC, j.id DESC
""")


def _age(day: date, as_of: date) -> str:
    days = (as_of - day).days
    return next(key for key, low, high in AGES if days >= low and (high is None or days <= high))


def cash_report(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    filters: Filters,
    with_treasury: bool,
    all_companies: bool,
    company_ids,
) -> dict:
    start, end = _period(date_from, date_to)
    params = {
        "all_companies": all_companies,
        "company_ids": list(company_ids),
        "branch_id": filters.branch_id,
        "driver_id": filters.driver_id,
    }
    as_of = today()

    buckets: dict[int, dict] = defaultdict(lambda: {key: ZERO for key, _, _ in AGES} | {"oldest": None})
    for r in db.execute(AGING, params).mappings():
        if r["held"] <= 0:
            continue
        b = buckets[r["driver_id"]]
        b[_age(r["business_date"], as_of)] += r["held"]
        b["oldest"] = min(filter(None, (b["oldest"], r["business_date"])))
    balances = {r.driver_id: (r.posted, r.pending) for r in db.execute(BALANCES, params)}
    names = _people(db, set(balances) | set(buckets))
    rows = []
    for driver_id in set(balances) | set(buckets):
        posted, pending = balances.get(driver_id, (ZERO, ZERO))
        b = buckets.get(driver_id) or {key: ZERO for key, _, _ in AGES} | {"oldest": None}
        if not posted and not pending:
            continue
        rows.append(
            {
                "driver": names.get(driver_id),
                "posted": Decimal(posted).quantize(ZERO),
                "pending": Decimal(pending).quantize(ZERO),
                **{key: b[key].quantize(ZERO) for key, _, _ in AGES},
                "oldest": b["oldest"],
                "oldest_days": (as_of - b["oldest"]).days if b["oldest"] else None,
            }
        )
    rows.sort(key=lambda r: (-r["d8_plus"], -r["posted"], r["driver"]["id"] if r["driver"] else ""))
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("posted", "pending", *(key for key, _, _ in AGES))}

    window = params | {"start": start, "end": end}
    found = list(db.execute(COLLECTORS, window).mappings())
    users = identity.user_names(db, {r["created_by"] for r in found})
    collectors = [
        {
            "user": users.get(r["created_by"], ""),
            "receipts": r["receipts"],
            "amount": Decimal(r["amount"]).quantize(ZERO),
            "confirmed": r["confirmed"],
            "reversed": r["reversed"],
        }
        for r in found
    ]

    out = {
        "from": date_from,
        "to": date_to,
        "as_of": as_of,
        "aging": {"rows": rows, "totals": totals},
        "collectors": collectors,
        "treasury": None,
        "deposits": None,
    }
    if with_treasury:
        branches = {b["id"]: b for b in org.list_branches(db)}
        span = {"date_from": date_from, "date_to": date_to, "branch_id": filters.branch_id}
        out["treasury"] = [
            {
                "branch": branches.get(r["branch_id"]),
                **{k: Decimal(r[k]).quantize(ZERO) for k in ("opening", "received", "paid_out", "closing")},
            }
            for r in db.execute(TREASURY, span).mappings()
        ]
        deposits = list(db.execute(DEPOSITS, span).mappings())
        by = identity.user_names(db, {r["created_by"] for r in deposits})
        out["deposits"] = [
            {
                "id": str(r["public_id"]),
                "business_date": r["business_date"],
                "branch": branches.get(r["branch_id"]),
                "amount": Decimal(r["amount"]).quantize(ZERO),
                "reference": r["reason"],
                "by": by.get(r["created_by"], ""),
                "reversed": r["reversed"],
                "has_receipt": r["has_receipt"],  # the bank's receipt, shown from /cash/journals/{id}/attachment
            }
            for r in deposits
        ]
    return out
