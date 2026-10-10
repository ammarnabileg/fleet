"""The rule-block engine (the rules designer): every block type, conditions, the order of the list, priority
groups, exceptions, validation, the templates on the client's worked months, and the four old calculators written as
blocks giving the same money."""

import itertools
from decimal import Decimal as D

import pytest

from app.core.errors import AppError
from app.modules.payroll import calculators as calc
from app.modules.payroll import rules
from app.modules.payroll.calculators import Month, Rules, Step
from app.modules.payroll.rules import convert
from app.modules.payroll.rules.engine import Facts, MonthException, needs, run, validate


def blk(type_, condition=None, on_exception="none", group=None, **params):
    return {"type": type_, "params": params, "condition": condition or [], "on_exception": on_exception, "group": group}


def go(blocks, floor=True, **facts):
    return run(validate(blocks), Facts(**facts), floor_at_zero=floor)


def lines(out):
    return [(i.code, i.amount) for i in out.items]


def net(out):
    return out.pay - out.penalties


def tpl(code):
    return rules.template(code)["blocks"]


PAY = blk("per_order", rate="0.350")
COND_STAR = [{"fact": "star_day_failed", "op": "is_true"}]


# ------------------------------------------------------------------ each block type


def test_pay_blocks():
    out = go([PAY], orders=603)
    assert lines(out) == [("orders_pay", D("211.050"))] and out.items[0].formula == "603 × 0.350 = 211.050"
    assert lines(go([blk("per_order", rate="1.500", source="hours")], hours=D("10.50"))) == [("count_pay", D("15.750"))]
    assert lines(go([blk("fixed_salary", mode="amount", amount="350")])) == [("fixed_salary", D("350.000"))]
    assert lines(go([blk("fixed_salary", mode="contract")], basic_salary=D("165"))) == [("fixed_salary", D("165.000"))]

    tiers = [{"from": 0, "rate": "0.300"}, {"from": 300, "rate": "0.350"}, {"from": 500, "rate": "0.400"}]
    assert lines(go([blk("tiered_rate", mode="all", tiers=tiers)], orders=450)) == [("orders_pay", D("157.500"))]
    out = go([blk("tiered_rate", mode="progressive", tiers=tiers)], orders=550)  # 300x0.300 + 200x0.350 + 50x0.400
    assert lines(out) == [("orders_pay", D("180.000"))] and out.items[0].formula.startswith("300 × 0.300 + 200 × 0.350")

    rates = [{"batch": 1, "rate": "0.750"}, {"batch": 2, "rate": "0.700"}, {"batch": 4, "rate": "0.550"}]
    out = go([blk("batch_rate", rates=rates)], batches=((4, 118), (2, 39)))  # two batch rows in one month
    assert lines(out) == [("orders_pay", D("64.900")), ("orders_pay", D("27.300"))] and out.pay == D("92.200")
    assert out.items[0].why["batch_level"] == 4
    assert lines(go([blk("batch_rate", rates=rates)], batch_level=3, orders=100)) == [("orders_pay", D("70.000"))]
    out = go([blk("batch_rate", rates=rates)], batches=((4, 118), (2, 39)), personal_rate=D("0.800"))
    assert lines(out) == [("orders_pay", D("125.600"))] and out.items[0].why["personal"] is True
    no_personal = blk("batch_rate", rates=rates, personal_rate=False)
    assert go([no_personal], batches=((1, 10),), personal_rate=D("0.800")).pay == D("7.500")

    task = blk("per_task_type", rates=[{"task": "grocery", "rate": "0.400"}, {"task": "pharmacy", "rate": "0.600"}])
    out = go([task], tasks={"grocery": 10, "pharmacy": 5})
    assert lines(out) == [("tasks_pay", D("4.000")), ("tasks_pay", D("3.000"))]


