"""The deductions payroll will apply: the monthly maximum and what moves to the next month (FR-PAY-03, BR-16)."""

from datetime import date
from decimal import Decimal as D

from app.modules.payroll.models import Deduction
from app.modules.payroll.service import due_in, month_cap, month_deduction


def plan(total, installments, start):
    return Deduction(total=D(total), installments=installments, start_month=start)


def run(plans, months, cap):
    """Payroll month by month: what is due, plus what earlier months could not take, up to the cap."""
    carried, out = D(0), []
    for m in months:
        deducted, carried = month_deduction(due_in(plans, m), carried, cap)
        out.append(deducted)
    return out, carried


def test_above_the_monthly_maximum_the_rest_moves_to_the_next_month():
    nov, dec, jan, feb = date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)
    # 150.000 over 3 months is 50.000 a month; with a maximum of 40.000 a month it takes a fourth month
    taken, left = run([plan("150.000", 3, nov)], [nov, dec, jan, feb], D("40.000"))
    assert taken == [D("40.000"), D("40.000"), D("40.000"), D("30.000")] and left == 0
    # within the maximum the plan is followed as it is
    taken, left = run([plan("150.000", 3, nov)], [nov, dec, jan], D("60.000"))
    assert taken == [D("50.000")] * 3 and left == 0
    # two deductions in the same months share the maximum
    plans = [plan("150.000", 3, nov), plan("60.000", 2, dec)]
    assert due_in(plans, dec) == D("80.000")
    taken, left = run(plans, [nov, dec, jan, feb], D("70.000"))
    assert taken == [D("50.000"), D("70.000"), D("70.000"), D("20.000")] and left == 0
    # a month with no salary (cap 0) deducts nothing and moves everything on
    assert month_deduction(D("50.000"), D("10.000"), D(0)) == (D(0), D("60.000"))


def test_the_maximum_is_a_share_of_the_salary_rounded_down_to_the_fils():
    assert month_cap(D("350.000"), D("25")) == D("87.500")
    assert month_cap(D("333.333"), D("10")) == D("33.333")
    assert month_cap(D("100.000"), D("33.33")) == D("33.330")
    assert month_cap(D("123.457"), D("10")) == D("12.345")  # 12.3457: never above the share


def test_the_share_has_no_default_and_stays_between_0_and_100(admin_client):
    current = admin_client.get("/api/v1/settings").json()["payroll"]
    assert current["value"]["max_deduction_percent"] is None  # BR-16: the client decides after legal advice
    for bad in ("0", "100.5", "-5"):
        r = admin_client.put(
            "/api/v1/settings/payroll",
            json={"version": current["version"], "value": current["value"] | {"max_deduction_percent": bad}},
        )
        assert r.status_code == 422 and r.json()["code"] == "invalid_settings", bad
    r = admin_client.put(
        "/api/v1/settings/payroll",
        json={"version": current["version"], "value": current["value"] | {"max_deduction_percent": "25"}},
    )
    assert r.status_code == 200 and r.json()["value"]["max_deduction_percent"] == "25"
