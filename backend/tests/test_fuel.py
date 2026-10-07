"""Fuel (BRD FR-FUL-01..05, UAT-03): a fill from the app checked against its model's tank and fuels, the official
price of its day and the odometer; a clean one approved at once into a finance fuel expense, a flagged one held for the
accountant who decides with the reason; the consumption against the model's reference; prices from a date."""

from datetime import timedelta

from app.core.clock import today, utcnow
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload

F = "/api/v1/fuel"


def camera(client, h) -> str:
    r = client.post(
        "/api/v1/driver/files", params={"source": "camera"}, headers=h, files={"file": ("p.jpg", jpeg(), "image/jpeg")}
    )
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def setup(admin_client, client, company, *, make="Toyota", model="Yaris", km=10_000) -> dict:
    v = make_vehicle(admin_client, company["id"], km=km, make=make, model=model)
    d = make_driver(admin_client, company["id"])
    hand_over(admin_client, v, d, km=km, started_at=(utcnow() - timedelta(days=2)).isoformat())
    return {"vehicle": v, "driver": d, "h": bearer(bind_device(client, d["phone"]))}


def references(admin_client):
    r = admin_client.post(
        f"{F}/prices",
        json={"fuel_type": "super_95", "price": "0.105", "effective_from": str(today() - timedelta(days=30))},
    )
    assert r.status_code == 201, r.text
    r = admin_client.post(
        f"{F}/models",
        json={
            "make": "Toyota",
            "model": "Yaris",
            "tank_litres": "42",
            "fuel_types": ["super_95", "ultra_98"],
            "litres_per_100km": "6.0",
        },
    )
    assert r.status_code == 201, r.text


def fill(client, s, *, litres, amount, km, fuel="super_95", minutes_ago=10, invoice=None):
    body = {
        "filled_at": (utcnow() - timedelta(minutes=minutes_ago)).isoformat(),
        "litres": litres,
        "amount": amount,
        "fuel_type": fuel,
        "station": "KNPC Salmiya",
        "odometer_km": km,
        "invoice_sha256": invoice or camera(client, s["h"]),
        "odometer_sha256": camera(client, s["h"]),
    }
    return client.post("/api/v1/driver/fuel", headers=s["h"], json=body)


def alerts(admin_client, kind_text) -> list[dict]:
    return [
        a
        for a in admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
        if kind_text in a["message"]
    ]


def test_a_clean_fill_is_approved_at_once_into_a_fuel_expense(admin_client, client, company):
    references(admin_client)
    s = setup(admin_client, client, company)
    form = client.get("/api/v1/driver/fuel", headers=s["h"]).json()
    assert form["vehicle"] == {
        "plate_number": s["vehicle"]["plate_number"],
        "fuel_types": ["super_95", "ultra_98"],
        "tank_litres": "42.0",
        "last_km": 10_000,
    }

    r = fill(client, s, litres="30", amount="3.150", km=10_200, minutes_ago=600)
    assert r.status_code == 201, r.text
    first = r.json()
    assert (first["status"], first["flags"], first["price"], first["expected_amount"]) == (
        "approved",
        [],
        "0.105",
        "3.150",
    )
    assert first["decided_by"] is None and first["driver"]["id"] == s["driver"]["id"]
    [expense] = [
        e for e in admin_client.get("/api/v1/finance/expenses").json() if e["reference_no"] == f"FUEL-{first['number']}"
    ]
    assert (expense["status"], expense["amount"], expense["quantity"], expense["payment_method"]) == (
        "approved",
        "3.150",
        "30.00",
        "payable",
    )
    assert expense["vehicle"]["id"] == s["vehicle"]["id"] and expense["created_by"] is None  # the checks approved it

    # 300 km later 20 litres: 6.67 per 100 km, within 20% of the reference 6.0
    second = fill(client, s, litres="20", amount="2.100", km=10_500, minutes_ago=300).json()
    assert (second["status"], second["km_since"], second["litres_per_100km"]) == ("approved", 300, "6.67")
    assert alerts(admin_client, "L/100 km") == []
    # 200 km later 20 litres: 10 per 100 km, over 7.2
    third = fill(client, s, litres="20", amount="2.100", km=10_700, minutes_ago=60).json()
    assert third["litres_per_100km"] == "10.00"
    assert len(alerts(admin_client, "L/100 km")) == 1

    # the same invoice twice: refused (the phone's retry is safe, a second claim is not taken)
    r = fill(client, s, litres="5", amount="0.525", km=10_710, invoice=first["invoice_sha256"])
    assert r.status_code == 409 and r.json()["code"] == "fuel_fill_exists"

    report = admin_client.get(
        f"{F}/consumption", params={"date_from": str(today() - timedelta(days=1)), "date_to": str(today())}
    ).json()
    [row] = [x for x in report if x["vehicle"]["id"] == s["vehicle"]["id"]]
    # 40 litres after the first fill over 500 km: 8 per 100 km, 33.3% over the reference
    assert (row["fills"], row["litres"], row["km"], row["litres_per_100km"], row["over_percent"], row["over"]) == (
        3,
        "70.00",
        500,
        "8.00",
        "33.3",
        True,
    )


