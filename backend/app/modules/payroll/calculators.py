"""How a pay scheme turns a month's figures into earnings and penalties. One calculator per shape of rule, never per
platform: a platform and its schemes are data (payroll.schemes, payroll.scheme_steps) naming their calculator, so a
platform whose rules fit these shapes needs no code, and a new shape is one class registered here.

"platform_rates" is not here: it means the platform's own pay rule (basic salary, rates per order, hour and valid
day, the invalid-days rule), which the run engine applies as it always has.

The client's open decisions (docs/payroll-schemes.md, section 6) are columns of the scheme, with their defaults:
no tier bonus and no marks deduction on a reduced month, the missing-target rate is the scheme's own (not the reduced
price), the highest tier only, and penalties never take a month below zero (what they could not take is shown)."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

FILS = Decimal("0.001")
ZERO = Decimal(0)


def money(v) -> Decimal:
    return Decimal(v or 0).quantize(FILS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Step:
    threshold: Decimal
    amount: Decimal | None


@dataclass(frozen=True)
class Rules:
    """One scheme's numbers, read once per run."""

    calculator: str
    per_order: Decimal | None = None
    target_orders: int = 420
    missing_order_rate: Decimal | None = None
    reduced_rate: Decimal | None = None
    bonus_when_reduced: bool = False
    marks_when_reduced: bool = False
    floor_at_zero: bool = True
    steps: dict[str, list[Step]] = field(default_factory=dict)  # by kind, sorted by threshold

    def highest(self, kind: str, value) -> Step | None:
        """The highest step reached: tiers and marks are not cumulative."""
        reached = [s for s in self.steps.get(kind, []) if value is not None and value >= s.threshold]
        return reached[-1] if reached else None

    def exact(self, kind: str, value) -> Step | None:
        return next((s for s in self.steps.get(kind, []) if value is not None and s.threshold == value), None)


@dataclass(frozen=True)
class Month:
    """The month's approved figures: orders and valid days (from the daily reports or the statement), and what the
    reviewer entered from the platform's partner report."""

    orders: int
    valid_days: int | None = None
    batch_level: int | None = None
    attendance_marks: int | None = None
    star_day_failed: bool | None = None


@dataclass(frozen=True)
class Item:
    code: str  # a salary-sheet column (columns.py)
    amount: Decimal  # earnings positive, penalties negative
    why: dict  # what the payslip says


@dataclass
class Result:
    items: list[Item]
    pay: Decimal  # the earnings
    penalties: Decimal  # the penalties taken (never more than the pay when the scheme floors at zero)
    uncovered: Decimal  # the penalties the month could not take


class Calculator(Protocol):
    code: str
    needs: tuple[str, ...]  # month figures without which the line is flagged and blocks approval

    def items(self, rules: Rules, month: Month) -> list[Item]: ...


CALCULATORS: dict[str, Calculator] = {}


def calculator(cls):
    CALCULATORS[cls.code] = cls()
    return cls


def missing(calc: Calculator, month: Month) -> list[str]:
    return [f for f in calc.needs if getattr(month, f) is None]


def run(rules: Rules, month: Month) -> Result:
    calc = CALCULATORS[rules.calculator]
    items = calc.items(rules, month)
    pay = sum((i.amount for i in items if i.amount > 0), ZERO)
    penalties = -sum((i.amount for i in items if i.amount < 0), ZERO)
    uncovered = ZERO
    if rules.floor_at_zero and penalties > pay:
        uncovered, penalties = penalties - pay, pay
        items.append(Item("uncovered_penalty", uncovered, {"uncovered": str(uncovered)}))
    return Result(items, money(pay), money(penalties), money(uncovered))


def _missing_target(rules: Rules, month: Month) -> list[Item]:
    short = max(0, rules.target_orders - month.orders)
    if not short or not rules.missing_order_rate:
        return []
    return [
        Item(
            "missing_target",
            -money(short * rules.missing_order_rate),
            {"target": rules.target_orders, "missing": short, "rate": str(rules.missing_order_rate)},
        )
    ]


@calculator
class PerOrder:
    """One price per order (Talabat's fixed-price schemes), and a deduction per order short of the target when the
    scheme has one."""

    code = "per_order"
    needs = ("orders",)

    def items(self, rules: Rules, month: Month) -> list[Item]:
        out = [
            Item(
                "orders_pay",
                money(month.orders * rules.per_order),
                {"orders": month.orders, "rate": str(rules.per_order)},
            )
        ]
        return out + _missing_target(rules, month)


@calculator
class BatchLevels:
    """The price per order follows the month's batch level (Talabat's batch system)."""

    code = "batch"
    needs = ("orders", "batch_level")

    def items(self, rules: Rules, month: Month) -> list[Item]:
        step = rules.exact("batch_rate", month.batch_level)
        if step is None:  # a level the scheme does not price: the highest level below it, never a guess above
            step = rules.highest("batch_rate", month.batch_level)
        rate = step.amount if step else ZERO
        out = [
            Item(
                "orders_pay",
                money(month.orders * rate),
                {"orders": month.orders, "rate": str(rate), "batch_level": month.batch_level},
            )
        ]
        return out + _missing_target(rules, month)


@calculator
class TieredTarget:
    """A base price per order, a bonus for the highest tier reached, a deduction per order short of the target,
    deductions for attendance marks, and a reduced price for every order when the marks pass a limit or a mandatory
    star day was missed (Keeta)."""

    code = "tiered_target"
    needs = ("orders", "attendance_marks", "star_day_failed")

    def items(self, rules: Rules, month: Month) -> list[Item]:
        out: list[Item] = []
        marks = month.attendance_marks or 0
        reduce_at = rules.highest("marks_reduce", marks)  # e.g. threshold 5: more than 4 marks
        reduced = bool(month.star_day_failed) or reduce_at is not None
        rate = rules.reduced_rate if reduced else rules.per_order
        why = {"orders": month.orders, "rate": str(rate)}
        if reduced:
            why["reduced_by"] = "star_day" if month.star_day_failed else "marks"
        out.append(Item("orders_pay", money(month.orders * rate), why))

        if not reduced or rules.bonus_when_reduced:
            tier = rules.highest("tier_bonus", month.orders)
            if tier:
                out.append(
                    Item("tier_bonus", money(tier.amount), {"orders": month.orders, "from": int(tier.threshold)})
                )

        out += _missing_target(rules, month)  # the scheme's own rate, even on a reduced month

        if not reduced or rules.marks_when_reduced:
            mark = rules.highest("marks_deduction", marks)  # 3 -> 10, 4 -> 30
            if mark:
                out.append(Item("marks_deduction", -money(mark.amount), {"marks": marks}))
        return out
