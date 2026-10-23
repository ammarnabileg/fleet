"""Fuel economy: litres per 100 km and cost per km from consecutive fills (a driver's approved claims, the fuel
expenses of a vehicle) whose odometer goes forward, agrees with the car's photographed readings, and whose litres are
known. Where the data does not allow it, no figure: the reasons instead."""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.core.clock import today, utcnow
from tests.conftest import hand_over, make_vehicle
from tests.test_finance import approve as approve_expense
from tests.test_finance import expense
from tests.test_fuel_claims import C, P, claim, driver_of, scheme

E = "/api/v1/cash/fuel-economy"
DAY = 24 * 60


@pytest.fixture
def world(admin_client, company):
    """A platform whose scheme puts fuel on the company."""
    r = admin_client.post(f"{P}/platforms", json={"code": "plat", "name": {"ar": "p", "en": "p"}, "pay_basic": False})
    assert r.status_code == 201, r.text
    platform = r.json()
    return {"platform": platform, "gas": scheme(admin_client, platform["id"], "gas", ["gas", "sim"])}


def approved(admin_client, client, s, **body):
    r = claim(client, s, **body)
    assert r.status_code == 201, r.text
    r = admin_client.post(f"{C}/{r.json()['id']}/approve", json={})
    assert r.status_code == 200, r.text
    return r.json()


def economy(admin_client, **params):
    r = admin_client.get(E, params={"from": str(today() - timedelta(days=30)), "to": str(today())} | params)
    assert r.status_code == 200, r.text
    return r.json()


def long_custody(admin_client, client, company, world):
    """A driver who has held his car for almost a week (claims may be up to a week old)."""
    s = driver_of(admin_client, client, company, world, custody=False)
    s["vehicle"] = make_vehicle(admin_client, company["id"], km=10_000)
    at = (utcnow() - timedelta(days=6, hours=20)).isoformat()
    hand_over(admin_client, s["vehicle"], s["driver"], km=10_000, started_at=at)
    return s


def test_litres_on_the_claim_and_the_price_per_litre(admin_client, client, company, world):
    s = driver_of(admin_client, client, company, world)
    r = claim(client, s, amount="5.000", litres="2.00")  # 2.500 a litre: a typo
    assert r.status_code == 422 and r.json()["code"] == "fuel_price_implausible"
    r = claim(client, s, amount="4.200", litres="40")
    assert r.status_code == 201 and r.json()["litres"] == "40.00"
    no_litres = claim(client, s, amount="3.000")  # an older app: none
    assert no_litres.status_code == 201 and no_litres.json()["litres"] is None
    [row] = [x for x in admin_client.get(C).json() if x["id"] == r.json()["id"]]
    assert (row["litres"], row["price_per_litre"]) == ("40.00", "0.105")
    # the accountant reads the litres from the receipt when the driver gave none
    out = admin_client.post(f"{C}/{no_litres.json()['id']}/approve", json={"litres": "30"}).json()
    assert (out["litres"], out["price_per_litre"]) == ("30.00", "0.100")


def test_consecutive_fills_give_the_figures_and_missing_litres_break_the_stretch(admin_client, client, company, world):
    s = long_custody(admin_client, client, company, world)
    approved(admin_client, client, s, amount="3.150", litres="30", odometer_km=10_100, minutes_ago=6 * DAY)
    approved(admin_client, client, s, amount="4.200", litres="40", odometer_km=10_500, minutes_ago=4 * DAY)
    approved(admin_client, client, s, amount="4.620", litres="44", odometer_km=10_900, minutes_ago=2 * DAY)
    approved(admin_client, client, s, amount="4.000", odometer_km=11_300, minutes_ago=DAY)  # no litres
    out = economy(admin_client)
    [v] = out["vehicles"]
    assert v["vehicle"]["id"] == s["vehicle"]["id"]
    # 84 litres over 800 km: the first fill only starts the distance, the last has no litres
    assert (v["stretches"], v["km"], v["litres"], v["l_per_100km"], v["cost_per_km"]) == (
        2,
        800,
        "84.00",
        "10.50",
        "0.011",
    )
    assert (v["fills"], v["fills_litres"], v["fills_odometer"]) == (4, 3, 4)
    assert v["skipped"] == {"no_litres": 1, "stretch_litres_missing": 1}
    assert out["fleet"]["l_per_100km"] == "10.50" and out["fleet"]["median_l_per_100km"] == "10.50"
    [d] = out["drivers"]
    assert (d["driver"]["id"], d["l_per_100km"], d["stretches"]) == (s["driver"]["id"], "10.50", 2)
    assert sum(m["km"] for m in out["months"]) == 800
    [x] = [e for e in out["exceptions"] if e.get("km") == 11_300]
    assert x["flags"] == ["no_litres", "stretch_litres_missing"]


