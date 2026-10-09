"""Treasury phase 2, part C: petty cash custody. An employee holds cash funded from a branch treasury, pays small
expenses from it and returns the rest; the custody on screen is account 1115 in the books, counted once."""

from datetime import timedelta
from decimal import Decimal as D

from app.core.clock import today
from tests.conftest import fund_treasury, login, make_employee, make_user
from tests.test_finance import main_branch, period, types
from tests.test_treasury import branch_public_id, journals, treasury
from tests.test_treasury_closing import closed

F = "/api/v1/finance"
C = "/api/v1/cash"


def holders(client) -> dict[str, dict]:
    r = client.get(f"{C}/petty")
    assert r.status_code == 200, r.text
    return {h["employee"]["id"]: h for h in r.json()}


def fund(client, employee, amount, branch=None, **extra):
    branch = branch or main_branch(client)
    return client.post(f"{C}/petty/{employee['id']}/fund", json={"branch_id": branch, "amount": str(amount)} | extra)


def give_back(client, employee, amount, branch=None):
    branch = branch or main_branch(client)
    return client.post(f"{C}/petty/{employee['id']}/return", json={"branch_id": branch, "amount": str(amount)})


def petty_expense(client, company_id, holder, amount, **extra):
    body = {"company_id": company_id, "type_id": types(client)["fuel"], "expense_date": str(today()),
            "amount": str(amount), "payment_method": "petty", "petty_employee_id": holder["id"]} | extra  # fmt: skip
    return client.post(f"{F}/expenses", json=body)


