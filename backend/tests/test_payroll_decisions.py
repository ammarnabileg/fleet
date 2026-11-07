"""The client's final payroll decisions (docs/payroll-schemes.md, section 6, A to J), each pinned by a worked month
through the whole run, on schemes set up as the panel sets them up (its defaults); and a scheme's terms changing by
version from a month without touching the months already paid."""

import pytest

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.test_schemes import BATCH, IBAN, KEETA, MONTH, NEXT, P, assign, fixed, platform, scheme

PREV = add_months(MONTH, -1)
# what the panel's scheme form sends for a new scheme when the office leaves the defaults
PANEL_DEFAULTS = {"target_orders": 420, "required_valid_days": 28, "missing_order_rate": None}


def set_cap(admin_client, **extra):
    version = admin_client.get("/api/v1/settings").json()["payroll"]["version"]
    value = {"max_deduction_percent": "50.00", "deduction_cap_base": "gross"} | extra
    r = admin_client.put("/api/v1/settings/payroll", json={"version": version, "value": value})
    assert r.status_code == 200, r.text


@pytest.fixture
def keeta_and_talabat(admin_client, company):
    keeta, talabat = platform(admin_client, "keeta_t"), platform(admin_client, "talabat_t")  # beside the seeded two
    return {
        "keeta": keeta,
        "talabat": talabat,
        "standard": scheme(admin_client, keeta["id"], KEETA | PANEL_DEFAULTS | {"missing_order_rate": "0.350"}),
        "batch": scheme(admin_client, talabat["id"], BATCH | PANEL_DEFAULTS),
        "fixed_1": scheme(
            admin_client, talabat["id"], fixed("fixed_1", "0.350", ["maintenance", "housing", "gas", "sim"])
        ),
        "fixed_3": scheme(admin_client, talabat["id"], fixed("fixed_3", "0.680", [])),
    }


def month_of(admin_client, company, setup, scheme_code, platform_code, month=MONTH, **figures):
    """A driver on the scheme with the month's approved figures; returns his employee id."""
    from tests.conftest import make_driver

    d = make_driver(admin_client, company["id"], platform_id=setup[platform_code]["id"], iban=IBAN, basic_salary="300")
    assert assign(admin_client, setup[scheme_code], d, month=month).json()["set"] == 1
    body = {"employee_id": d["id"], "month": str(month)} | figures
    r = admin_client.post(f"{P}/statements", json=body)
    assert r.status_code == 201, r.text
    return d["id"]


def run_lines(admin_client, company, month=MONTH) -> tuple[dict, dict]:
    run = admin_client.post(f"{P}/runs", json={"company_id": company["id"], "month": str(month)})
    assert run.status_code == 201, run.text
    return run.json(), {x["employee"]["id"]: x for x in run.json()["lines"]}


def items(line) -> dict:
    return {b["code"]: b["amount"] for b in line["breakdown"]}


def test_the_seeded_defaults_are_the_decisions(admin_client, keeta_and_talabat):
    """The columns' defaults and the panel's defaults are the decided values: A and C off, the floor on (D), no
    missing-target rule unless the scheme names one (F), tiers by the highest reached (H)."""
    s = keeta_and_talabat
    for code in ("standard", "batch", "fixed_1", "fixed_3"):
        x = s[code]
        assert (x["bonus_when_reduced"], x["marks_when_reduced"], x["floor_at_zero"]) == (False, False, True), code
        assert (x["target_orders"], x["required_valid_days"]) == (420, 28), code
    assert s["standard"]["missing_order_rate"] == "0.350"  # B: Keeta's own rate
    assert s["batch"]["missing_order_rate"] is None and s["fixed_1"]["missing_order_rate"] is None  # F


