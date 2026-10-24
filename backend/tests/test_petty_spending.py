"""A petty cash holder spends from his custody in the driver app: the amount, an expense type allowed for petty cash,
the invoice's camera photo. The office approves it (a finance expense paid from his custody: the custody goes down)
or rejects it with a reason; a request never asks for more than he can still spend."""

import uuid
from datetime import timedelta

from app.core.clock import today
from tests.conftest import bearer, bind_device, fund_treasury, login, make_driver, make_user
from tests.test_app_screens import save
from tests.test_finance import types
from tests.test_fuel_claims import camera
from tests.test_petty_cash import fund, holders

DRIVER = "/api/v1/driver/petty"
C = "/api/v1/cash/petty-expenses"
F = "/api/v1/finance"


def holder(admin_client, client, company, db, amount="20") -> dict:
    fund_treasury(db, "100")
    d = make_driver(admin_client, company["id"])
    if amount:
        assert fund(admin_client, d, amount).status_code == 201
    return {"driver": d, "h": bearer(bind_device(client, d["phone"]))}


def spend(client, s, *, amount="4.250", photo=None, category=None, admin=None, **extra):
    body = {
        "client_ref": str(uuid.uuid4()),
        "amount": amount,
        "category": category or types(admin)["office"],
        "invoice_sha256": photo or camera(client, s["h"]),
    } | extra
    return client.post(f"{DRIVER}/expenses", headers=s["h"], json=body)