def test_no_figure_from_untrustworthy_odometers_and_too_little_data(admin_client, client, company, world):
    s = long_custody(admin_client, client, company, world)
    # below the handover's photographed reading (10,000): contradicts the car's readings
    approved(admin_client, client, s, amount="3.150", litres="30", odometer_km=9_000, minutes_ago=6 * DAY)
    approved(admin_client, client, s, amount="4.200", litres="40", odometer_km=10_500, minutes_ago=5 * DAY)
    approved(admin_client, client, s, amount="4.200", litres="40", odometer_km=10_400, minutes_ago=4 * DAY)  # back
    approved(admin_client, client, s, amount="4.200", litres="40", minutes_ago=3 * DAY)  # no odometer
    approved(admin_client, client, s, amount="4.200", litres="40", odometer_km=10_700, minutes_ago=2 * DAY)
    out = economy(admin_client)
    [v] = out["vehicles"]
    # one stretch: 10,500 -> 10,700 with the two fills after it (the backwards one and the one with no odometer
    # still put fuel in) and its own: 120 litres over 200 km is not plausible
    assert v["l_per_100km"] is None and v["cost_per_km"] is None
    assert v["insufficient"] == "few_stretches"
    flags = {e["km"]: e["flags"] for e in out["exceptions"] if "km" in e}
    assert flags[9_000] == ["odometer_conflict"]
    assert flags[10_400] == ["odometer_backwards"]
    assert flags[None] == ["no_odometer"]
    assert flags[10_700] == ["implausible"]
    assert out["fleet"]["l_per_100km"] is None and out["fleet"]["insufficient"] == "few_stretches"


def test_fuel_expenses_of_a_vehicle_count_with_their_odometer(admin_client, company):
    v = make_vehicle(admin_client, company["id"], km=50_000)
    for days, km, litres, amount in (
        (20, 50_000, "40", "4.000"),
        (15, 50_450, "45", "4.500"),
        (10, 50_900, "45", "4.500"),
    ):
        approve_expense(
            admin_client,
            expense(
                admin_client,
                company["id"],
                payment_method="payable",
                expense_date=str(today() - timedelta(days=days)),
                amount=amount,
                quantity=litres,
                vehicle_id=v["id"],
                odometer_km=km,
            ),
        )
    r = admin_client.post(
        "/api/v1/finance/expenses",
        json={"company_id": company["id"], "type_id": 1, "expense_date": str(today()), "amount": "1",
              "payment_method": "payable", "odometer_km": 5},
    )  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "expense_odometer_needs_vehicle"
    out = economy(admin_client, vehicle_id=v["id"])
    [row] = out["vehicles"]
    assert (row["stretches"], row["km"], row["l_per_100km"], row["cost_per_km"]) == (2, 900, "10.00", "0.010")
    assert D(out["fleet"]["spent"]) == D("13.000")


def test_the_period_is_bounded(admin_client):
    r = admin_client.get(E, params={"from": str(today()), "to": str(today() - timedelta(days=1))})
    assert r.status_code == 422 and r.json()["code"] == "invalid_range"