def test_keeta_reduced_months_a_b_c_h(admin_client, company, keeta_and_talabat):
    set_cap(admin_client)
    s = keeta_and_talabat
    k800 = month_of(
        admin_client, company, s, "standard", "keeta", orders=800, attendance_marks=5, star_day_failed=False
    )
    k400 = month_of(
        admin_client, company, s, "standard", "keeta", orders=400, attendance_marks=5, star_day_failed=False
    )
    star = month_of(admin_client, company, s, "standard", "keeta", orders=720, attendance_marks=0, star_day_failed=True)
    full = month_of(
        admin_client, company, s, "standard", "keeta", orders=720, attendance_marks=4, star_day_failed=False
    )
    _, lines = run_lines(admin_client, company)

    # A, C: 800 orders, 5 marks: every order at 0.200, no tier bonus, no -30, nothing short of the target
    line = lines[k800]
    assert items(line) == {"orders_pay": "160.000"}
    assert (line["gross"], line["deductions"], line["net"]) == ("160.000", "0.000", "160.000")
    assert line["breakdown"][0]["why"]["reduced_by"] == "marks"

    # B, C: 400 orders, 5 marks: 400 x 0.200 - 20 short x 0.350 (not 0.200), still no -30
    line = lines[k400]
    assert items(line) == {"orders_pay": "80.000", "missing_target": "-7.000"}
    assert line["breakdown"][1]["why"] == {"target": 420, "missing": 20, "rate": "0.350"}
    assert (line["gross"], line["net"]) == ("80.000", "73.000")

    # A: a missed star day reduces the month the same way: no bonus even past the highest tier
    assert items(lines[star]) == {"orders_pay": "144.000"}

    # H: 720 orders on a full month: the 710 tier's 200 only, not 50 + 90 + 130 + 200; 4 marks: the 30, not 10 + 30
    assert items(lines[full]) == {"orders_pay": "252.000", "tier_bonus": "200.000", "marks_deduction": "-30.000"}
    assert lines[full]["net"] == "422.000"


def test_fewer_valid_days_takes_nothing_more_e(admin_client, company, keeta_and_talabat):
    """E: under 28 valid days there is no automatic deduction on a scheme (not the platform's invalid-days rule, not
    the absence rule); the target and the star day still apply."""
    s = keeta_and_talabat
    keeta = s["keeta"]
    r = admin_client.patch(
        f"{P}/platforms/{keeta['id']}",
        json={"version": keeta["version"], "invalid_days": "daily_wage", "driver_fields": ["valid_days", "orders"]},
    )
    assert r.status_code == 200, r.text
    set_cap(admin_client, absence_deduction="daily_wage")
    short = month_of(
        admin_client, company, s, "standard", "keeta",
        orders=500, valid_days=20, working_days=30, attendance_marks=0, star_day_failed=False,
    )  # fmt: skip
    missed = month_of(
        admin_client, company, s, "standard", "keeta",
        orders=300, valid_days=20, working_days=30, attendance_marks=0, star_day_failed=True,
    )  # fmt: skip
    _, lines = run_lines(admin_client, company)
    line = lines[short]  # 500 x 0.350 + the 450 tier's 50, nothing for the 10 days
    assert items(line) == {"orders_pay": "175.000", "tier_bonus": "50.000"}
    assert (line["cells"]["invalid_days_deduction"], line["cells"]["absence_deduction"]) == ("0.000", "0.000")
    assert line["net"] == "225.000"
    # the star day and the target still apply: 300 x 0.200 - 120 x 0.350
    assert items(lines[missed]) == {"orders_pay": "60.000", "missing_target": "-42.000"}
    assert lines[missed]["net"] == "18.000"


def test_talabat_has_no_missing_target_and_one_batch_level_a_month_f_i(admin_client, company, keeta_and_talabat):
    set_cap(admin_client)
    s = keeta_and_talabat
    f400 = month_of(admin_client, company, s, "fixed_3", "talabat", orders=400)
    b400 = month_of(admin_client, company, s, "batch", "talabat", orders=400, batch_level=2)
    _, lines = run_lines(admin_client, company)
    # F: 400 orders, 20 short of the 420 target: no deduction on Talabat
    assert items(lines[f400]) == {"orders_pay": "272.000"} and lines[f400]["net"] == "272.000"
    # I: the month's one batch level prices every order of the month
    assert items(lines[b400]) == {"orders_pay": "270.000"}
    assert lines[b400]["breakdown"][0]["why"]["batch_level"] == 2 and lines[b400]["cells"]["batch_level"] == 2


def test_driver_borne_expenses_are_never_deducted_g(admin_client, company, keeta_and_talabat):
    """G: who bears maintenance, gas, housing and the phone is information: a driver bearing all of it is paid the
    same month as one bearing none of it."""
    set_cap(admin_client)
    s = keeta_and_talabat
    r = admin_client.patch(f"{P}/schemes/{s['fixed_3']['id']}", json={"version": 1, "per_order": "0.350"})
    assert r.status_code == 200, r.text  # nobody on it yet: the same price as fixed_1, nothing else in common
    covered = month_of(admin_client, company, s, "fixed_1", "talabat", orders=450)
    borne = month_of(admin_client, company, s, "fixed_3", "talabat", orders=450)
    _, lines = run_lines(admin_client, company)
    pay = lambda x: (x["gross"], x["deductions"], x["net"], x["breakdown"])  # noqa: E731
    assert pay(lines[covered]) == pay(lines[borne])
    assert lines[borne]["deductions"] == "0.000"


