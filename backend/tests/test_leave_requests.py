"""Absence requests (طلب التغيب) on configurable leave types, with the Kuwait labour law's defaults: eligibility,
limits, balances, the paid/unpaid split along the tiers, the driver's requests (idempotent), the office's decisions,
payroll, the Art. 41 alerts and the follow-up alert."""

import uuid
from datetime import date, timedelta

import pytest

from app.core.clock import today
from app.modules.attendance import rules
from app.modules.attendance import service as attendance
from tests.conftest import bearer, bind_device, jpeg, login, make_driver, make_employee, make_user
from tests.test_attendance import _payroll_settings

L = "/api/v1/leaves"
D = "/api/v1/driver/leaves"
T = today()


def ago(n: int) -> str:
    return str(T - timedelta(days=n))


def ahead(n: int) -> str:
    return str(T + timedelta(days=n))


def driver(admin_client, client, company, *, years: float | None = 3, **extra):
    hire = None if years is None else str(T - timedelta(days=int(years * 365.25)))
    d = make_driver(admin_client, company["id"], hire_date=hire, **extra)
    return d, bearer(bind_device(client, d["phone"]))


def attach(client, h) -> str:
    r = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("c.jpg", jpeg(), "image/jpeg")}
    )
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def ask(client, h, kind, first, last, **extra):
    body = {"client_ref": str(uuid.uuid4()), "kind": kind, "date_from": first, "date_to": last, **extra}
    return client.post(D, headers=h, json=body)


def alerts(client, kind):
    return client.get("/api/v1/alerts", params={"kind": kind, "limit": 200}).json()


def leaves_settings(admin_client, **value):
    cur = admin_client.get("/api/v1/settings").json()["leaves"]
    r = admin_client.put("/api/v1/settings/leaves", json={"version": cur["version"], "value": cur["value"] | value})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ the arithmetic


def test_the_tiers_split_in_order():
    sick = [
        {"days": 15, "pay_percent": 100},
        {"days": 10, "pay_percent": 75},
        {"days": 10, "pay_percent": 50},
        {"days": 10, "pay_percent": 25},
        {"days": 30, "pay_percent": 0},
    ]
    assert rules.split(20, sick) == [{"days": 15, "pay_percent": 100}, {"days": 5, "pay_percent": 75}]
    assert rules.split(10, sick, used_before=20) == [{"days": 5, "pay_percent": 75}, {"days": 5, "pay_percent": 50}]
    assert rules.split(5, sick, used_before=80) == [{"days": 5, "pay_percent": 0}]  # past every tier: unpaid
    assert rules.split(3, [{"days": None, "pay_percent": 0}]) == [{"days": 3, "pay_percent": 0}]
    days = list(rules.days(date(2026, 1, 1), date(2026, 1, 3)))
    assert rules.pay_by_day(days, [{"days": 2, "pay_percent": 100}, {"days": 1, "pay_percent": 75}]) == {
        days[0]: 100,
        days[1]: 100,
        days[2]: 75,
    }
    # working days leave the weekly rest day (Friday) out
    assert len(rules.counted(date(2026, 10, 19), date(2026, 10, 25), "working", [4])) == 6
    assert rules.service_year(date(2020, 3, 10), date(2026, 1, 5)) == (date(2025, 3, 10), date(2026, 3, 9))
    assert rules.accrued(date(2025, 1, 1), date(2025, 12, 31), 30) == 30
    assert rules.months_between(date(2025, 1, 15), date(2025, 10, 14)) == 8


# ------------------------------------------------------------------ the driver's requests


