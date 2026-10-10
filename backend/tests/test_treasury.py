"""Treasury phase 1: the branch treasury on screen moves with the books when money leaves it outside the cash ledger
(an expense paid from it, a supplier's invoice paid later from it, an advance), counted once in the books; cash taken
from the bank back to the treasury; the treasury's and the bank's movements with their running balance; and a GL
reversal dated by the accountant."""

import io
from datetime import timedelta
from decimal import Decimal as D

import openpyxl
import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.cash.models import ACCOUNT_KINDS, Journal
from tests.conftest import fund_treasury, login, make_driver, make_employee, make_user, upload
from tests.test_catalog import LANGS
from tests.test_finance import approve, expense, main_branch, month, payroll_settings, period, post

F = "/api/v1/finance"
C = "/api/v1/cash"


def treasury(client, branch_id=None) -> D:
    rows = client.get(f"{C}/treasury").json()
    row = next(r for r in rows if branch_id is None and r["branch"]["is_default"] or r["branch"]["id"] == branch_id)
    return D(row["treasury"])


def bank(client) -> D:
    return D(next(r for r in client.get(f"{C}/treasury").json() if r["branch"]["is_default"])["bank"])


def branch_public_id(client) -> str:
    return next(b["public_id"] for b in client.get("/api/v1/branches").json() if b["is_default"])


def moves(client, account="treasury", **params) -> dict:
    r = client.get(f"{C}/treasury/{branch_public_id(client)}/movements", params={"account": account} | params)
    assert r.status_code == 200, r.text
    return r.json()


def journals(db, kind) -> list[Journal]:
    db.expire_all()
    return list(db.query(Journal).filter(Journal.kind == kind).order_by(Journal.id))


def test_a_treasury_expense_lowers_the_treasury_when_approved_and_gives_it_back_when_cancelled(
    admin_client, company, db
):
    fund_treasury(db, "100")
    assert treasury(admin_client) == D("100.000")
    # a branch is required when the money comes out of a treasury; not for the bank
    body = {"company_id": company["id"], "type_id": 1, "expense_date": str(today()), "amount": "5"}
    types = {t["code"]: t["id"] for t in admin_client.get(f"{F}/expense-types").json()}
    body["type_id"] = types["fuel"]
    r = admin_client.post(f"{F}/expenses", json=body | {"payment_method": "treasury"})
    assert r.status_code == 422 and r.json()["code"] == "expense_branch_required"
    r = admin_client.post(f"{F}/expenses", json=body | {"payment_method": "treasury", "branch_id": 999_999})
    assert r.status_code == 422 and r.json()["code"] == "branch_not_found"
    assert admin_client.post(f"{F}/expenses", json=body | {"payment_method": "bank"}).status_code == 201

    # pending: nothing out yet; approved: out of the treasury, with the receipt's photo and its number and type
    sha = upload(admin_client)
    e = expense(admin_client, company["id"], amount="30", files=[sha])
    assert e["branch_id"] == main_branch(admin_client)
    assert treasury(admin_client) == D("100.000")
    approve(admin_client, e)
    assert treasury(admin_client) == D("70.000")
    [out] = journals(db, "disbursement")
    assert (out.source_type, out.status, out.attachment_sha256) == ("expense", "posted", sha)
    assert out.reason.startswith(f"EXP-{e['number']}") and "وقود" in out.reason

    # never reversed on its own: only with its expense
    r = admin_client.post(f"{C}/journals/{out.public_id}/reverse", json={"reason": "wrong amount"})
    assert r.status_code == 409 and r.json()["code"] == "disbursement_from_expense"
    r = admin_client.post(f"{F}/expenses/{e['id']}/cancel", json={"reason": "entered twice"})
    assert r.status_code == 200, r.text
    assert treasury(admin_client) == D("100.000")
    [back] = journals(db, "reversal")
    assert (back.reverses_id, back.reason) == (out.id, "entered twice")

    # more than the treasury holds: refused, the expense stays pending and nothing moves
    big = expense(admin_client, company["id"], amount="100.001")
    r = admin_client.post(f"{F}/expenses/{big['id']}/approve", json={})
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"
    assert admin_client.get(f"{F}/expenses/{big['id']}").json()["status"] == "pending"
    assert treasury(admin_client) == D("100.000")
    # a cancelled pending one moves nothing
    p = expense(admin_client, company["id"], amount="1")
    assert admin_client.post(f"{F}/expenses/{p['id']}/cancel", json={"reason": "not needed"}).status_code == 200
    assert len(journals(db, "disbursement")) == 1 and treasury(admin_client) == D("100.000")


