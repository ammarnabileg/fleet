"""M2: daily reports and the cash ledger. The spec's ledger scenarios (T-LED-01..13, appendix E) and the BRD
acceptance scenarios UAT-01..06, through the API; the database guards straight in SQL (they hold for everyone)."""

from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.clock import today
from tests.conftest import bearer, bind_device, jpeg, login, make_driver, make_user


@pytest.fixture
def driver(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    return d | {"h": bearer(bind_device(client, d["phone"]))}


def shot(client, h):
    r = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    )
    return r.json()["sha256"]


def report(client, d, *, cash, orders=25, day=None, **extra):
    body = {
        "business_date": str(day or today()),
        "orders_count": orders,
        "cash_amount": str(cash),
        "screenshot_sha256": shot(client, d["h"]),
    } | extra
    return client.post("/api/v1/driver/reports", json=body, headers=d["h"])


def cash_of(client, d):
    c = client.get("/api/v1/driver/cash", headers=d["h"]).json()
    return D(c["posted"]), D(c["pending"])


def approve(admin_client, rid, **body):
    return admin_client.post(f"/api/v1/daily-reports/{rid}/approve", json=body)


@pytest.fixture
def earlier(admin_client, client, driver):
    """Earlier days already approved: 81.500 posted (the spec's starting point)."""
    r = report(client, driver, cash="81.500", day=today() - timedelta(days=1))
    assert approve(admin_client, r.json()["id"]).status_code == 200
    return driver


def test_uat01_a_report_needs_its_date_and_screenshot(client, driver):
    r = client.post("/api/v1/driver/reports", json={"orders_count": 3, "cash_amount": "1"}, headers=driver["h"])
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    r = client.post(
        "/api/v1/driver/reports",
        headers=driver["h"],
        json={"business_date": str(today()), "orders_count": 3, "cash_amount": "1"},
    )
    assert r.status_code == 422 and r.json()["code"] == "field_required"
    r = report(client, driver, cash="1", day=today() - timedelta(days=5))
    assert r.status_code == 422 and r.json()["code"] == "invalid_business_date"


def test_the_screenshot_must_be_an_image_from_this_phone(admin_client, client, driver, company):
    other = make_driver(admin_client, company["id"])
    other_h = bearer(bind_device(client, other["phone"]))
    foreign = shot(client, other_h)
    r = report(client, driver, cash="1", screenshot_sha256=foreign)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    pdf = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=driver["h"],
        files={"file": ("s.pdf", b"%PDF-1.4 x", "application/pdf")},
    ).json()["sha256"]
    r = report(client, driver, cash="1", screenshot_sha256=pdf)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"


def test_uat02_tled01_a_report_is_unapproved_cash_until_reviewed(client, earlier):
    r = report(client, earlier, cash="40.500")
    assert r.status_code == 201 and r.json()["status"] == "submitted"
    assert cash_of(client, earlier) == (D("81.500"), D("40.500"))


def test_uat03_tled02_a_correction_posts_an_adjustment_with_its_reason(admin_client, client, earlier, db):
    rid = report(client, earlier, cash="40.500").json()["id"]
    r = approve(admin_client, rid, cash_amount="38.500")
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    r = approve(admin_client, rid, cash_amount="38.500", reason="cash recount: 38.500")
    assert r.status_code == 200 and D(r.json()["approved_cash"]) == D("38.500")
    assert cash_of(client, earlier) == (D("120.000"), D("0"))
    statement = admin_client.get(f"/api/v1/cash/drivers/{earlier['id']}/statement").json()
    adjustment = next(x for x in statement["lines"] if x["kind"] == "adjustment")
    assert D(adjustment["amount"]) == D("-2.000") and adjustment["reason"] == "cash recount: 38.500"


def test_tled03_deciding_twice_changes_nothing(admin_client, client, driver, db):
    from app.modules.cash import service as cash

    rid = report(client, driver, cash="10").json()["id"]
    assert approve(admin_client, rid).status_code == 200
    assert approve(admin_client, rid).json()["code"] == "report_not_submitted"
    posted = db.execute(text("SELECT id FROM cash.journals WHERE status = 'posted'")).scalar()
    assert cash._decide(db, posted, "posted", 1) is False  # a conditional update: the second decision is a no-op
    db.rollback()
    with pytest.raises(DBAPIError, match="only a pending journal"):
        db.execute(text("UPDATE cash.journals SET status = 'rejected' WHERE status = 'posted'"))
    db.rollback()


