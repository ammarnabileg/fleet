"""Approval workflows (BRD FR-WFL-01..05): steps by role or person from an amount, a reason for every refusal, every
decision kept, one person one step, delegation while away and escalation after a time; and every process the BRD
names goes through its workflow, while a process without one keeps its permission."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.core.clock import today
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
    name,
    upload,
)
from tests.test_finance import expense, month, payroll_settings, treasury_float  # noqa: F401 (fixture)
from tests.test_maintenance import center, portal_client, quote, receive

W = "/api/v1/approvals"
F = "/api/v1/finance"


def step(label, *, role=None, user=None, min_amount="0", hours=None, escalate=None) -> dict:
    body = {"name": name(label, label), "min_amount": min_amount}
    if role:
        body["role"] = role
    if user:
        body["user_id"] = user["public_id"]
    if hours:
        body |= {"escalate_after_hours": hours, "escalate_role": escalate}
    return body


def configure(admin_client, process, steps, *, active=True) -> dict:
    current = {w["process"]: w for w in admin_client.get(f"{W}/workflows").json()}[process]
    r = admin_client.put(
        f"{W}/workflows/{process}", json={"version": current["version"], "active": active, "steps": steps}
    )
    assert r.status_code == 200, r.text
    return r.json()


def as_user(new_client, user) -> object:
    c = new_client()
    login(c, user["username"])
    return c


def inbox(c) -> list[dict]:
    r = c.get(f"{W}/inbox")
    assert r.status_code == 200, r.text
    return r.json()


def waiting(c, ref) -> dict:
    found = [x for x in inbox(c) if x["document_ref"] == ref]
    assert len(found) == 1, (ref, [x["document_ref"] for x in inbox(c)])
    return found[0]


def decide(c, request, approve=True, reason=None):
    body = {"approve": approve} | ({"reason": reason} if reason else {})
    return c.post(f"{W}/requests/{request['id']}/decide", json=body)


def history(c, process, document_id) -> list[dict]:
    r = c.get(f"{W}/history/{process}/{document_id}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def people(admin_client, new_client):
    """Two accountants in one role, a manager named in person, a director to escalate to."""
    acc = ["approvals.view", "finance.view"]
    users = {
        "acc1": make_user(admin_client, "acc1", permissions=acc, role="accountant"),
        "acc2": make_user(admin_client, "acc2", permissions=acc, role="accountant"),
        "boss": make_user(admin_client, "boss", permissions=acc),
        "dir": make_user(admin_client, "dir", permissions=acc, role="director"),
    }
    return {k: {"user": u, "c": as_user(new_client, u)} for k, u in users.items()}


def test_without_a_workflow_the_permission_decides(admin_client, company):
    assert all(not w["active"] and w["steps"] == [] for w in admin_client.get(f"{W}/workflows").json())
    e = expense(admin_client, company["id"])
    assert admin_client.post(f"{F}/expenses/{e['id']}/approve", json={}).json()["status"] == "approved"
    assert history(admin_client, "expense", e["id"]) == []


def test_two_steps_by_role_then_by_person_above_an_amount(admin_client, company, people):
    configure(
        admin_client,
        "expense",
        [step("المحاسب", role="accountant"), step("المدير", user=people["boss"]["user"], min_amount="100")],
    )
    acc1, acc2, boss = people["acc1"]["c"], people["acc2"]["c"], people["boss"]["c"]

    # 50.000: only the first step applies; it waits in both accountants' inboxes, not the manager's
    small = expense(admin_client, company["id"], amount="50")
    ref = f"EXP-{small['number']}"
    assert waiting(acc2, ref)["amount"] == "50.000"
    assert not [x for x in inbox(boss) if x["document_ref"] == ref]
    # the finance permission alone no longer approves it: the superuser holds no step
    r = admin_client.post(f"{F}/expenses/{small['id']}/approve", json={})
    assert r.status_code == 403 and r.json()["code"] == "not_your_step"
    done = decide(acc1, waiting(acc1, ref))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "approved"
    assert admin_client.get(f"{F}/expenses/{small['id']}").json()["status"] == "approved"

    # 150.000: the accountant, then the manager in person
    big = expense(admin_client, company["id"], amount="150")
    ref = f"EXP-{big['number']}"
    assert decide(acc1, waiting(acc1, ref)).json()["current"] == 1
    assert admin_client.get(f"{F}/expenses/{big['id']}").json()["status"] == "pending"  # not approved yet
    assert not [x for x in inbox(acc2) if x["document_ref"] == ref]
    r = acc2.post(f"{W}/requests/{waiting(boss, ref)['id']}/decide", json={"approve": True})
    assert r.status_code == 403 and r.json()["code"] == "not_your_step"
    r = decide(boss, waiting(boss, ref), reason="ok")
    assert r.json()["status"] == "approved"
    assert admin_client.get(f"{F}/expenses/{big['id']}").json()["status"] == "approved"

    # FR-WFL-04: who, when, what, why, for each step
    (h,) = history(admin_client, "expense", big["id"])
    assert [(d["step"], d["decision"], d["by"]["name"], d["reason"]) for d in h["decisions"]] == [
        (0, "approved", "User acc1 (acc1)", None),
        (1, "approved", "User boss (boss)", "ok"),
    ]
    assert all(d["at"] for d in h["decisions"]) and h["closed_at"]
    assert [s["role"]["code"] if s["role"] else s["user"]["name"] for s in h["steps"]] == [
        "accountant",
        "User boss (boss)",
    ]


def test_a_refusal_needs_its_reason_and_refuses_the_document(admin_client, company, people):
    configure(admin_client, "expense", [step("المحاسب", role="accountant"), step("المدير", role="director")])
    e = expense(admin_client, company["id"])
    ref = f"EXP-{e['number']}"
    acc1 = people["acc1"]["c"]
    r = decide(acc1, waiting(acc1, ref), approve=False)
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    assert decide(acc1, waiting(acc1, ref)).status_code == 200
    d = people["dir"]["c"]
    r = decide(d, waiting(d, ref), approve=False, reason="No receipt attached")
    assert r.json()["status"] == "rejected"
    expense_now = admin_client.get(f"{F}/expenses/{e['id']}").json()
    assert expense_now["status"] == "rejected" and expense_now["decision_note"] == "No receipt attached"
    assert history(admin_client, "expense", e["id"])[0]["decisions"][-1]["reason"] == "No receipt attached"
    assert inbox(d) == []
    r = decide(d, r.json())
    assert r.status_code == 409 and r.json()["code"] == "approval_closed"


def test_one_person_approves_one_step_of_a_document(admin_client, company, people):
    configure(admin_client, "expense", [step("أولى", role="accountant"), step("ثانية", role="accountant")])
    e = expense(admin_client, company["id"])
    ref = f"EXP-{e['number']}"
    acc1, acc2 = people["acc1"]["c"], people["acc2"]["c"]
    decide(acc1, waiting(acc1, ref))
    assert waiting(acc1, ref)["current"] == 1  # still listed: the role is theirs
    r = decide(acc1, waiting(acc1, ref))
    assert r.status_code == 409 and r.json()["code"] == "approver_repeated"
    assert decide(acc2, waiting(acc2, ref)).json()["status"] == "approved"


def test_delegation_while_away(admin_client, company, people):
    boss, acc2 = people["boss"], people["acc2"]
    configure(admin_client, "expense", [step("المدير", user=boss["user"])])
    e = expense(admin_client, company["id"])
    ref = f"EXP-{e['number']}"
    assert not [x for x in inbox(acc2["c"]) if x["document_ref"] == ref]
    # a delegation that starts tomorrow gives nothing today
    r = boss["c"].post(
        f"{W}/delegations",
        json={"delegate_id": people["acc1"]["user"]["public_id"], "date_from": str(today() + timedelta(days=1)),
              "date_to": str(today() + timedelta(days=5))},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["status"] == "upcoming"
    assert not [x for x in inbox(people["acc1"]["c"]) if x["document_ref"] == ref]
    r = decide(people["acc1"]["c"], waiting(boss["c"], ref))
    assert r.status_code == 403 and r.json()["code"] == "not_your_step"
    r = boss["c"].post(f"{W}/delegations", json={"delegate_id": boss["user"]["public_id"],
                                               "date_from": str(today()), "date_to": str(today())})  # fmt: skip
    assert r.json()["code"] == "delegate_self"
    r = boss["c"].post(
        f"{W}/delegations",
        json={
            "delegate_id": acc2["user"]["public_id"],
            "date_from": str(today()),
            "date_to": str(today() + timedelta(days=3)),
            "reason": "Annual leave",
        },
    )
    assert r.status_code == 201, r.text
    delegation = r.json()
    assert delegation["status"] == "active" and delegation["delegate"]["name"] == "User acc2 (acc2)"
    # someone else's delegation is for whoever manages the workflows
    r = acc2["c"].post(
        f"{W}/delegations",
        json={"user_id": boss["user"]["public_id"], "delegate_id": acc2["user"]["public_id"],
              "date_from": str(today()), "date_to": str(today())},
    )  # fmt: skip
    assert r.status_code == 403
    # the delegate sees it and decides on the manager's behalf
    r = decide(acc2["c"], waiting(acc2["c"], ref))
    assert r.json()["status"] == "approved"
    d = r.json()["decisions"][0]
    assert d["by"]["name"] == "User acc2 (acc2)" and d["on_behalf_of"]["name"] == "User boss (boss)"
    # cancelled, the delegation stops at once
    e2 = expense(admin_client, company["id"])
    assert boss["c"].post(f"{W}/delegations/{delegation['id']}/cancel").json()["status"] == "cancelled"
    assert not [x for x in inbox(acc2["c"]) if x["document_ref"] == f"EXP-{e2['number']}"]
    assert [x["status"] for x in acc2["c"].get(f"{W}/delegations").json()] == ["cancelled"]
    assert sorted(x["status"] for x in boss["c"].get(f"{W}/delegations").json()) == ["cancelled", "upcoming"]


def test_a_step_waiting_too_long_escalates(admin_client, company, people, owner_db, db):
    from app.modules.approvals import service

    configure(admin_client, "expense", [step("المحاسب", role="accountant", hours=4, escalate="director")])
    e = expense(admin_client, company["id"])
    ref = f"EXP-{e['number']}"
    d = people["dir"]["c"]
    assert not [x for x in inbox(d) if x["document_ref"] == ref]
    assert service.escalate(db) == 0  # not yet
    owner_db.execute(text("UPDATE approvals.requests SET step_since = now() - interval '5 hours'"))
    owner_db.commit()
    assert service.escalate(db) == 1
    assert service.escalate(db) == 0  # once per step
    alerts = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "approval_escalated"]
    assert len(alerts) == 1 and ref in alerts[0]["message"]
    r = decide(d, waiting(d, ref))
    assert r.json()["status"] == "approved"
    assert [x["decision"] for x in r.json()["decisions"]] == ["escalated", "approved"]
    assert r.json()["decisions"][0]["by"] is None  # the system


def test_withdrawn_switched_off_and_changed_amounts(admin_client, company, people, db):
    from app.modules.approvals import service

    configure(admin_client, "expense", [step("المحاسب", role="accountant")])
    acc1 = people["acc1"]["c"]
    # a cancelled expense leaves the inbox
    e = expense(admin_client, company["id"])
    assert admin_client.post(f"{F}/expenses/{e['id']}/cancel", json={"reason": "Entered twice"}).status_code == 200
    assert not [x for x in inbox(acc1) if x["document_ref"] == f"EXP-{e['number']}"]
    assert history(admin_client, "expense", e["id"])[0]["cancel_note"] == "withdrawn"
    # an amount that changed after a step was approved starts over (what was approved is what is applied)
    acc1_id = db.scalar(text("SELECT id FROM identity.users WHERE username = 'acc1'"))
    acc2_id = db.scalar(text("SELECT id FROM identity.users WHERE username = 'acc2'"))
    configure(admin_client, "payroll_run", [step("أولى", role="accountant"), step("ثانية", role="accountant")])
    doc = {"document_id": 999_001, "document_key": uuid.uuid4(), "document_ref": "TEST-1", "company_id": None}
    assert service.gate(db, "payroll_run", **doc, amount=D("100"), actor_user_id=acc1_id) is False
    assert service.gate(db, "payroll_run", **doc, amount=D("120"), actor_user_id=acc2_id) is False  # step 1 again
    db.commit()
    rows = db.execute(text("SELECT status, cancel_note, current FROM approvals.requests WHERE document_id = 999001 "
                           "ORDER BY id")).all()  # fmt: skip
    assert [tuple(r) for r in rows] == [("cancelled", "amount_changed", 1), ("pending", None, 1)]
    # switched off, the requests under way are cancelled and the permission decides again
    e = expense(admin_client, company["id"])
    configure(admin_client, "expense", [step("المحاسب", role="accountant")], active=False)
    assert history(admin_client, "expense", e["id"])[0]["cancel_note"] == "workflow_off"
    assert admin_client.post(f"{F}/expenses/{e['id']}/approve", json={}).json()["status"] == "approved"


def test_workflow_rules(admin_client, new_client, people):
    put = lambda body: admin_client.put(f"{W}/workflows/expense", json={"version": 0, "active": True} | body)  # noqa: E731
    r = put({"steps": [{"name": name("أ", "A")}]})
    assert r.json()["code"] == "step_needs_one_approver" and r.json()["params"]["position"] == 1
    r = put({"steps": [step("أ", role="accountant", user=people["boss"]["user"])]})
    assert r.json()["code"] == "step_needs_one_approver"
    r = put({"steps": [step("أ", role="accountant") | {"escalate_after_hours": 4}]})
    assert r.json()["code"] == "step_escalation_incomplete"
    r = put({"steps": [step("أ", role="maintenance_center")]})
    assert r.json()["code"] == "step_role_not_allowed"
    r = put({"steps": [step("أ", role="no_such_role")]})
    assert r.status_code == 404
    assert put({"version": 3, "steps": []}).json()["code"] == "version_conflict"
    # a role nobody holds is shown, so it is not left to stop every request
    r = admin_client.post("/api/v1/roles", json={"code": "nobody_role", "name": name("دور", "Role"), "permissions": []})
    assert r.status_code == 201, r.text
    flow = configure(admin_client, "expense", [step("أ", role="accountant"), step("ب", role="nobody_role")])
    assert [s["holders"] for s in flow["steps"]] == [2, 0]
    roles = [r["code"] for r in admin_client.get(f"{W}/options").json()["roles"]]
    assert "accountant" in roles and "maintenance_center" not in roles
    # configuring is its own permission; the audit log keeps every change
    r = people["acc1"]["c"].put(f"{W}/workflows/expense", json={"version": flow["version"], "active": False,
                                                                 "steps": []})  # fmt: skip
    assert r.status_code == 403
    events = admin_client.get("/api/v1/audit", params={"entity_type": "workflow"}).json()
    assert events and events[0]["action"] == "approvals.workflow_updated"


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_every_process_goes_through_its_workflow(admin_client, client, new_client, company, people, owner_db):
    """A single checker's step on each of the seven processes: the superuser's own approval is refused, the checker's
    from the inbox applies the module's decision."""
    for process in ("daily_report", "maintenance_request", "maintenance_quote", "maintenance_invoice",
                    "accident_estimate", "expense", "payroll_run"):  # fmt: skip
        configure(admin_client, process, [step("المراجع", role="accountant")])
    acc = people["acc1"]["c"]

    def through(process, ref_part):
        found = [x for x in inbox(acc) if x["process"] == process and ref_part in x["document_ref"]]
        assert len(found) == 1, (process, ref_part, [(x["process"], x["document_ref"]) for x in inbox(acc)])
        r = decide(acc, found[0])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        return found[0]

    cid = company["id"]
    # a daily report from the driver's app
    driver = make_driver(admin_client, cid)
    vehicle = make_vehicle(admin_client, cid, km=20_000)
    hand_over(admin_client, vehicle, driver, km=20_000)
    h = bearer(bind_device(client, driver["phone"]))
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    report = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={"business_date": str(today()), "orders_count": 4, "cash_amount": "8", "screenshot_sha256": shot},
    ).json()
    r = admin_client.post(f"/api/v1/daily-reports/{report['id']}/approve", json={})
    assert r.status_code == 403 and r.json()["code"] == "not_your_step"
    through("daily_report", str(today()))
    approved = admin_client.get("/api/v1/daily-reports", params={"status": "approved"}).json()
    assert [x["id"] for x in approved] == [report["id"]]

    # a maintenance request through the office (the driver's car is in an accident), then its quote above the limit
    m = "/api/v1/maintenance"
    c = center(admin_client)
    s = {"portal": portal_client(admin_client, new_client, c, "noor9")}
    owner_db.execute(text("UPDATE fleet.vehicles SET status = 'accident' WHERE public_id = :v"), {"v": vehicle["id"]})
    owner_db.commit()
    req = client.post(
        "/api/v1/driver/maintenance",
        headers=h,
        json={"client_ref": str(uuid.uuid4()), "kind": "mechanical", "description": "Brakes"},
    ).json()
    assert req["status"] == "requested"
    r = admin_client.post(f"{m}/requests/{req['id']}/approve", json={})
    assert r.status_code == 403
    through("maintenance_request", f"MNT-{req['number']}")
    assert admin_client.post(f"{m}/requests/{req['id']}/refer", json={"center_id": c["id"]}).status_code == 200
    assert receive(s, req["id"]).status_code == 200
    assert quote(s, req["id"], "250.000").json()["status"] == "quote_pending"
    through("maintenance_quote", f"MNT-{req['number']}")
    assert admin_client.get(f"{m}/requests/{req['id']}").json()["status"] == "in_repair"

    # an office invoice of the center
    r = admin_client.post(
        f"{m}/invoices",
        json={
            "center_id": c["id"],
            "company_id": cid,
            "number": "W-1",
            "invoice_date": str(today()),
            "total": "45",
            "file_sha256": upload(admin_client),
            "items": [{"kind": "other", "description": "Brakes", "unit_price": "45"}],
        },
    )
    assert r.status_code == 201, r.text
    through("maintenance_invoice", "INV-W-1")
    assert admin_client.get(f"{m}/invoices", params={"status": "approved"}).json()[0]["number"] == "W-1"

    # an accident's damage estimate from the center, on another driver's vehicle
    from tests.test_accidents import estimate, refer, reported

    driver2, vehicle2 = make_driver(admin_client, cid), make_vehicle(admin_client, cid, km=30_000)
    hand_over(admin_client, vehicle2, driver2, km=30_000)
    acc_s = {"h": bearer(bind_device(client, driver2["phone"])), "center": c, "portal": s["portal"]}
    aid = reported(client, acc_s)
    refer(admin_client, acc_s, aid)
    assert estimate(acc_s, aid).status_code == 200
    r = admin_client.post(f"/api/v1/accidents/{aid}/estimate/approve")
    assert r.status_code == 403
    through("accident_estimate", "ACC-")
    assert admin_client.get(f"/api/v1/accidents/{aid}").json()["estimate_status"] == "approved"

    # an expense
    e = expense(admin_client, cid)
    through("expense", f"EXP-{e['number']}")

    # a payroll run: refused (sent back with its reason), then approved
    make_employee(admin_client, cid, basic_salary="300.000", payment_method="cash")
    payroll_settings(admin_client)
    first, _ = month()
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": cid, "month": str(first)}).json()
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve")
    assert r.status_code == 403  # its request opened when it was prepared
    found = [x for x in inbox(acc) if x["process"] == "payroll_run"][0]
    assert decide(acc, found, approve=False, reason="Missing an employee").json()["status"] == "rejected"
    assert admin_client.get(f"/api/v1/payroll/runs/{run['id']}").json()["status"] == "draft"
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/recompute")
    assert r.status_code == 200, r.text
    r = acc.post(f"/api/v1/payroll/runs/{run['id']}/approve")
    assert r.status_code == 403  # the module's own route still needs its permission
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve")
    assert r.status_code == 403
    through("payroll_run", f"PAY-{first:%Y-%m}")
    assert admin_client.get(f"/api/v1/payroll/runs/{run['id']}").json()["status"] == "approved"
    assert len(history(acc, "payroll_run", run["id"])) == 2  # refused, then approved