def test_a_payable_paid_from_the_treasury_lowers_it(admin_client, company, db):
    other = admin_client.post("/api/v1/branches", json={"name": {"ar": "فرع ٢", "en": "Branch 2"}})
    assert other.status_code == 201, other.text
    second = other.json()["id"]
    fund_treasury(db, "20", branch_id=second)
    e = approve(admin_client, expense(admin_client, company["id"], amount="15", payment_method="payable"))
    assert treasury(admin_client, second) == D("20.000")  # entered to be paid later: nothing out yet
    r = admin_client.post(f"{F}/expenses/{e['id']}/pay", json={"paid_from": "treasury"})
    assert r.status_code == 422 and r.json()["code"] == "expense_branch_required"
    r = admin_client.post(f"{F}/expenses/{e['id']}/pay", json={"paid_from": "treasury", "branch_id": second})
    assert r.status_code == 200 and r.json()["branch_id"] == second
    assert treasury(admin_client, second) == D("5.000")
    # paid from the bank: the treasury does not move
    b = approve(admin_client, expense(admin_client, company["id"], amount="3", payment_method="payable"))
    assert admin_client.post(f"{F}/expenses/{b['id']}/pay", json={"paid_from": "bank"}).status_code == 200
    assert treasury(admin_client, second) == D("5.000") and len(journals(db, "disbursement")) == 1
    # more than the treasury holds: refused, still unpaid
    c = approve(admin_client, expense(admin_client, company["id"], amount="6", payment_method="payable"))
    r = admin_client.post(f"{F}/expenses/{c['id']}/pay", json={"paid_from": "treasury", "branch_id": second})
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"
    assert admin_client.get(f"{F}/expenses/{c['id']}").json()["unpaid"]