def test_incentive_blocks():
    over = blk("target_overage", threshold=310, rate="0.500", below_rate="0.500")
    assert lines(go([PAY, over], orders=603))[1] == ("target_bonus", D("146.500"))
    assert lines(go([PAY, over], orders=293))[1] == ("target_shortfall", D("-8.500"))
    assert len(go([PAY, blk("target_overage", threshold=310, rate="0.500")], orders=293).items) == 1  # no deduction

    tiers = [{"from": 450, "amount": "50"}, {"from": 540, "amount": "90"}, {"from": 620, "amount": "130"}]
    assert lines(go([PAY, blk("tier_bonus", tiers=tiers)], orders=560))[1] == ("tier_bonus", D("90.000"))
    assert lines(go([PAY, blk("tier_bonus", tiers=tiers, mode="cumulative")], orders=630))[1] == (
        "tier_bonus",
        D("270.000"),
    )
    assert len(go([PAY, blk("tier_bonus", tiers=tiers)], orders=449).items) == 1

    bonus = blk("monthly_bonus", [{"fact": "orders", "op": "gte", "value": 400}], amount="25")
    assert lines(go([PAY, bonus], orders=400))[1] == ("monthly_bonus", D("25.000"))
    assert len(go([PAY, bonus], orders=399).items) == 1

    commit = blk("commitment_bonus", amount="15")
    clean = dict(orders=10, attendance_marks=0, late_count=0, absent_days=0)
    assert lines(go([PAY, commit], **clean))[1] == ("commitment_bonus", D("15.000"))
    assert len(go([PAY, commit], **(clean | {"late_count": 1})).items) == 1
    out = go([PAY, commit], **(clean | {"attendance_marks": 1}))
    assert out.trace[-1]["skipped"] == "not_clean"


def test_attendance_blocks():
    req = blk("required_days", days=28, invalidates=True, deduction="per_day", amount="5")
    special = blk("special_day_violation", amount="100", when="month_invalid")
    out = go([PAY, req, special], orders=1000, valid_days=26)
    assert lines(out)[1:] == [("required_days_deduction", D("-10.000")), ("special_day_deduction", D("-100.000"))]
    assert lines(go([PAY, req, special], orders=1000, valid_days=28)) == [("orders_pay", D("350.000"))]
    info = blk("required_days", days=28)  # decision E: nothing extra, shown in the trace
    out = go([PAY, info], orders=10, valid_days=20)
    assert len(out.items) == 1 and out.trace[-1]["applied"] and out.trace[-2]["info"] == "below_required"

    assert lines(go([PAY, blk("lateness", amount="2.500")], orders=100, late_count=3))[1] == (
        "late_deduction",
        D("-7.500"),
    )
    absence = blk("absence", mode="daily_wage", divisor=30)
    out = go([blk("fixed_salary", mode="amount", amount="300"), absence], absent_days=2)  # 2 x 300/30
    assert lines(out)[1] == ("absence_days_deduction", D("-20.000"))
    assert lines(go([PAY, blk("absence", mode="amount", amount="7")], orders=100, absent_days=2))[1][1] == D("-14.000")

    invalid = blk("invalid_days", mode="daily_wage", divisor=26)
    out = go([blk("fixed_salary", mode="contract"), invalid], basic_salary=D("300"), working_days=26, valid_days=21)
    assert lines(out)[1] == ("invalid_days_deduction", D("-57.690"))  # 5 x 11.538, as the platform rule did

    star = blk("star_day")
    assert lines(go([PAY, star, special], orders=1000, star_day_failed=True))[1] == (
        "special_day_deduction",
        D("-100.000"),
    )
    assert len(go([PAY, star, special], orders=10, star_day_failed=False).items) == 1


