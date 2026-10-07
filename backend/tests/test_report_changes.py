"""Changing a daily report (BRD FR-DWR-04, FR-DWR-06, BR-06, UAT-04): the driver edits it until it is approved, the
reviewer may send it back with the reason, a second report for the same day points to the first; after approval a
change is asked for and decided, its cash difference posted with the driver's reason. Every change is kept."""

from decimal import Decimal as D

import pytest
from sqlalchemy import text

from tests.conftest import bearer, bind_device, make_driver
from tests.test_cash import approve, cash_of, report, shot

R = "/api/v1/daily-reports"


@pytest.fixture
def driver(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    return d | {"h": bearer(bind_device(client, d["phone"]))}


def mine(client, d) -> dict:
    return {r["id"]: r for r in client.get("/api/v1/driver/reports", headers=d["h"]).json()}


def patch(client, d, rid, **body):
    return client.patch(f"/api/v1/driver/reports/{rid}", json=body, headers=d["h"])


def changes(admin_client, rid) -> list[dict]:
    r = admin_client.get(f"{R}/{rid}/changes")
    assert r.status_code == 200, r.text
    return r.json()


def told(client, d) -> list[dict]:
    return client.get("/api/v1/driver/notifications", headers=d["h"]).json()["items"]


def test_the_driver_edits_until_approval_and_every_change_is_kept(admin_client, client, new_client, driver, company):
    rid = report(client, driver, cash="20", orders=10).json()["id"]
    assert cash_of(client, driver) == (D("0"), D("20.000"))
    r = patch(client, driver, rid, cash_amount="25", orders_count=12)
    assert r.status_code == 200, r.text
    assert (r.json()["cash_amount"], r.json()["orders_count"], r.json()["status"]) == ("25.000", 12, "submitted")
    assert cash_of(client, driver) == (D("0"), D("25.000"))  # the pending collection follows, never doubled
    assert patch(client, driver, rid, notes="نسيت طلبين").status_code == 200
    assert patch(client, driver, rid, cash_amount="25.000").status_code == 200  # nothing new: nothing logged
    log = changes(admin_client, rid)
    assert [(c["kind"], c["status"], c["by_driver"]) for c in log] == [("edit", "applied", True)] * 2
    assert (log[0]["before"], log[0]["after"]) == (
        {"cash_amount": "20.000", "orders_count": 10},
        {"cash_amount": "25.000", "orders_count": 12},
    )
    assert log[1]["after"] == {"notes": "نسيت طلبين"}
    # a field the platform asks cannot be emptied; nobody else's report
    assert patch(client, driver, rid, orders_count=None).json()["code"] == "field_required"
    other = new_client()
    d2 = make_driver(admin_client, company["id"])
    h2 = bearer(bind_device(other, d2["phone"]))
    assert other.patch(f"/api/v1/driver/reports/{rid}", json={"orders_count": 1}, headers=h2).status_code == 404

    # UAT-04: a second report for the day is refused and names the first
    again = report(client, driver, cash="5")
    assert again.status_code == 409 and again.json()["code"] == "report_exists"
    assert again.json()["params"] == {"report_id": rid}

    assert approve(admin_client, rid).status_code == 200
    assert cash_of(client, driver) == (D("25.000"), D("0"))
    r = patch(client, driver, rid, orders_count=13)
    assert r.status_code == 409 and r.json()["code"] == "report_not_editable"


def test_the_reviewer_sends_it_back_and_the_driver_corrects_it(admin_client, client, driver, db):
    from app.modules.daily_ops import service as daily

    rid = report(client, driver, cash="30", orders=15).json()["id"]
    db.execute(text("UPDATE daily_ops.reports SET submitted_at = now() - interval '25 hours'"))
    db.commit()
    assert daily.scan_overdue(db) == 1
    assert admin_client.post(f"{R}/{rid}/send-back", json={}).status_code == 422  # the reason is required
    r = admin_client.post(f"{R}/{rid}/send-back", json={"reason": "اللقطة لا تظهر الكاش"})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["review_note"]) == ("returned", "اللقطة لا تظهر الكاش")
    assert admin_client.get("/api/v1/alerts").json() == []  # it waits on the driver now
    assert approve(admin_client, rid).json()["code"] == "report_not_submitted"
    assert admin_client.post(f"{R}/{rid}/send-back", json={"reason": "مرة ثانية"}).status_code == 409
    (notice,) = told(client, driver)
    assert notice["kind"] == "report_returned" and "اللقطة لا تظهر الكاش" in notice["message"]
    assert mine(client, driver)[rid]["status"] == "returned"

    # corrected, it goes back to review, on a fresh clock
    r = patch(client, driver, rid, cash_amount="28.5", screenshot_sha256=shot(client, driver["h"]))
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert daily.scan_overdue(db) == 0
    assert [(c["kind"], c["reason"]) for c in changes(admin_client, rid)] == [
        ("returned", "اللقطة لا تظهر الكاش"),
        ("edit", None),
    ]
    assert approve(admin_client, rid).status_code == 200
    assert cash_of(client, driver) == (D("28.500"), D("0"))