def test_the_books_count_the_money_once_and_a_cancel_nets_to_zero(admin_client, company, db):
    fund_treasury(db, "100")
    e = approve(admin_client, expense(admin_client, company["id"], amount="12.500"))
    later = approve(
        admin_client, expense(admin_client, company["id"], kind="other", amount="4", payment_method="payable")
    )
    r = admin_client.post(
        f"{F}/expenses/{later['id']}/pay", json={"paid_from": "treasury", "branch_id": main_branch(admin_client)}
    )
    assert r.status_code == 200, r.text
    assert treasury(admin_client) == D("83.500")
    result = post(admin_client)
    # the disbursement journals make no entry: the expense and the payment credit the treasury, once each
    assert result["errors"] == [] and result["by_kind"] == {"expense": 2, "expense_payment": 1}
    assert admin_client.post(f"{F}/entries/approve", json=period()).status_code == 200
    rows = admin_client.get(f"{F}/trial-balance", params=period()).json()
    tb = {b["account"]["code"]: b for b in rows}
    assert (tb["1110"]["debit"], tb["1110"]["credit"]) == ("0.000", "16.500")
    assert (tb["5120"]["debit"], tb["5120"]["credit"]) == ("12.500", "0.000")
    assert (tb["6190"]["debit"], tb["2110"]["closing"]) == ("4.000", "0.000")
    assert sum(D(b["closing"]) for b in rows) == 0

    # cancelled: the treasury gets it back at once; the books list the entry to reverse, and the cash reversal
    # makes no entry of its own: reversed, everything of that expense nets to zero
    assert admin_client.post(f"{F}/expenses/{e['id']}/cancel", json={"reason": "wrong one"}).status_code == 200
    assert treasury(admin_client) == D("96.000")
    result = post(admin_client)
    assert result["created"] == 0 and [s["source_ref"] for s in result["stale"]] == [f"EXP-{e['number']}"]
    r = admin_client.post(f"{F}/entries/{result['stale'][0]['id']}/reverse", json={"reason": "expense cancelled"})
    assert r.status_code == 200, r.text
    assert post(admin_client) == {"created": 0, "by_kind": {}, "stale": [], "errors": []}
    tb = {b["account"]["code"]: b["closing"] for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert (tb["1110"], tb["5120"]) == ("-4.000", "0.000")  # only the payment stands, as in the treasury: 100 - 4
    assert treasury(admin_client) == D("100.000") - D("4.000")


def test_an_advance_is_paid_out_of_the_treasury_and_comes_back_when_cancelled(admin_client, company, db):
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    advance = {"employee_id": office["id"], "source_type": "advance", "reason": "advance", "total": "50"}
    r = admin_client.post("/api/v1/deductions", json=advance)
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"
    assert admin_client.get("/api/v1/deductions").json() == []  # nothing made
    fund_treasury(db, "80")
    r = admin_client.post("/api/v1/deductions", json=advance)
    assert r.status_code == 201, r.text
    assert treasury(admin_client) == D("30.000")
    [out] = journals(db, "disbursement")
    assert out.source_type == "deduction" and "سلفة" in out.reason
    # a SIM card is not cash: the treasury does not move
    sim = advance | {"source_type": "sim", "total": "5"}
    assert admin_client.post("/api/v1/deductions", json=sim).status_code == 201
    assert treasury(admin_client) == D("30.000")
    # in the books once: the deduction's entry credits the treasury, the disbursement makes none
    result = post(admin_client)
    assert result["by_kind"] == {"deduction": 2}
    # cancelled before payroll took anything: all of it back in the treasury
    r = admin_client.post(f"/api/v1/deductions/{r.json()['id']}/cancel", json={"reason": "not paid out"})
    assert r.status_code == 200, r.text
    assert treasury(admin_client) == D("80.000")

    # the accountant pays advances from elsewhere (its role on another account): the treasury is not touched
    accounts = {a["code"]: a["id"] for a in admin_client.get(f"{F}/accounts").json()}
    assert admin_client.put(f"{F}/roles", json={"roles": {"deduction_advance": accounts["1120"]}}).status_code == 200
    assert admin_client.post("/api/v1/deductions", json=advance | {"total": "500"}).status_code == 201
    assert treasury(admin_client) == D("80.000") and len(journals(db, "disbursement")) == 1


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_an_advance_partly_taken_by_payroll_is_not_cancelled(admin_client, companies, db):
    b = companies["b"]["id"]
    fund_treasury(db, "100")
    office = make_employee(admin_client, b, basic_salary="300.000", payment_method="cash")
    first, _ = month()
    r = admin_client.post(
        "/api/v1/deductions",
        json={"employee_id": office["id"], "source_type": "advance", "reason": "advance", "total": "60",
              "installments": 2, "start_month": str(first)},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    advance = r.json()
    payroll_settings(admin_client)
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": b, "month": str(first)}).json()
    assert admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve").status_code == 200
    assert treasury(admin_client) == D("40.000")
    # payroll took 30 of it: refused, the screen and the books stay together
    r = admin_client.post(f"/api/v1/deductions/{advance['id']}/cancel", json={"reason": "forgiven"})
    assert r.status_code == 409 and r.json()["code"] == "advance_partly_recovered"
    assert r.json()["params"] == {"taken": "30.000"} and treasury(admin_client) == D("40.000")
    # the run reopened: nothing taken any more, the cancel gives all of it back
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/reopen", json={"reason": "a wrong figure"})
    assert r.status_code == 200, r.text
    r = admin_client.post(f"/api/v1/deductions/{advance['id']}/cancel", json={"reason": "forgiven"})
    assert r.status_code == 200, r.text
    assert treasury(admin_client) == D("100.000")


def books_start(client, day) -> None:
    cur = client.get("/api/v1/settings").json()["finance"]
    value = cur["value"] | {"books_start_date": str(day) if day else None}
    r = client.put("/api/v1/settings/finance", json={"version": cur["version"], "value": value})
    assert r.status_code == 200, r.text


def test_treasury_money_is_dated_as_the_books_date_it(admin_client, company, db):
    fund_treasury(db, "100")
    branch = main_branch(admin_client)
    # the books start tomorrow: nothing out of the treasury today (the books would never count it)
    books_start(admin_client, today() + timedelta(1))
    later = approve(admin_client, expense(admin_client, company["id"], amount="3", payment_method="payable"))
    r = admin_client.post(f"{F}/expenses/{later['id']}/pay", json={"paid_from": "treasury", "branch_id": branch})
    assert r.status_code == 422 and r.json()["code"] == "before_books_start"
    types = {t["code"]: t["id"] for t in admin_client.get(f"{F}/expense-types").json()}
    body = {"company_id": company["id"], "type_id": types["fuel"], "amount": "1", "payment_method": "treasury",
            "branch_id": branch, "expense_date": str(today())}  # fmt: skip
    r = admin_client.post(f"{F}/expenses", json=body)
    assert r.status_code == 422 and r.json()["code"] == "before_books_start"
    books_start(admin_client, None)

    # out of the treasury on the day its entry takes: the expense's date, the day a payable is paid, the day an
    # advance is made
    e = approve(
        admin_client, expense(admin_client, company["id"], amount="2", expense_date=str(today() - timedelta(3)))
    )
    r = admin_client.post(f"{F}/expenses/{later['id']}/pay", json={"paid_from": "treasury", "branch_id": branch})
    assert r.status_code == 200, r.text
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    advance = {"employee_id": office["id"], "source_type": "advance", "reason": "advance", "total": "4"}
    assert admin_client.post("/api/v1/deductions", json=advance).status_code == 201
    assert [j.business_date for j in journals(db, "disbursement")] == [today() - timedelta(3), today(), today()]
    admin_client.post(f"{F}/entries/post", json={"date_from": str(today() - timedelta(10)), "date_to": str(today())})
    entries = admin_client.get(
        f"{F}/entries", params={"date_from": str(today() - timedelta(10)), "date_to": str(today())}
    ).json()
    dated = {(x["source_kind"], x["source_ref"]): x["entry_date"] for x in entries}
    assert dated[("expense", f"EXP-{e['number']}")] == str(today() - timedelta(3))
    assert dated[("expense_payment", f"EXP-{later['number']}")] == str(today())
    assert [d for (k, _), d in dated.items() if k == "deduction"] == [str(today())]

    # dated in the future: refused from the treasury (not from the bank)
    r = admin_client.post(f"{F}/expenses", json=body | {"expense_date": str(today() + timedelta(1))})
    assert r.status_code == 422 and r.json()["code"] == "treasury_date_future"
    bank_body = body | {"expense_date": str(today() + timedelta(1)), "payment_method": "bank"}
    assert admin_client.post(f"{F}/expenses", json=bank_body).status_code == 201

    # before the books start: refused when entered, and when approved if its date was moved before it since
    start = today() - timedelta(1)
    books_start(admin_client, start)
    r = admin_client.post(f"{F}/expenses", json=body | {"expense_date": str(start - timedelta(1))})
    assert r.status_code == 422 and r.json()["code"] == "before_books_start"
    pending = expense(admin_client, company["id"], amount="1", expense_date=str(start))
    db.execute(
        text("UPDATE finance.expenses SET expense_date = :d WHERE public_id = :p"),
        {"d": start - timedelta(2), "p": pending["id"]},
    )
    db.commit()
    r = admin_client.post(f"{F}/expenses/{pending['id']}/approve", json={})
    assert r.status_code == 422 and r.json()["code"] == "before_books_start"


def test_a_reversal_never_leaves_a_treasury_or_a_bank_negative(admin_client, company):
    driver = make_driver(admin_client, company["id"])
    receipt = admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "10"})
    branch = main_branch(admin_client)
    dep = admin_client.post(
        f"{C}/bank-deposits",
        json={"branch_id": branch, "amount": "10", "reference": "DEP-2", "receipt_sha256": upload(admin_client)},
    ).json()
    receipt_journal = next(ln for ln in moves(admin_client)["lines"] if ln["kind"] == "deposit")["journal_id"]
    assert receipt.status_code == 201
    r = admin_client.post(f"{C}/journals/{receipt_journal}/reverse", json={"reason": "wrong driver"})
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"  # the cash went to the bank
    wd = admin_client.post(
        f"{C}/bank-withdrawals",
        json={"branch_id": branch, "amount": "10", "reference": "WD-2", "attachment_sha256": upload(admin_client)},
    ).json()
    r = admin_client.post(f"{C}/journals/{dep['id']}/reverse", json={"reason": "wrong amount"})
    assert r.status_code == 422 and r.json()["code"] == "bank_insufficient"  # taken back out already
    assert admin_client.post(f"{C}/journals/{wd['id']}/reverse", json={"reason": "not taken"}).status_code == 201
    r = admin_client.post(f"{C}/journals/{receipt_journal}/reverse", json={"reason": "wrong driver"})
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"  # still in the bank
    assert admin_client.post(f"{C}/journals/{dep['id']}/reverse", json={"reason": "wrong amount"}).status_code == 201
    assert (
        admin_client.post(f"{C}/journals/{receipt_journal}/reverse", json={"reason": "wrong driver"}).status_code == 201
    )
    assert (treasury(admin_client), bank(admin_client)) == (D("0.000"), D("0.000"))


