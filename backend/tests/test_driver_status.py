"""The driver's live status: separate states computed on the server, alerts several at once, the office's status
templates (validated, versioned, rolled back) and contact requests (acknowledged in the app, retry-safe)."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle, upload
from tests.test_reports_more import _id, reading
from tests.test_tracking import now, point, send

LIVE = "/api/v1/driver/live-status"


@pytest.fixture
def driver(admin_client, client, company, db):
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=3)).isoformat())
    headers = bearer(bind_device(client, d["phone"]))
    ids = _id(db, "fleet.vehicles", v["id"]), _id(db, "fleet.custodies", c["id"]), _id(db, "people.employees", d["id"])
    return {"vehicle": v, "driver": d, "custody": c, "headers": headers, "ids": ids}


def start_day(admin_client, db, driver, hours_ago=2):
    reading(db, *driver["ids"], "start_day", 10_010, now() - timedelta(hours=hours_ago), upload(admin_client))
    db.commit()


def ack(client, headers, request_id, ref):
    return client.post(f"/api/v1/driver/contact-requests/{request_id}/ack", headers=headers, json={"client_ref": ref})


def title(templates, code):
    return next(x for x in templates if x["code"] == code)["title"]["ar"]


def ask(admin_client, driver_id, message="x"):
    return admin_client.post(
        "/api/v1/driver-status/contact-requests", json={"driver_id": driver_id, "message": message}
    )


def codes(body):
    return [a["code"] for a in body["alerts"]]


def heartbeat(client, headers, **status):
    r = client.post("/api/v1/driver/status", headers=headers, json=status)
    assert r.status_code == 200, r.text


def test_separate_states_working_with_active_tracking(admin_client, client, db, driver):
    start_day(admin_client, db, driver)
    send(client, driver["headers"], [point(1, now() - timedelta(minutes=1))])
    heartbeat(client, driver["headers"], location_permission="always", gps_enabled=True, tracking_service_running=True)
    body = client.get(LIVE, headers=driver["headers"]).json()
    assert body["shift"]["state"] == "working" and body["shift"]["started_at"] and body["shift"]["duration"]
    assert body["vehicle"]["state"] == "available"
    assert body["vehicle"]["plate_number"] == driver["vehicle"]["plate_number"]
    assert body["tracking"]["state"] == "active" and body["tracking"]["last_update"]
    assert "location_problem" not in codes(body)
    assert body["config_version"] == 0 and body["min_app_template_version"] == 1
    # no cached version: the templates come with it; the cached one: nothing more
    assert {t["code"] for t in body["config"]["templates"]} >= {"shift_working", "contact_request", "location_problem"}
    again = client.get(LIVE, headers=driver["headers"], params={"config_version": 0}).json()
    assert again["config"] is None


def test_off_duty_and_stale_tracking_raise_a_location_problem(client, db, driver):
    # holding the car three hours, no point ever: stale, not live, whatever the notification says
    heartbeat(client, driver["headers"], location_permission="while_in_use", gps_enabled=False)
    body = client.get(LIVE, headers=driver["headers"]).json()
    assert body["shift"]["state"] == "off_duty" and body["shift"]["started_at"] is None
    assert body["tracking"]["state"] == "stale"
    problem = next(a for a in body["alerts"] if a["code"] == "location_problem")
    assert set(problem["data"]["reasons"]) == {"permission_denied", "gps_off", "stale"}
    assert problem["kind"] == "location" and problem["actions"] == ["open_location_settings"]


def test_no_custody_means_no_vehicle_and_tracking_off(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    headers = bearer(bind_device(client, d["phone"]))
    body = client.get(LIVE, headers=headers).json()
    assert body["vehicle"]["state"] == "none" and body["tracking"]["state"] == "off"
    assert "location_problem" not in codes(body)


def test_an_open_accident_is_a_breakdown(client, db, driver):
    db.execute(text("UPDATE fleet.vehicles SET status = 'accident' WHERE id = :v"), {"v": driver["ids"][0]})
    db.commit()
    assert client.get(LIVE, headers=driver["headers"]).json()["vehicle"]["state"] == "breakdown"


def test_several_alerts_at_once_most_important_first(admin_client, client, db, driver, monkeypatch):
    from app.modules.cash import service as cash
    from app.modules.driver_status import service

    monkeypatch.setattr(
        service.cash, "driver_balance", lambda db, employee_id: cash.Balance(Decimal("150.000"), Decimal("0"))
    )
    r = admin_client.post(
        "/api/v1/driver-status/contact-requests", json={"driver_id": driver["driver"]["id"], "message": "Call me"}
    )
    assert r.status_code == 201, r.text
    body = client.get(LIVE, headers=driver["headers"]).json()
    found = codes(body)
    assert {"contact_request", "custody_settlement", "location_problem"} <= set(found)
    priorities = [a["priority"] for a in body["alerts"]]
    assert priorities == sorted(priorities, reverse=True) and found[0] == "contact_request"
    settlement = next(a for a in body["alerts"] if a["code"] == "custody_settlement")
    assert settlement["values"]["amount"] == "150.000" and "150.000" in settlement["title"]
    contact = next(a for a in body["alerts"] if a["code"] == "contact_request")
    assert contact["data"]["message"] == "Call me" and contact["expires_at"]
    # the custody alert never replaces the tracking state: both are there
    assert body["tracking"]["state"] == "stale"


def test_an_expired_contact_request_is_hidden_from_the_driver(admin_client, client, db, driver):
    admin_client.post(
        "/api/v1/driver-status/contact-requests", json={"driver_id": driver["driver"]["id"], "message": "x"}
    )
    db.execute(text("UPDATE notifications.contact_requests SET created_at = now() - interval '2 days'"))
    db.commit()
    assert "contact_request" not in codes(client.get(LIVE, headers=driver["headers"]).json())
    # the office still sees it open, to close it
    assert admin_client.get("/api/v1/driver-status/contact-requests").json()[0]["status"] == "open"


def test_contact_request_flow_and_retry_safe_acknowledge(admin_client, client, db, driver):
    r = admin_client.post(
        "/api/v1/driver-status/contact-requests",
        json={"driver_id": driver["driver"]["id"], "message": "Please call", "reason": "route"},
    ).json()
    ref = str(uuid.uuid4())
    first = ack(client, driver["headers"], r["id"], ref)
    assert first.status_code == 200 and first.json()["status"] == "acknowledged"
    retry = ack(client, driver["headers"], r["id"], ref)
    assert retry.status_code == 200 and retry.json() == first.json()
    alerts = "SELECT count(*) FROM notifications.alerts WHERE kind = 'contact_acknowledged'"
    assert db.execute(text(alerts)).scalar() == 1
    assert "contact_request" not in codes(client.get(LIVE, headers=driver["headers"]).json())
    listed = admin_client.get("/api/v1/driver-status/contact-requests", params={"status": "all"}).json()
    assert listed[0]["status"] == "acknowledged" and listed[0]["acknowledged_at"]
    closed = admin_client.post(f"/api/v1/driver-status/contact-requests/{r['id']}/close").json()
    assert closed["status"] == "closed"
    # a late retry after the office closed it changes nothing
    late = ack(client, driver["headers"], r["id"], ref)
    assert late.status_code == 200 and late.json()["status"] == "closed"


def test_contact_requests_respect_permission_and_company_scope(admin_client, client, new_client, companies, driver):
    make_user(admin_client, "other_co", permissions=["tracking.live"], company_ids=[companies["b"]["id"]])
    c = new_client()
    login(c, "other_co")
    r = c.post("/api/v1/driver-status/contact-requests", json={"driver_id": driver["driver"]["id"], "message": "x"})
    assert r.status_code == 404
    mine = admin_client.post(
        "/api/v1/driver-status/contact-requests", json={"driver_id": driver["driver"]["id"], "message": "x"}
    ).json()
    assert c.post(f"/api/v1/driver-status/contact-requests/{mine['id']}/close").status_code == 404
    assert c.get("/api/v1/driver-status").json() == []
    make_user(admin_client, "no_live", permissions=["vehicles.view"])
    n = new_client()
    login(n, "no_live")
    assert n.get("/api/v1/driver-status/contact-requests").status_code == 403
    assert n.put("/api/v1/driver-status/templates/shift_working", json={}).status_code in (403, 422)
    # another driver cannot acknowledge his request
    other = make_driver(admin_client, companies["a"]["id"])
    headers = bearer(bind_device(client, other["phone"]))
    ack = client.post(
        f"/api/v1/driver/contact-requests/{mine['id']}/ack", headers=headers, json={"client_ref": str(uuid.uuid4())}
    )
    assert ack.status_code == 404


def test_the_panel_lists_each_drivers_states(admin_client, driver):
    rows = admin_client.get("/api/v1/driver-status").json()
    row = next(r for r in rows if r["driver"]["id"] == driver["driver"]["id"])
    assert row["shift"]["state"] == "off_duty" and row["tracking"]["state"] == "stale"
    assert row["vehicle"]["state"] == "available"


def _template(admin_client, code):
    t = next(x for x in admin_client.get("/api/v1/driver-status/templates").json()["templates"] if x["code"] == code)
    return {k: v for k, v in t.items() if k != "code"}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"kind": "rocket"}, "template_kind_unknown"),
        ({"icon": "skull"}, "template_icon_unknown"),
        ({"color": "red"}, "template_color_invalid"),
        ({"title": {"ar": "معك {cash}", "en": "x"}}, "template_variable_unknown"),
        ({"subtitle": {"ar": "{amount", "en": "x"}}, "template_text_invalid"),
        ({"actions": ["open_cash", "format_phone"]}, "template_action_unknown"),
        ({"actions": ["open_cash", "open_custody", "acknowledge", "open_contact"]}, "template_actions_too_many"),
        ({"visibility": "when_raining"}, "template_visibility_unknown"),
        ({"priority": 101}, "template_priority_invalid"),
        ({"audience": "company", "company_ids": []}, "template_audience_companies"),
    ],
)
def test_template_validation_rejects_what_the_app_cannot_render(admin_client, change, code):
    t = _template(admin_client, "custody_settlement") | change
    r = admin_client.put(
        "/api/v1/driver-status/templates/custody_settlement", json={"template": t, "config_version": 0}
    )
    assert r.status_code == 422 and r.json()["code"] == code, r.text
    preview = admin_client.post(
        "/api/v1/driver-status/templates/preview", json={"code": "custody_settlement", "template": t}
    )
    assert preview.status_code == 422


def test_publish_bumps_the_version_and_rollback_restores_the_previous(admin_client, client, driver):
    t = _template(admin_client, "custody_settlement")
    preview = admin_client.post(
        "/api/v1/driver-status/templates/preview",
        json={"code": "custody_settlement", "template": t | {"title": {"ar": "سلّم {amount}", "en": "In {amount}"}}},
    ).json()
    assert preview["title"] == "سلّم 125.500" and preview["kind"] == "custody"

    def publish(title, version):
        r = admin_client.put(
            "/api/v1/driver-status/templates/custody_settlement",
            json={"template": t | {"title": {"ar": title, "en": title}}, "config_version": version},
        )
        assert r.status_code == 200, r.text
        return r.json()

    assert publish("one {amount}", 0)["config_version"] == 1
    assert publish("two {amount}", 1)["config_version"] == 2
    stale = admin_client.put(
        "/api/v1/driver-status/templates/custody_settlement", json={"template": t, "config_version": 1}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "status_config_changed"
    body = client.get(LIVE, headers=driver["headers"], params={"config_version": 1}).json()
    assert body["config_version"] == 2
    assert title(body["config"]["templates"], "custody_settlement") == "two {amount}"

    back = admin_client.post("/api/v1/driver-status/templates/rollback", json={"config_version": 2}).json()
    assert back["config_version"] == 3 and back["history"][0]["restored_from"] == 1
    assert title(back["templates"], "custody_settlement") == "one {amount}"
    back = admin_client.post("/api/v1/driver-status/templates/rollback", json={"config_version": 3}).json()
    assert title(back["templates"], "custody_settlement") == "معك {amount} د.ك للتسوية"
    assert not back["can_rollback"]
    none_left = admin_client.post("/api/v1/driver-status/templates/rollback", json={"config_version": 4})
    assert none_left.status_code == 409


def test_an_inactive_or_other_company_template_hides_the_alert(admin_client, client, companies, driver):
    t = _template(admin_client, "location_problem")
    r = admin_client.put(
        "/api/v1/driver-status/templates/location_problem",
        json={"template": t | {"audience": "company", "company_ids": [companies["b"]["id"]]}, "config_version": 0},
    )
    assert r.status_code == 200, r.text
    body = client.get(LIVE, headers=driver["headers"]).json()
    assert "location_problem" not in codes(body)
    assert "location_problem" not in {x["code"] for x in body["config"]["templates"]}


def test_template_management_needs_the_settings_permission(admin_client, new_client):
    make_user(admin_client, "viewer", permissions=["settings.view"])
    c = new_client()
    login(c, "viewer")
    assert c.get("/api/v1/driver-status/templates").status_code == 200
    t = _template(admin_client, "shift_working")
    r = c.put("/api/v1/driver-status/templates/shift_working", json={"template": t, "config_version": 0})
    assert r.status_code == 403
    assert c.post("/api/v1/driver-status/templates/rollback", json={"config_version": 0}).status_code == 403


def test_the_live_stream_carries_driver_status_events(admin_client, driver, monkeypatch):
    from app.core import live

    published = []
    monkeypatch.setattr(live.broker(), "publish", lambda company, message: published.append(message))
    ask(admin_client, driver["driver"]["id"])
    assert published and published[-1]["event"] == "driver_status"