def test_deduction_and_expense_blocks():
    miss = blk("missing_orders", target=420, rate="0.350")
    assert lines(go([PAY, miss], orders=400))[1] == ("missing_target", D("-7.000"))
    assert len(go([PAY, miss], orders=420).items) == 1

    per_mark = blk("attendance_marks", mode="per_mark", amount="20")
    assert lines(go([PAY, per_mark], orders=1000, attendance_marks=2))[1] == ("marks_deduction", D("-40.000"))
    table = blk("attendance_marks", mode="table", table=[{"from": 3, "amount": "10"}, {"from": 4, "amount": "30"}])
    assert lines(go([PAY, table], orders=1000, attendance_marks=6))[1] == ("marks_deduction", D("-30.000"))  # highest
    assert len(go([PAY, table], orders=0, attendance_marks=2).items) == 1

    gas = blk("expense", kind="gas", responsibility="driver")
    out = go([PAY, gas], orders=10)  # decision G: informational only
    assert len(out.items) == 1 and out.trace[-2]["info"] == "informational"
    approved = blk("expense", kind="phone", responsibility="driver", amount="3", approved=True)
    assert lines(go([PAY, approved], orders=10))[1] == ("expense_deduction", D("-3.000"))
    unapproved = blk("expense", kind="phone", responsibility="driver", amount="3")
    assert len(go([PAY, unapproved], orders=10).items) == 1
    advance = blk("expense", kind="advance", responsibility="driver", amount="3", approved=True)
    assert len(go([PAY, advance], orders=10).items) == 1  # advances stay in the deductions module


def test_price_change_replaces_the_base_price_or_is_a_separate_line():
    replace = blk("price_change", COND_STAR, rate="0.200", mode="replace")
    out = go([PAY, replace], orders=480, star_day_failed=True)
    assert lines(out) == [("orders_pay", D("96.000"))]
    assert out.items[0].why["base_rate"] == "0.350" and out.items[0].why["reduced_by"] == "star_day"
    separate = blk("price_change", COND_STAR, rate="0.200", mode="separate")
    out = go([PAY, separate], orders=480, star_day_failed=True)
    assert lines(out) == [("orders_pay", D("168.000")), ("price_change", D("-72.000"))] and net(out) == D("96.000")
    assert lines(go([PAY, replace], orders=480, star_day_failed=False)) == [("orders_pay", D("168.000"))]
    # every order: split batches are all re-priced
    rates = [{"batch": 1, "rate": "0.750"}, {"batch": 2, "rate": "0.700"}]
    out = go([blk("batch_rate", rates=rates), replace], batches=((1, 10), (2, 20)), star_day_failed=True)
    assert lines(out) == [("orders_pay", D("2.000")), ("orders_pay", D("4.000"))]


# ------------------------------------------------------------------ conditions, order, groups, exceptions


def test_conditions_combine_with_and():
    cond = [
        {"fact": "orders", "op": "gte", "value": 100},
        {"fact": "marks", "op": "lt", "value": 3},
        {"fact": "valid_days", "op": "gte", "value": 20},
        {"fact": "has_exception", "op": "has_not", "value": "any"},
        {"fact": "field", "key": "rating", "op": "gte", "value": 4},
    ]
    bonus = blk("monthly_bonus", cond, amount="10")
    base = dict(orders=100, attendance_marks=2, valid_days=20, fields={"rating": 4})
    assert len(go([PAY, bonus], **base).items) == 2
    for change in ({"orders": 99}, {"attendance_marks": 3}, {"valid_days": 19}, {"fields": {"rating": 3}}):
        assert len(go([PAY, bonus], **(base | change)).items) == 1, change
    assert len(go([PAY, bonus], **base, exceptions=(MonthException("accepted_excuse"),)).items) == 1
    flag = blk("monthly_bonus", [{"fact": "field", "key": "uniform", "op": "is_true"}], amount="5")
    assert len(go([PAY, flag], orders=1, fields={"uniform": True}).items) == 2
    assert len(go([PAY, flag], orders=1, fields={"uniform": False}).items) == 1
    batch = blk("monthly_bonus", [{"fact": "batch", "op": "eq", "value": 1}], amount="5")
    rates = blk("batch_rate", rates=[{"batch": 1, "rate": "0.700"}, {"batch": 2, "rate": "0.600"}])
    assert len(go([rates, batch], batches=((1, 5), (2, 7))).items) == 3
    assert len(go([rates, batch], batches=((2, 7),)).items) == 1