def test_uat04_tled04_one_report_per_driver_and_day(client, driver, db):
    assert report(client, driver, cash="5").status_code == 201
    r = report(client, driver, cash="6")
    assert r.status_code == 409 and r.json()["code"] == "report_exists"
    rid = db.execute(text("SELECT source_id FROM cash.journals WHERE kind = 'collection'")).scalar()
    with pytest.raises(IntegrityError, match="journals_one_per_source"):
        db.execute(
            text(
                "INSERT INTO cash.journals (kind, business_date, source_type, source_id, created_by) "
                "VALUES ('collection', current_date, 'daily_report', :r, 1)"
            ),
            {"r": rid},
        )
    db.rollback()


def test_tled05_a_rejected_report_can_be_sent_again(admin_client, client, earlier):
    rid = report(client, earlier, cash="10").json()["id"]
    r = admin_client.post(f"/api/v1/daily-reports/{rid}/reject", json={"reason": "wrong screenshot"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert cash_of(client, earlier) == (D("81.500"), D("0"))
    assert report(client, earlier, cash="9").status_code == 201
    assert cash_of(client, earlier) == (D("81.500"), D("9.000"))
    mine = client.get("/api/v1/driver/reports", headers=earlier["h"]).json()
    assert [x["status"] for x in mine][:2] == ["submitted", "rejected"]


def test_uat06_tled06_above_the_limit_alerts_and_never_blocks(admin_client, client, earlier):
    r = report(client, earlier, cash="40.500")  # 81.500 + 40.500 = 122.000 > 80.000
    assert r.status_code == 201
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
    assert [a["kind"] for a in alerts] == ["cash_balance_high"] and "122.000" in alerts[0]["message"]
    balances = admin_client.get("/api/v1/cash/balances").json()
    assert balances[0]["over_limit"] and D(balances[0]["total"]) == D("122.000")


def test_uat05_tled07_tled09_a_numbered_receipt_at_the_cashier(admin_client, client, earlier, db):
    rid = report(client, earlier, cash="38.500").json()["id"]
    approve(admin_client, rid)  # 120.000 posted
    r = admin_client.post("/api/v1/cash/receipts", json={"driver_id": earlier["id"], "amount": "50"})
    assert r.status_code == 201 and r.json()["receipt_no"] == 1
    assert cash_of(client, earlier) == (D("70.000"), D("0"))
    second = admin_client.post("/api/v1/cash/receipts", json={"driver_id": earlier["id"], "amount": "5"}).json()
    assert second["receipt_no"] == 2
    treasury = admin_client.get("/api/v1/cash/treasury").json()[0]
    assert D(treasury["treasury"]) == D("55.000")
    mine = client.get("/api/v1/driver/cash", headers=earlier["h"]).json()["receipts"]
    assert [x["receipt_no"] for x in mine] == [2, 1] and mine[0]["driver_confirmed_at"] is None
    ok = client.post(f"/api/v1/driver/cash/receipts/{mine[0]['id']}/confirm", headers=earlier["h"])
    assert ok.status_code == 200 and ok.json()["driver_confirmed_at"]
    with pytest.raises(IntegrityError, match="receipts_branch_id_receipt_no_key"):
        db.execute(
            text(
                "INSERT INTO cash.receipts (branch_id, receipt_no, driver_id, amount, created_by) "
                "SELECT branch_id, 1, driver_id, 1, 1 FROM cash.receipts LIMIT 1"
            )
        )
    db.rollback()


def test_tled08_tled10_the_database_guards_hold_for_everyone(admin_client, client, driver, db):
    rid = report(client, driver, cash="12").json()["id"]
    approve(admin_client, rid)
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": driver["id"], "amount": "2"})
    posted = db.execute(text("SELECT id FROM cash.journals WHERE kind = 'collection'")).scalar()
    deposit_source = db.execute(text("SELECT source_id FROM cash.journals WHERE kind = 'deposit'")).scalar()
    accounts = db.execute(text("SELECT id FROM cash.accounts ORDER BY id LIMIT 2")).scalars().all()

    def fails(sql, needle, **params):
        with pytest.raises((DBAPIError, IntegrityError), match=needle):
            db.execute(text(sql), params)
            db.commit()
        db.rollback()

    fails(
        "INSERT INTO cash.journals (kind, business_date, source_type, source_id, created_by) "
        "VALUES ('deposit', current_date, 'receipt', :s, 1)",
        "journals_one_per_source",
        s=deposit_source,
    )  # T-LED-08
    fails(
        "WITH j AS (INSERT INTO cash.journals (kind, business_date, source_type, source_id, reason, created_by) "
        "VALUES ('adjustment', current_date, 'manual', 1, 'typo', 1) RETURNING id) "
        "INSERT INTO cash.journal_lines SELECT j.id, :a, 5 FROM j",
        "does not balance",
        a=accounts[0],
    )  # 10a
    fails("UPDATE cash.journal_lines SET amount = 1 WHERE journal_id = :j", "immutable", j=posted)  # 10b
    fails("DELETE FROM cash.journals WHERE id = :j", "append-only", j=posted)  # 10c
    fails("INSERT INTO cash.journal_lines VALUES (:j, :a, 1)", "pending journal", j=posted, a=accounts[1])  # 10d
    jid = db.execute(  # 10e
        text(
            "INSERT INTO cash.journals (kind, business_date, source_type, source_id, created_by) "
            "VALUES ('deposit', current_date, 'receipt', 778, 1) RETURNING id"
        )
    ).scalar()
    with pytest.raises(DBAPIError, match="cannot be posted"):
        db.execute(text("UPDATE cash.journals SET status = 'posted' WHERE id = :j"), {"j": jid})
    db.rollback()


def test_tled11_a_reversal_restores_the_balance_once(admin_client, client, earlier, db):
    rid = report(client, earlier, cash="12").json()["id"]
    approve(admin_client, rid)
    assert cash_of(client, earlier)[0] == D("93.500")
    journal = db.execute(
        text(
            "SELECT public_id FROM cash.journals j WHERE kind = 'collection' AND source_id = "
            "(SELECT id FROM daily_ops.reports WHERE public_id = :r)"
        ),
        {"r": rid},
    ).scalar()
    r = admin_client.post(f"/api/v1/cash/journals/{journal}/reverse", json={"reason": "report entered twice"})
    assert r.status_code == 201 and r.json()["kind"] == "reversal"
    assert cash_of(client, earlier)[0] == D("81.500")
    again = admin_client.post(f"/api/v1/cash/journals/{journal}/reverse", json={"reason": "again"})
    assert again.status_code == 409 and again.json()["code"] == "journal_exists"


def test_tled13_invariants_and_treasury_to_bank(admin_client, client, earlier, db):
    from app.modules.cash import service as cash

    admin_client.post("/api/v1/cash/receipts", json={"driver_id": earlier["id"], "amount": "60"})
    branch = admin_client.get("/api/v1/cash/treasury").json()[0]["branch"]["id"]
    r = admin_client.post(
        "/api/v1/cash/bank-deposits", json={"branch_id": branch, "amount": "70", "reference": "NBK-1"}
    )
    assert r.status_code == 422 and r.json()["code"] == "treasury_insufficient"
    r = admin_client.post(
        "/api/v1/cash/bank-deposits", json={"branch_id": branch, "amount": "50", "reference": "NBK-1"}
    )
    assert r.status_code == 201
    row = admin_client.get("/api/v1/cash/treasury").json()[0]
    assert (D(row["treasury"]), D(row["bank"]), D(row["cod_clearing"])) == (D("10.000"), D("50.000"), D("-81.500"))
    total = db.execute(
        text(
            "SELECT sum(l.amount) FROM cash.journal_lines l JOIN cash.journals j ON j.id = l.journal_id "
            "WHERE j.status = 'posted'"
        )
    ).scalar()
    assert total == 0 and cash.check_invariants(db) == []


def test_manual_adjustment_and_review_overdue(admin_client, client, driver, db):
    from app.modules.daily_ops import service as daily

    r = admin_client.post(
        "/api/v1/cash/adjustments", json={"driver_id": driver["id"], "amount": "-3", "reason": "fuel advance"}
    )
    assert r.status_code == 201
    assert cash_of(client, driver) == (D("-3.000"), D("0"))
    report(client, driver, cash="4")
    db.execute(text("UPDATE daily_ops.reports SET submitted_at = now() - interval '25 hours'"))
    db.commit()
    assert daily.scan_overdue(db) == 1 and daily.scan_overdue(db) == 0
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["daily_report_overdue"]
    rid = admin_client.get("/api/v1/daily-reports").json()[0]["id"]
    approve(admin_client, rid)
    assert admin_client.get("/api/v1/alerts").json() == []


def test_reviewers_follow_permissions_and_company_scope(admin_client, client, new_client, companies):
    b = make_driver(admin_client, companies["b"]["id"])
    b["h"] = bearer(bind_device(client, b["phone"]))
    rid = report(client, b, cash="5").json()["id"]
    assert admin_client.get(f"/api/v1/daily-reports/{rid}/screenshot").status_code == 200
    make_user(
        admin_client,
        "rev_a",
        permissions=["daily_reports.view", "daily_reports.review", "cash.view", "cash.collect"],
        company_ids=[companies["a"]["id"]],
    )
    c = new_client()
    login(c, "rev_a")
    assert c.get("/api/v1/daily-reports").json() == []
    assert approve(c, rid).status_code == 404
    assert c.get("/api/v1/cash/balances").json() == []
    assert c.post("/api/v1/cash/receipts", json={"driver_id": b["id"], "amount": "1"}).status_code == 404
    make_user(admin_client, "viewer", permissions=["daily_reports.view"])
    c = new_client()
    login(c, "viewer")
    assert approve(c, rid).status_code == 403
    assert c.post("/api/v1/cash/receipts", json={"driver_id": b["id"], "amount": "1"}).status_code == 403


def test_tled12_uat18_end_of_service_settles_the_account_to_zero(admin_client, client, earlier, db):
    rid = report(client, earlier, cash="38.500").json()["id"]  # pending at resignation
    admin_client.post(f"/api/v1/employees/{earlier['id']}/status", json={"status_code": "resigned"})
    kinds = {a["kind"] for a in admin_client.get("/api/v1/alerts").json()}
    assert "driver_left_with_cash" in kinds  # with the vehicle alert when he holds one
    body = {"driver_id": earlier["id"], "payroll_amount": "60", "writeoff_amount": "60", "reason": "approved by CFO"}
    r = admin_client.post("/api/v1/cash/settlements", json=body)
    assert r.status_code == 409 and r.json()["code"] == "pending_journals_exist"
    approve(admin_client, rid)  # 81.500 + 38.500 = 120.000
    r = admin_client.post("/api/v1/cash/settlements", json=body | {"writeoff_amount": "50"})
    assert r.status_code == 422 and r.json()["code"] == "settlement_must_zero"
    r = admin_client.post("/api/v1/cash/settlements", json=body | {"writeoff_amount": "60", "reason": None})
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    r = admin_client.post("/api/v1/cash/settlements", json=body)
    assert r.status_code == 201 and r.json()["closed"]
    assert (D(r.json()["posted"]), D(r.json()["pending"])) == (D("0"), D("0"))
    assert "driver_left_with_cash" not in {a["kind"] for a in admin_client.get("/api/v1/alerts").json()}
    event = db.execute(
        text("SELECT payload FROM integrations.outbox WHERE event_type = 'cash.settlement.posted'")
    ).scalar()
    assert event["payroll_amount"] == "60.000"
    r = admin_client.post(
        "/api/v1/cash/adjustments", json={"driver_id": earlier["id"], "amount": "1", "reason": "late"}
    )
    assert r.status_code == 409 and r.json()["code"] == "account_closed"
    total = db.execute(
        text(
            "SELECT sum(l.amount) FROM cash.journal_lines l JOIN cash.journals j ON j.id = l.journal_id "
            "WHERE j.status = 'posted'"
        )
    ).scalar()
    assert total == 0


def test_settlement_pays_out_what_the_company_owes(admin_client, driver):
    admin_client.post(
        "/api/v1/cash/adjustments", json={"driver_id": driver["id"], "amount": "-7", "reason": "overpaid"}
    )
    r = admin_client.post("/api/v1/cash/settlements", json={"driver_id": driver["id"]})
    assert r.status_code == 409 and r.json()["code"] == "settlement_needs_end_of_service"
    admin_client.post(f"/api/v1/employees/{driver['id']}/status", json={"status_code": "terminated"})
    r = admin_client.post("/api/v1/cash/settlements", json={"driver_id": driver["id"], "payroll_amount": "7"})
    assert r.status_code == 422
    r = admin_client.post("/api/v1/cash/settlements", json={"driver_id": driver["id"]})
    assert r.status_code == 201 and D(r.json()["posted"]) == D("0")
    assert D(admin_client.get("/api/v1/cash/treasury").json()[0]["treasury"]) == D("-7.000")