def test_another_keeta_scheme_can_be_added_later_j(admin_client, company, keeta_and_talabat):
    s = keeta_and_talabat
    second = scheme(
        admin_client,
        s["keeta"]["id"],
        KEETA | {"code": "premium", "name": {"ar": "كيتا المميز", "en": "Keeta premium"}, "per_order": "0.400"},
    )
    listed = admin_client.get(f"{P}/schemes", params={"platform_id": s["keeta"]["id"]}).json()
    assert {x["code"] for x in listed} == {"standard", "premium"}
    set_cap(admin_client)
    k = month_of(admin_client, company, {**s, "premium": second}, "premium", "keeta", orders=500, attendance_marks=0,
                 star_day_failed=False)  # fmt: skip
    _, lines = run_lines(admin_client, company)
    assert items(lines[k]) == {"orders_pay": "200.000", "tier_bonus": "50.000"}


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_terms_change_by_version_and_paid_months_never_change(admin_client, company, keeta_and_talabat):
    set_cap(admin_client)
    s = keeta_and_talabat
    fx = s["fixed_3"]
    d = month_of(admin_client, company, s, "fixed_3", "talabat", month=PREV, orders=380)
    r = admin_client.post(f"{P}/statements", json={"employee_id": d, "month": str(MONTH), "orders": 380})
    assert r.status_code == 201, r.text
    prev, lines = run_lines(admin_client, company, PREV)
    assert (lines[d]["gross"], lines[d]["scheme_version"]) == ("258.400", 1)  # 380 x 0.680
    assert admin_client.post(f"{P}/runs/{prev['id']}/approve").status_code == 200

    # the month paid on the scheme cannot take a new price; a used scheme needs the month the change applies from
    r = admin_client.patch(f"{P}/schemes/{fx['id']}", json={"version": 1, "per_order": "0.700"})
    assert r.status_code == 422 and r.json()["params"] == {"field": "effective_month"}
    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}", json={"version": 1, "per_order": "0.700", "effective_month": str(PREV)}
    )
    assert r.status_code == 409 and r.json()["code"] == "scheme_version_month"
    assert r.json()["params"] == {"from": str(MONTH)[:7]}

    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}",
        json={"version": 1, "per_order": "0.700", "effective_month": str(MONTH), "version_note": "سعر الشهر الجديد"},
    )
    assert r.status_code == 200, r.text
    x = r.json()
    assert (x["per_order"], x["version_no"], x["effective_month"], x["change_from"]) == (
        "0.700",
        2,
        str(MONTH),
        str(MONTH),
    )
    assert [(v["version_no"], v["effective_month"], v["per_order"]) for v in x["versions"]] == [
        (2, str(MONTH), "0.700"),
        (1, str(PREV), "0.680"),
    ]
    assert x["versions"][0]["note"] == "سعر الشهر الجديد" and x["versions"][0]["created_by"]

    # this month on the new price; the approved month as it was paid, and recomputed on its own month's terms
    _, lines = run_lines(admin_client, company, MONTH)
    assert (lines[d]["gross"], lines[d]["scheme_version"]) == ("266.000", 2)  # 380 x 0.700
    paid = admin_client.get(f"{P}/runs/{prev['id']}").json()["lines"][0]
    assert (paid["gross"], paid["scheme_version"]) == ("258.400", 1)
    r = admin_client.post(f"{P}/runs/{prev['id']}/reopen", json={"reason": "مراجعة بعد تغيير السعر"})
    assert r.status_code == 200, r.text
    again = admin_client.post(f"{P}/runs/{prev['id']}/recompute").json()["lines"][0]
    assert (again["gross"], again["scheme_version"]) == ("258.400", 1)

    # a version nobody was paid on yet is replaced from its own month; a later one is scheduled; the same terms again
    # make no version
    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}", json={"version": 2, "per_order": "0.710", "effective_month": str(MONTH)}
    )
    assert [v["version_no"] for v in r.json()["versions"]] == [2, 1] and r.json()["per_order"] == "0.710"
    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}", json={"version": 3, "per_order": "0.750", "effective_month": str(NEXT)}
    )
    x = r.json()
    assert (x["per_order"], x["next_version"]) == ("0.710", {"version_no": 3, "effective_month": str(NEXT)})
    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}", json={"version": 4, "per_order": "0.750", "effective_month": str(NEXT)}
    )
    assert [v["version_no"] for v in r.json()["versions"]] == [3, 2, 1]
    r = admin_client.patch(
        f"{P}/schemes/{fx['id']}", json={"version": 5, "per_order": "0.760", "effective_month": str(MONTH)}
    )
    assert r.status_code == 409 and r.json()["params"] == {"from": str(NEXT)[:7]}  # not before the latest version


