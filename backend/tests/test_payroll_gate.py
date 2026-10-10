"""The reconciliation gate: until the owner turns on payroll.live_approval_enabled (after comparing one month with a
previous month's sheet of the client), runs are computed, reviewed and exported, and approving one is refused."""

from tests.conftest import login, make_user
from tests.test_payroll_decisions import run_lines, set_cap
from tests.test_schemes import IBAN, P


def _settings(c):
    return c.get("/api/v1/settings").json()["payroll"]


def _put(c, **value):
    s = _settings(c)
    return c.put("/api/v1/settings/payroll", json={"version": s["version"], "value": s["value"] | value})


def test_runs_are_prepared_but_not_approved_until_the_owner_turns_the_gate_on(admin_client, company, new_client):
    from tests.conftest import make_employee

    set_cap(admin_client)
    assert _settings(admin_client)["value"]["live_approval_enabled"] is False  # every install starts closed
    make_employee(admin_client, company["id"], basic_salary="400.000", iban=IBAN)
    run, _ = run_lines(admin_client, company)
    assert admin_client.get(f"{P}/gate").json() == {"live_approval_enabled": False}
    assert admin_client.post(f"{P}/runs/{run['id']}/recompute").status_code == 200
    assert admin_client.get(f"{P}/runs/{run['id']}/export").status_code == 200

    r = admin_client.post(f"{P}/runs/{run['id']}/approve", headers={"Accept-Language": "ar"})
    assert r.status_code == 409 and r.json()["code"] == "payroll_not_reconciled"
    assert admin_client.get(f"{P}/runs/{run['id']}").json()["status"] == "draft"

    # a settings editor who is not the owner cannot open it, but still saves the rest of the payroll settings
    make_user(admin_client, "settings1", permissions=["settings.view", "settings.update", "payroll.view"])
    editor = new_client()
    login(editor, "settings1")
    r = _put(editor, live_approval_enabled=True)
    assert r.status_code == 403 and r.json()["code"] == "owner_only"
    r = editor.put(
        "/api/v1/settings/payroll",
        json={"version": _settings(editor)["version"], "value": {"max_deduction_percent": "40.00"}},
    )
    assert r.status_code == 200 and r.json()["value"]["live_approval_enabled"] is False
    assert editor.get("/api/v1/auth/me").json()["all_permissions"] is False

    # the owner (a role with all permissions) opens it after the test; then a run is approved
    make_user(admin_client, "owner1", role="system_admin")
    owner = new_client()
    login(owner, "owner1")
    assert owner.get("/api/v1/auth/me").json()["all_permissions"] is True
    assert _put(owner, live_approval_enabled=True).status_code == 200
    assert admin_client.get(f"{P}/gate").json() == {"live_approval_enabled": True}
    r = editor.put(
        "/api/v1/settings/payroll",
        json={"version": _settings(editor)["version"], "value": {"max_deduction_percent": "50.00"}},
    )
    assert r.status_code == 200 and r.json()["value"]["live_approval_enabled"] is True  # left out: unchanged
    assert _put(editor, live_approval_enabled=False).json()["code"] == "owner_only"  # closing it is the owner's too
    r = admin_client.post(f"{P}/runs/{run['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text

    # closed again: refused at once (read from the database, not from a cache)
    assert _put(owner, live_approval_enabled=False).status_code == 200
    assert admin_client.post(f"{P}/runs/{run['id']}/reopen", json={"reason": "تصحيح بعد المطابقة"}).status_code == 200
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").json()["code"] == "payroll_not_reconciled"
    trail = admin_client.get("/api/v1/audit", params={"entity_type": "settings", "entity_id": "payroll"}).json()
    assert any(e["after"].get("live_approval_enabled") is True for e in trail if e.get("after"))
