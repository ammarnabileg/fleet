"""Treasury phase 2, part B: month close. The month's check lists what is left to do, the month closes only when it
is clean, a closed month takes no entry and no cash journal (service and database, every path), and only the latest
closed month reopens."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.conftest import bearer, bind_device, fund_treasury, login, make_driver, make_user
from tests.test_accounting_settings import send, workbook
from tests.test_cash import report
from tests.test_catalog import LANGS
from tests.test_finance import expense, payroll_settings, types
from tests.test_treasury_closing import closed, move

F = "/api/v1/finance"
C = "/api/v1/cash"
THIS = today().replace(day=1)
PREV = add_months(THIS, -1)
PREV2 = add_months(THIS, -2)


def label(m) -> str:
    return f"{m:%Y-%m}"


def end(m):
    return add_months(m, 1) - timedelta(days=1)


def check(client, m) -> dict:
    r = client.get(f"{F}/periods/{label(m)}/check")
    assert r.status_code == 200, r.text
    return {p["code"]: p["params"] for p in r.json()["problems"]}


def close(client, m):
    return client.post(f"{F}/periods/{label(m)}/close")


def manual(client, day, amount="5", approve=True) -> dict:
    accounts = {a["code"]: a["id"] for a in client.get(f"{F}/accounts").json()}
    lines = [{"account_id": accounts["6130"], "debit": amount}, {"account_id": accounts["2110"], "credit": amount}]
    r = client.post(f"{F}/entries/manual", json={"entry_date": str(day), "description": "Rent", "lines": lines})
    assert r.status_code == 201, r.text
    if approve:
        assert client.post(f"{F}/entries/approve", json={"ids": [r.json()["id"]]}).status_code == 200
    return r.json()


def post(client, m):
    r = client.post(f"{F}/entries/post", json={"date_from": str(m), "date_to": str(end(m))})
    assert r.status_code == 200, r.text
    return r.json()


def approve_all(client, m):
    assert client.post(f"{F}/entries/approve", json={"date_from": str(m), "date_to": str(end(m))}).status_code == 200


def test_the_check_lists_what_is_left_and_the_month_closes_when_it_is_clean(
    admin_client, client, companies, db, owner_db
):
    company, other = companies["a"], companies["b"]
    fund_treasury(db, "100")
    # the current month is not over
    assert "month_not_over" in check(admin_client, THIS)
    # an earlier month with entries, still open
    manual(admin_client, PREV2 + timedelta(3))
    # in the month: a draft, an approved expense not entered, a pending one, a cancelled one already entered, a
    # treasury day with movements not counted, a draft payroll run, a pending daily report
    entered = expense(
        admin_client, company["id"], amount="3", payment_method="bank", expense_date=str(PREV + timedelta(2))
    )
    assert admin_client.post(f"{F}/expenses/{entered['id']}/approve", json={}).status_code == 200
    post(admin_client, PREV)
    approve_all(admin_client, PREV)
    r = admin_client.post(f"{F}/expenses/{entered['id']}/cancel", json={"reason": "entered twice"})
    assert r.status_code == 200
    done = expense(
        admin_client, company["id"], amount="4", payment_method="bank", expense_date=str(PREV + timedelta(4))
    )
    assert admin_client.post(f"{F}/expenses/{done['id']}/approve", json={}).status_code == 200
    waiting = expense(
        admin_client, company["id"], amount="2", payment_method="bank", expense_date=str(PREV + timedelta(5))
    )
    manual(admin_client, PREV + timedelta(1), approve=False)
    move(db, "6", PREV + timedelta(6))
    move(db, "1", PREV + timedelta(8))
    payroll_settings(admin_client)
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": other["id"], "month": str(PREV)})
    assert run.status_code == 201, run.text
    d = make_driver(admin_client, company["id"])
    d = d | {"h": bearer(bind_device(client, d["phone"]))}
    rep = report(client, d, cash="0")
    assert rep.status_code == 201, rep.text
    owner_db.execute(
        text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :p"),
        {"d": PREV + timedelta(9), "p": rep.json()["id"]},
    )
    owner_db.commit()

    problems = check(admin_client, PREV)
    assert problems["earlier_month_open"] == {"month": label(PREV2)}
    assert problems["draft_entries"] == {"count": 1}
    assert problems["stale_entries"] == {"count": 1}
    assert problems["documents_not_entered"] == {"count": 3}  # the approved expense and the two cash movements
    assert problems["pending_expenses"] == {"count": 1}
    assert problems["draft_payroll_runs"] == {"count": 1}
    assert problems["pending_daily_reports"] == {"count": 1}
    branch = problems["treasury_days_open"]
    assert (branch["count"], branch["first"]) == (2, str(PREV + timedelta(6)))
    assert "month_not_over" not in problems
    for code in problems:  # each says what to do, in both languages
        assert all(code in cat["period_problem"] for cat in LANGS.values()), code
    r = close(admin_client, PREV)
    assert r.status_code == 422 and r.json()["code"] == "period_not_ready"
    assert r.json()["params"]["count"] == len(problems) and r.json()["params"]["month"] == label(PREV)

    # each fixed: the earlier month closed, the draft approved, the stale one reversed, the rest entered, the
    # pending decided, the treasury days counted, the run approved, the report decided
    assert close(admin_client, PREV2).status_code == 200
    stale = post(admin_client, PREV)["stale"]
    r = admin_client.post(f"{F}/entries/{stale[0]['id']}/reverse", json={"reason": "expense cancelled"})
    assert r.status_code == 200, r.text
    assert admin_client.post(f"{F}/expenses/{waiting['id']}/reject", json={"note": "not ours"}).status_code == 200
    closed(admin_client, PREV + timedelta(6), "106")
    assert check(admin_client, PREV)["treasury_days_open"] == {
        "branch": {"ar": "الفرع الرئيسي", "en": "Main branch"},
        "count": 1,
        "first": str(PREV + timedelta(8)),
    }
    closed(admin_client, PREV + timedelta(8), "107")
    r = admin_client.post(f"/api/v1/payroll/runs/{run.json()['id']}/approve")
    assert r.status_code == 200, r.text
    r = admin_client.post(f"/api/v1/daily-reports/{rep.json()['id']}/reject", json={"reason": "wrong day"})
    assert r.status_code == 200, r.text
    post(admin_client, PREV)
    approve_all(admin_client, PREV)
    assert check(admin_client, PREV) == {}

    r = close(admin_client, PREV)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed" and r.json()["reopenable"] and r.json()["closed_by"]
    months = {p["month"]: p for p in admin_client.get(f"{F}/periods").json()}
    assert months[label(PREV)]["status"] == "closed" and not months[label(PREV2)]["reopenable"]
    assert months[label(THIS)]["status"] == "open"
    r = close(admin_client, PREV)
    assert r.status_code == 409 and r.json()["code"] == "period_closed"


def test_a_closed_month_takes_no_entry_from_any_path(admin_client, company, db, owner_db):
    # what stood in the month before it closed: a draft and an approved entry, an approved expense not entered
    draft = manual(admin_client, PREV + timedelta(1), approve=False)
    standing = manual(admin_client, PREV + timedelta(2))
    late = expense(
        admin_client, company["id"], amount="3", payment_method="bank", expense_date=str(PREV + timedelta(3))
    )
    assert admin_client.post(f"{F}/expenses/{late['id']}/approve", json={}).status_code == 200
    payroll_settings(admin_client)
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": company["id"], "month": str(PREV)}).json()
    owner_db.execute(
        text("INSERT INTO finance.periods (month, status, closed_by, closed_at) VALUES (:m, 'closed', 1, now())"),
        {"m": PREV},
    )
    owner_db.commit()

    def refused(r):
        assert r.status_code == 409 and r.json()["code"] == "period_closed", r.text
        assert r.json()["params"] == {"month": label(PREV)}

    day = str(PREV + timedelta(4))
    accounts = {a["code"]: a["id"] for a in admin_client.get(f"{F}/accounts").json()}
    lines = [{"account_id": accounts["6130"], "debit": "1"}, {"account_id": accounts["2110"], "credit": "1"}]
    refused(
        admin_client.post(f"{F}/entries/manual", json={"entry_date": day, "description": "Accrual", "lines": lines})
    )
    refused(admin_client.post(f"{F}/entries/approve", json={"ids": [draft["id"]]}))
    refused(admin_client.post(f"{F}/entries/{standing['id']}/reverse", json={"reason": "wrong", "entry_date": day}))
    body = {"company_id": company["id"], "type_id": types(admin_client)["other"], "expense_date": day, "amount": "1",
            "payment_method": "bank"}  # fmt: skip
    refused(admin_client.post(f"{F}/expenses", json=body))
    refused(admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve"))
    # the posting skips the closed month: the late expense waits
    r = admin_client.post(f"{F}/entries/post", json={"date_from": str(PREV), "date_to": str(end(PREV))})
    assert r.status_code == 200 and r.json()["created"] == 0
    # a reversal dated today (the default) is fine: today's month is open
    r = admin_client.post(f"{F}/entries/{standing['id']}/reverse", json={"reason": "wrong"})
    assert r.status_code == 200 and r.json()["entry_date"] == str(today())

    # the cash ledger: nothing dated in the month, by the service ...
    from app.core.errors import AppError
    from app.modules.cash import service as cash

    with pytest.raises(AppError) as e:
        move(db, "1", PREV + timedelta(5))
    assert e.value.code == "period_closed"
    db.rollback()
    # ... and by the database, for entries and journals alike
    with pytest.raises(DBAPIError, match="is closed"):
        owner_db.execute(
            text(
                "INSERT INTO finance.entries (entry_date, source_kind, source_ref, description) "
                "VALUES (:d, 'manual', 'MAN-X', 'x')"
            ),
            {"d": day},
        )
    owner_db.rollback()
    with pytest.raises(DBAPIError, match="is closed"):
        owner_db.execute(
            text("UPDATE finance.entries SET status = 'approved', approved_at = now() WHERE public_id = :p"),
            {"p": draft["id"]},
        )
    owner_db.rollback()
    with pytest.raises(DBAPIError, match="is closed"):
        owner_db.execute(
            text(
                "INSERT INTO cash.journals (kind, business_date, source_type, source_id, created_by, reason) "
                "VALUES ('adjustment', :d, 'manual', 1, 1, 'x')"
            ),
            {"d": day},
        )
    owner_db.rollback()
    # a journal written in an open month is fine
    assert cash.account(db, "adjustments")
    move(db, "1", today())


def test_a_pending_journal_of_a_closed_month_is_not_posted(admin_client, client, company, owner_db):
    d = make_driver(admin_client, company["id"])
    d = d | {"h": bearer(bind_device(client, d["phone"]))}
    rep = report(client, d, cash="10", day=today())
    assert rep.status_code == 201, rep.text
    owner_db.execute(
        text("INSERT INTO finance.periods (month, status, closed_by, closed_at) VALUES (:m, 'closed', 1, now())"),
        {"m": THIS},
    )
    owner_db.commit()
    r = admin_client.post(f"/api/v1/daily-reports/{rep.json()['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "period_closed"
    with pytest.raises(DBAPIError, match="is closed"):
        owner_db.execute(text("UPDATE cash.journals SET status = 'posted' WHERE status = 'pending'"))
    owner_db.rollback()


def test_openings_and_imports_need_an_open_month(admin_client, owner_db):
    cur = admin_client.get("/api/v1/settings").json()["finance"]
    start = PREV
    value = cur["value"] | {"books_start_date": str(start)}
    assert (
        admin_client.put("/api/v1/settings/finance", json={"version": cur["version"], "value": value}).status_code
        == 200
    )
    owner_db.execute(
        text("INSERT INTO finance.periods (month, status, closed_by, closed_at) VALUES (:m, 'closed', 1, now())"),
        {"m": add_months(PREV, -1)},
    )
    owner_db.commit()
    accounts = {a["code"]: a["id"] for a in admin_client.get(f"{F}/accounts").json()}
    r = admin_client.post(f"{F}/opening", json={"lines": [{"account_id": accounts["1120"], "debit": "10"}]})
    assert r.status_code == 409 and r.json()["code"] == "period_closed"
    # the old books: the opening (the day before the start) and an entry in a closed month are listed, nothing done
    owner_db.execute(
        text("INSERT INTO finance.periods (month, status, closed_by, closed_at) VALUES (:m, 'closed', 1, now())"),
        {"m": PREV},
    )
    owner_db.commit()
    day = (PREV + timedelta(3)).strftime("%d/%m/%Y")
    data = workbook(
        opening=[("1120", "البنك", 10, None, None)],
        entries=[("A-1", day, "6130", 5, None, "Rent", None), ("A-1", day, "1120", None, 5, None, None)],
    )
    r = send(admin_client, data)
    assert r.status_code == 200, r.text
    assert sorted((e["sheet"], e["code"]) for e in r.json()["errors"]) == [
        ("أرصدة افتتاحية", "period_closed"),
        ("قيود", "period_closed"),
    ]
    assert send(admin_client, data, apply=True).json()["applied"] is False


def test_only_the_latest_closed_month_reopens(admin_client, new_client, company):
    for m in (PREV2, PREV):
        r = close(admin_client, m)
        assert r.status_code == 200, r.text
    r = admin_client.post(f"{F}/periods/{label(PREV2)}/reopen", json={"reason": "late invoice"})
    assert r.status_code == 409 and r.json()["code"] == "period_not_latest"
    r = admin_client.post(f"{F}/periods/{label(THIS)}/reopen", json={"reason": "late invoice"})
    assert r.status_code == 409 and r.json()["code"] == "period_not_latest"
    r = admin_client.post(f"{F}/periods/{label(PREV)}/reopen", json={"reason": "late invoice"})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reopen_reason"]) == ("open", "late invoice")
    months = {p["month"]: p for p in admin_client.get(f"{F}/periods").json()}
    assert months[label(PREV2)]["reopenable"] and not months[label(PREV)]["reopenable"]
    # open again: an entry dated in it is taken
    manual(admin_client, PREV + timedelta(2))
    audit = admin_client.get("/api/v1/audit", params={"entity_type": "period"}).json()
    actions = [a["action"] for a in (audit["items"] if isinstance(audit, dict) else audit)]
    assert {"finance.period.closed", "finance.period.reopened"} <= set(actions)
    r = admin_client.get(f"{F}/periods/2026-13/check")
    assert r.status_code == 422 and r.json()["code"] == "invalid_month"

    # finance.close over every company; the check for any finance reader over every company
    make_user(admin_client, "reader", permissions=["finance.view"])
    make_user(admin_client, "closer_a", permissions=["finance.view", "finance.close"], company_ids=[company["id"]])
    c = new_client()
    login(c, "reader")
    assert c.get(f"{F}/periods/{label(PREV)}/check").status_code == 200
    assert close(c, PREV).status_code == 403
    c = new_client()
    login(c, "closer_a")
    r = close(c, PREV)
    assert r.status_code == 403 and r.json()["code"] == "all_companies_required"
    roles = {r["code"]: r for r in admin_client.get("/api/v1/roles").json()}
    assert "finance.close" in roles["accountant"]["permissions"]
    assert "finance.close" in roles["management"]["permissions"]


def test_every_problem_has_its_text():
    from app.modules.finance.periods import PROBLEMS

    for lang, catalog in LANGS.items():
        assert catalog["period_problem"].keys() == set(PROBLEMS), lang