def test_uat03_a_flagged_fill_waits_for_the_accountant(admin_client, client, new_client, company):
    references(admin_client)
    s = setup(admin_client, client, company)
    big = fill(client, s, litres="55", amount="5.775", km=10_300).json()  # more than the 42-litre tank
    assert (big["status"], big["flags"]) == ("pending", ["over_tank"])
    assert not [
        e for e in admin_client.get("/api/v1/finance/expenses").json() if e["reference_no"] == f"FUEL-{big['number']}"
    ]
    assert len(alerts(admin_client, f"#{big['number']}")) == 1

    make_user(admin_client, "fuel_viewer", permissions=["fuel.view"])
    viewer = new_client()
    login(viewer, "fuel_viewer")
    assert viewer.post(f"{F}/fills/{big['id']}/approve", json={"note": "خزان إضافي"}).status_code == 403
    assert admin_client.post(f"{F}/fills/{big['id']}/approve", json={}).status_code == 422  # the reason is required
    r = admin_client.post(f"{F}/fills/{big['id']}/approve", json={"note": "خزان احتياطي مركّب في السيارة"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["decision_note"] == "خزان احتياطي مركّب في السيارة"
    assert [
        e for e in admin_client.get("/api/v1/finance/expenses").json() if e["reference_no"] == f"FUEL-{big['number']}"
    ]
    assert alerts(admin_client, f"#{big['number']}") == []  # resolved with the decision
    assert admin_client.post(f"{F}/fills/{big['id']}/reject", json={"note": "متأخر"}).status_code == 409

    wrong = fill(client, s, litres="30", amount="5.000", km=10_400, fuel="diesel")
    wrong = wrong.json()
    assert wrong["flags"] == ["wrong_fuel_type", "no_price"]  # diesel: not this model's, and no price set for it
    r = admin_client.post(f"{F}/fills/{wrong['id']}/reject", json={"note": "السيارة تعمل بالبنزين"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    told = client.get("/api/v1/driver/notifications", headers=s["h"]).json()["items"]
    assert told[0]["kind"] == "fuel_rejected" and "السيارة تعمل بالبنزين" in told[0]["message"]
    mine = client.get("/api/v1/driver/fuel", headers=s["h"]).json()["fills"]
    assert {x["number"]: (x["status"], x["reason"]) for x in mine}[wrong["number"]] == (
        "rejected",
        "السيارة تعمل بالبنزين",
    )
    again = fill(client, s, litres="30", amount="3.150", km=10_400, invoice=wrong["invoice_sha256"])
    assert again.status_code == 201  # a refused invoice may be sent again, corrected


def test_each_check_names_what_it_found(admin_client, client, company):
    references(admin_client)
    s = setup(admin_client, client, company)
    assert fill(client, s, litres="30", amount="3.300", km=10_100).json()["flags"] == ["price_mismatch"]  # 4.8% over
    assert fill(client, s, litres="30", amount="3.170", km=10_100).json()["flags"] == []  # within 1%
    assert fill(client, s, litres="10", amount="1.050", km=9_000).json()["flags"] == ["odometer_backwards"]
    assert fill(client, s, litres="10", amount="1.050", km=15_000).json()["flags"] == ["odometer_jump"]  # 400 a day
    assert fill(client, s, litres="10", amount="1.300", km=10_150, fuel="ultra_98").json()["flags"] == ["no_price"]
    gallery = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=s["h"],
        files={"file": ("g.jpg", jpeg(), "image/jpeg")},
    ).json()["sha256"]
    r = fill(client, s, litres="10", amount="1.050", km=10_160, invoice=gallery)
    assert r.status_code == 422 and r.json()["code"] == "photo_not_from_camera"  # the invoice photographed now
    other = setup(admin_client, client, company, make="Nissan", model="Sunny")
    assert fill(client, other, litres="30", amount="3.150", km=10_100).json()["flags"] == ["no_model"]


def test_the_office_enters_a_fill_and_prices_apply_from_their_date(admin_client, client, company):
    references(admin_client)
    s = setup(admin_client, client, company)
    r = admin_client.post(
        f"{F}/prices", json={"fuel_type": "super_95", "price": "0.115", "effective_from": str(today())}
    )
    assert r.status_code == 201 and r.json()["current"]["super_95"] == "0.115"
    r = admin_client.post(
        f"{F}/prices", json={"fuel_type": "super_95", "price": "0.120", "effective_from": str(today())}
    )
    assert r.status_code == 409 and r.json()["code"] == "fuel_price_exists"

    def office(at, litres, amount, km):
        return admin_client.post(
            f"{F}/fills",
            json={
                "vehicle_id": s["vehicle"]["id"],
                "filled_at": at.isoformat(),
                "litres": litres,
                "amount": amount,
                "fuel_type": "super_95",
                "odometer_km": km,
                "invoice_sha256": upload(admin_client),
            },
        )

    yesterday = office(utcnow() - timedelta(days=1), "20", "2.100", 10_100).json()  # yesterday's price, 0.105
    assert (yesterday["price"], yesterday["flags"], yesterday["source"]) == ("0.105", [], "office")
    assert yesterday["driver"]["id"] == s["driver"]["id"]  # he held the vehicle then
    now = office(utcnow(), "20", "2.300", 10_200).json()
    assert (now["price"], now["flags"]) == ("0.115", [])
    before = office(utcnow() - timedelta(days=5), "20", "2.100", 9_000).json()
    assert before["driver"] is None  # nobody held it five days ago

    models = admin_client.get(f"{F}/models").json()
    [yaris] = [m for m in models if m["model"] == "Yaris"]
    body = {
        "make": "Toyota",
        "model": "Yaris",
        "tank_litres": "45",
        "fuel_types": ["super_95"],
        "litres_per_100km": "6.5",
    }
    assert admin_client.put(f"{F}/models/{yaris['id']}", json=body | {"version": yaris["version"]}).status_code == 200
    r = admin_client.put(f"{F}/models/{yaris['id']}", json=body | {"version": yaris["version"]})
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"


def test_a_hidden_fuel_screen_is_refused_to_the_app(admin_client, client, company):
    s = setup(admin_client, client, company)
    current = admin_client.get("/api/v1/settings").json()["driver_app"]
    r = admin_client.put(
        "/api/v1/settings/driver_app",
        json={"version": current["version"], "value": current["value"] | {"hidden_screens": ["fuel"]}},
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/driver/fuel", headers=s["h"])
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
