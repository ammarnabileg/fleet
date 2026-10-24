"""Configuration export and import (JSON): what an office set up on one installation, moved to a fresh one and back.
The second installation is a real one: the test database is made again from the migrated template, so nothing of
the first survives but the file."""

import io
import json

import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.i18n import store
from app.modules.payroll.service import add_months
from tests.conftest import PASSWORD, login, make_user, name

C = "/api/v1/config"
P = "/api/v1/payroll"
F = "/api/v1/finance"
PASS = "a long enough passphrase"
SERVICE_ACCOUNT = '{"type": "service_account", "private_key": "TOP-SECRET-KEY-VALUE"}'
PNG = b"\x89PNG\r\n\x1a\n" + b"logo-image-bytes" * 4


def ok(r, status=None):
    assert r.status_code == status if status else r.status_code < 300, r.text
    return r.json() if r.content and "json" in r.headers.get("content-type", "") else r


def setting(c, section, **values):
    cur = c.get("/api/v1/settings").json()[section]
    ok(c.put(f"/api/v1/settings/{section}", json={"version": cur["version"], "value": cur["value"] | values}))


def configure(c, company) -> None:
    """Something in every section, through the API as the office would."""
    setting(c, "tracking", interval_moving_s=45)
    setting(c, "cash", fuel_max_amount="61.500", treasury_deposit_weekdays=[0, 3])
    splash = ok(c.post("/api/v1/files", files={"file": ("s.jpg", b"\xff\xd8\xff\xe0splash-image", "image/jpeg")}), 201)
    setting(c, "driver_app", splash_enabled=True, splash_image=splash["sha256"], hidden_screens=["fines"])
    ok(c.post("/api/v1/branches", json={"name": name("فرع الجهراء", "Jahra branch")}), 201)
    ok(c.post("/api/v1/employment-statuses", json={"code": "on_trial", "name": name("تحت التجربة", "On trial")}), 201)
    ok(c.post("/api/v1/roles", json={"code": "dispatch", "name": name("مرحّل", "Dispatch"), "permissions": [
        "employees.view", "vehicles.view"]}), 201)  # fmt: skip
    acct = ok(c.post(f"{F}/accounts", json={"code": "6299", "name": name("قرطاسية", "Stationery"), "type": "expense"}))
    ok(c.post(f"{F}/expense-types", json={"code": "stationery", "name": name("قرطاسية", "Stationery"),
        "account_id": acct["id"], "petty": True}), 201)  # fmt: skip
    ok(c.put(f"{F}/roles", json={"roles": {"fuel_expense": acct["id"]}}))
    p = ok(c.post(f"{P}/platforms", json={"code": "zoomy", "name": name("زومي", "Zoomy"), "daily_fields": ["orders"]}),
           201)  # fmt: skip
    monthly = [{"key": "rating", "type": "money", "label": name("التقييم", "Rating")}]
    daily = [{"key": "orders", "builtin": "orders", "type": "int", "label": name("الطلبات", "Orders")}]
    ok(c.put(f"{P}/platforms/{p['id']}/fields", json={"version": 0, "daily": daily, "monthly": monthly}))
    flat = {"platform_id": p["id"], "code": "flat", "name": name("ثابت", "Flat")}
    s = ok(c.post(f"{P}/schemes/from-template", json=flat), 201)
    d = c.get(f"{P}/schemes/{s['id']}/designer").json()
    blocks = [b | {"params": b["params"] | {"rate": "0.450"}} for b in d["versions"][0]["blocks"]]
    nxt = add_months(today().replace(day=1), 1).isoformat()
    ok(c.post(f"{P}/schemes/{s['id']}/blocks", json={"version": d["scheme"]["version"], "blocks": blocks,
        "effective_month": nxt}))  # fmt: skip
    ok(c.put("/api/v1/approvals/workflows/expense", json={"version": 0, "active": True, "steps": [
        {"name": name("المرحّل", "Dispatch"), "role": "dispatch", "min_amount": "5.000"}]}))  # fmt: skip
    ok(c.post("/api/v1/maintenance/centers", json={"name": "مركز النور", "phone": "+96522223333"}), 201)
    logo = ok(c.post("/api/v1/print-templates/images", files={"file": ("l.png", PNG, "image/png")}), 201)
    t = c.get("/api/v1/print-templates").json()
    tpl = t["default"] | {"page": t["default"]["page"] | {"accent": "#AA3300"}}
    tpl["header"] = tpl["header"] | {"logo": logo["sha256"]}
    ok(c.put("/api/v1/print-templates/default", json={"template": tpl, "config_version": t["config_version"]}))
    own = tpl | {"page": tpl["page"] | {"accent": "#003366"}}
    ok(c.put(f"/api/v1/print-templates/companies/{company['id']}", json={"template": own, "config_version": 1}))
    ds = c.get("/api/v1/driver-status/templates").json()
    first = ds["templates"][0]
    body = {k: first[k] for k in ("kind", "name", "icon", "color", "title", "subtitle", "priority", "visibility",
                                  "ttl_minutes", "actions")} | {"priority": 77, "audience": "company",
                                                                "company_ids": [company["id"]]}  # fmt: skip
    ok(c.put(f"/api/v1/driver-status/templates/{first['code']}", json={"template": body, "config_version": 0}))
    annual = next(x for x in c.get("/api/v1/leave-types").json() if x["code"] == "annual")
    ok(c.put("/api/v1/leave-types/annual", json={"version": annual["version"], "sort_order": 333}))
    push = {"enabled": False, "app_id": "1:123456789:android:abcdef12", "api_key": "A" * 30, "sender_id": "123456789"}
    ok(c.put("/api/v1/integrations/connections/push", json={"version": 0, "config": push,
        "secrets": {"service_account": SERVICE_ACCOUNT}}))  # fmt: skip
    ok(c.put("/api/v1/i18n/translations/fr", json={"items": [
        {"scope": "app", "key": KEY, "text": "Bonjour chauffeur", "reviewed": True}]}))  # fmt: skip
    ok(c.post("/api/v1/i18n/translations/fr/publish"))
    assert s