def test_whoever_approved_through_a_delegate_does_not_approve_again(admin_client, new_client, company, people):
    """The director's delegate approves the director's own step; the director then holds the next step by role, and
    is refused: it would be one person approving two steps."""
    d, acc2 = people["dir"], people["acc2"]
    dir2 = as_user(new_client, make_user(admin_client, "dir2", permissions=["approvals.view"], role="director"))
    configure(admin_client, "expense", [step("المدير", user=d["user"]), step("المديرون", role="director")])
    r = d["c"].post(f"{W}/delegations", json={"delegate_id": acc2["user"]["public_id"], "date_from": str(today()),
                                             "date_to": str(today())})  # fmt: skip
    assert r.status_code == 201, r.text
    e = expense(admin_client, company["id"])
    ref = f"EXP-{e['number']}"
    r = decide(acc2["c"], waiting(acc2["c"], ref))
    assert r.json()["decisions"][0]["on_behalf_of"]["name"] == "User dir (dir)"
    r = decide(d["c"], waiting(d["c"], ref))
    assert r.status_code == 409 and r.json()["code"] == "approver_repeated"
    assert decide(dir2, waiting(dir2, ref)).json()["status"] == "approved"


def test_the_gate_itself_refuses_a_refusal_without_its_reason(admin_client, people, db):
    """Every screen asks for the reason first; the gate does not rely on them."""
    from app.core.errors import AppError
    from app.modules.approvals import service

    configure(admin_client, "payroll_run", [step("أولى", role="accountant")])
    acc1_id = db.scalar(text("SELECT id FROM identity.users WHERE username = 'acc1'"))
    doc = {"document_id": 999_002, "document_key": uuid.uuid4(), "document_ref": "TEST-2", "company_id": None}
    for reason in (None, ""):
        with pytest.raises(AppError) as err:
            service.gate(db, "payroll_run", **doc, amount=D("10"), actor_user_id=acc1_id, approve=False, reason=reason)
        assert err.value.code == "reason_required"
        db.rollback()
