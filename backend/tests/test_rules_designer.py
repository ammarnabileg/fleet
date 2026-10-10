"""The rules designer's calls: the catalog and templates, «جرّب» on sample figures, and the month's six stages."""

from app.core.clock import today
from tests.conftest import login, make_driver, make_user

P = "/api/v1/payroll"
MONTH = today().replace(day=1)


def test_the_catalog_lists_the_seven_categories_and_the_templates(admin_client, new_client):
    cat = admin_client.get(f"{P}/rules/catalog").json()
    assert cat["categories"] == ["pay", "incentive", "attendance", "deduction", "expense", "exception", "priority"]
    assert {t["type"] for t in cat["types"]} >= {"per_order", "price_change", "missing_orders", "special_day_violation"}
    price = next(t for t in cat["types"] if t["type"] == "price_change")
    assert price["needs_condition"] and [p["name"] for p in price["params"]] == ["rate", "mode"]
    assert len(cat["templates"]) == 7 and all(t["blocks"] for t in cat["templates"])
    make_user(admin_client, "nobody", permissions=[])
    c = new_client()
    login(c, "nobody")
    assert c.get(f"{P}/rules/catalog").status_code == 403


def test_try_shows_each_line_its_formula_and_the_net(admin_client):
    keeta = next(t for t in admin_client.get(f"{P}/rules/catalog").json()["templates"] if t["code"] == "keeta_paid")
    r = admin_client.post(
        f"{P}/rules/preview",
        json={"blocks": keeta["blocks"], "month": {"orders": 603, "attendance_marks": 1, "star_day_failed": False,
                                                    "basic_salary": "200"}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert [(x["code"], x["amount"], x["formula"]) for x in out["lines"]] == [
        ("fixed_salary", "200.000", "200.000"),
        ("target_bonus", "146.500", "(603 − 310) × 0.500 = 146.500"),
        ("marks_deduction", "-20.000", "1 × 20.000 = −20.000"),
    ]
    assert out["net"] == "326.500" and out["needs"] == []
    assert [x.get("skipped") for x in out["trace"] if x.get("skipped")] == ["star_day_kept", "month_valid"]
    r = admin_client.post(f"{P}/rules/preview", json={"blocks": keeta["blocks"], "month": {"orders": 300}})
    assert r.json()["needs"] == ["attendance_marks", "star_day_failed"]
    bad = admin_client.post(f"{P}/rules/preview", json={"blocks": [{"type": "per_order", "params": {}}], "month": {}})
    assert bad.status_code == 422 and bad.json()["code"] == "rule_block_param"
    assert bad.json()["params"] == {"position": 1, "param": "rate"}
    r = admin_client.post(f"{P}/rules/preview", json={"blocks": keeta["blocks"], "month": {"orders": -1}})
    assert r.status_code == 422 and r.json()["code"] == "rule_sample_invalid"


def test_the_month_in_six_stages(admin_client, company):
    p = admin_client.post(f"{P}/platforms", json={"code": "stp", "name": {"ar": "س", "en": "s"}}).json()
    make_driver(admin_client, company["id"], platform_id=p["id"], platform_driver_id="S-1")
    make_driver(admin_client, company["id"], platform_id=p["id"])
    s = admin_client.get(f"{P}/month-status", params={"month": str(MONTH)}).json()
    assert list(s) == ["month", "collect", "check", "policy", "engine", "review", "close"]
    assert s["collect"]["counts"]["drivers"] == 2 and s["collect"]["state"] == "done"
    assert s["check"]["counts"]["driver_id_missing"] == 1
    assert s["engine"] == {"state": "todo", "counts": {"runs": 0, "drafts": 0, "figures_missing": 0},
                           "link": "payroll?tab=runs"}  # fmt: skip
    assert s["close"]["state"] == "todo"