def test_the_order_of_the_list_is_the_approved_priority():
    """Documented: a commitment bonus paid only when no deduction came before it. With the missing-target deduction
    before the bonus, a month short of the target gets no bonus; with the bonus first, it does. The office approves
    one order; the engine never infers it."""
    miss = blk("missing_orders", target=420, rate="0.350")
    bonus = blk("commitment_bonus", [{"fact": "penalized", "op": "is_false"}], amount="20", require_clean=False)
    first = go([PAY, miss, bonus], orders=400)
    later = go([PAY, bonus, miss], orders=400)
    assert net(first) == D("133.000") and net(later) == D("153.000")  # 140 - 7, and 140 + 20 - 7
    assert net(go([PAY, miss, bonus], orders=420)) == net(go([PAY, bonus, miss], orders=420)) == D("167.000")

    # the tier bonus before the price change is paid; after it, its condition sees the reduced month
    tiers = blk("tier_bonus", tiers=[{"from": 450, "amount": "50"}])
    reduce = blk("price_change", COND_STAR, rate="0.200")
    gated = blk("tier_bonus", [{"fact": "price_changed", "op": "is_false"}], tiers=[{"from": 450, "amount": "50"}])
    assert net(go([PAY, tiers, reduce], orders=500, star_day_failed=True)) == D("150.000")
    assert net(go([PAY, reduce, gated], orders=500, star_day_failed=True)) == D("100.000")


def test_within_a_priority_group_the_first_rule_that_holds_applies():
    hi = blk("monthly_bonus", [{"fact": "orders", "op": "gte", "value": 600}], group="bonus", amount="100")
    lo = blk("monthly_bonus", [{"fact": "orders", "op": "gte", "value": 400}], group="bonus", amount="40")
    assert lines(go([PAY, hi, lo], orders=650))[1:] == [("monthly_bonus", D("100.000"))]
    assert lines(go([PAY, hi, lo], orders=450))[1:] == [("monthly_bonus", D("40.000"))]
    out = go([PAY, lo, hi], orders=650)  # the other order: the lower rule comes first and wins
    assert lines(out)[1:] == [("monthly_bonus", D("40.000"))] and out.trace[-1]["skipped"] == "group_done"


def test_exceptions_neutralize_count_as_valid_or_correct_the_figures():
    excuse = (MonthException("accepted_excuse", days=1),)
    star = blk("star_day", on_exception="neutralize")
    special = blk("special_day_violation", amount="100")
    assert go([PAY, star, special], orders=0, star_day_failed=True).uncovered == D("100.000")
    out = go([PAY, star, special], orders=0, star_day_failed=True, exceptions=excuse)
    assert lines(out) == [("orders_pay", D("0.000"))]  # the excuse: the star day does not make the month invalid
    plain = blk("star_day")  # without the behaviour, the excuse changes nothing
    assert lines(go([PAY, plain, special], orders=1000, star_day_failed=True, exceptions=excuse))[1][1] == D("-100.000")

    marks = blk("attendance_marks", on_exception="neutralize", mode="per_mark", amount="20")
    assert lines(go([PAY, marks], orders=1000, attendance_marks=3, exceptions=excuse))[1][1] == D("-40.000")  # 3 - 1
    whole = (MonthException("exception_day"),)  # no number of days: the whole month
    assert len(go([PAY, marks], orders=0, attendance_marks=3, exceptions=whole).items) == 1

    req = blk("required_days", on_exception="count_valid", days=28, deduction="fixed", amount="10")
    days = (MonthException("exception_day", days=2),)
    assert len(go([PAY, req], orders=0, valid_days=26, exceptions=days).items) == 1  # 26 + 2 approved days
    assert len(go([PAY, req], orders=100, valid_days=25, exceptions=days).items) == 2
    counted = [
        blk("exception_days", effect="count_valid"),
        PAY,
        blk("required_days", days=28, deduction="fixed", amount="10"),
    ]
    assert len(go(counted, orders=0, valid_days=26, exceptions=days).items) == 1

    error = (MonthException("company_error", corrections={"orders": 450}),)
    out = go([PAY], orders=430, exceptions=error)
    assert lines(out) == [("orders_pay", D("157.500"))] and out.trace[0]["info"] == "corrected"
    flagged = blk("monthly_bonus", [{"fact": "has_exception", "op": "has", "value": "company_error"}], amount="1")
    assert len(go([PAY, flagged], orders=1, exceptions=error).items) == 2


