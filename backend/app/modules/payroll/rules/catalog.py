"""What a rule block can be: its type, the category the designer lists it under, its parameters (each checked by kind),
the payslip line it writes, and the facts a condition may test. The designer builds its forms from this catalog, and
the engine (engine.py) checks every block against it, so a block the catalog does not describe is never run.

Labels are in the i18n catalog: rule_block.<type>, rule_category.<category>, rule_param.<param>, rule_choice.<value>,
rule_fact.<fact>, rule_op.<op>, payroll_column.<line code>."""

import re
from dataclasses import dataclass

CATEGORIES = ("pay", "incentive", "attendance", "deduction", "expense", "exception", "priority")
# facts a block reads its count from: the month's figures, and any number field the platform defines (its key)
BUILTIN_SOURCES = (
    "orders",
    "valid_days",
    "working_days",
    "hours",
    "attendance_marks",
    "late_count",
    "absent_days",
)
KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
EXCEPTION_KINDS = ("accepted_excuse", "company_error", "exception_day")
# what an approved exception excuses, each on its own: an excuse for the star day never clears the marks, a number of
# days never clears a missed star day
EXCUSES = ("star_day", "marks", "lateness", "absence", "valid_days")
EXPENSE_KINDS = ("gas", "maintenance", "phone", "housing", "advance")
ON_EXCEPTION = ("none", "neutralize", "count_valid")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str  # money | int | bool | choice | source | key | rows
    required: bool = True
    default: object = None
    options: tuple[str, ...] = ()
    rows: tuple["Param", ...] = ()
    when: tuple[str, str] | None = None  # required (and shown) only when another param has this value
    low: int | None = None  # whole numbers: the smallest and largest accepted
    high: int | None = None

    def out(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "default": self.default,
            "options": list(self.options),
            "rows": [r.out() for r in self.rows],
            "when": list(self.when) if self.when else None,
            "min": self.low,
            "max": self.high,
        }


@dataclass(frozen=True)
class BlockType:
    code: str
    category: str
    params: tuple[Param, ...] = ()
    lines: tuple[str, ...] = ()  # the payslip lines it writes (salary-sheet column codes)
    prices_orders: bool = False  # sets the price of the month's orders (what a price change re-prices)
    needs_condition: bool = False
    exceptions: tuple[str, ...] = ("none",)  # the on_exception behaviours it accepts
    needs: tuple[str, ...] = ()  # facts it always reads (beyond its source)

    def out(self) -> dict:
        return {
            "type": self.code,
            "category": self.category,
            "params": [p.out() for p in self.params],
            "lines": list(self.lines),
            "needs_condition": self.needs_condition,
            "on_exception": list(self.exceptions),
        }


SOURCE = Param("source", "source", required=False, default="orders")
ATTENDANCE_EXC = ("none", "neutralize", "count_valid")