KEY = next(k for k in store.keys("app") if "{" not in (store.reference("app", k) or "{"))


def export(c, *sections, passphrase=None) -> dict:
    if passphrase:
        r = c.post(f"{C}/export", json={"sections": list(sections), "include_secrets": True, "passphrase": passphrase})
    else:
        r = c.get(f"{C}/export", params={"sections": ",".join(sections)} if sections else None)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    return r.json()


def do_import(c, doc, *, dry_run, passphrase=None, status=200, **extra):
    data = {"dry_run": "true" if dry_run else "false"} | ({"passphrase": passphrase} if passphrase else {}) | extra
    r = c.post(f"{C}/import", data=data, files={"file": ("c.json", json.dumps(doc).encode(), "application/json")})
    assert r.status_code == status, r.text
    return r.json()


def counts(report) -> dict:
    return {s["key"]: (s["created"], s["updated"], len(s["skipped"])) for s in report["sections"]}


@pytest.fixture
def reinstall(database_url, admin_engine, new_client):
    """Another installation: the database made again from the migrated template, the first admin set up again."""

    def go():
        from app.core.db import get_engine, new_session
        from app.modules.i18n import service as i18n
        from app.modules.identity import service as identity
        from app.modules.integrations import service as integrations
        from app.modules.org import service as org

        get_engine().dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database_url["live"]}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{database_url["live"]}" TEMPLATE "{database_url["template"]}"'))
        org._cache.clear()
        integrations._cache.clear()
        i18n._effective_cache.clear()
        with new_session() as db:
            identity.bootstrap_superuser(db, username="admin", full_name="Admin", password=PASSWORD)
        c = new_client()
        login(c, "admin")
        return c

    return go


