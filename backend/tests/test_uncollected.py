"""Decision D: penalties above the month's pay end the net at zero, and the remainder is an uncollected deductions
balance for review, recorded when the run is approved, never carried by itself; an accountant with payroll.approve
carries a line to the next month (a manual deduction) or drops it, each with a note."""

import pytest

from tests.conftest import bearer, bind_device, login, make_driver, make_user
from tests.test_payroll_decisions import run_lines, set_cap
from tests.test_schemes import IBAN, KEETA, MONTH, NEXT, P, assign, platform, scheme

U = f"{P}/uncollected"


def _month(admin_client, driver, **figures):
    r = admin_client.post(f"{P}/statements", json={"employee_id": driver["id"], "month": str(MONTH)} | figures)
    assert r.status_code == 201, r.text


def setup_month(admin_client, company):
    """A Keeta driver whose penalties pass his pay, one on a platform's own rule whose platform deductions pass his
    salary, and one whose month covers everything."""
    set_cap(admin_client)
    keeta = platform(admin_client, "keeta_t")  # beside the seeded platforms
    standard = scheme(admin_client, keeta["id"], KEETA)
    plain = admin_client.post(f"{P}/platforms", json={"code": "plain", "name": {"ar": "منصة", "en": "Plain"}}).json()
    k = make_driver(admin_client, company["id"], platform_id=keeta["id"], iban=IBAN, basic_salary="300")
    t = make_driver(admin_client, company["id"], platform_id=plain["id"], iban=IBAN, basic_salary="300.000")
    ok = make_driver(admin_client, company["id"], platform_id=plain["id"], iban=IBAN, basic_salary="300.000")
    assign(admin_client, standard, k)
    _month(admin_client, k, orders=100, attendance_marks=0, star_day_failed=True)  # 20.000 - 112.000
    _month(admin_client, t, platform_deductions="350.000", late="20.000")  # 300 - 370
    _month(admin_client, ok, platform_deductions="10.000")
    return k, t, ok


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_penalties_above_the_pay_end_at_zero_and_wait_for_review(admin_client, company, new_client):
    k, t, ok = setup_month(admin_client, company)
    run, lines = run_lines(admin_client, company)
    assert run["blocking"] == 0  # a month whose penalties pass its pay is not an error any more
    lk, lt = lines[k["id"]], lines[t["id"]]
    assert (lk["gross"], lk["deductions"], lk["net"], lk["cells"]["uncovered_penalty"]) == (
        "20.000",
        "20.000",
        "0.000",
        "92.000",
    )
    assert (lt["gross"], lt["deductions"], lt["net"], lt["cells"]["uncovered_penalty"]) == (
        "300.000",
        "300.000",
        "0.000",
        "70.000",
    )
    assert lk["flags"] == ["uncollected"] and lt["flags"] == ["uncollected"] and lines[ok["id"]]["flags"] == []
    assert admin_client.get(U).json() == []  # a draft is recomputed at will: nothing for review yet

    assert admin_client.post(f"{P}/runs/{run['id']}/approve").status_code == 200
    rows = {x["employee"]["id"]: x for x in admin_client.get(U, params={"month": str(MONTH)}).json()}
    assert set(rows) == {k["id"], t["id"]}
    assert (rows[t["id"]]["amount"], rows[t["id"]]["status"], rows[t["id"]]["run"]["id"]) == (
        "70.000",
        "review",
        run["id"],
    )
    assert rows[t["id"]]["reason"] == {
        "gross": "300.000",
        "items": [{"code": "platform_deductions", "amount": "350.000"}, {"code": "late", "amount": "20.000"}],
    }
    assert rows[k["id"]]["reason"]["items"] == [{"code": "missing_target", "amount": "112.000"}]
    assert admin_client.get(U + "/counts").json() == {"review": 2, "amount": "162.000"}
    assert [x["employee"]["id"] for x in admin_client.get(U, params={"employee_id": t["id"]}).json()] == [t["id"]]

    # the accountant sees it; deciding takes payroll.approve
    make_user(admin_client, "accountant1", permissions=["payroll.view"])
    acc = new_client()
    login(acc, "accountant1")
    assert len(acc.get(U).json()) == 2
    r = acc.post(f"{U}/{rows[k['id']]['id']}/carry", json={"note": "يُخصم الشهر القادم"})
    assert r.status_code == 403


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_carried_with_approval_or_dropped_with_a_note(admin_client, client, company):
    k, t, _ = setup_month(admin_client, company)
    run, _ = run_lines(admin_client, company)
    before = admin_client.post(f"{P}/runs/{run['id']}/approve").json()["lines"]
    rows = {x["employee"]["id"]: x for x in admin_client.get(U).json()}

    assert admin_client.post(f"{U}/{rows[k['id']]['id']}/carry", json={"note": ""}).status_code == 422  # a note
    r = admin_client.post(
        f"{U}/{rows[k['id']]['id']}/carry", json={"note": "اتفاق مع السائق", "version": rows[k["id"]]["version"]}
    )
    assert r.status_code == 200, r.text
    carried = r.json()
    assert (carried["status"], carried["note"], carried["deduction"]["start_month"]) == (
        "carried",
        "اتفاق مع السائق",
        str(NEXT),
    )
    assert carried["decided_by"]
    ded = [d for d in admin_client.get("/api/v1/deductions", params={"employee_id": k["id"]}).json()]
    assert len(ded) == 1 and ded[0]["id"] == carried["deduction"]["id"]
    assert (ded[0]["source_type"], ded[0]["total"], ded[0]["installments"], ded[0]["status"]) == (
        "other",
        "92.000",
        1,
        "approved",
    )
    assert ded[0]["schedule"] == [{"month": str(NEXT), "amount": "92.000"}] and "اتفاق مع السائق" in ded[0]["reason"]
    told = client.get("/api/v1/driver/notifications", headers=bearer(bind_device(client, k["phone"]))).json()
    assert [n["kind"] for n in told["items"]][:1] == ["deduction_added"]
    r = admin_client.post(f"{U}/{rows[k['id']]['id']}/carry", json={"note": "مرة أخرى"})
    assert r.status_code == 409 and r.json()["code"] == "uncollected_decided"

    r = admin_client.post(f"{U}/{rows[t['id']]['id']}/drop", json={"note": "خطأ من المنصة، استُرد"})
    assert r.status_code == 200 and (r.json()["status"], r.json()["deduction"]) == ("dropped", None)
    assert admin_client.get("/api/v1/deductions", params={"employee_id": t["id"]}).json() == []
    assert admin_client.get(U + "/counts").json()["review"] == 0
    assert admin_client.get(U, params={"status": "carried"}).json()[0]["id"] == rows[k["id"]]["id"]

    # the approved run never changes; the audit keeps every decision
    assert admin_client.get(f"{P}/runs/{run['id']}").json()["lines"] == before
    trail = admin_client.get("/api/v1/audit", params={"entity_type": "uncollected", "limit": 50}).json()
    actions = {a["action"] for a in (trail["items"] if isinstance(trail, dict) else trail)}
    assert {"uncollected.recorded", "uncollected.carried", "uncollected.dropped"} <= actions


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_reopening_takes_the_balance_back_and_the_corrected_month_records_it_afresh(admin_client, company):
    """70 carried, then the month reopened and corrected to 10: the 70 deduction is cancelled (nothing of it was
    taken: no later month is approved) and only the 10 is reviewed and carried again."""
    k, t, _ = setup_month(admin_client, company)
    run, _ = run_lines(admin_client, company)
    admin_client.post(f"{P}/runs/{run['id']}/approve")
    rows = {x["employee"]["id"]: x for x in admin_client.get(U).json()}
    carried = admin_client.post(f"{U}/{rows[t['id']]['id']}/carry", json={"note": "يُخصم الشهر القادم"}).json()
    admin_client.post(f"{U}/{rows[k['id']]['id']}/drop", json={"note": "يُسقط"})

    assert admin_client.post(f"{P}/runs/{run['id']}/reopen", json={"reason": "تصحيح خصم المنصة"}).status_code == 200
    assert admin_client.get(U).json() == []  # every line taken back, decided or not
    ded = admin_client.get("/api/v1/deductions", params={"employee_id": t["id"]}).json()
    assert [(d["id"], d["status"]) for d in ded] == [(carried["deduction"]["id"], "cancelled")]
    r = admin_client.post(f"{U}/{rows[k['id']]['id']}/drop", json={"note": "مرة أخرى"})
    assert r.status_code == 404  # taken back with the reopening

    st = next(
        x
        for x in admin_client.get(f"{P}/statements", params={"month": str(MONTH)}).json()
        if x["employee"]["id"] == t["id"]
    )
    r = admin_client.post(
        f"{P}/statements/{st['id']}/approve", json={"platform_deductions": "310.000", "late": "0.000"}
    )
    assert r.status_code == 200, r.text
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").status_code == 200
    again = {x["employee"]["id"]: x for x in admin_client.get(U).json()}
    assert {e: (x["status"], x["amount"]) for e, x in again.items()} == {
        t["id"]: ("review", "10.000"),
        k["id"]: ("review", "92.000"),  # the drop is decided again, on the month as approved now
    }
    admin_client.post(f"{U}/{again[t['id']]['id']}/carry", json={"note": "بعد التصحيح"})
    live = [
        d
        for d in admin_client.get("/api/v1/deductions", params={"employee_id": t["id"]}).json()
        if d["status"] == "approved"
    ]
    assert [d["total"] for d in live] == ["10.000"]  # never the 70 as well


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_a_decision_and_a_reopening_never_interleave(admin_client, company, db):
    """Both lock the run's row: a carry under way finishes first and the reopening then cancels what it carried; a
    carry that waited for a reopening is refused (the run is a draft again)."""
    import threading

    from sqlalchemy import text

    from app.core.db import new_session
    from app.modules.payroll import runs, uncollected

    scope = {"all_companies": True, "company_ids": ()}
    k, t, _ = setup_month(admin_client, company)
    run, _ = run_lines(admin_client, company)
    admin_client.post(f"{P}/runs/{run['id']}/approve")
    rows = {x["employee"]["id"]: x for x in admin_client.get(U).json()}
    done = {}

    def call(key, fn):
        with new_session() as s:
            try:
                fn(s)
                done[key] = "ok"
            except Exception as exc:  # noqa: BLE001
                done[key] = getattr(exc, "code", repr(exc))

    with new_session() as holder:  # something holds the run's row (an approval step, another decision)
        holder.execute(text("SELECT id FROM payroll.runs WHERE public_id = :p FOR UPDATE"), {"p": run["id"]})
        carry = threading.Thread(
            target=call,
            args=(
                "carry",
                lambda s: uncollected.carry(
                    s, rows[t["id"]]["id"], note="ترحيل", version=None, actor_user_id=1, **scope
                ),
            ),
        )
        carry.start()
        carry.join(1.0)
        reopen = threading.Thread(
            target=call,
            args=("reopen", lambda s: runs.reopen(s, run["id"], reason="تصحيح بعد الترحيل", actor_user_id=1, **scope)),
        )
        reopen.start()
        reopen.join(1.0)
        assert carry.is_alive() and reopen.is_alive() and not done  # both wait for the run's row, in that order
        holder.rollback()
    carry.join(15)
    reopen.join(15)
    assert done == {"carry": "ok", "reopen": "ok"}
    ded = admin_client.get("/api/v1/deductions", params={"employee_id": t["id"]}).json()
    assert [d["status"] for d in ded] == ["cancelled"] and admin_client.get(U).json() == []

    # the other way round: a carry that waited for the reopening finds a draft and is refused
    admin_client.post(f"{P}/runs/{run['id']}/approve")
    line = admin_client.get(U, params={"employee_id": t["id"]}).json()[0]
    with new_session() as holder:
        holder.execute(text("SELECT id FROM payroll.runs WHERE public_id = :p FOR UPDATE"), {"p": run["id"]})
        late = threading.Thread(
            target=call,
            args=(
                "late",
                lambda s: uncollected.carry(s, line["id"], note="متأخر", version=None, actor_user_id=1, **scope),
            ),
        )
        late.start()
        late.join(1.0)
        holder.execute(
            text("UPDATE payroll.runs SET status = 'draft', approved_at = NULL WHERE public_id = :p"), {"p": run["id"]}
        )
        holder.commit()
    late.join(15)
    assert done["late"] == "run_not_approved"
    assert db.execute(text("SELECT count(*) FROM payroll.deductions WHERE status = 'approved'")).scalar() == 0


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_the_payslip_and_the_excel_say_what_was_not_taken_even_without_a_column(admin_client, client, company):
    import io

    import openpyxl

    _, t, _ = setup_month(admin_client, company)
    plain = next(p for p in admin_client.get(f"{P}/platforms").json() if p["code"] == "plain")
    columns = [
        {"code": "name", "header": "الاسم"},
        {"code": "gross", "header": "الإجمالي"},
        {"code": "platform_deductions", "header": "خصومات المنصة"},
        {"code": "net", "header": "الصافي"},
    ]
    r = admin_client.patch(f"{P}/platforms/{plain['id']}", json={"version": plain["version"], "columns": columns})
    assert r.status_code == 200, r.text
    run, _ = run_lines(admin_client, company)
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").status_code == 200
    slip = client.get("/api/v1/driver/payslips", headers=bearer(bind_device(client, t["phone"]))).json()[0]
    assert [x["code"] for x in slip["rows"]] == ["gross", "platform_deductions", "uncovered_penalty", "net"]
    assert slip["rows"][2]["value"] == "70.000" and slip["uncollected"] == "70.000"
    wb = openpyxl.load_workbook(io.BytesIO(admin_client.get(f"{P}/runs/{run['id']}/export").content))
    headers = [[c.value for c in ws[1]] for ws in wb]
    assert any(h == ["الاسم", "الإجمالي", "خصومات المنصة", "خصومات غير محصلة (للمراجعة)", "الصافي"] for h in headers)
