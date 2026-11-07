"""A car handed to a driver while another driver holds it, or to a driver who holds one: in one step, at one moment.
release: the holder leaves the car (and the receiver gives his own back); swap: the two drivers exchange cars. One
reading per car serves its return and its handover, and the odometer rules accept it."""

from datetime import timedelta

from app.core.clock import utcnow
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload

T = "/api/v1/custodies/transfer"
CHECK = "/api/v1/custodies/transfer-check"


def custody(admin_client, vehicle):
    (c,) = [
        x
        for x in admin_client.get("/api/v1/custodies", params={"open": "true"}).json()
        if x["vehicle"]["id"] == vehicle["id"]
    ]
    return c


def detail(admin_client, c):
    return admin_client.get(f"/api/v1/custodies/{c['id']}").json()


def status(admin_client, vehicle):
    return admin_client.get(f"/api/v1/vehicles/{vehicle['id']}").json()["status"]


def told(client, h) -> list[str]:
    return [n["kind"] for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"]]


def held_an_hour(admin_client, vehicle, driver, km=None):
    return hand_over(admin_client, vehicle, driver, km=km, started_at=(utcnow() - timedelta(hours=1)).isoformat())


def test_release_takes_the_holder_out_and_hands_it_over_with_one_reading(admin_client, client, company):
    x = make_vehicle(admin_client, company["id"], km=50_000)
    b = make_driver(admin_client, company["id"])
    a = make_driver(admin_client, company["id"])
    hb = bearer(bind_device(client, b["phone"]))
    cb = held_an_hour(admin_client, x, b)

    check = admin_client.get(CHECK, params={"vehicle_id": x["id"], "driver_id": a["id"]}).json()
    assert check["holder"]["driver"]["id"] == b["id"] and check["holder"]["custody_id"] == cb["id"]
    assert check["driver_vehicle"] is None and check["modes_allowed"] == ["release"]
    # a plain handover is still refused: the office goes through the transfer
    r = admin_client.post(
        "/api/v1/custodies",
        json={"vehicle_id": x["id"], "driver_id": a["id"], "odometer_km": 50_020, "photo_sha256": upload(admin_client)},
    )
    assert r.status_code == 409 and r.json()["code"] == "vehicle_has_custody"

    front = upload(admin_client)
    body = {
        "vehicle_id": x["id"],
        "driver_id": a["id"],
        "mode": "release",
        "odometer_km": 50_020,
        "photo_sha256": upload(admin_client),
        "photos": [{"position": "front", "sha256": front}],
    }
    r = admin_client.post(T, json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert [c["driver"]["id"] for c in out["ended"]] == [b["id"]]
    assert [c["driver"]["id"] for c in out["started"]] == [a["id"]]
    assert out["ended"][0]["ended_at"] == out["started"][0]["started_at"]

    old, new = detail(admin_client, out["ended"][0]), detail(admin_client, out["started"][0])
    assert [(r["kind"], r["value_km"], r["flags"]) for r in old["readings"]] == [
        ("handover", 50_000, []),
        ("return", 50_020, []),
    ]
    assert [(r["kind"], r["value_km"], r["flags"]) for r in new["readings"]] == [("handover", 50_020, [])]
    assert old["photos"] == [{"stage": "return", "position": "front", "sha256": front}]
    assert new["photos"] == [{"stage": "handover", "position": "front", "sha256": front}]
    assert status(admin_client, x) == "assigned"
    assert custody(admin_client, x)["driver"]["id"] == a["id"]
    # one reading per moment: no review, no alert (the same photo is not "reused", the km do not go down)
    assert admin_client.get("/api/v1/odometer/readings", params={"review_status": "pending"}).json() == []
    assert told(client, hb)[0] == "vehicle_taken"
    assert client.get("/api/v1/driver/vehicle", headers=hb).json()["vehicle"] is None
    msg = client.get("/api/v1/driver/notifications", headers=hb).json()["items"][0]["message"]
    assert x["plate_number"] in msg


def test_release_when_the_receiver_holds_a_car_gives_it_back(admin_client, company):
    x = make_vehicle(admin_client, company["id"], km=10_000)
    y = make_vehicle(admin_client, company["id"], km=20_000)
    b, a = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    held_an_hour(admin_client, x, b)
    cy = held_an_hour(admin_client, y, a)
    check = admin_client.get(CHECK, params={"vehicle_id": x["id"], "driver_id": a["id"]}).json()
    assert check["modes_allowed"] == ["swap", "release"]
    assert (check["driver_vehicle"]["id"], check["driver_vehicle"]["custody_id"]) == (y["id"], cy["id"])
    assert check["driver_vehicle"]["last_odometer_km"] == 20_000

    body = {"vehicle_id": x["id"], "driver_id": a["id"], "mode": "release", "odometer_km": 10_050}
    r = admin_client.post(T, json=body | {"photo_sha256": upload(admin_client)})
    assert r.status_code == 422 and r.json()["code"] == "other_reading_required"
    r = admin_client.post(
        T,
        json=body
        | {
            "photo_sha256": upload(admin_client),
            "other_odometer_km": 20_070,
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 201, r.text
    assert sorted(c["vehicle"]["id"] for c in r.json()["ended"]) == sorted([x["id"], y["id"]])
    assert status(admin_client, y) == "available" and status(admin_client, x) == "assigned"
    assert custody(admin_client, x)["driver"]["id"] == a["id"]
    returned = detail(admin_client, cy)
    assert returned["ended_at"] is not None and returned["readings"][-1]["value_km"] == 20_070
    # nobody else holds a car twice: b has none, a has one
    opened = admin_client.get("/api/v1/custodies", params={"open": "true"}).json()
    assert sorted(c["driver"]["id"] for c in opened if c["vehicle"]["id"] in (x["id"], y["id"])) == [a["id"]]


def test_release_of_a_free_car_to_a_driver_who_holds_one(admin_client, company):
    x = make_vehicle(admin_client, company["id"], km=10_000)
    y = make_vehicle(admin_client, company["id"], km=20_000)
    a = make_driver(admin_client, company["id"])
    held_an_hour(admin_client, y, a)
    check = admin_client.get(CHECK, params={"vehicle_id": x["id"], "driver_id": a["id"]}).json()
    assert check["holder"] is None and check["modes_allowed"] == ["release"]
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": a["id"],
            "mode": "swap",
            "odometer_km": 10_000,
            "photo_sha256": upload(admin_client),
            "other_odometer_km": 20_010,
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "swap_needs_two_cars"
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": a["id"],
            "mode": "release",
            "odometer_km": 10_000,
            "photo_sha256": upload(admin_client),
            "other_odometer_km": 20_010,
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 201, r.text
    assert [c["vehicle"]["id"] for c in r.json()["ended"]] == [y["id"]]
    assert status(admin_client, y) == "available"
    # nobody busy: the dialog does a normal handover
    free = make_vehicle(admin_client, company["id"])
    other = make_driver(admin_client, company["id"])
    check = admin_client.get(CHECK, params={"vehicle_id": free["id"], "driver_id": other["id"]}).json()
    assert check == {"holder": None, "driver_vehicle": None, "modes_allowed": ["handover"]}


def test_swap_exchanges_the_two_cars_with_two_readings_each(admin_client, client, company):
    x = make_vehicle(admin_client, company["id"], km=30_000)
    y = make_vehicle(admin_client, company["id"], km=40_000)
    b, a = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    hb = bearer(bind_device(client, b["phone"]))
    cb = held_an_hour(admin_client, x, b)
    ca = held_an_hour(admin_client, y, a)
    at = (utcnow() - timedelta(minutes=10)).replace(microsecond=0)
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": a["id"],
            "mode": "swap",
            "started_at": at.isoformat(),
            "odometer_km": 30_040,
            "photo_sha256": upload(admin_client),
            "other_odometer_km": 40_060,
            "other_photo_sha256": upload(admin_client),
            "note": "تبديل بطلب السائقين",
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert len(out["ended"]) == 2 and len(out["started"]) == 2
    assert custody(admin_client, x)["driver"]["id"] == a["id"]
    assert custody(admin_client, y)["driver"]["id"] == b["id"]
    for c in (cb, ca):
        assert detail(admin_client, c)["ended_at"].startswith(at.isoformat()[:19])
    readings = {
        v["id"]: [
            (rd["kind"], rd["value_km"], rd["flags"])
            for rd in admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v["id"]}).json()
        ]
        for v in (x, y)
    }
    # newest first: the handover then the return at the same moment, both with the one reading
    assert readings[x["id"]][:2] == [("handover", 30_040, []), ("return", 30_040, [])]
    assert readings[y["id"]][:2] == [("handover", 40_060, []), ("return", 40_060, [])]
    assert status(admin_client, x) == status(admin_client, y) == "assigned"
    assert told(client, hb)[0] == "vehicle_swapped"
    assert client.get("/api/v1/driver/vehicle", headers=hb).json()["vehicle"]["plate_number"] == y["plate_number"]
    audit = admin_client.get("/api/v1/audit", params={"action": "custody.started", "limit": 50}).json()
    swapped = [e["after"] for e in audit if (e["after"] or {}).get("transfer") == "swap"]
    assert len(swapped) == 2 and {e["note"] for e in swapped} == {"تبديل بطلب السائقين"}
    assert len(admin_client.get("/api/v1/audit", params={"action": "custody.ended", "limit": 50}).json()) == 2


def test_the_odometer_rules_still_apply(admin_client, company):
    x = make_vehicle(admin_client, company["id"], km=60_000)
    b, a = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    held_an_hour(admin_client, x, b)
    body = {"vehicle_id": x["id"], "driver_id": a["id"], "mode": "release"}
    # backdated beyond the limit, before the holder's start, in the future: refused
    for at, code in (
        (utcnow() - timedelta(days=8), "time_too_old"),
        (utcnow() - timedelta(hours=2), "ended_before_start"),
        (utcnow() + timedelta(hours=1), "time_in_future"),
    ):
        r = admin_client.post(
            T, json=body | {"odometer_km": 60_010, "photo_sha256": upload(admin_client), "started_at": at.isoformat()}
        )
        assert r.status_code == 422 and r.json()["code"] == code, r.text
    # a reading below the last one goes through, flagged for review on the return and the handover
    r = admin_client.post(T, json=body | {"odometer_km": 59_000, "photo_sha256": upload(admin_client)})
    assert r.status_code == 201, r.text
    pending = admin_client.get("/api/v1/odometer/readings", params={"review_status": "pending"}).json()
    assert sorted(p["kind"] for p in pending) == ["return"]
    assert pending[0]["flags"] == ["lower_than_previous"]


def test_the_receivers_are_checked_and_the_same_driver_is_refused(admin_client, company):
    x = make_vehicle(admin_client, company["id"])
    y = make_vehicle(admin_client, company["id"])
    b, a = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    held_an_hour(admin_client, x, b)
    held_an_hour(admin_client, y, a)
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": b["id"],
            "mode": "release",
            "odometer_km": 10_000,
            "photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "transfer_same_driver"
    assert admin_client.get(CHECK, params={"vehicle_id": x["id"], "driver_id": b["id"]}).json()["modes_allowed"] == []
    # a photo that is not there: refused, and nothing changed
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": a["id"],
            "mode": "swap",
            "odometer_km": 10_010,
            "photo_sha256": "0" * 64,
            "other_odometer_km": 10_010,
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "file_not_found", r.text
    assert custody(admin_client, x)["driver"]["id"] == b["id"]
    assert custody(admin_client, y)["driver"]["id"] == a["id"]


def test_permission_and_company_scope(admin_client, new_client, companies):
    a_co, b_co = companies["a"], companies["b"]
    x = make_vehicle(admin_client, a_co["id"])
    holder, taker = make_driver(admin_client, a_co["id"]), make_driver(admin_client, a_co["id"])
    held_an_hour(admin_client, x, holder)
    other_x = make_vehicle(admin_client, b_co["id"])
    make_user(admin_client, "viewer_t", permissions=["custody.view"])
    make_user(admin_client, "sup_t", permissions=["custody.view", "custody.assign"], company_ids=[a_co["id"]])
    viewer = new_client()
    login(viewer, "viewer_t")
    body = {
        "vehicle_id": x["id"],
        "driver_id": taker["id"],
        "mode": "release",
        "odometer_km": 10_000,
        "photo_sha256": upload(admin_client),
    }
    assert viewer.post(T, json=body).status_code == 403
    assert viewer.get(CHECK, params={"vehicle_id": x["id"], "driver_id": taker["id"]}).status_code == 403
    sup = new_client()
    login(sup, "sup_t")
    assert sup.get(CHECK, params={"vehicle_id": other_x["id"], "driver_id": taker["id"]}).status_code == 404
    assert sup.post(T, json=body | {"vehicle_id": other_x["id"]}).status_code == 404
    # the receiver holds a car of a company out of the supervisor's scope: refused
    y_b = make_vehicle(admin_client, b_co["id"])
    held_an_hour(admin_client, y_b, taker)
    r = sup.post(
        T, json=body | {"photo_sha256": upload(sup), "other_odometer_km": 10_000, "other_photo_sha256": upload(sup)}
    )
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    # the check answers the same: nothing of a car outside his companies
    r = sup.get(CHECK, params={"vehicle_id": x["id"], "driver_id": taker["id"]})
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    assert custody(admin_client, x)["driver"]["id"] == holder["id"]


def test_the_driver_is_told_of_every_change_of_his_car(admin_client, client, company):
    """The app reads "my car" again on these notices: nothing of the car before stays on his phone."""
    x = make_vehicle(admin_client, company["id"], km=10_000)
    y = make_vehicle(admin_client, company["id"], km=20_000)
    a = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, a["phone"]))
    cy = held_an_hour(admin_client, y, a)
    assert told(client, h) == ["vehicle_handed_over"]
    r = admin_client.post(
        T,
        json={
            "vehicle_id": x["id"],
            "driver_id": a["id"],
            "mode": "release",
            "odometer_km": 10_000,
            "photo_sha256": upload(admin_client),
            "other_odometer_km": 20_010,
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 201, r.text
    assert told(client, h)[0] == "vehicle_handed_over"
    assert x["plate_number"] in client.get("/api/v1/driver/notifications", headers=h).json()["items"][0]["message"]
    c = custody(admin_client, x)
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return", json={"odometer_km": 10_030, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text
    assert told(client, h)[0] == "vehicle_returned"
    assert detail(admin_client, cy)["ended_at"] is not None


def test_a_transfer_cannot_end_a_custody_before_what_was_recorded_in_it(admin_client, client, company):
    x = make_vehicle(admin_client, company["id"], km=70_000)
    y = make_vehicle(admin_client, company["id"], km=80_000)
    b, a = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    hb, ha = bearer(bind_device(client, b["phone"])), bearer(bind_device(client, a["phone"]))
    held_an_hour(admin_client, x, b)
    held_an_hour(admin_client, y, a)

    def start_day(h, km, minutes_ago):
        photo = client.post("/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=h)
        at = (utcnow() - timedelta(minutes=minutes_ago)).isoformat()
        body = {"value_km": km, "photo_sha256": photo.json()["sha256"], "recorded_at": at}
        assert client.post("/api/v1/driver/odometer", json=body, headers=h).status_code == 201

    start_day(ha, 80_010, 10)  # only on Y: a swap ending both custodies must check both cars
    body = {
        "vehicle_id": x["id"],
        "driver_id": a["id"],
        "mode": "swap",
        "odometer_km": 70_020,
        "other_odometer_km": 80_030,
        "started_at": (utcnow() - timedelta(minutes=30)).isoformat(),
    }
    r = admin_client.post(
        T, json=body | {"photo_sha256": upload(admin_client), "other_photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 422 and r.json()["code"] == "transfer_before_last_reading", r.text
    start_day(hb, 70_010, 5)
    r = admin_client.post(
        T,
        json=body
        | {
            "started_at": (utcnow() - timedelta(minutes=8)).isoformat(),
            "photo_sha256": upload(admin_client),
            "other_photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "transfer_before_last_reading", r.text  # X's, this time
    r = admin_client.post(
        T,
        json=body
        | {"started_at": None, "photo_sha256": upload(admin_client), "other_photo_sha256": upload(admin_client)},
    )
    assert r.status_code == 201, r.text