def test_a_custody_is_funded_from_the_treasury_and_returned(admin_client, new_client, company, db):
    fund_treasury(db, "100")
    office = make_employee(admin_client, company["id"])
    r = fund(admin_client, office, "30", note="petty cash for the office")
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "petty_fund" and r.json()["reason"] == "petty cash for the office"
    assert treasury(admin_client) == D("70.000")
    h = holders(admin_client)[office["id"]]
    assert (h["balance"], h["last_movement"], h["branch_id"]) == ("30.000", str(today()), main_branch(admin_client))

    r = fund(admin_client, office, "70.001")
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"
    r = give_back(admin_client, office, "30.001")
    assert r.status_code == 422 and r.json()["code"] == "petty_insufficient"
    assert give_back(admin_client, office, "10").status_code == 201
    assert treasury(admin_client) == D("80.000")
    assert holders(admin_client)[office["id"]]["balance"] == "20.000"
    nobody = make_employee(admin_client, company["id"])
    r = give_back(admin_client, nobody, "1")
    assert r.status_code == 422 and r.json()["code"] == "petty_insufficient"
    assert nobody["id"] not in holders(admin_client)

    # its movements with the running balance; the treasury's show who holds it
    m = admin_client.get(f"{C}/petty/{office['id']}/movements").json()
    assert (m["opening"], m["closing"], m["account"]) == ("0.000", "20.000", "petty")
    assert [(ln["kind"], ln["amount"], ln["balance"]) for ln in m["lines"]] == [
        ("petty_fund", "30.000", "30.000"),
        ("petty_return", "-10.000", "20.000"),
    ]
    t = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/movements").json()
    funded = next(ln for ln in t["lines"] if ln["kind"] == "petty_fund")
    assert funded["driver"]["id"] == office["id"] and funded["amount"] == "-30.000" and funded["reversible"]

    # in the books: Dr 1115 / Cr 1110, and back
    admin_client.post(f"{F}/entries/post", json=period())
    admin_client.post(f"{F}/entries/approve", json=period())
    tb = {b["account"]["code"]: b for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert (tb["1115"]["debit"], tb["1115"]["credit"], tb["1115"]["closing"]) == ("30.000", "10.000", "20.000")
    assert (tb["1110"]["debit"], tb["1110"]["credit"]) == ("10.000", "30.000")

    # a custody is not a company's: treasury.view to see it, treasury.manage to move it, over every company
    make_user(admin_client, "viewer", permissions=["treasury.view"])
    make_user(admin_client, "limited", permissions=["treasury.view", "treasury.manage"], company_ids=[company["id"]])
    c = new_client()
    login(c, "viewer")
    assert c.get(f"{C}/petty").status_code == 200
    assert c.get(f"{C}/petty/{office['id']}/movements").status_code == 200
    assert fund(c, office, "1").status_code == 403
    c = new_client()
    login(c, "limited")
    for r in (c.get(f"{C}/petty"), c.get(f"{C}/petty/{office['id']}/movements"), fund(c, office, "1")):
        assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"

    # the treasury's closed day holds for the custody too
    closed(admin_client, today(), "80")
    r = fund(admin_client, office, "1")
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    r = give_back(admin_client, office, "1")
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"


def test_an_expense_paid_from_a_custody(admin_client, new_client, company, db):
    fund_treasury(db, "100")
    holder = make_employee(admin_client, company["id"])
    r = petty_expense(admin_client, company["id"], holder, "5", petty_employee_id=None)
    assert r.status_code == 422 and r.json()["code"] == "expense_petty_holder_required"
    r = petty_expense(admin_client, company["id"], holder, "5")
    assert r.status_code == 422 and r.json()["code"] == "petty_holder_unknown"
    assert fund(admin_client, holder, "20").status_code == 201
    r = petty_expense(admin_client, company["id"], holder, "5", expense_date=str(today() + timedelta(1)))
    assert r.status_code == 422 and r.json()["code"] == "treasury_date_future"
    make_user(admin_client, "clerk", permissions=["finance.view", "finance.create"], company_ids=[company["id"]])
    c = new_client()
    login(c, "clerk")
    r = petty_expense(c, company["id"], holder, "5")
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"

    # more than the custody holds: refused at approval, nothing moves
    big = petty_expense(admin_client, company["id"], holder, "20.001").json()
    r = admin_client.post(f"{F}/expenses/{big['id']}/approve", json={})
    assert r.status_code == 422 and r.json()["code"] == "petty_insufficient"
    assert admin_client.get(f"{F}/expenses/{big['id']}").json()["status"] == "pending"
    # approved: out of the custody, not out of the treasury
    e = petty_expense(admin_client, company["id"], holder, "15").json()
    assert e["petty_employee"]["id"] == holder["id"] and e["payment_method"] == "petty"
    assert admin_client.post(f"{F}/expenses/{e['id']}/approve", json={}).status_code == 200
    assert holders(admin_client)[holder["id"]]["balance"] == "5.000"
    assert treasury(admin_client) == D("80.000")
    [out] = journals(db, "disbursement")
    assert out.source_type == "expense" and out.reason.startswith(f"EXP-{e['number']}")
    r = admin_client.post(f"{C}/journals/{out.public_id}/reverse", json={"reason": "wrong amount"})
    assert r.status_code == 409 and r.json()["code"] == "disbursement_from_expense"
    m = admin_client.get(f"{C}/petty/{holder['id']}/movements").json()
    assert [ln["kind"] for ln in m["lines"]] == ["petty_fund", "disbursement"] and m["closing"] == "5.000"
    assert not m["lines"][1]["reversible"]
    # the fund cannot be reversed while the custody spent part of it
    fund_line = m["lines"][0]
    r = admin_client.post(f"{C}/journals/{fund_line['journal_id']}/reverse", json={"reason": "wrong holder"})
    assert r.status_code == 422 and r.json()["code"] == "petty_insufficient"

    # in the books once: the expense credits 1115, the disbursement makes no entry; 1115 = the custody
    result = admin_client.post(f"{F}/entries/post", json=period()).json()
    assert result["errors"] == [] and result["by_kind"] == {"cash_journal": 1, "expense": 1}
    admin_client.post(f"{F}/entries/approve", json=period())
    tb = {b["account"]["code"]: b for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert (tb["1115"]["debit"], tb["1115"]["credit"], tb["1115"]["closing"]) == ("20.000", "15.000", "5.000")
    assert tb["5120"]["debit"] == "15.000"

    # cancelled: back in the custody; reversed in the books, 1115 is the custody again
    r = admin_client.post(f"{F}/expenses/{e['id']}/cancel", json={"reason": "entered twice"})
    assert r.status_code == 200, r.text
    assert holders(admin_client)[holder["id"]]["balance"] == "20.000"
    stale = admin_client.post(f"{F}/entries/post", json=period()).json()["stale"]
    assert admin_client.post(f"{F}/entries/{stale[0]['id']}/reverse", json={"reason": "cancelled"}).status_code == 200
    admin_client.post(f"{F}/entries/post", json=period())
    tb = {b["account"]["code"]: b["closing"] for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert (tb["1115"], tb["5120"], tb["1110"]) == ("20.000", "0.000", "-20.000")
    # now intact: the fund reverses (and the treasury takes it back)
    r = admin_client.post(f"{C}/journals/{fund_line['journal_id']}/reverse", json={"reason": "wrong holder"})
    assert r.status_code == 201, r.text
    assert holders(admin_client)[holder["id"]]["balance"] == "0.000" and treasury(admin_client) == D("100.000")


def test_the_chart_has_the_custody_account_and_role(admin_client):
    accounts = {a["code"]: a for a in admin_client.get(f"{F}/accounts").json()}
    assert accounts["1115"]["type"] == "asset" and accounts["1115"]["roles"] == ["petty_cash"]
    assert accounts["1115"]["name"]["ar"] == "العهد النقدية"
