"""The contracted platforms section: the two core platforms built in (seeded, never deleted), others added and removed
by hand; a platform's drivers with their ID on it (linked inline, those missing listed); and a driver with no platform
picking his company in the app, as a request the office approves (his platform and ID set) or rejects with a reason,
his daily form following the company he picked while it waits and payroll reading only what the office set."""

from tests.conftest import bearer, bind_device, login, make_driver, make_user

P = "/api/v1/payroll"
D = "/api/v1/driver/platform-request"


def plats(c):
    return {p["code"]: p for p in c.get(f"{P}/platforms").json()}


def test_the_core_platforms_are_built_in_and_never_deleted(admin_client, company):
    seeded = plats(admin_client)
    assert seeded["keeta"]["is_core"] and seeded["talabat"]["is_core"]
    assert list(seeded)[:2] == ["keeta", "talabat"]  # listed first
    for code in ("keeta", "talabat"):
        r = admin_client.delete(f"{P}/platforms/{seeded[code]['id']}")
        assert r.status_code == 409 and r.json()["code"] == "platform_core"
    r = admin_client.post(f"{P}/platforms", json={"code": "extra", "name": {"ar": "إضافية", "en": "Extra"}})
    assert r.status_code == 201 and r.json()["is_core"] is False
    extra = r.json()
    used = admin_client.post(f"{P}/platforms", json={"code": "used", "name": {"ar": "مستخدمة", "en": "Used"}}).json()
    make_driver(admin_client, company["id"], platform_id=used["id"])
    r = admin_client.delete(f"{P}/platforms/{used['id']}")
    assert r.status_code == 409 and r.json()["code"] == "platform_in_use"
    assert admin_client.delete(f"{P}/platforms/{extra['id']}").status_code == 204
    assert "extra" not in plats(admin_client) and "used" in plats(admin_client)
    assert admin_client.delete(f"{P}/platforms/{extra['id']}").status_code == 404


def test_a_platforms_drivers_and_their_ids(admin_client, new_client, company):
    k = plats(admin_client)["keeta"]
    a = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="K-100")
    b = make_driver(admin_client, company["id"], platform_id=k["id"])
    other = make_driver(admin_client, company["id"])
    rows = admin_client.get(f"{P}/platforms/{k['id']}/drivers").json()
    assert {r["id"]: r["platform_driver_id"] for r in rows} == {a["id"]: "K-100", b["id"]: None}
    missing = admin_client.get(f"{P}/platforms/{k['id']}/drivers", params={"missing": "true"}).json()
    assert [r["id"] for r in missing] == [b["id"]]
    o = admin_client.get(f"{P}/platforms/{k['id']}/overview").json()
    assert (o["drivers"], o["with_driver_id"], o["missing_driver_id"], o["pending_requests"]) == (2, 1, 1, 0)
    assert o["platform"]["code"] == "keeta"

    url = f"{P}/platforms/{k['id']}/drivers"
    r = admin_client.put(f"{url}/{b['id']}", json={"platform_driver_id": " K-200 "})
    assert r.status_code == 200 and r.json()["platform_driver_id"] == "K-200", r.text
    r = admin_client.put(f"{url}/{b['id']}", json={"platform_driver_id": "k-100"})  # another driver's ID
    assert r.status_code == 409 and r.json()["code"] == "platform_driver_id_taken"
    r = admin_client.put(f"{url}/{other['id']}", json={"platform_driver_id": "K-300"})
    assert r.status_code == 409 and r.json()["code"] == "driver_not_on_platform"
    assert admin_client.get(f"/api/v1/employees/{b['id']}").json()["platform_driver_id"] == "K-200"
    assert admin_client.put(f"{url}/{b['id']}", json={"platform_driver_id": ""}).json()["platform_driver_id"] is None

    make_user(admin_client, "hubview", permissions=["payroll.view"])
    v = new_client()
    login(v, "hubview")
    assert v.get(url).status_code == 200 and v.get(f"{P}/platforms/{k['id']}/overview").status_code == 200
    r = v.put(f"{url}/{b['id']}", json={"platform_driver_id": "K-9"})
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert v.delete(f"{P}/platforms/{k['id']}").status_code == 403