def test_round_trip_to_a_fresh_installation(admin_client, company, reinstall):
    configure(admin_client, company)
    plain = export(admin_client)
    text_ = json.dumps(plain)
    assert plain["format"] == "fleet-config" and plain["version"] == 1 and plain["secrets"] is None
    assert "TOP-SECRET-KEY-VALUE" not in text_  # no secret without a passphrase
    assert plain["sections"]["integrations"]["push"]["secret_names"] == ["service_account"]
    assert "id" not in plain["sections"]["companies"][0]  # natural keys, never database ids
    sealed = export(admin_client, passphrase=PASS)
    assert sealed["secrets"]["alg"] == "AES-256-GCM" and "TOP-SECRET-KEY-VALUE" not in json.dumps(sealed)
    assert len(sealed["files"]) == 2  # the splash image and the logo, embedded

    b = reinstall()
    preview = do_import(b, sealed, dry_run=True, passphrase=PASS)
    got = counts(preview)
    assert got["companies"][0] == 2 and got["roles"][0] == 1 and got["pay_schemes"][0] == 1, got
    assert all(s["skipped"] == [] for s in preview["sections"]), preview
    # the dry run wrote nothing
    assert b.get("/api/v1/companies").json() == []
    assert b.get("/api/v1/settings").json()["tracking"]["value"]["interval_moving_s"] == 30
    assert not any(r["code"] == "dispatch" for r in b.get("/api/v1/roles").json())

    done = do_import(b, sealed, dry_run=False, passphrase=PASS)
    assert counts(done) == got and done["secrets"] == "used"
    again = export(b, passphrase=PASS)
    assert again["sections"] == sealed["sections"]  # everything came across, by natural key
    assert again["files"].keys() == sealed["files"].keys()
    scheme = next(x for x in again["sections"]["pay_schemes"] if x["code"] == "flat")
    assert [v["blocks"][0]["params"]["rate"] for v in scheme["versions"]] == ["0.000", "0.450"]
    settings = b.get("/api/v1/settings").json()
    assert settings["tracking"]["value"]["interval_moving_s"] == 45 and settings["tracking"]["version"] == 1
    sha = settings["driver_app"]["value"]["splash_image"]
    assert b.get(f"/api/v1/driver/splash/{sha}").status_code == 200
    push = next(x for x in b.get("/api/v1/integrations/connections").json() if x["kind"] == "push")
    assert push["secrets"]["service_account"]["set"] and push["config"]["sender_id"] == "123456789"
    roles = {r["code"]: r for r in b.get("/api/v1/roles").json()}
    assert roles["dispatch"]["permissions"] == ["employees.view", "vehicles.view"]
    flow = next(w for w in b.get("/api/v1/approvals/workflows").json() if w["process"] == "expense")
    assert flow["active"] and flow["steps"][0]["role"]["code"] == "dispatch"
    fr = b.get("/api/v1/driver/translations", params={"lang": "fr"}).json()
    assert fr["version"] >= 1 and fr["strings"][KEY] == "Bonjour chauffeur"
    assert b.get("/api/v1/audit", params={"action": "config.imported"}).json()

    # the same file again: nothing to do
    twice = do_import(b, sealed, dry_run=False, passphrase=PASS)
    assert all(s["created"] == s["updated"] == 0 for s in twice["sections"]), counts(twice)


def test_merge_never_deletes_and_brings_a_changed_setting_back(admin_client, company, reinstall):
    setting(admin_client, "tracking", interval_moving_s=40)
    ok(admin_client.post("/api/v1/employment-statuses", json={"code": "on_trial", "name": name("تجربة", "Trial")}), 201)
    doc = export(admin_client, "settings", "employment_statuses")
    assert set(doc["sections"]) == {"settings", "employment_statuses"}
    ok(admin_client.post("/api/v1/employment-statuses", json={"code": "extra_one", "name": name("إضافي", "Extra")}),
       201)  # fmt: skip
    setting(admin_client, "tracking", interval_moving_s=90)
    done = do_import(admin_client, doc, dry_run=False)
    assert counts(done)["settings"] == (0, 1, 0)
    settings = admin_client.get("/api/v1/settings").json()
    assert settings["tracking"]["value"]["interval_moving_s"] == 40 and settings["tracking"]["version"] == 3
    codes = {s["code"] for s in admin_client.get("/api/v1/employment-statuses").json()}
    assert {"on_trial", "extra_one"} <= codes  # not in the file, still here


def test_secrets_need_the_right_passphrase(admin_client, reinstall):
    push = {"enabled": True, "app_id": "1:123456789:android:abcdef12", "api_key": "A" * 30, "sender_id": "123456789"}
    from app.modules.integrations import service as integrations

    class Fake:
        def check(self):
            return None

    integrations_fcm = integrations._fcm
    integrations._fcm = lambda loaded: Fake()
    try:
        ok(admin_client.put("/api/v1/integrations/connections/push", json={"version": 0, "config": push,
            "secrets": {"service_account": SERVICE_ACCOUNT}}))  # fmt: skip
    finally:
        integrations._fcm = integrations_fcm
    sealed = export(admin_client, "integrations", passphrase=PASS)
    short = admin_client.post(f"{C}/export", json={"include_secrets": True, "passphrase": "short"})
    assert short.status_code == 422 and short.json()["code"] == "config_passphrase_short"

    b = reinstall()
    wrong = do_import(b, sealed, dry_run=True, passphrase="not the passphrase", status=422)
    assert wrong["code"] == "config_passphrase_wrong"
    without = do_import(b, sealed, dry_run=False)  # no passphrase: imported without the secrets, switched off
    assert without["secrets"] == "skipped"
    report = next(s for s in without["sections"] if s["key"] == "integrations")
    assert [w["code"] for w in report["warnings"]] == ["config_integration_off"]
    conn = next(x for x in b.get("/api/v1/integrations/connections").json() if x["kind"] == "push")
    assert not conn["secrets"]["service_account"]["set"] and conn["config"]["enabled"] is False
    right = do_import(b, sealed, dry_run=False, passphrase=PASS)
    assert counts(right)["integrations"] == (0, 1, 0)
    conn = next(x for x in b.get("/api/v1/integrations/connections").json() if x["kind"] == "push")
    assert conn["secrets"]["service_account"]["set"] and conn["config"]["enabled"] is True
    assert conn["state"] == "untested"  # nothing is tried during an import
    from app.core.db import new_session

    with new_session() as db:
        loaded = integrations._read(db, "push")
    assert loaded.secrets["service_account"] == SERVICE_ACCOUNT


