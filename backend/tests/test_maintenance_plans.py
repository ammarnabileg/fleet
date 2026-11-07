"""Maintenance plans: periodic schedules by date and by distance (due, overdue, or unknown when the reading they need
is missing: never guessed), done by a request's pickup or by hand; and a request's follow-up: priority, the user
responsible, the expected date, late and escalated alerts that close by themselves."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.maintenance import service
from tests.conftest import make_vehicle
from tests.test_maintenance import M, P, camera, make_setup, ready, receive, sent

S = f"{M}/schedules"


@pytest.fixture
def s(admin_client, client, new_client, company):
    return make_setup(admin_client, client, new_client, company)


def schedule(admin_client, vehicle, **body):
    r = admin_client.post(S, json={"vehicle_id": vehicle["id"], "title": "Oil"} | body)
    assert r.status_code == 201, r.text
    return r.json()


def alerts(admin_client, kind=None):
    rows = admin_client.get("/api/v1/alerts").json()
    return [a for a in rows if kind is None or a["kind"] == kind]


def test_schedules_by_date_and_by_distance(admin_client, client, db, s, company):
    v = s["vehicle"]  # read at 20,000 when handed over
    by_date = schedule(admin_client, v, title="Service", every_days=90, last_done_on=str(today() - timedelta(days=85)))
    assert (by_date["state"], by_date["days_left"], by_date["due_on"]) == (
        "due",
        5,
        str(today() + timedelta(days=5)),
    )
    oil = schedule(admin_client, v, every_km=5_000, last_done_km=15_500)
    assert (oil["state"], oil["due_km"], oil["km_left"], oil["current_km"]) == ("due", 20_500, 500, 20_000)
    tyres = schedule(admin_client, v, title="Tyres", kind="tyres", every_km=5_000, last_done_km=14_000)
    assert (tyres["state"], tyres["km_left"]) == ("overdue", -1_000)
    fresh = schedule(admin_client, v, title="Filter", every_km=10_000)  # counting from now: the last reading
    assert (fresh["last_done_km"], fresh["state"]) == (20_000, "ok")
    unread = make_vehicle(admin_client, company["id"], km=0)
    unknown = schedule(admin_client, unread, every_km=5_000)
    assert (unknown["state"], unknown["km_state"], unknown["due_km"]) == ("unknown", "no_baseline", None)

    r = admin_client.post(S, json={"vehicle_id": v["id"], "title": "oil", "every_days": 30})
    assert r.status_code == 409 and r.json()["code"] == "schedule_title_taken"
    r = admin_client.post(S, json={"vehicle_id": v["id"], "title": "Nothing"})
    assert r.status_code == 422 and r.json()["code"] == "schedule_interval_required"
    rows = admin_client.get(S, params={"vehicle_id": v["id"]}).json()
    assert [x["state"] for x in rows] == ["overdue", "due", "due", "ok"]
    assert [x["title"] for x in admin_client.get(S, params={"state": "unknown"}).json()] == ["Oil"]

    # the daily scan: once per situation, nothing for what cannot be known
    assert service.scan_due(db) == 3
    assert service.scan_due(db) == 0
    [over] = alerts(admin_client, "maintenance_overdue")
    assert over["entity_id"] == tyres["id"] and "19,000" in over["message"]
    assert len(alerts(admin_client, "maintenance_due")) == 2

    # a request carries out the tyres schedule: done when the driver collects the car, at his reading
    body = {"vehicle_id": v["id"], "center_id": s["center"]["id"], "kind": "tyres", "description": "Tyres"}
    r = admin_client.post(f"{M}/requests", json=body | {"schedule_id": unknown["id"]})
    assert r.status_code == 422 and r.json()["code"] == "schedule_other_vehicle"
    r = admin_client.post(f"{M}/requests", json=body | {"schedule_id": tyres["id"]})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["schedule"] == {"id": tyres["id"], "title": "Tyres"}
    r = admin_client.post(f"{M}/requests", json=body | {"schedule_id": tyres["id"]})
    assert r.status_code == 409 and r.json()["code"] == "schedule_has_request"
    [row] = [x for x in admin_client.get(S, params={"vehicle_id": v["id"]}).json() if x["id"] == tyres["id"]]
    assert row["open_request"]["id"] == rid
    receive(s, rid)
    ready(s, rid)
    pickup = {
        "odometer_km": 20_170,
        "odometer_photo": camera(client, s["h"]),
        "picked_up_at": datetime.now(UTC).isoformat(),
    }
    assert client.post(f"/api/v1/driver/maintenance/{rid}/picked-up", json=pickup, headers=s["h"]).status_code == 200
    [row] = [x for x in admin_client.get(S, params={"vehicle_id": v["id"]}).json() if x["id"] == tyres["id"]]
    assert (row["last_done_on"], row["last_done_km"], row["state"], row["open_request"]) == (
        str(today()),
        20_170,
        "ok",
        None,
    )
    assert alerts(admin_client, "maintenance_overdue") == []  # closed by itself

    # done by hand (another workshop): from that day on; never back in time
    r = admin_client.post(f"{S}/{by_date['id']}/done", json={"done_on": str(today())})
    assert (
        r.status_code == 200 and r.json()["state"] == "ok" and r.json()["due_on"] == str(today() + timedelta(days=90))
    )
    r = admin_client.post(f"{S}/{by_date['id']}/done", json={"done_on": str(today() - timedelta(days=1))})
    assert r.status_code == 422 and r.json()["code"] == "schedule_done_before_last"
    # stopped: out of the list and of the alerts
    r = admin_client.put(f"{S}/{oil['id']}", json={"version": oil["version"], "active": False})
    assert r.status_code == 200 and r.json()["state"] == "inactive"
    assert oil["id"] not in [x["id"] for x in admin_client.get(S).json()]
    assert alerts(admin_client, "maintenance_due") == []


def test_follow_up_late_escalated_and_closed_by_itself(admin_client, client, db, owner_db, s, new_client, company):
    [me] = admin_client.get(f"{M}/assignees").json()
    rid = sent(client, s)
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert (detail["priority"], detail["assignee"], detail["expected_ready_on"], detail["late"]) == (
        "normal",
        None,
        None,
        None,
    )
    body = {
        "version": detail["version"],
        "priority": "high",
        "assignee_id": me["id"],
        "expected_ready_on": str(today()),
    }
    r = admin_client.put(f"{M}/requests/{rid}/plan", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["priority"], out["assignee"]["id"], out["expected_ready_on"]) == ("high", me["id"], str(today()))
    r = admin_client.put(f"{M}/requests/{rid}/plan", json=body)
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    portal_user = s["portal"].get("/api/v1/auth/me").json()
    r = admin_client.put(
        f"{M}/requests/{rid}/plan", json={"version": out["version"], "assignee_id": portal_user["public_id"]}
    )
    assert r.status_code == 422 and r.json()["code"] == "assignee_not_allowed"

    # three days past its date: late, and escalated (two days by default)
    receive(s, rid)
    owner_db.execute(
        text("UPDATE maintenance.requests SET expected_ready_on = :d WHERE public_id = :r"),
        {"d": today() - timedelta(days=3), "r": rid},
    )
    owner_db.commit()
    assert service.scan_due(db) == 2
    assert service.scan_due(db) == 0
    [late] = alerts(admin_client, "maintenance_late")
    [esc] = alerts(admin_client, "maintenance_escalated")
    assert late["entity_id"] == rid and esc["params"]["assignee"] == me["name"]
    [row] = admin_client.get(f"{M}/requests", params={"late": True}).json()
    assert (row["id"], row["late"], row["escalated"]) == (rid, "expected", True)

    # the center gives a new date: the alerts close, the timeline says so
    r = s["portal"].post(f"{P}/requests/{rid}/expected", json={"expected_ready_on": str(today() - timedelta(days=1))})
    assert r.status_code == 422 and r.json()["code"] == "expected_in_past"
    r = s["portal"].post(f"{P}/requests/{rid}/expected", json={"expected_ready_on": str(today() + timedelta(days=2))})
    assert r.status_code == 200, r.text
    assert r.json()["events"][-1]["note"] == ":expected_date"
    assert alerts(admin_client, "maintenance_late") == alerts(admin_client, "maintenance_escalated") == []
    assert admin_client.get(f"{M}/requests", params={"late": True}).json() == []
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert (detail["late"], detail["escalated"], detail["expected_ready_on"]) == (
        None,
        False,
        str(today() + timedelta(days=2)),
    )

    # urgent and late: escalated at once
    owner_db.execute(
        text("UPDATE maintenance.requests SET expected_ready_on = :d WHERE public_id = :r"),
        {"d": today() - timedelta(days=1), "r": rid},
    )
    owner_db.commit()
    r = admin_client.put(f"{M}/requests/{rid}/plan", json={"version": detail["version"], "priority": "urgent"})
    assert r.status_code == 200 and r.json()["escalated"] is True
    assert len(alerts(admin_client, "maintenance_escalated")) == 1
    # ready: nothing is late any more
    ready(s, rid)
    assert alerts(admin_client, "maintenance_late") == alerts(admin_client, "maintenance_escalated") == []
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    r = admin_client.put(f"{M}/requests/{rid}/plan", json={"version": detail["version"], "priority": "low"})
    assert r.status_code == 200  # ready, not finished yet


def test_a_long_stay_with_no_expected_date_is_alerted(admin_client, client, db, owner_db, s):
    rid = sent(client, s)
    receive(s, rid)
    assert service.scan_due(db) == 0
    owner_db.execute(
        text("UPDATE maintenance.requests SET received_at = received_at - interval '8 days' WHERE public_id = :r"),
        {"r": rid},
    )
    owner_db.commit()
    assert service.scan_due(db) == 1
    [a] = alerts(admin_client, "maintenance_long_stay")
    assert a["entity_id"] == rid
    assert [x["late"] for x in admin_client.get(f"{M}/requests", params={"late": True}).json()] == ["long_stay"]