def test_who_bears_what_follows_the_version_of_the_month(admin_client, company, keeta_and_talabat, db):
    from app.modules.payroll import service as payroll
    from app.modules.people import service as people
    from tests.conftest import make_driver

    s = keeta_and_talabat
    d = make_driver(admin_client, company["id"], platform_id=s["talabat"]["id"])
    assign(admin_client, s["fixed_1"], d)
    r = admin_client.patch(
        f"{P}/schemes/{s['fixed_1']['id']}",
        json={"version": 1, "company_covers": ["maintenance"], "effective_month": str(NEXT)},
    )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["company_covers"]) == ["gas", "housing", "maintenance", "sim"]  # this month's terms
    driver = people.ref_by_public_id(db, d["id"], all_companies=True, company_ids=())
    assert sorted(payroll.company_covers(db, driver.id, today())) == ["gas", "housing", "maintenance", "sim"]
    assert payroll.company_covers(db, driver.id, NEXT) == ["maintenance"]


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_a_change_of_terms_waits_for_a_run_being_approved_and_then_sees_it_paid(
    admin_client, company, keeta_and_talabat
):
    """The run holds the schemes it pays on (FOR SHARE) until it is saved; a change of terms locks the scheme and reads
    what was paid after it got the lock: a change for the month being approved waits, then is refused."""
    import threading

    from sqlalchemy import text

    from app.core.db import new_session
    from app.modules.payroll import runs, schemes

    set_cap(admin_client)
    s = keeta_and_talabat
    fx = s["fixed_3"]
    month_of(admin_client, company, s, "fixed_3", "talabat", month=PREV, orders=380)
    prev, _ = run_lines(admin_client, company, PREV)
    scope = {"all_companies": True, "company_ids": ()}
    done = {}

    def change(session_done_key, month):
        with new_session() as session:
            try:
                schemes.update(
                    session,
                    fx["id"],
                    version=1,
                    changes={"per_order": "0.700", "effective_month": month},
                    actor_user_id=1,
                )
                done[session_done_key] = "ok"
            except Exception as exc:  # noqa: BLE001
                done[session_done_key] = getattr(exc, "code", repr(exc))

    # an approval under way: it read the scheme FOR SHARE and is about to save the month as paid
    with new_session() as approving:
        approving.execute(text("SELECT id FROM payroll.schemes WHERE public_id = :p FOR SHARE"), {"p": fx["id"]})
        t = threading.Thread(target=change, args=("change", PREV))
        t.start()
        t.join(1.0)
        assert t.is_alive() and not done  # the change waits for the approval
        approving.execute(
            text("UPDATE payroll.runs SET status = 'approved', approved_at = now() WHERE public_id = :p"),
            {"p": prev["id"]},
        )
        approving.commit()
    t.join(15)
    assert done == {"change": "scheme_version_month"}  # it sees the month paid once it has the scheme

    # and the run really takes that lock: an approval waits for a change of terms under way
    with new_session() as changing:
        changing.execute(
            text("UPDATE payroll.runs SET status = 'draft', approved_at = NULL WHERE public_id = :p"), {"p": prev["id"]}
        )
        changing.commit()
        changing.execute(text("SELECT id FROM payroll.schemes WHERE public_id = :p FOR UPDATE"), {"p": fx["id"]})

        def approve():
            with new_session() as session:
                done["approve"] = runs.approve(session, prev["id"], actor_user_id=1, **scope)["status"]

        a = threading.Thread(target=approve)
        a.start()
        a.join(1.0)
        assert a.is_alive() and "approve" not in done
        changing.rollback()
    a.join(15)
    assert done["approve"] == "approved"
