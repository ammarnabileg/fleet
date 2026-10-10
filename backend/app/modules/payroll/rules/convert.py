"""The four calculators written as block lists that give the same money: how every existing scheme, and a platform's
own pay rule, becomes a version the designer shows and edits. The calculators stay for the versions and runs that
used them; tests run both on the same months (tests/test_rules_engine.py)."""

from decimal import Decimal

from app.modules.payroll.calculators import Rules


def _m(v) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.001")))


def _block(type_: str, params: dict | None = None, condition=None, **extra) -> dict:
    return {
        "type": type_,
        "params": params or {},
        "condition": condition or [],
        "on_exception": extra.get("on_exception", "none"),
        "group": extra.get("group"),
        "label": None,
    }


def _missing(rules: Rules) -> list[dict]:
    if not rules.missing_order_rate:
        return []
    return [
        _block(
            "missing_orders", {"source": "orders", "target": rules.target_orders, "rate": _m(rules.missing_order_rate)}
        )
    ]


COVER_KINDS = {"maintenance": "maintenance", "housing": "housing", "gas": "gas", "sim": "phone"}


def covers(company_covers) -> list[dict]:
    """What the scheme puts on the company, as expense blocks (informational, decision G): the parts that ask what
    the company bears (fuel claims, maintenance) keep reading it from the blocks."""
    return [
        _block("expense", {"kind": COVER_KINDS[c], "responsibility": "company"})
        for c in ("maintenance", "housing", "gas", "sim")
        if c in (company_covers or [])
    ]


def from_rules(rules: Rules, company_covers=()) -> list[dict]:
    """A scheme's calculator and numbers as blocks, with what it puts on the company (floor_at_zero stays the
    version's own setting)."""
    return _from_rules(rules) + covers(company_covers)


def _from_rules(rules: Rules) -> list[dict]:
    calc, steps = rules.calculator, rules.steps
    if calc == "per_order":
        return [_block("per_order", {"rate": _m(rules.per_order), "source": "orders"}), *_missing(rules)]
    if calc == "batch":
        rates = [{"batch": int(s.threshold), "rate": _m(s.amount)} for s in steps.get("batch_rate", [])]
        return [_block("batch_rate", {"rates": rates, "personal_rate": False}), *_missing(rules)]
    if calc == "tiered_target":
        out = [
            _block("per_order", {"rate": _m(rules.per_order), "source": "orders"}),
            _block(
                "price_change",
                {"rate": _m(rules.reduced_rate), "mode": "replace"},
                [{"fact": "star_day_failed", "op": "is_true"}],
                group="reduced",
            ),
        ]
        reduce = steps.get("marks_reduce", [])
        if reduce:  # the lowest number of marks from which every order is paid at the reduced price
            out.append(
                _block(
                    "price_change",
                    {"rate": _m(rules.reduced_rate), "mode": "replace"},
                    [{"fact": "marks", "op": "gte", "value": int(reduce[0].threshold)}],
                    group="reduced",
                )
            )
        not_reduced = [{"fact": "price_changed", "op": "is_false"}]  # decisions A and C
        tiers = [{"from": int(s.threshold), "amount": _m(s.amount)} for s in steps.get("tier_bonus", [])]
        if tiers:
            cond = [] if rules.bonus_when_reduced else not_reduced
            out.append(_block("tier_bonus", {"source": "orders", "mode": "highest", "tiers": tiers}, cond))
        out += _missing(rules)  # the scheme's own rate, even on a reduced month (decision B)
        table = [{"from": int(s.threshold), "amount": _m(s.amount)} for s in steps.get("marks_deduction", [])]
        if table:
            cond = [] if rules.marks_when_reduced else not_reduced
            out.append(_block("attendance_marks", {"mode": "table", "table": table}, cond))
        return out
    raise ValueError(calc)


def from_platform(platform) -> list[dict]:
    """A platform's own pay rule (basic salary, rates per order, hour and valid day, the invalid-days rule) as blocks.
    A rule that pays nothing still pays: its block list is the basic salary of the driver's contract (or nothing)."""
    out = []
    if platform.pay_basic:
        out.append(_block("fixed_salary", {"mode": "contract"}))
    for source, rate in (
        ("orders", platform.per_order),
        ("hours", platform.per_hour),
        ("valid_days", platform.per_valid_day),
    ):
        if rate:
            out.append(_block("per_order", {"rate": _m(rate), "source": source}))
    if platform.invalid_days == "daily_wage":
        out.append(_block("invalid_days", {"mode": "daily_wage", "divisor": int(platform.day_divisor)}))
    elif platform.invalid_days == "fixed":
        amount = _m(platform.invalid_day_amount or 0)
        out.append(_block("invalid_days", {"mode": "fixed", "amount": amount, "divisor": int(platform.day_divisor)}))
    return out