def test_the_holder_sees_his_custody_and_a_request_waits_then_its_approval_lowers_it(admin_client, client, company, db):
    s = holder(admin_client, client, company, db)
    view = client.get(DRIVER, headers=s["h"]).json()
    assert (view["has_custody"], view["balance"], view["available"], view["expenses"]) == (True, "20.000", "20.000", [])
    assert [m["kind"] for m in view["movements"]] == ["petty_fund"] and view["movements"][0]["amount"] == "20.000"
    codes = {c["code"] for c in view["categories"]}
    assert {"office", "repairs", "other", "fuel"} <= codes

    r = spend(client, s, admin=admin_client, amount="4.250", vendor="Stationery", note="paper")
    assert r.status_code == 201, r.text
    mine = r.json()
    assert (mine["status"], mine["amount"], mine["vendor"], mine["invoice_date"]) == (
        "pending",
        "4.250",
        "Stationery",
        str(today()),
    )
    view = client.get(DRIVER, headers=s["h"]).json()
    assert (view["balance"], view["pending"], view["available"]) == ("20.000", "4.250", "15.750")
    [alert] = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "petty_expense"]
    assert alert["entity_id"] == mine["id"]
    assert holders(admin_client)[s["driver"]["id"]]["pending"] == {"count": 1, "amount": "4.250"}

    [row] = admin_client.get(C, params={"status": "pending"}).json()
    assert (row["id"], row["driver"]["id"], row["balance"], row["category"]["code"]) == (
        mine["id"],
        s["driver"]["id"],
        "20.000",
        "office",
    )
    assert admin_client.get(f"{C}/pending-count").json() == {"count": 1}
    photo = admin_client.get(row["invoice_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"

    r = admin_client.post(f"{C}/{mine['id']}/approve", json={"note": "ok"})
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "approved" and done["expense_id"] and done["balance"] == "15.750"
    expense = admin_client.get(f"{F}/expenses/{done['expense_id']}").json()
    assert (expense["status"], expense["payment_method"], expense["amount"], expense["petty_employee"]["id"]) == (
        "approved",
        "petty",
        "4.250",
        s["driver"]["id"],
    )
    assert holders(admin_client)[s["driver"]["id"]]["balance"] == "15.750"
    assert holders(admin_client)[s["driver"]["id"]].get("pending") is None
    view = client.get(DRIVER, headers=s["h"]).json()
    assert (view["balance"], view["available"], view["expenses"][0]["status"]) == ("15.750", "15.750", "approved")
    assert [m["kind"] for m in view["movements"]] == ["petty_fund"]  # the spending is listed once, as his request
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()
    assert any(n["kind"] == "petty_approved" for n in (notices.get("items") if isinstance(notices, dict) else notices))
    r = admin_client.post(f"{C}/{mine['id']}/reject", json={"reason": "too late"})
    assert r.status_code == 409 and r.json()["code"] == "petty_expense_decided"

    # the expense cancelled later: the money is back in his custody, the request reads rejected
    r = admin_client.post(f"{F}/expenses/{done['expense_id']}/cancel", json={"reason": "wrong invoice"})
    assert r.status_code == 200, r.text
    view = client.get(DRIVER, headers=s["h"]).json()
    assert view["balance"] == "20.000"
    assert (view["expenses"][0]["status"], view["expenses"][0]["decision_note"]) == ("rejected", "wrong invoice")


def test_refusals_over_balance_photo_rules_and_an_idempotent_resend(admin_client, client, company, db):
    s = holder(admin_client, client, company, db, amount="10")
    r = spend(client, s, admin=admin_client, amount="10.001")
    assert r.status_code == 422 and r.json()["code"] == "petty_over_balance"
    assert spend(client, s, admin=admin_client, amount="6").status_code == 201
    r = spend(client, s, admin=admin_client, amount="4.001")  # 6 already asked
    assert r.status_code == 422 and r.json()["code"] == "petty_over_balance"

    gallery = camera(client, s["h"], source="upload")
    r = spend(client, s, admin=admin_client, amount="1", photo=gallery)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    other = holder(admin_client, client, company, db, amount="5")
    theirs = camera(client, other["h"])
    r = spend(client, s, admin=admin_client, amount="1", photo=theirs)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"

    photo = camera(client, s["h"])
    body = {"client_ref": str(uuid.uuid4()), "amount": "1.500", "category": types(admin_client)["office"],
            "invoice_sha256": photo}  # fmt: skip
    assert client.post(f"{DRIVER}/expenses", headers=s["h"], json=body).status_code == 201
    r = client.post(f"{DRIVER}/expenses", headers=s["h"], json=body)
    assert r.status_code == 409 and r.json()["code"] == "petty_expense_exists"
    r = spend(client, s, admin=admin_client, amount="1", photo=photo)
    assert r.status_code == 409 and r.json()["code"] == "petty_invoice_used"

    r = spend(client, s, admin=admin_client, amount="1", invoice_date=str(today() + timedelta(days=1)))
    assert r.status_code == 422 and r.json()["code"] == "petty_invoice_future"
    r = spend(client, s, admin=admin_client, amount="1", category=types(admin_client)["fuel"] + 9999)
    assert r.status_code == 422 and r.json()["code"] == "petty_category_unknown"
    # an expense type the office did not allow for petty cash
    t = types(admin_client)["office"]
    assert admin_client.patch(f"{F}/expense-types/{t}", json={"petty": False}).json()["petty"] is False
    r = spend(client, s, admin=admin_client, amount="1")
    assert r.status_code == 422 and r.json()["code"] == "petty_category_unknown"
    assert "office" not in {c["code"] for c in client.get(DRIVER, headers=s["h"]).json()["categories"]}

    nobody = holder(admin_client, client, company, db, amount=None)
    view = client.get(DRIVER, headers=nobody["h"]).json()
    assert (view["has_custody"], view["balance"], view["categories"]) == (False, "0.000", [])
    r = spend(client, nobody, admin=admin_client, amount="1", category=types(admin_client)["other"])
    assert r.status_code == 409 and r.json()["code"] == "petty_no_custody"


def test_reject_needs_a_reason_cancel_while_pending_and_the_office_scope(admin_client, client, new_client, company, db):
    s = holder(admin_client, client, company, db)
    a = spend(client, s, admin=admin_client, amount="2").json()
    b = spend(client, s, admin=admin_client, amount="3").json()
    r = admin_client.post(f"{C}/{a['id']}/reject", json={"reason": ""})
    assert r.status_code == 422
    r = admin_client.post(f"{C}/{a['id']}/reject", json={"reason": "no invoice number"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()
    items = notices.get("items") if isinstance(notices, dict) else notices
    assert any(n["kind"] == "petty_rejected" for n in items)
    assert client.get(DRIVER, headers=s["h"]).json()["balance"] == "20.000"

    r = client.post(f"{DRIVER}/expenses/{b['id']}/cancel", headers=s["h"])
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.post(f"{DRIVER}/expenses/{b['id']}/cancel", headers=s["h"])
    assert r.status_code == 409 and r.json()["code"] == "petty_expense_decided"
    other = holder(admin_client, client, company, db, amount="5")
    c = spend(client, s, admin=admin_client, amount="1").json()
    r = client.post(f"{DRIVER}/expenses/{c['id']}/cancel", headers=other["h"])
    assert r.status_code == 404

    make_user(admin_client, "pviewer", permissions=["treasury.view"])
    make_user(admin_client, "pmanager", permissions=["treasury.view", "treasury.manage"])
    make_user(admin_client, "plimited", permissions=["treasury.view", "treasury.manage", "finance.approve"],
              company_ids=[company["id"]])  # fmt: skip
    v = new_client()
    login(v, "pviewer")
    assert v.get(C).status_code == 200
    assert v.post(f"{C}/{c['id']}/reject", json={"reason": "nope"}).status_code == 403
    m = new_client()
    login(m, "pmanager")
    r = m.post(f"{C}/{c['id']}/approve", json={})
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    lim = new_client()
    login(lim, "plimited")
    r = lim.get(C)
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"

    # the screen hidden by the office: refused
    r = save(admin_client, hidden_screens=["petty"])
    assert r.status_code == 200, r.text
    r = client.get(DRIVER, headers=s["h"])
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
