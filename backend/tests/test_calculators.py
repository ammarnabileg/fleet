"""The pay scheme calculators on the worked months of docs/payroll-schemes.md (section 5), with the client's default
decisions (section 6)."""

from decimal import Decimal as D

from app.modules.payroll import calculators as calc
from app.modules.payroll.calculators import Month, Rules, Step


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
BATCH = Rules(
    calculator="batch",
    steps=steps(
        batch_rate=[(1, "0.700"), (2, "0.675"), (3, "0.600"), (4, "0.525"), (5, "0.400"), (6, "0.400"), (7, "0.400")]
    ),
)
FIXED_2 = Rules(calculator="per_order", per_order=D("0.550"))


def keeta(orders, marks=0, star=False, rules=KEETA):
    return calc.run(rules, Month(orders=orders, attendance_marks=marks, star_day_failed=star))


def codes(result):
    return {i.code: i.amount for i in result.items}


def test_keeta_worked_months():
    r = keeta(560, marks=2)  # 196.000 + tier 3 (540) 90
    assert (r.pay, r.penalties, r.uncovered) == (D("286.000"), 0, 0)
    assert codes(r) == {"orders_pay": D("196.000"), "tier_bonus": D("90.000")}

    r = keeta(400, marks=3)  # 140.000 - 20 short x 0.350 - 10 for 3 marks
    assert r.pay - r.penalties == D("123.000")
    assert codes(r) == {"orders_pay": D("140.000"), "missing_target": D("-7.000"), "marks_deduction": D("-10.000")}

    r = keeta(480, marks=5)  # reduced: 480 x 0.200, no tier bonus, no -30 (defaults A and C)
    assert (r.pay, r.penalties) == (D("96.000"), 0) and set(codes(r)) == {"orders_pay"}
    assert r.items[0].why["reduced_by"] == "marks"

    r = keeta(300, star=True)  # reduced by the star day; the shortfall at the scheme's 0.350 (default B)
    assert r.pay - r.penalties == D("18.000") and r.items[0].why["reduced_by"] == "star_day"

    r = keeta(100, star=True)  # 20.000 - 112.000: ends at zero, 92.000 shown as not taken (default D)
    assert (r.pay, r.penalties, r.uncovered) == (D("20.000"), D("20.000"), D("92.000"))


def test_keeta_tiers_and_marks_are_the_highest_reached_not_added():
    assert codes(keeta(710))["tier_bonus"] == D("200.000")
    assert codes(keeta(709))["tier_bonus"] == D("130.000")
    assert "tier_bonus" not in codes(keeta(449))
    assert codes(keeta(500, marks=4))["marks_deduction"] == D("-30.000")
    assert "marks_deduction" not in codes(keeta(500, marks=2))


def test_the_decisions_are_the_schemes_settings():
    other = Rules(**{**KEETA.__dict__, "bonus_when_reduced": True, "marks_when_reduced": True, "floor_at_zero": False})
    r = keeta(480, marks=5, rules=other)
    assert codes(r) == {"orders_pay": D("96.000"), "tier_bonus": D("50.000"), "marks_deduction": D("-30.000")}
    r = keeta(100, star=True, rules=other)
    assert (r.pay, r.penalties, r.uncovered) == (D("20.000"), D("112.000"), 0)  # no floor: the month goes negative


def test_talabat_batch_and_fixed_price():
    r = calc.run(BATCH, Month(orders=450, batch_level=2))
    assert r.pay == D("303.750") and r.items[0].why["batch_level"] == 2
    assert calc.run(BATCH, Month(orders=100, batch_level=6)).pay == D("40.000")
    assert calc.run(BATCH, Month(orders=100, batch_level=9)).pay == D("40.000")  # above the last priced level

    r = calc.run(FIXED_2, Month(orders=380))  # no missing-target rule for Talabat by default (F)
    assert (r.pay, r.penalties) == (D("209.000"), 0)
    with_target = Rules(**{**FIXED_2.__dict__, "missing_order_rate": D("0.350")})
    assert calc.run(with_target, Month(orders=380)).penalties == D("14.000")


def test_what_each_calculator_needs():
    assert calc.missing(calc.CALCULATORS["batch"], Month(orders=10)) == ["batch_level"]
    assert calc.missing(calc.CALCULATORS["tiered_target"], Month(orders=10, attendance_marks=0)) == ["star_day_failed"]
    assert calc.missing(calc.CALCULATORS["per_order"], Month(orders=0)) == []
