"""Treasury phase 2, part A: the branch treasury's daily count and close. The cash counted against the posted balance
at the end of the day, a difference posted on the cash differences account, days closed in order, a closed day taking
no more treasury movement (service and database), the last closing reopened, and the morning alert."""

from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today
from tests.conftest import fund_treasury, login, make_driver, make_employee, make_user, upload
from tests.test_finance import expense, main_branch, month, period
from tests.test_treasury import branch_public_id, journals, treasury

F = "/api/v1/finance"
C = "/api/v1/cash"


def move(db, amount, day, branch_id=None) -> None:
    """A posted treasury movement dated `day` (cash from the opening balances), as if recorded then."""
    from app.modules.cash import service as cash

    if branch_id is None:
        branch_id = db.scalar(text("SELECT id FROM org.branches ORDER BY is_default DESC, id LIMIT 1"))
    amount = D(amount)
    cash._journal(
        db,
        "adjustment",
        source_type="test_move",
        source_id=branch_id,
        lines=[(cash.account(db, "treasury", branch_id=branch_id), amount), (cash.account(db, "opening"), -amount)],
        actor_user_id=1,
        reason="test movement",
        post=True,
        business_date=day,
    )
    db.commit()


def close(client, day, counted, branch=None, **extra):
    branch = branch or branch_public_id(client)
    return client.post(f"{C}/treasury/{branch}/close", json={"day": str(day), "counted": str(counted)} | extra)


def closed(client, day, counted, **extra) -> dict:
    r = close(client, day, counted, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def test_a_shortage_is_posted_and_the_closed_day_takes_no_more_movement(admin_client, company, db):
    fund_treasury(db, "100")
    driver = make_driver(admin_client, company["id"])
    assert admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "20"}).status_code == 201
    status = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/closing").json()
    assert (status["day"], status["book_balance"], status["last_closed_day"]) == (str(today()), "120.000", None)

    # a difference needs its explanation
    r = close(admin_client, today(), "115")
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    c = closed(admin_client, today(), "115", note="5 KD short, cashier to explain")
    assert (c["book_balance"], c["counted"], c["difference"], c["reopenable"]) == ("120.000", "115.000", "-5.000", True)
    assert treasury(admin_client) == D("115.000")  # the screen is the count
    [diff] = journals(db, "count_diff")
    assert (diff.business_date, diff.source_type) == (today(), "treasury_closing")
    assert diff.reason == "5 KD short, cashier to explain"

    # the closed day takes nothing more on the treasury: a receipt, a treasury expense, a bank deposit
    r = admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "1"})
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    assert r.json()["params"] == {"day": str(today())}
    body = {"company_id": company["id"], "type_id": 1, "expense_date": str(today()), "amount": "1",
            "payment_method": "treasury", "branch_id": main_branch(admin_client)}  # fmt: skip
    body["type_id"] = next(t["id"] for t in admin_client.get(f"{F}/expense-types").json() if t["code"] == "fuel")
    r = admin_client.post(f"{F}/expenses", json=body)
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    deposit = {"branch_id": main_branch(admin_client), "amount": "10", "reference": "DEP-1",
               "receipt_sha256": upload(admin_client)}  # fmt: skip
    r = admin_client.post(f"{C}/bank-deposits", json=deposit)
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    # nothing about the driver's own cash: only the treasury is closed
    assert treasury(admin_client) == D("115.000")

    # the movements say which days are closed
    m = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/movements").json()
    assert m["closed_through"] == str(today()) and all(ln["closed"] for ln in m["lines"])
    assert m["lines"][-1]["kind"] == "count_diff" and m["closing"] == "115.000"
    # never reversed on its own
    r = admin_client.post(f"{C}/journals/{diff.public_id}/reverse", json={"reason": "wrong count"})
    assert r.status_code == 409 and r.json()["code"] == "count_diff_from_closing"

    # in the books: Dr cash differences / Cr treasury, on the closed day
    assert admin_client.post(f"{F}/entries/post", json=period()).status_code == 200
    assert admin_client.post(f"{F}/entries/approve", json=period()).status_code == 200
    tb = {b["account"]["code"]: b for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert (tb["4310"]["debit"], tb["4310"]["credit"]) == ("5.000", "0.000")
    assert (tb["1110"]["debit"], tb["1110"]["credit"]) == ("20.000", "5.000")

    # reopened: the difference reversed on the same day, the day open again
    r = admin_client.post(f"{C}/treasury/closings/{c['id']}/reopen", json={"reason": "recounted: it was there"})
    assert r.status_code == 200, r.text
    assert r.json()["reopened_at"] and r.json()["reopen_reason"] == "recounted: it was there"
    assert treasury(admin_client) == D("120.000")
    [back] = journals(db, "reversal")
    assert (back.reverses_id, back.business_date) == (diff.id, today())
    assert admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "1"}).status_code == 201
    admin_client.post(f"{F}/entries/post", json=period())
    admin_client.post(f"{F}/entries/approve", json=period())
    tb = {b["account"]["code"]: b["closing"] for b in admin_client.get(f"{F}/trial-balance", params=period()).json()}
    assert tb["4310"] == "0.000" and tb["1110"] == "21.000"  # this month's: the receipts only
    # the list keeps it, reopened
    lst = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/closings").json()
    assert lst["last_closed_day"] is None and [x["reopened_at"] is not None for x in lst["lines"]] == [True]