def test_the_floor_at_the_end_shows_what_could_not_be_taken():
    special = blk("special_day_violation", amount="100", when="star_day_failed")
    out = go([PAY, special], orders=100, star_day_failed=True)
    assert (out.pay, out.penalties, out.uncovered) == (D("35.000"), D("35.000"), D("65.000"))
    assert out.items[-1].code == "uncovered_penalty"
    out = go([PAY, special], floor=False, orders=100, star_day_failed=True)
    assert (out.pay, out.penalties, out.uncovered) == (D("35.000"), D("100.000"), 0)


# ------------------------------------------------------------------ the templates on the client's months


def test_keeta_as_actually_paid():
    blocks = tpl("keeta_paid")
    out = run(blocks, Facts(orders=603, attendance_marks=0, star_day_failed=False, basic_salary=D("200")))
    assert net(out) == D("346.500") and lines(out) == [("fixed_salary", D("200.000")), ("target_bonus", D("146.500"))]
    out = run(blocks, Facts(orders=293, attendance_marks=0, star_day_failed=False, basic_salary=D("165")))
    assert net(out) == D("156.500") and lines(out)[1] == ("target_shortfall", D("-8.500"))
    out = run(blocks, Facts(orders=310, attendance_marks=2, star_day_failed=True, basic_salary=D("120")))
    assert lines(out)[1:3] == [("marks_deduction", D("-40.000")), ("special_day_deduction", D("-100.000"))]
    assert (out.pay, out.penalties, out.uncovered) == (D("120.000"), D("120.000"), D("20.000"))
    excused = run(blocks, Facts(orders=310, attendance_marks=0, star_day_failed=True, basic_salary=D("120"),
                                exceptions=(MonthException("accepted_excuse"),)))  # fmt: skip
    assert net(excused) == D("120.000")


def test_talabat_as_actually_paid_split_batches():
    blocks = tpl("talabat_batch_paid")
    out = run(blocks, Facts(batches=((4, 118), (2, 39))))
    assert out.pay == D("92.200") and lines(out) == [("orders_pay", D("64.900")), ("orders_pay", D("27.300"))]
    assert run(blocks, Facts(batches=((5, 100), (6, 50)))).pay == D("67.500")
    assert run(blocks, Facts(batches=((1, 100), (3, 50)), personal_rate=D("1.000"))).pay == D("150.000")


