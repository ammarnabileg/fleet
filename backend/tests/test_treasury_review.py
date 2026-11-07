"""Treasury phase 2 review fixes: a document of a closed month that changed later is entered in the first open month
(never skipped silently); the month's check sees pending cash journals and change requests; a deduction approved
after its day closed enters the books and leaves the treasury on the approval day; the lock order (month, then
treasury, then bank, then custody); petty expenses decided by an all-companies user; no custody before its role."""

import threading
from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.core.clock import today
from tests import test_approvals
from tests.conftest import bearer, bind_device, fund_treasury, login, make_driver, make_employee, make_user, upload
from tests.test_approvals import configure, step
from tests.test_cash import approve as approve_report
from tests.test_cash import report
from tests.test_catalog import LANGS
from tests.test_finance import main_branch, payroll_settings
from tests.test_more_approvals import waiting
from tests.test_periods import PREV, PREV2, THIS, check, close, end, label
from tests.test_petty_cash import fund, holders, petty_expense
from tests.test_treasury import journals
from tests.test_treasury_closing import closed

F = "/api/v1/finance"
C = "/api/v1/cash"


def close_directly(owner_db, month) -> None:
    owner_db.execute(
        text("INSERT INTO finance.periods (month, status, closed_by, closed_at) VALUES (:m, 'closed', 1, now())"),
        {"m": month},
    )
    owner_db.commit()


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_a_closed_months_document_that_changed_is_entered_in_the_first_open_month(admin_client, companies, owner_db):
    """A deduction of 60 made last month, payroll took 30, the month closed, then the deduction is cancelled: its
    entry (60) is reversed today and its new figure (30) is entered on the first day of this month."""
    b = companies["b"]["id"]
    office = make_employee(admin_client, b, basic_salary="300.000", payment_method="cash", hire_date=str(PREV2))
    body = {"employee_id": office["id"], "source_type": "other", "reason": "damage", "total": "60",
            "installments": 2}  # fmt: skip
    r = admin_client.post("/api/v1/deductions", json=body)
    assert r.status_code == 201, r.text
    deduction = r.json()
    owner_db.execute(
        text("UPDATE payroll.deductions SET created_at = :t, start_month = :m WHERE public_id = :p"),
        {"t": f"{PREV + timedelta(4)}T09:00:00+03:00", "m": PREV, "p": deduction["id"]},
    )
    owner_db.commit()
    payroll_settings(admin_client)
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": b, "month": str(PREV)}).json()
    r = admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve")
    assert r.status_code == 200, r.text
    span = {"date_from": str(PREV), "date_to": str(end(PREV))}
    assert admin_client.post(f"{F}/entries/post", json=span).json()["errors"] == []
    admin_client.post(f"{F}/entries/approve", json=span)
    r = close(admin_client, PREV)
    assert r.status_code == 200, r.text

    r = admin_client.post(f"/api/v1/deductions/{deduction['id']}/cancel", json={"reason": "forgiven in part"})
    assert r.status_code == 200, r.text
    stale = admin_client.post(f"{F}/entries/post", json=span).json()["stale"]
    assert [(s["entered"], s["document"]) for s in stale] == [("60.000", "30.000")]
    assert admin_client.post(f"{F}/entries/{stale[0]['id']}/reverse", json={"reason": "cancelled"}).status_code == 200

    # everything up to now closed: it cannot be entered, and the posting says so
    close_directly(owner_db, THIS)
    result = admin_client.post(f"{F}/entries/post", json=span).json()
    assert result["created"] == 0
    assert [(e["code"], e["params"]) for e in result["errors"]] == [("period_closed", {"month": label(PREV)})]
    owner_db.execute(text("DELETE FROM finance.periods WHERE month = :m"), {"m": THIS})
    owner_db.commit()
    # this month open: entered on its first day, saying which day it is for
    result = admin_client.post(f"{F}/entries/post", json=span).json()
    assert (result["created"], result["errors"]) == (1, [])
    made = admin_client.get(
        f"{F}/entries", params={"date_from": str(THIS), "date_to": str(end(THIS)), "source_kind": "deduction"}
    ).json()
    [entry] = [e for e in made if e["amount"] == "30.000"]
    assert entry["entry_date"] == str(THIS) and f"(عن {PREV + timedelta(4)})" in entry["description"]
    assert admin_client.post(f"{F}/entries/post", json=span).json() == {
        "created": 0, "by_kind": {}, "stale": [], "errors": []
    }  # fmt: skip
    admin_client.post(f"{F}/entries/approve", json={"ids": [entry["id"]]})
    tb = admin_client.get(f"{F}/trial-balance", params={"date_from": str(PREV), "date_to": str(end(THIS))}).json()
    closing = {x["account"]["code"]: x["closing"] for x in tb}
    assert closing["4290"] == "-30.000"  # what the employee owes for it: 30, as the deduction says now
    assert sum(D(x["closing"]) for x in tb) == 0