def test_a_surplus_goes_to_the_cash_differences_too(admin_client, db):
    move(db, "40", today() - timedelta(1))
    c = closed(admin_client, today() - timedelta(1), "42.5", note="found in the drawer")
    assert c["difference"] == "2.500" and treasury(admin_client) == D("42.500")
    first, _ = month()
    if first <= today() - timedelta(1):
        admin_client.post(f"{F}/entries/post", json=period())
        entries = admin_client.get(f"{F}/entries", params=period() | {"source_kind": "cash_journal"}).json()
        [e] = [x for x in entries if x["entry_date"] == str(today() - timedelta(1)) and x["amount"] == "2.500"]
        lines = admin_client.get(f"{F}/entries/{e['id']}").json()["lines"]
        assert [(ln["account"]["code"], ln["debit"], ln["credit"]) for ln in lines] == [
            ("1110", "2.500", "0.000"),
            ("4310", "0.000", "2.500"),
        ]


def test_days_are_closed_in_order_against_their_own_balance(admin_client, db):
    d5, d3, d1 = (today() - timedelta(n) for n in (5, 3, 1))
    move(db, "10", d5)
    move(db, "7", d3)
    move(db, "-2", d1)
    # the first closing starts the series: any day
    c5 = closed(admin_client, d5, "10")
    assert (c5["book_balance"], c5["difference"], c5["journal_id"]) == ("10.000", "0.000", None)
    r = close(admin_client, d1, "15")
    assert r.status_code == 409 and r.json()["code"] == "treasury_close_order"
    assert r.json()["params"] == {"day": str(d3)}
    status = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/closing").json()
    assert (status["next_day"], status["day"], status["book_balance"]) == (str(d3), str(d3), "17.000")
    assert status["open_days"] == [str(d3), str(d1)]
    c3 = closed(admin_client, d3, "17")
    assert c3["book_balance"] == "17.000"
    # a closed day, or one before the last closing, again: refused; the future too
    for day in (d3, d5, today() - timedelta(4)):
        r = close(admin_client, day, "17")
        assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed", day
    r = close(admin_client, today() + timedelta(1), "15")
    assert r.status_code == 422 and r.json()["code"] == "treasury_close_future"
    # a day without movements may be skipped
    c1 = closed(admin_client, d1, "15")
    assert c1["book_balance"] == "15.000"
    status = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/closing").json()
    assert (status["last_closed_day"], status["next_day"]) == (str(d1), str(today()))

    # only the last closing reopens
    r = admin_client.post(f"{C}/treasury/closings/{c3['id']}/reopen", json={"reason": "a wrong count"})
    assert r.status_code == 409 and r.json()["code"] == "treasury_closing_not_last"
    assert admin_client.post(f"{C}/treasury/closings/{c1['id']}/reopen", json={"reason": "wrong"}).status_code == 200
    r = admin_client.post(f"{C}/treasury/closings/{c1['id']}/reopen", json={"reason": "wrong"})
    assert r.status_code == 409 and r.json()["code"] == "treasury_closing_not_last"
    lst = admin_client.get(f"{C}/treasury/{branch_public_id(admin_client)}/closings").json()
    assert lst["last_closed_day"] == str(d3)
    assert [(x["day"], x["reopenable"]) for x in lst["lines"]] == [(str(d1), False), (str(d3), True), (str(d5), False)]
    # d1 open again: a movement dated in it is taken, then d1 closes on its new balance
    move(db, "1", d1)
    assert closed(admin_client, d1, "16")["book_balance"] == "16.000"