def test_money_out_of_a_treasury_or_bank_waits_for_the_branch_lock(admin_client, company, db):
    """Who reads a balance before taking money out holds the branch's lock, treasury then bank: a deposit waits while
    another transaction holds the treasury."""
    import threading

    from app.core.db import new_session
    from app.modules.cash import service as cash

    driver = make_driver(admin_client, company["id"])
    admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "10"})
    branch = main_branch(admin_client)
    photo = upload(admin_client)
    done = {}
    with new_session() as holder:
        cash.lock_branches(holder, treasury=[branch])
        t = threading.Thread(
            target=lambda: done.setdefault(
                "deposit",
                admin_client.post(
                    f"{C}/bank-deposits",
                    json={"branch_id": branch, "amount": "10", "reference": "DEP-3", "receipt_sha256": photo},
                ).status_code,
            )
        )
        t.start()
        t.join(1.5)
        assert t.is_alive() and "deposit" not in done  # waiting on the treasury
        holder.rollback()  # the lock released
    t.join(10)
    assert done == {"deposit": 201}
    with new_session() as other:  # and the bank's lock for a withdrawal, taken after the treasury's
        cash.lock_branches(other, bank=[branch])
        held = db.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"cash.bank:{branch}"}
        )
        assert held is False
        db.rollback()


