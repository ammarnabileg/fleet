"""Two more money decisions under the approval workflows (BRD FR-WFL-02, FR-CSH-09): a manual correction of a driver's
cash balance and a deduction the office enters itself. With a workflow and a step for the amount they wait, pending,
until the last step; refused, they keep the reason and change nothing. Without one they apply at once, as before."""

from datetime import date

import pytest
from sqlalchemy import text

from app.core.clock import today
from tests import test_approvals
from tests.conftest import bearer, bind_device, fund_treasury, make_driver
from tests.test_approvals import configure, decide, inbox, step

C = "/api/v1/cash"


@pytest.fixture
def approvers(admin_client, new_client):
    return test_approvals.people.__wrapped__(admin_client, new_client)


def waiting(c, process, part) -> dict:
    found = [x for x in inbox(c) if x["process"] == process and part in x["document_ref"]]
    assert len(found) == 1, (process, part, [(x["process"], x["document_ref"]) for x in inbox(c)])
    return found[0]


def balance(admin_client, driver) -> tuple[str, str]:
    s = admin_client.get(f"{C}/drivers/{driver['id']}/statement").json()
    return s["posted"], s["pending"]


def test_a_cash_adjustment_waits_for_its_workflow_above_the_amount(admin_client, company, approvers):
    d = make_driver(admin_client, company["id"])
    adjust = lambda amount, why: admin_client.post(  # noqa: E731
        f"{C}/adjustments", json={"driver_id": d["id"], "amount": amount, "reason": why}
    )
    assert adjust("4", "عد ناقص").json()["status"] == "posted"  # no workflow yet: at once
    configure(admin_client, "cash_adjustment", [step("المحاسب", role="accountant", min_amount="10")])
    assert adjust("6", "فرق صغير").json()["status"] == "posted"  # under the step's amount: at once
    assert balance(admin_client, d) == ("10.000", "0.000")

    j = adjust("-25", "سلّم نقداً للمشرف").json()
    assert j["status"] == "pending"
    assert balance(admin_client, d) == ("10.000", "-25.000")  # shown, not counted
    acc = approvers["acc1"]["c"]
    request = waiting(acc, "cash_adjustment", "-25.000")
    assert request["document_ref"].startswith(d["name"]["ar"])  # the name as text, not a dict
    assert decide(admin_client, request).status_code == 403  # not the superuser's step
    r = decide(acc, request)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert balance(admin_client, d) == ("-15.000", "0.000")

    j = adjust("30", "خطأ في الإدخال").json()
    assert decide(acc, waiting(acc, "cash_adjustment", "+30.000"), approve=False).status_code == 422  # no reason
    r = decide(acc, waiting(acc, "cash_adjustment", "+30.000"), approve=False, reason="لا يوجد دليل")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert balance(admin_client, d) == ("-15.000", "0.000")  # refused: nothing changed
    lines = admin_client.get(f"{C}/drivers/{d['id']}/statement").json()["lines"]
    assert {line["journal_id"]: line["status"] for line in lines}[j["id"]] == "rejected"
    actions = [e["action"] for e in admin_client.get("/api/v1/audit", params={"entity_type": "journal"}).json()]
    assert "cash.adjustment_approved" in actions and "cash.adjustment_rejected" in actions


def test_a_manual_deduction_waits_then_is_approved_refused_or_withdrawn(admin_client, client, company, approvers, db):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    fund_treasury(db)  # an advance is paid out of the treasury

    def deduct(total, why):
        r = admin_client.post(
            "/api/v1/deductions",
            json={"employee_id": d["id"], "source_type": "advance", "reason": why, "total": total, "installments": 2},
        )
        assert r.status_code == 201, r.text
        return r.json()

    assert deduct("40", "سلفة أولى")["status"] == "approved"  # no workflow: at once
    configure(admin_client, "manual_deduction", [step("المحاسب", role="accountant")])
    acc = approvers["acc1"]["c"]

    late = deduct("120", "سلفة العيد")
    assert late["status"] == "pending"
    mine = lambda: [x["reason"] for x in client.get("/api/v1/driver/deductions", headers=h).json()]  # noqa: E731
    assert mine() == ["سلفة أولى"]  # the driver sees it once it is approved
    # decided after the month it was to start in: it starts with the current month instead
    db.execute(
        text("UPDATE payroll.deductions SET start_month = :m WHERE public_id = :p"),
        {"m": date(2026, 1, 1), "p": late["id"]},
    )
    db.commit()
    r = decide(acc, waiting(acc, "manual_deduction", "120.000"))
    assert r.status_code == 200 and r.json()["status"] == "approved"
    [approved] = [x for x in admin_client.get("/api/v1/deductions").json() if x["id"] == late["id"]]
    assert (approved["status"], approved["start_month"]) == ("approved", str(today().replace(day=1)))
    assert sorted(mine()) == sorted(["سلفة أولى", "سلفة العيد"])
    told = [n["kind"] for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"]]
    assert told.count("deduction_added") == 2  # once each, when approved

    refused = deduct("75", "شريحة هاتف")
    decide(acc, waiting(acc, "manual_deduction", "75.000"), approve=False, reason="الشريحة مدفوعة")
    [row] = admin_client.get("/api/v1/deductions", params={"status": "rejected"}).json()
    assert (row["id"], row["cancel_reason"]) == (refused["id"], "الشريحة مدفوعة")
    r = admin_client.post(f"/api/v1/deductions/{refused['id']}/cancel", json={"reason": "متأخر"})
    assert r.status_code == 409  # refused is final

    withdrawn = deduct("33", "خطأ")
    r = admin_client.post(f"/api/v1/deductions/{withdrawn['id']}/cancel", json={"reason": "أُدخل بالخطأ"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert not [x for x in inbox(acc) if "33.000" in x["document_ref"]]  # its request stopped
    assert sorted(mine()) == sorted(["سلفة أولى", "سلفة العيد"])
