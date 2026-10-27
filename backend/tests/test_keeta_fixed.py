"""Keeta's fixed-salary schemes (200 over 3 years, 165 from 2 to 3, 140 under 2): target 420 with each order above or
below at the scheme's rate, 50 at 510 and 100 at 610, two red marks a month free, 3 marks − 10 and 4 marks − 30, a
mark on a star day or more than 4 marks puts the whole month at 0.200 per order (the deductions still taken), and the
platform sheet's tips added and its food damage, other adjustment and discount taken."""

from decimal import Decimal as D

import pytest

from app.modules.payroll import rules
from app.modules.payroll.rules.engine import Facts, run, validate


def pay(code, **facts):
    out = run(validate(rules.template(code)["blocks"]), Facts(**{"star_day_failed": False, "attendance_marks": 0,
                                                                  **facts}))  # fmt: skip
    return out.pay - out.penalties


@pytest.mark.parametrize(
    ("code", "orders", "marks", "expected"),
    [
        ("keeta_fixed_200", 420, 0, "200.000"),
        ("keeta_fixed_200", 450, 2, "214.280"),  # 30 × 0.476; two marks are his days off
        ("keeta_fixed_200", 400, 0, "190.480"),  # 20 short × 0.476
        ("keeta_fixed_200", 510, 3, "282.840"),  # 90 × 0.476 + 50 − 10
        ("keeta_fixed_200", 610, 4, "360.440"),  # 190 × 0.476 + 100 − 30
        ("keeta_fixed_200", 450, 5, "90.000"),  # more than 4 marks: 450 × 0.200
        ("keeta_fixed_165", 450, 0, "176.790"),  # 165 + 30 × 0.393
        ("keeta_fixed_140", 400, 0, "133.340"),  # 140 − 20 × 0.333
    ],
)
def test_the_fixed_salary_with_its_target_bonuses_and_marks(code, orders, marks, expected):
    assert pay(code, orders=orders, attendance_marks=marks) == D(expected)


def test_a_mark_on_a_star_day_puts_the_month_at_0200_and_the_deductions_are_still_taken():
    sheet = {
        "tips": D("0.400"),
        "food_damage": D("-5.000"),
        "other_adjustment": D("-2.000"),
        "platform_discount": D("0"),
    }
    assert pay("keeta_fixed_200", orders=450, star_day_failed=True, fields=sheet) == D("83.400")  # 90 + 0.4 − 5 − 2
    assert pay("keeta_fixed_200", orders=420, fields=sheet) == D("193.400")  # 200 + 0.4 − 7


def test_the_sheets_tips_and_deductions_are_read_signed_from_its_columns(admin_client, company):
    import json

    from tests.conftest import make_driver
    from tests.test_month_mapping import MONTH, P, platform, xlsx

    k = platform(admin_client, "kamounts")
    make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="KA-1")
    head = ["معرّف سائق التوصيل", "الطلبات المُسلمة", "البقشيش", "تعويض عن تلف الطعام ", "تعديل آخر", "الخصم"]
    data = xlsx({"تفاصيل سائق التوصيل": [head, ["KA-1", 363, "0.400", "-12.500", "-80.000", "0.000"]]})
    keys = ["platform_driver_id", "sheet_orders", "tips", "food_damage", "other_adjustment", "platform_discount"]
    mapping = {"sheet": "تفاصيل سائق التوصيل", "columns": dict(zip(keys, head, strict=True))}
    form = {"platform_id": str(k["id"]), "month": str(MONTH), "format": "mapped", "replace_month": "false",
            "mapping": json.dumps(mapping, ensure_ascii=False)}  # fmt: skip
    out = admin_client.post(f"{P}/month-imports/check", data=form, files={"file": ("k.xlsx", data, "x/y")}).json()
    assert "blocking" in out and not out["blocking"], out
    assert out["drivers"][0]["values"] == {"sheet_orders": "363", "tips": "0.400", "food_damage": "-12.500",
                                           "other_adjustment": "-80.000", "platform_discount": "0.000"}  # fmt: skip
    assert (
        admin_client.post(f"{P}/month-imports", data=form, files={"file": ("k.xlsx", data, "x/y")}).status_code == 201
    )
    review = admin_client.get(f"{P}/month-review", params={"platform_id": k["id"], "month": str(MONTH)}).json()
    row = review["rows"][0]  # the app recorded no orders: the sheet's 363 differ
    assert "sheet_orders_differ" in row["problems"] and row["platform_driver_id"] == "KA-1"