def test_sick_leave_needs_a_certificate_splits_along_the_year_and_is_idempotent(admin_client, client, company):
    d, h = driver(admin_client, client, company)
    view = client.get(D, headers=h).json()
    sick = next(t for t in view["types"] if t["code"] == "sick")
    assert sick["requires_attachment"] and sick["left_year"] == 75
    pre = client.post(f"{D}/preview", headers=h, json={"kind": "sick", "date_from": ahead(1), "date_to": ahead(20)})
    assert pre.json()["split"] == [{"days": 15, "pay_percent": 100}, {"days": 5, "pay_percent": 75}]
    r = ask(client, h, "sick", ahead(1), ahead(20))
    assert r.status_code == 422 and r.json()["code"] == "leave_attachment_required"
    body = {"client_ref": str(uuid.uuid4()), "kind": "sick", "date_from": ahead(1), "date_to": ahead(20)}
    body |= {"file_sha256": attach(client, h), "reason": "flu"}
    first = client.post(D, headers=h, json=body)
    assert first.status_code == 201, first.text
    again = client.post(D, headers=h, json=body)  # the outbox resends: the same request comes back
    assert again.json()["id"] == first.json()["id"]
    assert len(client.get(D, headers=h).json()["requests"]) == 1
    [alert] = [a for a in alerts(admin_client, "leave_requested") if a["entity_id"] == first.json()["id"]]
    assert alert["entity_type"] == "leave"
    # overlapping: refused
    r = ask(client, h, "sick", ahead(5), ahead(6), file_sha256=attach(client, h))
    assert r.status_code == 409 and r.json()["code"] == "leave_overlaps"
    # approved: the next sick days of the service year continue along the tiers
    assert admin_client.post(f"{L}/{first.json()['id']}/approve", json={}).json()["status"] == "approved"
    assert not [a for a in alerts(admin_client, "leave_requested") if a["entity_id"] == first.json()["id"]]
    pre = client.post(f"{D}/preview", headers=h, json={"kind": "sick", "date_from": ahead(30), "date_to": ahead(39)})
    assert pre.json()["split"] == [{"days": 5, "pay_percent": 75}, {"days": 5, "pay_percent": 50}]
    notices = client.get("/api/v1/driver/notifications", headers=h | {"Accept-Language": "en"}).json()["items"]
    assert notices[0]["kind"] == "leave_approved" and "Sick leave" in notices[0]["message"]


def test_hajj_after_two_years_once_per_service(admin_client, client, company):
    _, h = driver(admin_client, client, company, years=1)
    r = ask(client, h, "hajj", ahead(1), ahead(21))
    assert r.status_code == 422 and r.json() == r.json() | {"code": "leave_service_too_short"}
    assert "hajj" not in [t["code"] for t in client.get(D, headers=h).json()["types"]]
    _, h = driver(admin_client, client, company, years=3)
    assert ask(client, h, "hajj", ahead(1), ahead(22)).json()["code"] == "leave_too_long"
    done = ask(client, h, "hajj", ahead(1), ahead(21))
    assert done.status_code == 201 and done.json()["split"] == [{"days": 21, "pay_percent": 100}]
    r = ask(client, h, "hajj", ahead(100), ahead(101))
    assert r.status_code == 422 and r.json()["code"] == "leave_once_per_service"


def test_maternity_for_women_and_its_unpaid_months(admin_client, client, company):
    _, h = driver(admin_client, client, company, gender="male")
    assert ask(client, h, "maternity", ahead(1), ahead(70)).json()["code"] == "leave_gender"
    _, h = driver(admin_client, client, company)  # gender not recorded: not blocked, a warning
    pre = client.post(
        f"{D}/preview", headers=h, json={"kind": "maternity", "date_from": ahead(1), "date_to": ahead(70)}
    )
    assert pre.json()["warnings"] == ["gender_unknown"] and pre.json()["problems"] == []
    _, h = driver(admin_client, client, company, gender="female")
    r = ask(client, h, "maternity", ahead(1), ahead(100))
    assert r.json()["split"] == [{"days": 70, "pay_percent": 100}, {"days": 30, "pay_percent": 0}]


def test_annual_leave_balance(admin_client, client, company):
    d, h = driver(admin_client, client, company, years=0.5)
    assert ask(client, h, "annual", ahead(1), ahead(2)).json()["code"] == "leave_service_too_short"
    d, h = driver(admin_client, client, company, years=1.1)
    annual = next(t for t in client.get(D, headers=h).json()["types"] if t["code"] == "annual")
    earned = annual["accrued"]
    assert 32 <= earned <= 34 and annual["available"] == earned
    r = ask(client, h, "annual", ahead(1), ahead(earned + 1))
    assert r.status_code == 422 and r.json()["code"] == "leave_balance"
    assert ask(client, h, "annual", ahead(1), ahead(10)).status_code == 201
    [b] = [x for x in admin_client.get(f"/api/v1/employees/{d['id']}/leave-balances").json() if x["code"] == "annual"]
    assert (b["available"], b["pending"]) == (earned - 10, 10)