def test_plan_document_templates_with_decisions_a_to_j():
    k = tpl("keeta_plan")

    def keeta(orders, marks=0, star=False, **kw):
        kw.setdefault("valid_days", 28)
        return run(k, Facts(orders=orders, attendance_marks=marks, star_day_failed=star, **kw))

    assert net(keeta(560, 2)) == D("286.000")
    assert lines(keeta(400, 3)) == [
        ("orders_pay", D("140.000")),
        ("missing_target", D("-7.000")),
        ("marks_deduction", D("-10.000")),
    ]
    r = keeta(480, 5)  # A, C: reduced, no tier bonus, no -30
    assert lines(r) == [("orders_pay", D("96.000"))] and r.items[0].why["reduced_by"] == "marks"
    assert net(keeta(800, 5)) == D("160.000") and net(keeta(400, 5)) == D("73.000")  # B: 0.350 per missing order
    assert net(keeta(300, star=True)) == D("18.000")
    r = keeta(100, star=True)  # D: zero, the rest shown
    assert (r.pay, r.penalties, r.uncovered) == (D("20.000"), D("20.000"), D("92.000"))
    assert lines(keeta(710))[1] == ("tier_bonus", D("200.000")) and lines(keeta(709))[1][1] == D("130.000")  # H
    assert net(keeta(450, valid_days=20)) == net(keeta(450))  # E: fewer valid days, nothing extra
    excused = keeta(480, star=True, exceptions=(MonthException("exception_day"),))
    assert net(excused) == D("218.000")  # the star day excused: 480 x 0.350 + tier 50

    assert run(tpl("talabat_fixed_550"), Facts(orders=400)).pay == D("220.000")  # F: no missing-target deduction
    assert len(run(tpl("talabat_fixed_550"), Facts(orders=400)).items) == 1  # G: expenses informational
    assert run(tpl("talabat_batch_plan"), Facts(batch_level=2, orders=450)).pay == D("303.750")
    assert run(tpl("talabat_fixed_350"), Facts(orders=100)).pay == D("35.000")
    assert run(tpl("talabat_fixed_680"), Facts(orders=100)).pay == D("68.000")


def test_templates_are_valid_and_marked():
    ts = rules.templates()
    assert [t["code"] for t in ts] == [
        "talabat_batch_plan",
        "talabat_batch_paid",
        "talabat_fixed_350",
        "talabat_fixed_550",
        "talabat_fixed_680",
        "keeta_plan",
        "keeta_paid",
    ]
    assert {t["code"] for t in ts if t["needs_confirmation"]} == {
        "talabat_batch_plan",
        "talabat_fixed_350",
        "talabat_fixed_550",
        "talabat_fixed_680",
        "keeta_plan",
    }
    ts[0]["blocks"].clear()  # a copy: the next caller gets them whole
    assert rules.templates()[0]["blocks"]


# ------------------------------------------------------------------ the old calculators as blocks


def steps(**kinds):
    return {k: [Step(D(str(t)), None if a is None else D(str(a))) for t, a in v] for k, v in kinds.items()}


KEETA = Rules(
    calculator="tiered_target",
    per_order=D("0.350"),
    missing_order_rate=D("0.350"),
    reduced_rate=D("0.200"),
    steps=steps(
        tier_bonus=[(450, 50), (540, 90), (620, 130), (710, 200)],
        marks_deduction=[(3, 10), (4, 30)],
        marks_reduce=[(5, None)],
    ),
)
SCHEMES = [
    KEETA,
    Rules(**{**KEETA.__dict__, "bonus_when_reduced": True, "marks_when_reduced": True, "floor_at_zero": False}),
    Rules(**{**KEETA.__dict__, "missing_order_rate": None, "steps": steps(tier_bonus=[(450, 50)])}),
    Rules(
        calculator="batch",
        steps=steps(batch_rate=[(1, "0.700"), (2, "0.675"), (3, "0.600"), (4, "0.525"), (5, "0.400")]),
    ),
    Rules(calculator="batch", missing_order_rate=D("0.100"), steps=steps(batch_rate=[(2, "0.500"), (4, "0.400")])),
    Rules(calculator="per_order", per_order=D("0.550")),
    Rules(calculator="per_order", per_order=D("0.350"), missing_order_rate=D("0.350"), target_orders=300),
]
MONTHS = [
    Month(orders=o, attendance_marks=m, star_day_failed=s, batch_level=b)
    for o, m, s, b in itertools.product(
        (0, 100, 299, 400, 449, 450, 560, 709, 710, 900), (0, 2, 3, 4, 5, 7), (False, True), (1, 3, 6)
    )
]