def test_permissions(admin_client, new_client):
    make_user(admin_client, "viewer", permissions=["settings.view"])
    make_user(admin_client, "editor", permissions=["settings.view", "settings.update"])
    doc = export(admin_client, "settings")
    v = new_client()
    login(v, "viewer")
    assert v.get(f"{C}/export").status_code == 200
    assert v.get(f"{C}/sections").status_code == 200
    r = v.post(f"{C}/export", json={"include_secrets": True, "passphrase": PASS})
    assert r.status_code == 403 and r.json()["code"] == "config_owner_only"
    assert do_import(v, doc, dry_run=True, status=403)["code"] == "permission_denied"
    e = new_client()
    login(e, "editor")
    assert do_import(e, doc, dry_run=True, status=403)["code"] == "config_owner_only"
    nobody = new_client()
    assert nobody.get(f"{C}/export").status_code == 401


def test_file_versions_and_unknown_sections(admin_client):
    doc = export(admin_client, "settings")
    newer = doc | {"version": 2}
    r = do_import(admin_client, newer, dry_run=True, status=422)
    assert r["code"] == "config_version_newer" and r["params"] == {"version": 2, "supported": 1}
    extra = doc | {"sections": doc["sections"] | {"from_the_future": [{"x": 1}]}}
    report = do_import(admin_client, extra, dry_run=True)
    assert report["unknown_sections"] == ["from_the_future"]
    assert [s["key"] for s in report["sections"]] == ["settings"]
    r = admin_client.post(f"{C}/import", data={"dry_run": "true"}, files={"file": ("x.json", b"{nope", "text/plain")})
    assert r.status_code == 422 and r.json()["code"] == "config_file_invalid"
    other = do_import(
        admin_client, {"format": "something-else", "version": 1, "sections": {}}, dry_run=True, status=422
    )
    assert other["code"] == "config_file_invalid"
    assert admin_client.get(f"{C}/export", params={"sections": "nope"}).json()["code"] == "config_section_unknown"


def test_bad_items_are_skipped_with_their_reason(admin_client):
    doc = {
        "format": "fleet-config",
        "version": 1,
        "sections": {
            "pay_schemes": [
                {"platform": "missing", "code": "x", "name": name("س", "x"), "calculator": "blocks", "versions": []}
            ],  # fmt: skip
            "expense_types": [{"code": "ok_type", "name": name("نوع", "Type"), "account": "no-such"}],
            "employment_statuses": [
                {"code": "fine_one", "name": name("جيد", "Fine")},
                {"code": "Bad Code", "name": name("سيء", "Bad")},
            ],
            "approval_workflows": [
                {
                    "process": "expense",
                    "active": True,
                    "steps": [{"name": name("خطوة", "Step"), "username": "nobody_here"}],
                }
            ],  # fmt: skip
        },
    }
    report = {s["key"]: s for s in do_import(admin_client, doc, dry_run=False)["sections"]}
    assert report["pay_schemes"]["skipped"][0]["code"] == "config_platform_missing"
    assert report["expense_types"]["skipped"][0]["code"] == "config_account_missing"
    assert report["employment_statuses"]["created"] == 1
    assert report["employment_statuses"]["skipped"][0]["code"] == "config_item_invalid"
    assert report["approval_workflows"]["skipped"][0]["code"] == "config_user_missing"
    codes = {s["code"] for s in admin_client.get("/api/v1/employment-statuses").json()}
    assert "fine_one" in codes


def test_export_is_readable_with_the_sections_listed(admin_client):
    keys = [s["key"] for s in admin_client.get(f"{C}/sections").json()]
    assert keys[0] == "languages" and "integrations" in keys and "pay_schemes" in keys
    doc = export(admin_client)
    assert set(doc["sections"]) <= set(keys)
    assert json.load(io.BytesIO(json.dumps(doc).encode()))["format"] == "fleet-config"