def test_decisions_and_withdrawal(admin_client, client, company):
    _, h = driver(admin_client, client, company)
    a = ask(client, h, "emergency", ahead(1), ahead(2), reason="family").json()
    assert a["split"] == [{"days": 2, "pay_percent": 0}]  # unpaid unless the office makes it paid
    r = admin_client.post(f"{L}/{a['id']}/reject", json={})
    assert r.status_code == 422
    out = admin_client.post(f"{L}/{a['id']}/approve", json={"paid": True}).json()
    assert out["split"] == [{"days": 2, "pay_percent": 100}] and out["paid_override"]
    r = client.post(f"{D}/{a['id']}/cancel", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "leave_not_pending"
    b = ask(client, h, "bereavement", ahead(10), ahead(12)).json()
    out = admin_client.post(f"{L}/{b['id']}/reject", json={"note": "no proof given"}).json()
    assert out["status"] == "rejected"
    mine = {x["id"]: x for x in client.get(D, headers=h).json()["requests"]}
    assert mine[b["id"]]["decision_note"] == "no proof given"
    c = ask(client, h, "unpaid", ahead(20), ahead(20)).json()
    assert client.post(f"{D}/{c['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post(f"{D}/{c['id']}/cancel", headers=h).json()["status"] == "cancelled"  # a resend
    kinds = [n["kind"] for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"]]
    assert kinds[:2] == ["leave_rejected", "leave_approved"]


def test_scope_and_permissions(admin_client, client, new_client, companies):
    d, h = driver(admin_client, client, companies["a"])
    other, h2 = driver(admin_client, client, companies["a"])
    a = ask(client, h, "unpaid", ahead(1), ahead(1)).json()
    assert client.post(f"{D}/{a['id']}/cancel", headers=h2).status_code == 404  # another driver's
    make_user(admin_client, "hr_lb", permissions=["leaves.view", "leaves.approve"], company_ids=[companies["b"]["id"]])
    c = new_client()
    login(c, "hr_lb")
    assert c.get(f"{L}/{a['id']}").status_code == 404
    assert c.post(f"{L}/{a['id']}/approve", json={}).status_code == 404
    assert c.get(f"/api/v1/employees/{d['id']}/leave-balances").status_code == 404
    assert c.put("/api/v1/leave-types/sick", json={"version": 1, "active": False}).status_code == 403


# ------------------------------------------------------------------ the office


def test_leave_type_settings(admin_client):
    sick = next(t for t in admin_client.get("/api/v1/leave-types").json() if t["code"] == "sick")
    assert sick["legal_ref"] == "Art. 69" and sick["tier_period"] == "service_year"
    bad = [{"days": None, "pay_percent": 100}, {"days": 5, "pay_percent": 50}]
    r = admin_client.put("/api/v1/leave-types/bereavement", json={"version": 1, "tiers": bad})
    assert r.status_code == 422
    bv = next(t for t in admin_client.get("/api/v1/leave-types").json() if t["code"] == "bereavement")
    r = admin_client.put(
        "/api/v1/leave-types/bereavement",
        json={"version": bv["version"], "max_per_occurrence": 5, "tiers": [{"days": 5, "pay_percent": 100}]},
    )
    assert r.status_code == 200 and r.json()["max_per_occurrence"] == 5
    r = admin_client.put("/api/v1/leave-types/bereavement", json={"version": bv["version"], "active": False})
    assert r.status_code == 409  # an older version
    admin_client.put(
        "/api/v1/leave-types/bereavement",
        json={"version": bv["version"] + 1, "max_per_occurrence": 3, "tiers": [{"days": 3, "pay_percent": 100}]},
    )


def test_payroll_takes_the_unpaid_share_of_sick_days(admin_client, company):
    month = T.replace(day=1)
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    r = admin_client.post(
        L,
        json={
            "employee_id": office["id"],
            "kind": "sick",
            "date_from": str(month),
            "date_to": str(month + timedelta(days=19)),
            "approve": True,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["split"] == [{"days": 15, "pay_percent": 100}, {"days": 5, "pay_percent": 75}]
    _payroll_settings(admin_client, "daily_wage")  # 10 a day: five days at 75% lose 5 x 2.5
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": company["id"], "month": str(month)}).json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == office["id"])
    assert (line["cells"]["leave_days"], line["cells"]["absence_deduction"], line["net"]) == (20, "12.500", "287.500")
    _payroll_settings(admin_client, "none")


def test_art41_alerts_on_absence_without_permission(admin_client, company):
    e = make_employee(admin_client, company["id"])
    days = [{"employee_id": e["id"], "day": ago(n)} for n in range(1, 8)]  # 7 consecutive: not above the law's 7
    admin_client.post("/api/v1/attendance/marks", json={"kind": "absence", "days": days})
    assert not [a for a in alerts(admin_client, "absence_consecutive") if a["entity_id"] == e["id"]]
    admin_client.post(
        "/api/v1/attendance/marks", json={"kind": "absence", "days": [{"employee_id": e["id"], "day": ago(8)}]}
    )
    [a] = [a for a in alerts(admin_client, "absence_consecutive") if a["entity_id"] == e["id"]]
    assert "8" in a["message"]
    if T.timetuple().tm_yday < 30:
        pytest.skip("the yearly count needs days of this year")
    leaves_settings(admin_client, absence_alert_year_days=8)
    admin_client.post(
        "/api/v1/attendance/marks", json={"kind": "absence", "days": [{"employee_id": e["id"], "day": ago(20)}]}
    )
    assert [a for a in alerts(admin_client, "absence_yearly") if a["entity_id"] == e["id"]]
    leaves_settings(admin_client, absence_alert_year_days=20)


def test_follow_up_alert(admin_client, new_client, db, company):
    e = make_employee(admin_client, company["id"])

    def leave(followup, first):
        body = {"employee_id": e["id"], "kind": "unpaid", "date_from": first, "date_to": first}
        r = admin_client.post(L, json=body | ({"followup_from": followup} if followup else {}))
        assert r.status_code == 201, r.text
        return r.json()

    def alerted(x) -> bool:
        return any(a["entity_id"] == x["id"] for a in alerts(admin_client, "absence_followup"))

    default = leave(None, ahead(1))
    assert default["followup_from"] == str(T) and default["followup_due"] == ahead(55)
    due, early = leave(ago(55), ahead(3)), leave(ago(54), ahead(5))
    attendance.scan_followups(db)
    attendance.scan_followups(db)  # once per request
    assert alerted(due) and not alerted(early) and not alerted(default)
    assert len([a for a in alerts(admin_client, "absence_followup") if a["entity_id"] == due["id"]]) == 1
    # a viewer of leaves sees it; a user without the leave permissions does not
    make_user(admin_client, "lv_view", permissions=["leaves.view"])
    make_user(admin_client, "no_lv", permissions=["employees.view"])
    c = new_client()
    login(c, "lv_view")
    assert any(a["entity_id"] == due["id"] for a in alerts(c, "absence_followup"))
    c = new_client()
    login(c, "no_lv")
    assert alerts(c, "absence_followup") == []
    # the setting shortened: the earlier one is due now
    leaves_settings(admin_client, absence_followup_days=54)
    attendance.scan_followups(db)
    assert alerted(early)
    leaves_settings(admin_client, absence_followup_days=55)
    # the date moved forward: the alert closes; moved back, it is raised again
    r = admin_client.put(f"{L}/{early['id']}/followup-from", json={"followup_from": str(T)})
    assert r.json()["followup_due"] == ahead(55) and not alerted(early)
    assert admin_client.put(f"{L}/{early['id']}/followup-from", json={"followup_from": ago(400)}).status_code == 422
    admin_client.put(f"{L}/{early['id']}/followup-from", json={"followup_from": ago(60)})
    attendance.scan_followups(db)
    assert alerted(early)
    # followed up, or cancelled: closed, and not raised again
    assert admin_client.post(f"{L}/{early['id']}/followed-up", json={}).json()["followed_up_at"]
    admin_client.post(f"{L}/{due['id']}/cancel", json={"reason": "entered twice"})
    attendance.scan_followups(db)
    assert not alerted(early) and not alerted(due)