def test_the_month_check_sees_pending_cash_journals_and_change_requests(admin_client, client, company, db, owner_db):
    from app.modules.cash import service as cash

    d = make_driver(admin_client, company["id"])
    d = d | {"h": bearer(bind_device(client, d["phone"]))}
    # an adjustment waiting for its workflow, dated in the month
    cash._journal(
        db,
        "adjustment",
        source_type="manual",
        source_id=1,
        lines=[(cash.account(db, "driver", driver_id=1), D("5")), (cash.account(db, "adjustments"), D("-5"))],
        actor_user_id=1,
        reason="waits",
        business_date=PREV + timedelta(2),
    )
    db.commit()
    # an approved report of the month with a change asked for
    rid = report(client, d, cash="20", orders=10).json()["id"]
    assert approve_report(admin_client, rid).status_code == 200
    r = client.post(
        f"/api/v1/driver/reports/{rid}/change-request", json={"cash_amount": "22", "reason": "late order"},
        headers=d["h"],
    )  # fmt: skip
    assert r.status_code == 201, r.text
    owner_db.execute(
        text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :p"),
        {"d": PREV + timedelta(3), "p": rid},
    )
    owner_db.commit()
    problems = check(admin_client, PREV)
    assert problems["pending_cash_journals"] == {"count": 1}
    assert problems["pending_report_changes"] == {"count": 1}
    for code in ("pending_cash_journals", "pending_report_changes"):
        assert all(code in cat["period_problem"] for cat in LANGS.values())


@pytest.fixture
def approvers(admin_client, new_client):
    return test_approvals.people.__wrapped__(admin_client, new_client)


def test_a_deduction_approved_after_its_day_closed_takes_the_approval_day(
    admin_client, company, approvers, db, owner_db
):
    fund_treasury(db, "100")
    office = make_employee(admin_client, company["id"], basic_salary="300.000", payment_method="cash")
    configure(admin_client, "manual_deduction", [step("المحاسب", role="accountant")])
    acc = approvers["acc1"]["c"]

    def ask(source, total):
        body = {"employee_id": office["id"], "source_type": source, "reason": source, "total": total}
        r = admin_client.post("/api/v1/deductions", json=body)
        assert r.status_code == 201 and r.json()["status"] == "pending", r.text
        return r.json()

    yesterday = today() - timedelta(1)
    advance, other = ask("advance", "20"), ask("other", "7")
    owner_db.execute(
        text("UPDATE payroll.deductions SET created_at = :t WHERE public_id = :p"),
        {"t": f"{yesterday}T10:00:00+03:00", "p": advance["id"]},
    )
    owner_db.execute(
        text("UPDATE payroll.deductions SET created_at = :t WHERE public_id = :p"),
        {"t": f"{PREV + timedelta(5)}T10:00:00+03:00", "p": other["id"]},
    )
    owner_db.commit()
    closed(admin_client, yesterday, "100")  # the advance's request day counted and closed
    close_directly(owner_db, PREV)  # the other's month closed
    # approved anyway: out of the treasury today, and in the books today
    r = test_approvals.decide(acc, waiting(acc, "manual_deduction", "20.000"))
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    r = test_approvals.decide(acc, waiting(acc, "manual_deduction", "7.000"))
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    [out] = journals(db, "disbursement")
    assert out.business_date == today()
    span = {"date_from": str(THIS), "date_to": str(end(THIS))}
    assert admin_client.post(f"{F}/entries/post", json=span).json()["errors"] == []
    dated = admin_client.get(f"{F}/entries", params=span | {"source_kind": "deduction"}).json()
    assert sorted((e["amount"], e["entry_date"]) for e in dated) == [("20.000", str(today())), ("7.000", str(today()))]
    # an expense dated in the closed day is refused with what to do: record it with today's date
    assert "بتاريخ اليوم" in LANGS["ar"]["errors"]["treasury_day_closed"]
    assert "today's date" in LANGS["en"]["errors"]["treasury_day_closed"]