def test_after_approval_a_change_is_asked_for_and_decided(admin_client, client, driver):
    rid = report(client, driver, cash="20", orders=10).json()["id"]
    ask = lambda **body: client.post(  # noqa: E731
        f"/api/v1/driver/reports/{rid}/change-request", json=body, headers=driver["h"]
    )
    r = ask(cash_amount="22", reason="نسيت طلباً")
    assert r.status_code == 409 and r.json()["code"] == "report_not_approved"  # edit it directly until then
    assert approve(admin_client, rid, cash_amount="18", reason="العد في المكتب").status_code == 200
    assert cash_of(client, driver) == (D("18.000"), D("0"))

    assert ask(cash_amount="18", reason="لا شيء").json()["code"] == "nothing_changed"  # the approved figure
    r = ask(cash_amount="19", orders_count=11, reason="طلب متأخر لم يظهر")
    assert r.status_code == 201, r.text
    first = r.json()
    assert (first["status"], first["before"], first["after"]) == (
        "pending",
        {"cash_amount": "18.000", "orders_count": 10},
        {"cash_amount": "19.000", "orders_count": 11},
    )
    assert ask(cash_amount="21", reason="مرة أخرى").json()["code"] == "change_request_exists"
    assert mine(client, driver)[rid]["change_pending"] is True
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["daily_report_change_requested"]
    assert [c["id"] for c in admin_client.get(f"{R}/change-requests").json()] == [first["id"]]

    # refused, with the reason the driver reads; nothing moves
    decide = lambda cid, verb, **body: admin_client.post(f"{R}/change-requests/{cid}/{verb}", json=body)  # noqa: E731
    assert decide(first["id"], "reject").json()["code"] == "reason_required"
    assert decide(first["id"], "reject", note="الطلب ظاهر في يوم آخر").json()["status"] == "rejected"
    assert decide(first["id"], "approve").json()["code"] == "change_decided"
    assert told(client, driver)[0]["kind"] == "report_change_rejected"
    assert cash_of(client, driver) == (D("18.000"), D("0"))
    assert admin_client.get("/api/v1/alerts").json() == []

    # approved: the new figures, the difference posted with the driver's reason
    second = ask(cash_amount="22", reason="إيصال كاش إضافي").json()
    r = decide(second["id"], "approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    row = mine(client, driver)[rid]
    assert (row["cash_amount"], row["approved_cash"], row["orders_count"], row["change_pending"]) == (
        "22.000",
        "22.000",
        10,
        False,
    )
    assert cash_of(client, driver) == (D("22.000"), D("0"))
    statement = admin_client.get(f"/api/v1/cash/drivers/{driver['id']}/statement").json()
    assert any(x["amount"] == "4.000" and x["reason"] == "إيصال كاش إضافي" for x in statement["lines"])
    assert told(client, driver)[0]["kind"] == "report_change_approved"
    log = changes(admin_client, rid)
    assert [(c["kind"], c["status"]) for c in log] == [("request", "rejected"), ("request", "approved")]
    assert log[0]["decision_note"] == "الطلب ظاهر في يوم آخر"
    mine_log = client.get(f"/api/v1/driver/reports/{rid}/changes", headers=driver["h"]).json()
    assert [c["id"] for c in mine_log] == [c["id"] for c in log]


def test_no_change_once_the_months_payroll_is_approved(admin_client, client, driver, company):
    from tests.test_finance import month, payroll_settings

    rid = report(client, driver, cash="10", orders=5).json()["id"]
    assert approve(admin_client, rid).status_code == 200
    pending = client.post(
        f"/api/v1/driver/reports/{rid}/change-request", json={"orders_count": 6, "reason": "خطأ"}, headers=driver["h"]
    ).json()
    payroll_settings(admin_client)
    first, _ = month()
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": company["id"], "month": str(first)}).json()
    assert admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve").status_code == 200
    r = admin_client.post(f"{R}/change-requests/{pending['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "payroll_locked"
    assert (
        admin_client.post(f"{R}/change-requests/{pending['id']}/reject", json={"note": "الشهر مغلق"}).status_code == 200
    )
    r = client.post(
        f"/api/v1/driver/reports/{rid}/change-request", json={"orders_count": 7, "reason": "خطأ"}, headers=driver["h"]
    )
    assert r.status_code == 409 and r.json()["code"] == "payroll_locked"


def test_with_a_workflow_sent_back_stops_the_approval_and_the_correction_restarts_it(
    admin_client, client, new_client, driver
):
    from tests.conftest import make_user
    from tests.test_approvals import as_user, configure, inbox, step

    checker = as_user(new_client, make_user(admin_client, "acc7", permissions=["approvals.view"], role="accountant"))
    configure(admin_client, "daily_report", [step("المراجع", role="accountant")])
    rid = report(client, driver, cash="12", orders=6).json()["id"]
    waiting = [x for x in inbox(checker) if x["process"] == "daily_report"]
    assert len(waiting) == 1
    assert admin_client.post(f"{R}/{rid}/send-back", json={"reason": "الطلبات ناقصة"}).status_code == 200
    assert [x for x in inbox(checker) if x["process"] == "daily_report"] == []
    assert patch(client, driver, rid, orders_count=8).status_code == 200
    again = [x for x in inbox(checker) if x["process"] == "daily_report"]
    assert len(again) == 1 and again[0]["id"] != waiting[0]["id"]