def test_the_driver_picks_his_company_and_the_office_approves(admin_client, client, new_client, company):
    seeded = plats(admin_client)
    t, k = seeded["keeta"], seeded["talabat"]  # he picks keeta
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    view = client.get(D, headers=h).json()
    assert view["ask"] and view["platform"] is None and view["request"] is None
    assert [p["code"] for p in view["platforms"]][:2] == ["keeta", "talabat"]
    no_form = client.get("/api/v1/driver/reports/form", headers=h).json()

    r = client.post(D, headers=h, json={"platform_id": t["id"], "note": "من أول الشهر"})
    assert r.status_code == 201, r.text
    view = r.json()
    assert not view["ask"] and view["request"]["status"] == "pending" and view["request"]["platform"]["code"] == "keeta"
    again = client.post(D, headers=h, json={"platform_id": k["id"]})
    assert again.status_code == 409 and again.json()["code"] == "platform_request_pending"
    # while the office decides, his daily report asks the company he picked; payroll still has him on none
    form = client.get("/api/v1/driver/reports/form", headers=h).json()
    assert form["fields"] == t["daily_fields"] and form != no_form
    assert admin_client.get(f"/api/v1/employees/{d['id']}").json()["platform_id"] is None
    assert admin_client.get(f"{P}/platforms/{t['id']}/drivers").json() == []

    [alert] = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "platform_request"]
    assert alert["entity_id"] == view["request"]["id"]
    counts = admin_client.get(f"{P}/platform-requests/counts").json()
    assert counts["pending"] == 1 and counts["by_platform"] == {str(t["id"]): 1}
    [req] = admin_client.get(f"{P}/platform-requests", params={"status": "pending"}).json()
    assert req["employee"]["id"] == d["id"] and req["driver_note"] == "من أول الشهر"

    make_user(admin_client, "reqview", permissions=["payroll.view"])
    v = new_client()
    login(v, "reqview")
    assert v.get(f"{P}/platform-requests").status_code == 200
    assert v.post(f"{P}/platform-requests/{req['id']}/approve", json={}).status_code == 403

    r = admin_client.post(
        f"{P}/platform-requests/{req['id']}/approve", json={"version": req["version"], "platform_driver_id": "K-55"}
    )
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    e = admin_client.get(f"/api/v1/employees/{d['id']}").json()
    assert (e["platform_id"], e["platform_driver_id"]) == (t["id"], "K-55")
    assert not [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "platform_request"]
    told = client.get("/api/v1/driver/notifications", headers=h).json()["items"]
    assert told[0]["kind"] == "platform_request_approved"
    view = client.get(D, headers=h).json()
    assert view["platform"]["code"] == "keeta" and not view["ask"]
    r = admin_client.post(f"{P}/platform-requests/{req['id']}/reject", json={"note": "متأخر"})
    assert r.status_code == 409 and r.json()["code"] == "platform_request_decided"
    r = client.post(D, headers=h, json={"platform_id": k["id"]})
    assert r.status_code == 409 and r.json()["code"] == "platform_already_set"


def test_a_rejected_request_is_told_with_its_reason_and_he_picks_again(admin_client, client, company):
    k = plats(admin_client)["keeta"]
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    req = client.post(D, headers=h, json={"platform_id": k["id"]}).json()["request"]
    r = admin_client.post(f"{P}/platform-requests/{req['id']}/reject", json={"note": "no"})
    assert r.status_code == 422  # a reason of a few words at least
    r = admin_client.post(f"{P}/platform-requests/{req['id']}/reject", json={"note": "أنت على طلبات حسب كشف الشركة"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    view = client.get(D, headers=h).json()
    assert view["ask"] and view["request"]["status"] == "rejected"
    assert view["request"]["admin_note"] == "أنت على طلبات حسب كشف الشركة"
    told = client.get("/api/v1/driver/notifications", headers=h).json()["items"]
    assert told[0]["kind"] == "platform_request_rejected"
    assert admin_client.get(f"/api/v1/employees/{d['id']}").json()["platform_id"] is None

    t = plats(admin_client)["talabat"]
    second = client.post(D, headers=h, json={"platform_id": t["id"]}).json()["request"]
    r = client.post(f"{D}/{second['id']}/cancel", headers=h)  # he changes his mind before the office answers
    assert r.status_code == 200 and r.json()["ask"]
    assert client.post(f"{D}/{second['id']}/cancel", headers=h).json()["code"] == "platform_request_decided"
    third = client.post(D, headers=h, json={"platform_id": t["id"]}).json()["request"]
    # the office corrects the company he picked
    r = admin_client.post(f"{P}/platform-requests/{third['id']}/approve", json={"platform_id": k["id"]})
    assert r.status_code == 200 and r.json()["platform"]["code"] == "keeta"
    assert admin_client.get(f"/api/v1/employees/{d['id']}").json()["platform_id"] == k["id"]


def test_he_picks_a_scheme_with_his_company_and_it_is_set_when_the_office_approves(admin_client, client, company):
    from tests.test_scheme_blocks import from_template, platform

    k, other = platform(admin_client, "kpick"), platform(admin_client, "opick")
    s200 = from_template(admin_client, k, "keeta_fixed_200", "kpick_200")
    s165 = from_template(admin_client, k, "keeta_fixed_165", "kpick_165")
    elsewhere = from_template(admin_client, other, "keeta_fixed_140", "opick_140")
    off = admin_client.patch(f"{P}/schemes/{s165['id']}", json={"version": 1, "driver_selectable": False})
    assert off.status_code == 200, off.text
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))

    # before he is on the company: its schemes the drivers may pick, with their terms
    shown = client.get(f"{D}/{k['id']}/schemes", headers=h).json()
    assert [s["code"] for s in shown] == ["kpick_200"] and shown[0]["pay_kind"] == "fixed_salary" and shown[0]["blocks"]
    assert client.get(f"{D}/999999/schemes", headers=h).json()["code"] == "platform_not_found"

    for bad in (elsewhere, s165):  # another company's, one the office keeps to itself
        r = client.post(D, headers=h, json={"platform_id": k["id"], "scheme_id": bad["id"]})
        assert r.status_code == 422 and r.json()["code"] == "scheme_not_available", r.text
    r = client.post(D, headers=h, json={"platform_id": k["id"], "scheme_id": s200["id"]})
    assert r.status_code == 201 and r.json()["request"]["scheme"]["code"] == "kpick_200", r.text
    [req] = [x for x in admin_client.get(f"{P}/platform-requests", params={"status": "pending"}).json()
             if x["employee"]["id"] == d["id"]]  # fmt: skip
    assert req["scheme"]["code"] == "kpick_200"  # the office sees what he picked

    r = admin_client.post(f"{P}/platform-requests/{req['id']}/approve", json={"version": req["version"]})
    assert r.status_code == 200, r.text
    now = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [(x["scheme"]["code"], x["source"]) for x in now] == [("kpick_200", "registration")]
