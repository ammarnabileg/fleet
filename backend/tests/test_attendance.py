"""Absence and leave (BRD BR-18, FR-HR-06, FR-PAY-01): the days without a start of day listed for HR, marked; leaves
registered, approved, rejected, cancelled, never overlapping; payroll deducting absence only as the settings say,
and nothing changing in a month whose payroll is approved."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.core.clock import KUWAIT, today
from app.modules.attendance import service as attendance
from app.modules.payroll import runs
from app.modules.payroll.calculators import Rules
from tests.conftest import (
    bearer,
    bind_device,
    hand_over,
    jpeg,
    login,
    make_driver,
    make_employee,
    make_user,
    make_vehicle,
    upload,
)

A = "/api/v1/attendance"
L = "/api/v1/leaves"


def _id(db, table: str, public_id: str) -> int:
    return db.execute(text(f"SELECT id FROM {table} WHERE public_id = :p"), {"p": public_id}).scalar()  # noqa: S608


def start_day(db, vehicle_id: int, custody_id: int, driver_id: int, day, photo: str):
    at = datetime.combine(day, time(8), tzinfo=KUWAIT)
    db.execute(
        text(
            "INSERT INTO fleet.odometer_readings (vehicle_id, custody_id, driver_id, kind, value_km, photo_sha256, "
            "recorded_at, business_date) VALUES (:v, :c, :d, 'start_day', 10000, :p, :t, :b)"
        ),
        {"v": vehicle_id, "c": custody_id, "d": driver_id, "p": photo, "t": at, "b": day},
    )


def dated(db, employee: dict, *steps: tuple[str, int]):
    """The employee's status records, oldest first, dated so many days back (they are all made today in a test)."""
    eid = _id(db, "people.employees", employee["id"])
    ids = db.execute(
        text("SELECT id, status_code FROM people.status_history WHERE employee_id = :e ORDER BY id"), {"e": eid}
    ).all()
    assert [c for _, c in ids] == [c for c, _ in steps]
    for (hid, _), (_, back) in zip(ids, steps, strict=True):
        at = datetime.combine(today() - timedelta(days=back), time(9), tzinfo=KUWAIT)
        db.execute(text("UPDATE people.status_history SET changed_at = :t WHERE id = :i"), {"t": at, "i": hid})
    db.commit()


def week(admin_client, client, db, company):
    """A driver hired six days ago: a vehicle since four days ago, two starts of day and one daily report."""
    t = today()
    d = make_driver(admin_client, company["id"], hire_date=str(t - timedelta(days=6)))
    v = make_vehicle(admin_client, company["id"])
    started = datetime.combine(t - timedelta(days=4), time(7), tzinfo=KUWAIT)
    c = hand_over(admin_client, v, d, started_at=started.astimezone(UTC).isoformat())
    photo = upload(admin_client)
    vid, did, cid = (
        _id(db, "fleet.vehicles", v["id"]),
        _id(db, "people.employees", d["id"]),
        _id(db, "fleet.custodies", c["id"]),
    )
    for back in (5, 3):  # the fifth day back he had no vehicle: an office start, recorded all the same
        start_day(db, vid, cid, did, t - timedelta(days=back), photo)
    db.commit()
    h = bearer(bind_device(client, d["phone"]))
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={
            "business_date": str(t - timedelta(days=1)),
            "orders_count": 4,
            "cash_amount": "3",
            "screenshot_sha256": shot,
        },
    )
    assert r.status_code == 201, r.text
    return d


def days(client, d=None, back=6):
    t = today()
    params = {"date_from": str(t - timedelta(days=back)), "date_to": str(t)}
    if d:
        params["employee_id"] = d["id"]
    r = client.get(f"{A}/days", params=params)
    assert r.status_code == 200, r.text
    return [(x["day"], x["held_vehicle"]) for x in r.json()["days"]]