def test_the_month_is_locked_before_the_treasury(admin_client, company, database_url):
    """A deposit waiting on the treasury's lock already holds the month's: a close can never take the month while a
    writer holds the treasury and waits for the month (no deadlock)."""
    from sqlalchemy import create_engine

    from app.core.db import new_session
    from app.modules.cash import service as cash

    driver = make_driver(admin_client, company["id"])
    admin_client.post(f"{C}/receipts", json={"driver_id": driver["id"], "amount": "10"})
    branch = main_branch(admin_client)
    photo = upload(admin_client)
    done = {}
    key = f"finance.period:{label(THIS)}"
    engine = create_engine(database_url["url"])
    with new_session() as holder, engine.connect() as probe:
        cash.lock_branches(holder, treasury=[branch])
        t = threading.Thread(
            target=lambda: done.setdefault(
                "deposit",
                admin_client.post(
                    f"{C}/bank-deposits",
                    json={"branch_id": branch, "amount": "10", "reference": "DEP-L", "receipt_sha256": photo},
                ).status_code,
            )
        )
        t.start()
        t.join(1.5)
        assert t.is_alive()  # waiting on the treasury ...
        # ... holding the month (shared): an exclusive take of it fails
        assert probe.scalar(text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": key}) is False
        holder.rollback()
    t.join(10)
    engine.dispose()
    assert done == {"deposit": 201}


def test_a_month_not_over_is_refused_without_waiting_for_its_lock(admin_client, database_url):
    from sqlalchemy import create_engine

    engine = create_engine(database_url["url"])
    done = {}
    with engine.connect() as closer:  # a close of this month under way
        closer.execute(text("SELECT pg_advisory_lock(hashtextextended(:k, 0))"), {"k": f"finance.period:{label(THIS)}"})
        t = threading.Thread(target=lambda: done.setdefault("r", close(admin_client, THIS)))
        t.start()
        t.join(5)
        closer.execute(text("SELECT pg_advisory_unlock_all()"))
    t.join(5)
    engine.dispose()
    assert done["r"].status_code == 422 and done["r"].json()["params"]["problems"][0]["code"] == "month_not_over"


def test_a_petty_expense_is_decided_by_an_all_companies_user(admin_client, new_client, company, db):
    fund_treasury(db, "100")
    holder = make_employee(admin_client, company["id"])
    assert fund(admin_client, holder, "20").status_code == 201
    e = petty_expense(admin_client, company["id"], holder, "5").json()
    make_user(admin_client, "boss_a", permissions=["finance.view", "finance.create", "finance.approve"],
              company_ids=[company["id"]])  # fmt: skip
    c = new_client()
    login(c, "boss_a")
    for verb, body in (("approve", {}), ("cancel", {"reason": "not ours"})):
        r = c.post(f"{F}/expenses/{e['id']}/{verb}", json=body)
        assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope", verb
    assert admin_client.post(f"{F}/expenses/{e['id']}/approve", json={}).status_code == 200
    r = c.post(f"{F}/expenses/{e['id']}/cancel", json={"reason": "not ours"})
    assert r.status_code == 403
    assert holders(admin_client)[holder["id"]]["balance"] == "15.000"


def test_no_custody_while_its_role_has_no_account(admin_client, company, db, owner_db):
    fund_treasury(db, "100")
    holder = make_employee(admin_client, company["id"])
    assert admin_client.get(f"{C}/petty/status").json() == {"role_ready": True}
    assert fund(admin_client, holder, "20").status_code == 201
    owner_db.execute(text("DELETE FROM finance.account_roles WHERE role = 'petty_cash'"))
    owner_db.commit()
    assert admin_client.get(f"{C}/petty/status").json() == {"role_ready": False}
    r = fund(admin_client, holder, "5")
    assert r.status_code == 422 and r.json()["code"] == "petty_role_missing"
    r = petty_expense(admin_client, company["id"], holder, "5")
    assert r.status_code == 422 and r.json()["code"] == "petty_role_missing"
    assert holders(admin_client)[holder["id"]]["balance"] == "20.000"  # nothing moved
    # what it holds can still come back to the treasury
    r = admin_client.post(
        f"{C}/petty/{holder['id']}/return", json={"branch_id": main_branch(admin_client), "amount": "20"}
    )
    assert r.status_code == 201, r.text