def test_the_notes_and_coins_add_up_to_the_count(admin_client, db):
    move(db, "41.01", today())
    coins = {"20": 2, "0.250": 4, "0.005": 2}  # 40 + 1 + 0.010
    r = close(admin_client, today(), "41", denominations=coins, note="x")
    assert r.status_code == 422 and r.json()["code"] == "denominations_mismatch"
    assert r.json()["params"] == {"total": "41.010", "counted": "41.000"}
    r = close(admin_client, today(), "1", denominations={"3": 1}, note="x")
    assert r.status_code == 422 and r.json()["code"] == "denomination_unknown"
    r = close(admin_client, today(), "-1")
    assert r.status_code == 422
    c = closed(admin_client, today(), "41.010", denominations=coins | {"10": 0})
    assert c["denominations"] == {"20": 2, "0.25": 4, "0.005": 2} and c["difference"] == "0.000"


def test_every_treasury_path_respects_a_closed_day(admin_client, company, db):
    fund_treasury(db, "500")
    branch = main_branch(admin_client)
    yesterday = today() - timedelta(1)
    # a treasury expense dated yesterday entered before the close, approved after: refused at approval
    pending = expense(admin_client, company["id"], amount="3", expense_date=str(yesterday))
    payable = expense(admin_client, company["id"], amount="4", payment_method="payable")
    assert admin_client.post(f"{F}/expenses/{payable['id']}/approve", json={}).status_code == 200
    closed(admin_client, yesterday, "500")
    r = admin_client.post(f"{F}/expenses/{pending['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    assert admin_client.get(f"{F}/expenses/{pending['id']}").json()["status"] == "pending"
    # today is open: money out today goes through
    today_e = expense(admin_client, company["id"], amount="5")
    assert admin_client.post(f"{F}/expenses/{today_e['id']}/approve", json={}).status_code == 200
    closed(admin_client, today(), "495")
    # today closed: paying a payable from the treasury, an advance, a withdrawal, cancelling a treasury expense
    r = admin_client.post(f"{F}/expenses/{payable['id']}/pay", json={"paid_from": "treasury", "branch_id": branch})
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    advance = {"employee_id": office["id"], "source_type": "advance", "reason": "advance", "total": "4"}
    r = admin_client.post("/api/v1/deductions", json=advance)
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    wd = {"branch_id": branch, "amount": "1", "reference": "WD-1", "attachment_sha256": upload(admin_client)}
    r = admin_client.post(f"{C}/bank-withdrawals", json=wd)
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    r = admin_client.post(f"{F}/expenses/{today_e['id']}/cancel", json={"reason": "entered twice"})
    assert r.status_code == 409 and r.json()["code"] == "treasury_day_closed"
    assert treasury(admin_client) == D("495.000")
    # the bank alone is not the treasury: paying from the bank still works
    assert admin_client.post(f"{F}/expenses/{payable['id']}/pay", json={"paid_from": "bank"}).status_code == 200


def test_the_database_refuses_a_movement_in_a_closed_day(admin_client, db, owner_db):
    move(db, "10", today() - timedelta(2))
    c = closed(admin_client, today() - timedelta(1), "10")
    treasury_id = owner_db.scalar(text("SELECT id FROM cash.accounts WHERE kind = 'treasury' LIMIT 1"))
    opening_id = owner_db.scalar(text("SELECT id FROM cash.accounts WHERE kind = 'opening' LIMIT 1"))

    def post_directly(day):
        j = owner_db.scalar(
            text(
                "INSERT INTO cash.journals (kind, business_date, source_type, source_id, created_by, reason) "
                "VALUES ('adjustment', :d, 'manual', 1, 1, 'direct') RETURNING id"
            ),
            {"d": day},
        )
        owner_db.execute(
            text("INSERT INTO cash.journal_lines (journal_id, account_id, amount) VALUES (:j, :t, 1), (:j, :o, -1)"),
            {"j": j, "t": treasury_id, "o": opening_id},
        )
        owner_db.execute(text("UPDATE cash.journals SET status = 'posted' WHERE id = :j"), {"j": j})

    with pytest.raises(DBAPIError, match="is closed"):
        post_directly(today() - timedelta(3))  # before the last closing, though not itself closed
    owner_db.rollback()
    post_directly(today())  # after it: fine
    owner_db.rollback()
    # a closing never changes, except reopened once; never deleted
    with pytest.raises(DBAPIError, match="only changes when it is reopened"):
        owner_db.execute(text("UPDATE cash.treasury_closings SET counted = 11 WHERE public_id = :p"), {"p": c["id"]})
    owner_db.rollback()
    with pytest.raises(DBAPIError, match="never deleted"):
        owner_db.execute(text("DELETE FROM cash.treasury_closings WHERE public_id = :p"), {"p": c["id"]})
    owner_db.rollback()


def test_closing_needs_treasury_manage_over_every_company(admin_client, new_client, company, db):
    move(db, "5", today())
    make_user(admin_client, "viewer", permissions=["treasury.view"])
    make_user(admin_client, "limited", permissions=["treasury.view", "treasury.manage"], company_ids=[company["id"]])
    branch = branch_public_id(admin_client)
    for user, code in (("viewer", "permission_denied"), ("limited", "company_out_of_scope")):
        c = new_client()
        login(c, user)
        r = close(c, today(), "5", branch=branch)
        assert r.status_code == 403 and r.json()["code"] == code, user
        if user == "limited":
            assert c.get(f"{C}/treasury/{branch}/closings").status_code == 403
            assert c.get(f"{C}/treasury/{branch}/closing").status_code == 403
    c = new_client()
    login(c, "viewer")
    assert c.get(f"{C}/treasury/{branch}/closings").status_code == 200
    done = closed(admin_client, today(), "5")
    r = c.post(f"{C}/treasury/closings/{done['id']}/reopen", json={"reason": "wrong count"})
    assert r.status_code == 403
    missing = admin_client.post(
        f"{C}/treasury/closings/00000000-0000-0000-0000-000000000000/reopen", json={"reason": "wrong count"}
    )
    assert missing.status_code == 404 and missing.json()["code"] == "treasury_closing_not_found"


def test_the_morning_alert_for_a_day_not_closed(admin_client, db):
    from app.modules.cash import tasks
    from tests.test_accounting_settings import alerts

    yesterday = today() - timedelta(1)
    tasks.scan_treasury("morning")
    assert alerts(admin_client, "treasury_not_closed") == []  # no movement yesterday
    move(db, "8", yesterday)
    tasks.scan_treasury("morning")
    [a] = alerts(admin_client, "treasury_not_closed")
    assert a["entity_type"] == "branch" and a["params"]["day"] == str(yesterday)
    tasks.scan_treasury("morning")
    assert len(alerts(admin_client, "treasury_not_closed")) == 1
    closed(admin_client, yesterday, "8")
    assert alerts(admin_client, "treasury_not_closed") == []
    tasks.scan_treasury("morning")
    assert alerts(admin_client, "treasury_not_closed") == []