@pytest.mark.parametrize("index", range(len(SCHEMES)))
def test_every_calculator_as_blocks_gives_the_same_money(index):
    old_rules = SCHEMES[index]
    blocks = validate(convert.from_rules(old_rules))
    for month in MONTHS:
        old = calc.run(old_rules, month)
        facts = Facts(
            orders=month.orders,
            attendance_marks=month.attendance_marks,
            star_day_failed=month.star_day_failed,
            batch_level=month.batch_level,
        )
        new = run(blocks, facts, floor_at_zero=old_rules.floor_at_zero)
        assert [(i.code, i.amount) for i in new.items] == [(i.code, i.amount) for i in old.items], month
        assert (new.pay, new.penalties, new.uncovered) == (old.pay, old.penalties, old.uncovered), month
        if old.items and "reduced_by" in old.items[0].why:
            assert new.items[0].why["reduced_by"] == old.items[0].why["reduced_by"]
        need = set(needs(blocks, Facts(orders=1))) - {"batches"}
        assert need <= set(calc.CALCULATORS[old_rules.calculator].needs) - {"orders", "batch_level"}


class _Platform:
    def __init__(self, **kw):
        self.__dict__.update(
            dict(pay_basic=True, per_order=0, per_hour=0, per_valid_day=0, invalid_days="none", invalid_day_amount=None)
            | {"day_divisor": 30}
            | kw
        )


def test_a_platform_rule_as_blocks():
    p = _Platform(per_order=D("0.250"), per_hour=D("1.000"), invalid_days="daily_wage", day_divisor=26)
    blocks = validate(convert.from_platform(p))
    assert [b["type"] for b in blocks] == ["fixed_salary", "per_order", "per_order", "invalid_days"]
    out = run(blocks, Facts(orders=7, hours=D("2.5"), basic_salary=D("300"), working_days=26, valid_days=21))
    assert (out.pay, out.penalties) == (D("304.250"), D("57.690"))
    fixed = validate(convert.from_platform(_Platform(invalid_days="fixed", invalid_day_amount=D("10"))))
    out = run(fixed, Facts(basic_salary=D("300"), working_days=23, valid_days=20))
    assert net(out) == D("270.000")


# ------------------------------------------------------------------ validation and missing figures


@pytest.mark.parametrize(
    ("blocks", "code"),
    [
        ([], "rule_blocks_empty"),
        ([{"type": "teleport"}], "rule_block_unknown"),
        ([blk("per_order")], "rule_block_param"),  # no price
        ([blk("per_order", rate="-1")], "rule_block_param"),
        ([blk("per_order", rate="0.0005")], "rule_block_param"),  # finer than a fils
        ([blk("fixed_salary", mode="amount")], "rule_block_param"),  # the amount is wanted for this mode
        ([PAY, blk("price_change", rate="0.200")], "rule_block_condition_required"),
        ([blk("fixed_salary", mode="contract"), blk("price_change", COND_STAR, rate="0.2")], "rule_block_order"),
        ([PAY, blk("monthly_bonus", [{"fact": "month_invalid", "op": "is_true"}], amount="1")], "rule_block_order"),
        ([PAY, blk("special_day_violation", amount="1")], "rule_block_order"),
        ([PAY, blk("monthly_bonus", [{"fact": "price_changed", "op": "is_false"}], amount="1")], "rule_block_order"),
        (
            [PAY, blk("monthly_bonus", [{"fact": "orders", "op": "between", "value": 1}], amount="1")],
            "rule_condition_invalid",
        ),
        (
            [PAY, blk("monthly_bonus", [{"fact": "salary", "op": "gt", "value": 1}], amount="1")],
            "rule_condition_invalid",
        ),
        ([blk("per_order", on_exception="neutralize", rate="1")], "rule_block_exception"),
        ([blk("monthly_bonus", amount="1")], "rule_pay_missing"),
        ([PAY, blk("tier_bonus", tiers=[{"from": 1, "amount": "1"}, {"from": 1, "amount": "2"}])], "rule_block_param"),
        ([blk("per_order", rate="1", colour="red")], "rule_block_param"),
        ([blk("per_order", rate="1", source="rating")], "rule_block_param"),  # not one of the platform's fields
    ],
)
def test_validation_refuses_what_cannot_run(blocks, code):
    with pytest.raises(AppError) as e:
        validate(blocks, sources={"tips_count"})
    assert e.value.code == code