def test_an_entry_dated_ahead_is_reversed_up_to_its_own_date(admin_client):
    accounts = {a["code"]: a["id"] for a in admin_client.get(f"{F}/accounts").json()}
    ahead = today() + timedelta(5)
    lines = [{"account_id": accounts["6130"], "debit": "5"}, {"account_id": accounts["2110"], "credit": "5"}]
    body = {"entry_date": str(ahead), "description": "Rent accrual", "lines": lines}
    r = admin_client.post(f"{F}/entries/manual", json=body)
    assert r.status_code == 201, r.text
    entry = r.json()
    admin_client.post(f"{F}/entries/approve", json={"ids": [entry["id"]]})
    for day, code in ((ahead + timedelta(1), "reversal_date_future"), (ahead - timedelta(1), "reversal_before_entry")):
        r = admin_client.post(f"{F}/entries/{entry['id']}/reverse", json={"reason": "wrong", "entry_date": str(day)})
        assert r.status_code == 422 and r.json()["code"] == code, r.text
    r = admin_client.post(f"{F}/entries/{entry['id']}/reverse", json={"reason": "wrong", "entry_date": str(ahead)})
    assert r.status_code == 200 and r.json()["entry_date"] == str(ahead)


def test_cash_from_the_bank_to_the_treasury(admin_client, new_client, company, db):
    driver = make_driver(admin_client, company["id"])
    assert admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "40"}).status_code == 201
    branch = main_branch(admin_client)
    deposit = {"branch_id": branch, "amount": "30", "reference": "DEP-1", "receipt_sha256": upload(admin_client)}
    assert admin_client.post(f"{C}/bank-deposits", json=deposit).status_code == 201
    body = {"branch_id": branch, "amount": "30.001", "reference": "WD-1", "attachment_sha256": upload(admin_client)}
    r = admin_client.post(f"{C}/bank-withdrawals", json=body)
    assert r.status_code == 422 and r.json()["code"] == "bank_insufficient"
    no_slip = {k: v for k, v in body.items() if k != "attachment_sha256"}
    assert admin_client.post(f"{C}/bank-withdrawals", json=no_slip | {"amount": "5"}).status_code == 422
    r = admin_client.post(f"{C}/bank-withdrawals", json=body | {"amount": "12"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["kind"] == "bank_withdrawal" and out["reason"] == "WD-1" and out["has_attachment"]
    assert (treasury(admin_client), bank(admin_client)) == (D("22.000"), D("18.000"))
    assert admin_client.get(f"{C}/journals/{out['id']}/attachment").status_code == 200

    # treasury.manage, over every company
    make_user(admin_client, "viewer", permissions=["treasury.view"])
    make_user(admin_client, "limited", permissions=["treasury.view", "treasury.manage"], company_ids=[company["id"]])
    for user, code in (("viewer", 403), ("limited", 403)):
        c = new_client()
        login(c, user)
        r = c.post(f"{C}/bank-withdrawals", json=body | {"amount": "1"})
        assert r.status_code == code, (user, r.text)
    assert r.json()["code"] == "company_out_of_scope"

    # in the books: Dr treasury / Cr bank
    post(admin_client)
    entries = admin_client.get(f"{F}/entries", params=period()).json()
    wd = next(e for e in entries if e["description"].startswith("سحب من البنك") or "WD-1" in e["description"])
    lines = admin_client.get(f"{F}/entries/{wd['id']}").json()["lines"]
    assert [(ln["account"]["code"], ln["debit"], ln["credit"]) for ln in lines] == [
        ("1110", "12.000", "0.000"),
        ("1120", "0.000", "12.000"),
    ]


def test_the_treasury_and_bank_movements_with_their_running_balance(admin_client, new_client, companies, db):
    a, b = companies["a"]["id"], companies["b"]["id"]
    fund_treasury(db, "50")  # long ago: the opening of this month
    da = make_driver(admin_client, a, name={"ar": "سائق أ", "en": "Driver A"})
    db_ = make_driver(admin_client, b, name={"ar": "سائق ب", "en": "Driver B"})
    r1 = admin_client.post(f"{C}/receipts", json={"driver_id": da["id"], "amount": "20"}).json()
    admin_client.post(f"{C}/receipts", json={"driver_id": db_["id"], "amount": "10"})
    e = approve(admin_client, expense(admin_client, a, amount="7"))
    branch = main_branch(admin_client)
    dep = admin_client.post(
        f"{C}/bank-deposits",
        json={"branch_id": branch, "amount": "25", "reference": "DEP-9", "receipt_sha256": upload(admin_client)},
    ).json()

    m = moves(admin_client)
    assert (m["opening"], m["closing"]) == ("50.000", "48.000")
    assert [(ln["kind"], ln["amount"], ln["balance"]) for ln in m["lines"]] == [
        ("deposit", "20.000", "70.000"),
        ("deposit", "10.000", "80.000"),
        ("disbursement", "-7.000", "73.000"),
        ("bank_deposit", "-25.000", "48.000"),
    ]
    first, _, out, to_bank = m["lines"]
    assert first["driver"]["name"]["en"] == "Driver A" and first["receipt_no"] == r1["receipt_no"]
    assert out["description"].startswith(f"EXP-{e['number']}") and not out["reversible"]
    assert to_bank["description"] == "DEP-9" and to_bank["has_attachment"] and to_bank["reversible"]
    assert first["reversible"] and m["closing"] == str(treasury(admin_client))
    # the bank: the deposit in
    bk = moves(admin_client, "bank")
    assert (bk["opening"], bk["closing"], [ln["amount"] for ln in bk["lines"]]) == ("0.000", "25.000", ["25.000"])
    # a period before today: nothing in it, both balances the opening
    old = moves(admin_client, **{"from": str(today() - timedelta(days=500)), "to": str(today() - timedelta(days=450))})
    assert (old["opening"], old["closing"], old["lines"]) == ("0.000", "0.000", [])
    assert moves(admin_client, **{"from": str(today()), "to": str(today())})["opening"] == "50.000"

    # reversed from here: the bank deposit, once
    r = admin_client.post(f"{C}/journals/{dep['id']}/reverse", json={"reason": "wrong amount"})
    assert r.status_code == 201, r.text
    m = moves(admin_client)
    assert m["closing"] == "73.000" and m["lines"][3]["reversed"] and not m["lines"][3]["reversible"]
    assert m["lines"][4]["kind"] == "reversal" and m["lines"][4]["reverses_kind"] == "bank_deposit"

    # a user of company A only: the branch's treasury is every company's, so neither its movements, their export,
    # nor a treasury journal's attachment
    make_user(admin_client, "cashier_a", permissions=["treasury.view", "cash.reverse"], company_ids=[a])
    c = new_client()
    login(c, "cashier_a")
    for path in ("movements", "movements/export"):
        r = c.get(f"{C}/treasury/{branch_public_id(admin_client)}/{path}")
        assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope", path
    r = c.get(f"{C}/journals/{dep['id']}/attachment")
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    assert admin_client.get(f"{C}/journals/{dep['id']}/attachment").status_code == 200
    assert m["lines"][3]["attachment_type"] == "image/jpeg"
    # without cash.reverse nothing; without treasury.view not at all
    make_user(admin_client, "reader", permissions=["treasury.view"])
    c = new_client()
    login(c, "reader")
    assert not any(ln["reversible"] for ln in moves(c)["lines"])
    make_user(admin_client, "nobody", permissions=["cash.view"])
    c = new_client()
    login(c, "nobody")
    assert c.get(f"{C}/treasury/{branch_public_id(admin_client)}/movements").status_code == 403
    missing = admin_client.get(f"{C}/treasury/00000000-0000-0000-0000-000000000000/movements")
    assert missing.status_code == 404 and missing.json()["code"] == "branch_not_found"
    r = admin_client.get(
        f"{C}/treasury/{branch_public_id(admin_client)}/movements",
        params={"from": str(today()), "to": str(today() - timedelta(days=1))},
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_range"

    # in Excel: the opening, each line with its balance, the closing
    r = admin_client.get(
        f"{C}/treasury/{branch_public_id(admin_client)}/movements/export", headers={"Accept-Language": "ar"}
    )
    assert r.status_code == 200, r.text
    rows = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    assert rows[0] == ("التاريخ", "الوقت", "الحركة", "البيان", "المبلغ", "الرصيد")
    assert rows[1][2] == "رصيد أول المدة" and rows[-1][2] == "رصيد آخر المدة" and len(rows) == 1 + 2 + 5
    assert "سائق أ" in rows[2][3] and D(str(rows[-1][5])) == D("73")


def test_a_reversal_is_dated_by_the_accountant(admin_client, company, db):
    fund_treasury(db)
    approve(admin_client, expense(admin_client, company["id"], amount="2", expense_date=str(today() - timedelta(1))))
    first, last = month()
    post_body = {"date_from": str(today() - timedelta(days=5)), "date_to": str(today())}
    admin_client.post(f"{F}/entries/post", json=post_body)
    [e] = admin_client.get(f"{F}/entries", params=post_body).json()
    admin_client.post(f"{F}/entries/approve", json={"ids": [e["id"]]})
    for day, code in (
        (today() + timedelta(days=1), "reversal_date_future"),
        (today() - timedelta(2), "reversal_before_entry"),
    ):
        r = admin_client.post(f"{F}/entries/{e['id']}/reverse", json={"reason": "wrong", "entry_date": str(day)})
        assert r.status_code == 422 and r.json()["code"] == code, r.text
    assert r.json()["params"] == {"date": str(today() - timedelta(1))}
    r = admin_client.post(
        f"{F}/entries/{e['id']}/reverse", json={"reason": "wrong", "entry_date": str(today() - timedelta(1))}
    )
    assert r.status_code == 200 and r.json()["entry_date"] == str(today() - timedelta(1))
    assert first <= today() <= last


def test_every_cash_account_and_journal_kind_has_a_label(db):
    kinds = set(
        db.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'journals_kind_check' "
                "AND conrelid = 'cash.journals'::regclass"
            )
        )
        .split("ARRAY[")[1]
        .replace("'", " ")
        .replace("::text", " ")
        .replace(",", " ")
        .replace("]", " ")
        .replace(")", " ")
        .split()
    )
    assert {"disbursement", "bank_withdrawal"} <= kinds
    for lang, catalog in LANGS.items():
        assert catalog["cash_account"].keys() == set(ACCOUNT_KINDS), lang
        assert kinds <= catalog["journal_kind"].keys(), lang


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_a_run_approving_and_an_advance_cancelled_never_interleave(admin_client, companies, db):
    """The run locks its advances before it reads them, as the cancel does: one waits for the other."""
    import threading

    from app.core.db import new_session

    b = companies["b"]["id"]
    fund_treasury(db, "100")
    office = make_employee(admin_client, b, basic_salary="300.000", payment_method="cash")
    first, _ = month()
    r = admin_client.post(
        "/api/v1/deductions",
        json={"employee_id": office["id"], "source_type": "advance", "reason": "advance", "total": "20",
              "start_month": str(first)},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    payroll_settings(admin_client)
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": b, "month": str(first)}).json()
    done = {}
    with new_session() as cancelling:  # a cancel under way holds the advance
        cancelling.execute(
            text("SELECT id FROM payroll.deductions WHERE public_id = :p FOR UPDATE"), {"p": r.json()["id"]}
        )
        t = threading.Thread(
            target=lambda: done.setdefault(
                "run", admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve").status_code
            )
        )
        t.start()
        t.join(1.5)
        assert t.is_alive() and not done
        cancelling.rollback()
    t.join(15)
    assert done == {"run": 200}
