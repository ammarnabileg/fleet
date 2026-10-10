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
    keeta = platform(admin_client, "keeta")
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
def test_reopening_keeps_what_was_decided_and_reviews_the_rest_again(admin_client, company):
    k, t, _ = setup_month(admin_client, company)
    run, _ = run_lines(admin_client, company)
    admin_client.post(f"{P}/runs/{run['id']}/approve")
    rows = {x["employee"]["id"]: x for x in admin_client.get(U).json()}
    admin_client.post(f"{U}/{rows[k['id']]['id']}/drop", json={"note": "يُسقط"})

    assert admin_client.post(f"{P}/runs/{run['id']}/reopen", json={"reason": "تصحيح"}).status_code == 200
    left = admin_client.get(U).json()
    assert [(x["employee"]["id"], x["status"]) for x in left] == [(k["id"], "dropped")]  # the review line went
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").status_code == 200
    again = admin_client.get(U).json()
    assert sorted((x["employee"]["id"] == k["id"], x["status"], x["amount"]) for x in again) == [
        (False, "review", "70.000"),
        (True, "dropped", "92.000"),  # decided once: not reviewed again
    ]


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
