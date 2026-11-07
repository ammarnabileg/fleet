"""Deleting a pay scheme from the panel: one with drivers on it from this month needs another scheme of the same
platform to move them to first; then one nothing ever used is deleted, one an earlier month used is retired (offered
no more, kept for those months)."""

from app.modules.payroll.service import add_months
from tests.conftest import make_driver
from tests.test_scheme_blocks import MONTH, P, assign, from_template, platform


def test_a_scheme_with_drivers_moves_them_then_is_retired_and_an_unused_one_is_deleted(admin_client, company):
    k, t = platform(admin_client, "krem"), platform(admin_client, "trem")
    a = from_template(admin_client, k, "keeta_fixed_200", "krem_200")
    b = from_template(admin_client, k, "keeta_fixed_165", "krem_165")
    other = from_template(admin_client, t, "talabat_fixed_350", "trem_350")
    unused = from_template(admin_client, k, "keeta_fixed_140", "krem_140")
    d = make_driver(admin_client, company["id"], platform_id=k["id"])
    assign(admin_client, a, d, month=add_months(MONTH, -1))  # on it since last month: a month used it

    r = admin_client.delete(f"{P}/schemes/{a['id']}")  # drivers on it: where do they go?
    assert r.status_code == 409 and r.json()["code"] == "scheme_has_drivers", r.text
    r = admin_client.delete(f"{P}/schemes/{a['id']}", params={"move_to": other["id"]})  # another platform's
    assert r.status_code == 422 and r.json()["code"] == "scheme_platform_mismatch"
    r = admin_client.delete(f"{P}/schemes/{a['id']}", params={"move_to": b["id"]})
    assert r.status_code == 200 and r.json() == {"deleted": False, "retired": True, "moved": 1, "skipped": []}, r.text
    now = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [(h["scheme"]["id"], h["valid_to"]) for h in now] == [(b["id"], None), (a["id"], str(MONTH))]
    listed = {s["id"]: s for s in admin_client.get(f"{P}/schemes", params={"platform_id": k["id"]}).json()}
    assert listed[a["id"]]["is_active"] is False  # kept, offered no more

    r = admin_client.delete(f"{P}/schemes/{unused['id']}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert unused["id"] not in {s["id"] for s in admin_client.get(f"{P}/schemes").json()}