def test_validation_names_the_block_and_stores_the_params_exactly():
    with pytest.raises(AppError) as e:
        validate([PAY, blk("lateness")])
    assert e.value.params == {"position": 2, "param": "amount"}
    stored = validate(
        [blk("per_order", rate=0.5), blk("tier_bonus", tiers=[{"from": 9, "amount": 2}, {"from": 3, "amount": "1.5"}])]
    )
    assert stored[0]["params"] == {"rate": "0.500", "source": "orders"}
    assert stored[1]["params"]["tiers"] == [{"from": 3, "amount": "1.500"}, {"from": 9, "amount": "2.000"}]
    assert validate([blk("per_order", rate="1", source="tips_count")], sources={"tips_count"})


def test_missing_figures_are_named_never_guessed():
    blocks = tpl("keeta_plan")
    assert needs(blocks, Facts(orders=10)) == ["star_day_failed", "attendance_marks", "valid_days"]
    assert needs(blocks, Facts(orders=10, attendance_marks=0, star_day_failed=False, valid_days=3)) == []
    assert needs(tpl("talabat_batch_paid"), Facts(orders=10)) == ["batches"]
    assert needs(tpl("talabat_batch_paid"), Facts(orders=10, personal_rate=D("1"))) == []
    custom = validate([blk("per_order", rate="1", source="trips")], sources={"trips"})
    assert needs(custom, Facts(orders=1)) == ["trips"] and needs(custom, Facts(fields={"trips": 3})) == []


def test_every_block_param_choice_fact_and_line_has_its_labels():
    import json
    import pathlib

    from app.modules.payroll.columns import BY_CODE
    from app.modules.payroll.rules.catalog import (
        BUILTIN_SOURCES,
        CATEGORIES,
        EXCEPTION_KINDS,
        FACTS,
        ON_EXCEPTION,
        TYPES,
    )

    folder = pathlib.Path(__file__).resolve().parents[1] / "app" / "modules" / "i18n" / "catalog"
    for lang in ("ar", "en"):
        cat = json.loads((folder / f"{lang}.json").read_text(encoding="utf-8"))
        assert set(CATEGORIES) <= cat["rule_category"].keys()
        assert set(TYPES) <= cat["rule_block"].keys() and set(TYPES) <= cat["rule_block_help"].keys()
        for t in TYPES.values():
            for p in t.params + tuple(r for q in t.params for r in q.rows):
                assert p.name in cat["rule_param"], (lang, p.name)
                assert set(p.options) <= cat["rule_choice"].keys(), (lang, p.options)
            for code in t.lines:
                assert code in BY_CODE and code in cat["payroll_column"], (lang, code)
        assert set(FACTS) <= cat["rule_fact"].keys()
        assert {op for ops in FACTS.values() for op in ops} <= cat["rule_op"].keys()
        assert set(BUILTIN_SOURCES) <= cat["rule_source"].keys()
        assert set(EXCEPTION_KINDS) | set(ON_EXCEPTION) | {"any"} <= cat["rule_choice"].keys()
        assert {c for c in BY_CODE if c != "blank"} <= cat["payroll_column"].keys()