TYPES: dict[str, BlockType] = {
    t.code: t
    for t in (
        # ---------------------------------------------------------------- pay
        BlockType(
            "per_order", "pay", (Param("rate", "money"), SOURCE), ("orders_pay", "count_pay"), prices_orders=True
        ),
        BlockType(
            "fixed_salary",
            "pay",
            (
                Param("mode", "choice", default="amount", options=("amount", "contract")),
                Param("amount", "money", when=("mode", "amount")),
            ),
            ("fixed_salary",),
        ),
        BlockType(
            "tiered_rate",
            "pay",
            (
                SOURCE,
                Param("mode", "choice", default="all", options=("all", "progressive")),
                Param("tiers", "rows", rows=(Param("from", "int"), Param("rate", "money"))),
            ),
            ("orders_pay", "count_pay"),
            prices_orders=True,
        ),
        BlockType(
            "batch_rate",
            "pay",
            (
                Param("rates", "rows", rows=(Param("batch", "int", low=1, high=20), Param("rate", "money"))),
                Param("personal_rate", "bool", required=False, default=True),
            ),
            ("orders_pay",),
            prices_orders=True,
            needs=("batches",),
        ),
        BlockType(
            "per_task_type",
            "pay",
            (Param("rates", "rows", rows=(Param("task", "key"), Param("rate", "money"))),),
            ("tasks_pay",),
            needs=("tasks",),
        ),
        # ---------------------------------------------------------------- incentives
        BlockType(
            "monthly_bonus", "incentive", (Param("amount", "money"),), ("monthly_bonus",), exceptions=ATTENDANCE_EXC
        ),
        BlockType(
            "target_overage",
            "incentive",
            (
                SOURCE,
                Param("threshold", "int"),
                Param("rate", "money"),
                Param("below_rate", "money", required=False),
            ),
            ("target_bonus", "target_shortfall"),
        ),
        BlockType(
            "tier_bonus",
            "incentive",
            (
                SOURCE,
                Param("mode", "choice", default="highest", options=("highest", "cumulative")),
                Param("tiers", "rows", rows=(Param("from", "int"), Param("amount", "money"))),
            ),
            ("tier_bonus",),
            exceptions=ATTENDANCE_EXC,
        ),
        BlockType(
            "commitment_bonus",
            "incentive",
            (Param("amount", "money"), Param("require_clean", "bool", required=False, default=True)),
            ("commitment_bonus",),
            exceptions=ATTENDANCE_EXC,
        ),
        # ---------------------------------------------------------------- attendance
        BlockType(
            "required_days",
            "attendance",
            (
                Param("days", "int", low=1, high=31),
                Param("invalidates", "bool", required=False, default=False),
                Param("deduction", "choice", default="none", options=("none", "fixed", "per_day")),
                Param("amount", "money", when=("deduction", "fixed|per_day")),
            ),
            ("required_days_deduction",),
            exceptions=ATTENDANCE_EXC,
            needs=("valid_days",),
        ),
        BlockType(
            "lateness",
            "attendance",
            (Param("amount", "money"),),
            ("late_deduction",),
            exceptions=ATTENDANCE_EXC,
            needs=("late_count",),
        ),
        BlockType(
            "absence",
            "attendance",
            (
                Param("mode", "choice", default="amount", options=("amount", "daily_wage")),
                Param("amount", "money", when=("mode", "amount")),
                Param("divisor", "int", required=False, default=30, low=1, high=31),
            ),
            ("absence_days_deduction",),
            exceptions=ATTENDANCE_EXC,
            needs=("absent_days",),
        ),
        BlockType(
            "invalid_days",
            "attendance",
            (
                Param("mode", "choice", default="daily_wage", options=("daily_wage", "fixed")),
                Param("amount", "money", when=("mode", "fixed")),
                Param("divisor", "int", required=False, default=30, low=1, high=31),
            ),
            ("invalid_days_deduction",),
            exceptions=ATTENDANCE_EXC,
        ),
        BlockType("star_day", "attendance", (), (), exceptions=("none", "neutralize"), needs=("star_day_failed",)),
        # ---------------------------------------------------------------- deductions
        BlockType(
            "missing_orders",
            "deduction",
            (SOURCE, Param("target", "int"), Param("rate", "money")),
            ("missing_target",),
            exceptions=ATTENDANCE_EXC,
        ),
        BlockType(
            "attendance_marks",
            "deduction",
            (
                Param("mode", "choice", default="table", options=("per_mark", "table")),
                Param("amount", "money", when=("mode", "per_mark")),
                Param("table", "rows", rows=(Param("from", "int"), Param("amount", "money")), when=("mode", "table")),
            ),
            ("marks_deduction",),
            exceptions=ATTENDANCE_EXC,
            needs=("attendance_marks",),
        ),
        BlockType(
            "special_day_violation",
            "deduction",
            (
                Param("amount", "money"),
                Param("when", "choice", default="month_invalid", options=("month_invalid", "star_day_failed")),
            ),
            ("special_day_deduction",),
            exceptions=("none", "neutralize"),
        ),
        BlockType(
            "price_change",
            "deduction",
            (Param("rate", "money"), Param("mode", "choice", default="replace", options=("replace", "separate"))),
            ("orders_pay", "price_change"),
            needs_condition=True,
            exceptions=ATTENDANCE_EXC,
        ),
        # ---------------------------------------------------------------- expenses
        BlockType(
            "expense",
            "expense",
            (
                Param("kind", "choice", options=EXPENSE_KINDS),
                Param("responsibility", "choice", default="driver", options=("company", "driver")),
                Param("amount", "money", required=False),
                Param("approved", "bool", required=False, default=False),
            ),
            ("expense_deduction",),
        ),
        # ---------------------------------------------------------------- exceptions
        BlockType(
            "exception_days",
            "exception",
            (Param("effect", "choice", default="count_valid", options=("count_valid", "excuse_attendance")),),
            (),
        ),
    )
}

# what a condition may test (combined with AND); the value is a whole number unless said otherwise
NUMBER_OPS = ("gt", "gte", "lt", "lte", "eq")
BOOL_OPS = ("is_true", "is_false")
FACTS: dict[str, tuple[str, ...]] = {
    "star_day_failed": BOOL_OPS,
    "month_invalid": BOOL_OPS,  # set by a star-day or required-days block earlier in the list
    "price_changed": BOOL_OPS,  # a price change applied earlier in the list
    "penalized": BOOL_OPS,  # a deduction line was written earlier in the list
    "marks": NUMBER_OPS,
    "valid_days": NUMBER_OPS,
    "orders": NUMBER_OPS,
    "late_count": NUMBER_OPS,
    "absent_days": NUMBER_OPS,
    "has_exception": ("has", "has_not"),  # value: an exception kind or "any"
    "batch": ("eq",),  # the month has orders in this batch
    "field": NUMBER_OPS + BOOL_OPS,  # a field the platform defines (key)
}
FACT_NEEDS = {
    "star_day_failed": "star_day_failed",
    "marks": "attendance_marks",
    "valid_days": "valid_days",
    "orders": "orders",
    "late_count": "late_count",
    "absent_days": "absent_days",
    "batch": "batches",
}
SETS_INVALID = ("star_day", "required_days")  # blocks a month_invalid condition depends on


def palette() -> dict:
    """What the designer lists: block types by category, the condition facts and operators, the choices."""
    return {
        "categories": list(CATEGORIES),
        "types": [t.out() for t in TYPES.values()],
        "facts": [{"fact": f, "ops": list(ops)} for f, ops in FACTS.items()],
        "sources": list(BUILTIN_SOURCES),
        "exception_kinds": list(EXCEPTION_KINDS),
        "excuses": list(EXCUSES),
        "on_exception": list(ON_EXCEPTION),
    }