def test_the_days_without_a_start_of_day_are_listed_then_marked(admin_client, client, db, company):
    d = week(admin_client, client, db, company)
    make_employee(admin_client, company["id"])  # office staff: not listed
    t = today()
    ago = lambda n: str(t - timedelta(days=n))  # noqa: E731
    # started 5 and 3 days ago, reported yesterday; today is still going on; nothing before his hire date
    assert days(admin_client, d) == [(ago(2), True), (ago(4), True), (ago(6), False)]
    did = _id(db, "people.employees", d["id"])
    counts = attendance.month_counts(db, [did], t - timedelta(days=6), t)
    assert counts[did]["unclassified_days"] == 3  # the payroll line is flagged until HR marks them
    r = admin_client.post(
        f"{A}/marks",
        json={"kind": "absence", "note": "did not answer", "days": [{"employee_id": d["id"], "day": ago(4)}]},
    )
    assert r.status_code == 200 and r.json() == {"marked": 1}
    admin_client.post(f"{A}/marks", json={"kind": "no_vehicle", "days": [{"employee_id": d["id"], "day": ago(6)}]})
    assert days(admin_client, d) == [(ago(2), True)]
    # a mark changed, then taken off: the day is listed again
    admin_client.post(f"{A}/marks", json={"kind": "rest", "days": [{"employee_id": d["id"], "day": ago(4)}]})
    marks = admin_client.get(f"{A}/marks", params={"date_from": ago(6), "date_to": str(t)}).json()
    assert [(m["day"], m["kind"]) for m in marks] == [(ago(4), "rest"), (ago(6), "no_vehicle")]
    assert admin_client.post(f"{A}/marks/remove", json={"employee_id": d["id"], "day": ago(6)}).status_code == 204
    assert days(admin_client, d) == [(ago(2), True), (ago(6), False)]
    # a day still to come cannot be marked; nor a day of someone outside the user's companies
    r = admin_client.post(
        f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": d["id"], "day": str(t + timedelta(days=1))}]}
    )
    assert r.status_code == 422 and r.json()["code"] == "day_in_future"
    # one who resigned today still has his days before it to account for in his last pay
    other = make_driver(admin_client, company["id"], hire_date=ago(6))
    r = admin_client.post(f"/api/v1/employees/{other['id']}/status", json={"status_code": "resigned", "note": "left"})
    assert r.status_code == 200, r.text
    dated(db, other, ("active", 6), ("resigned", 0))
    assert [x for x, _ in days(admin_client, other)] == [ago(n) for n in range(1, 7)]
    # dated three days back: only the days before it
    dated(db, other, ("active", 6), ("resigned", 3))
    assert [x for x, _ in days(admin_client, other)] == [ago(4), ago(5), ago(6)]
    # suspended four days back, back on the job two days back: only the days on the job
    third = make_driver(admin_client, company["id"], hire_date=ago(6))
    for code in ("suspended", "active"):
        assert (
            admin_client.post(f"/api/v1/employees/{third['id']}/status", json={"status_code": code}).status_code == 200
        )
    dated(db, third, ("active", 6), ("suspended", 4), ("active", 2))
    assert [x for x, _ in days(admin_client, third)] == [ago(1), ago(2), ago(5), ago(6)]
    # his marks stay listed after he left, like an office employee's
    admin_client.post(f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": other["id"], "day": ago(5)}]})
    marks = admin_client.get(
        f"{A}/marks", params={"date_from": ago(6), "date_to": str(t), "employee_id": other["id"]}
    ).json()
    assert [(m["day"], m["kind"], m["employee"]["employee_number"]) for m in marks] == [
        (ago(5), "absence", other["employee_number"])
    ]


def test_leaves_never_overlap_and_an_approved_leave_covers_its_days(admin_client, client, db, company):
    d = week(admin_client, client, db, company)
    t = today()
    ago = lambda n: str(t - timedelta(days=n))  # noqa: E731
    body = {"employee_id": d["id"], "kind": "sick", "date_from": ago(4), "date_to": ago(2), "note": "flu"}
    leave = admin_client.post(L, json=body).json()
    assert (leave["status"], leave["days"], leave["kind"]) == ("pending", 3, "sick")
    assert days(admin_client, d) == [(ago(2), True), (ago(4), True), (ago(6), False)]  # not covered until approved
    r = admin_client.post(L, json=body | {"date_from": ago(2), "date_to": str(t + timedelta(days=2))})
    assert r.status_code == 409 and r.json()["code"] == "leave_overlaps"
    r = admin_client.post(f"{L}/{leave['id']}/reject", json={})
    assert r.status_code == 422  # a refusal needs its reason
    assert admin_client.post(f"{L}/{leave['id']}/approve", json={}).json()["status"] == "approved"
    assert days(admin_client, d) == [(ago(6), False)]
    r = admin_client.post(f"{L}/{leave['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "leave_not_pending"
    # cancelled: its days are listed again, and they are free for another leave
    r = admin_client.post(f"{L}/{leave['id']}/cancel", json={"reason": "entered for the wrong driver"})
    assert r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "entered for the wrong driver"
    assert len(days(admin_client, d)) == 3
    second = admin_client.post(L, json=body | {"kind": "annual", "approve": True}).json()
    assert second["status"] == "approved" and second["decided_by"] is not None
    rejected = admin_client.post(L, json=body | {"date_from": ago(6), "date_to": ago(6)}).json()
    assert (
        admin_client.post(f"{L}/{rejected['id']}/reject", json={"note": "no proof given"}).json()["status"]
        == "rejected"
    )
    listed = admin_client.get(L, params={"employee_id": d["id"]}).json()
    assert sorted(x["status"] for x in listed) == ["approved", "cancelled", "rejected"]
    assert admin_client.get(L, params={"status": "approved"}).json()[0]["id"] == second["id"]


def test_permissions_and_company_scope(admin_client, client, new_client, db, companies):
    d = week(admin_client, client, db, companies["a"])
    t = today()
    make_user(admin_client, "sup_a", permissions=["leaves.view"], company_ids=[companies["a"]["id"]])
    c = new_client()
    login(c, "sup_a")
    assert len(days(c, d)) == 3
    r = c.post(
        f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": d["id"], "day": str(t - timedelta(days=2))}]}
    )
    assert r.status_code == 403
    assert (
        c.post(L, json={"employee_id": d["id"], "kind": "annual", "date_from": str(t), "date_to": str(t)}).status_code
        == 403
    )
    make_user(admin_client, "hr_b", permissions=["leaves.view", "leaves.approve"], company_ids=[companies["b"]["id"]])
    c = new_client()
    login(c, "hr_b")
    assert days(c) == []
    r = c.post(
        f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": d["id"], "day": str(t - timedelta(days=2))}]}
    )
    assert r.status_code == 404
    # nor the marks made on company a's drivers
    span = {"date_from": str(t - timedelta(days=6)), "date_to": str(t)}
    one = {"employee_id": d["id"], "day": str(t - timedelta(days=2))}
    assert admin_client.post(f"{A}/marks", json={"kind": "rest", "days": [one]}).status_code == 200
    assert len(admin_client.get(f"{A}/marks", params=span).json()) >= 1
    assert c.get(f"{A}/marks", params=span).json() == []
    r = c.post(L, json={"employee_id": d["id"], "kind": "annual", "date_from": str(t), "date_to": str(t)})
    assert r.status_code == 404


def _payroll_settings(admin_client, absence: str):
    version = admin_client.get("/api/v1/settings").json()["payroll"]["version"]
    r = admin_client.put(
        "/api/v1/settings/payroll",
        json={
            "version": version,
            "value": {"max_deduction_percent": "50.00", "deduction_cap_base": "gross", "absence_deduction": absence},
        },
    )
    assert r.status_code == 200, r.text


def test_payroll_deducts_absence_and_unpaid_leave_only_as_the_settings_say(admin_client, company):
    month = today().replace(day=1)
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    # one absence on the first of the month, one day of unpaid leave on the second, and a paid leave day on the third
    admin_client.post(
        f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": office["id"], "day": str(month)}]}
    )
    for kind, day in (("unpaid", 1), ("annual", 2)):
        d = str(month + timedelta(days=day))
        r = admin_client.post(
            L, json={"employee_id": office["id"], "kind": kind, "date_from": d, "date_to": d, "approve": True}
        )
        assert r.status_code == 201, r.text
    # an absence marked on his approved leave day is not one: the leave stands
    third = str(month + timedelta(days=2))
    admin_client.post(f"{A}/marks", json={"kind": "absence", "days": [{"employee_id": office["id"], "day": third}]})
    body = {"company_id": company["id"], "month": str(month)}

    _payroll_settings(admin_client, "none")
    run = admin_client.post("/api/v1/payroll/runs", json=body).json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == office["id"])
    assert (line["cells"]["absence_days"], line["cells"]["leave_days"], line["cells"]["absence_deduction"]) == (
        1,
        2,
        "0.000",
    )
    assert line["net"] == "300.000"

    _payroll_settings(admin_client, "daily_wage")  # 300 / 30 = 10 a day, for the absence and the unpaid day
    run = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/recompute").json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == office["id"])
    assert (line["cells"]["absence_deduction"], line["deductions"], line["net"]) == ("20.000", "20.000", "280.000")

    # the month approved: nothing in it changes any more
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve")
    assert r.status_code == 200, r.text
    r = admin_client.post(
        f"{A}/marks", json={"kind": "rest", "days": [{"employee_id": office["id"], "day": str(month)}]}
    )
    assert r.status_code == 409 and r.json()["code"] == "payroll_locked"
    leave = admin_client.get(L, params={"employee_id": office["id"], "status": "approved"}).json()[0]
    r = admin_client.post(f"{L}/{leave['id']}/cancel", json={"reason": "a mistake"})
    assert r.status_code == 409 and r.json()["code"] == "payroll_locked"


class _Platform:
    pay_basic, per_order, per_hour, per_valid_day = True, Decimal(0), Decimal(0), Decimal(0)
    invalid_days, invalid_day_amount, day_divisor, driver_fields, daily_fields = (
        "none",
        None,
        30,
        [],
        ["orders", "cash"],
    )


class _Statement:
    status, orders = "approved", 100
    working_days = valid_days = hours = batch_level = attendance_marks = star_day_failed = None
    bonus = tips = cancelled_orders = platform_deductions = late = cash_shortage = Decimal(0)


class _Deduction:
    id, start_month, source_type = 1, date(2026, 1, 1), "accident"


def _line(absence_days: int, *, rules=None, due="0"):
    profile = {"basic_salary": Decimal("300"), "payment_method": "cash", "iban": None, "is_driver": True}
    profile |= {"name": {"ar": "س"}, "platform_driver_id": None, "job_title": None, "civil_id": None, "bank_name": None}
    return runs.compute(
        profile,
        _Platform(),
        _Statement(),
        {"working_days": 20, "orders": 100, "absence_days": absence_days, "unpaid_leave_days": 0},
        [runs.Due(_Deduction(), Decimal(due))] if Decimal(due) else [],
        cap_percent=Decimal("50"),
        cap_base="gross",
        name_lang="ar",
        rules=rules,
        absence_rule="daily_wage",
    )


def test_absence_lowers_what_the_cap_allows_and_is_not_taken_from_a_scheme_s_pay():
    # 10 days of 300 / 30: 100 off, so the cap is half of the 200 left, not of 300
    c = _line(10, due="200")
    cells = (c.cells["absence_deduction"], c.cells["car_repair"], c.cells["carried"], c.net)
    assert cells == (Decimal("100.000"), Decimal("100.000"), Decimal("100.000"), Decimal("100.000"))
    # paid by the order on a scheme: no basic salary to take a day's wage from
    c = _line(10, rules=Rules(calculator="per_order", per_order=Decimal("0.500")))
    assert c.cells["absence_deduction"] == Decimal("0") and c.net == Decimal("50.000")


def test_a_client_sheet_without_an_absence_column_still_shows_the_deduction():
    class Sheet:
        columns = [
            {"code": "name", "header": "الاسم"},
            {"code": "gross", "header": "الإجمالي"},
            {"code": "net", "header": "الصافي"},
        ]

    labels = {"absence_days": "أيام الغياب", "absence_deduction": "خصم الغياب"}
    assert runs.sheet_columns(Sheet(), labels, [{"absence_deduction": "0.000"}, {}]) == Sheet.columns
    cols = runs.sheet_columns(Sheet(), labels, [{"absence_deduction": "0.000"}, {"absence_deduction": "20.000"}])
    assert [(c["code"], c["header"]) for c in cols] == [
        ("name", "الاسم"),
        ("gross", "الإجمالي"),
        ("absence_days", "أيام الغياب"),
        ("absence_deduction", "خصم الغياب"),
        ("net", "الصافي"),
    ]
