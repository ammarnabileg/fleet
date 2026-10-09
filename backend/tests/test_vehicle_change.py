"""A change of vehicle names the other car (FR-ASG-04): the plate the driver types must be one of his company's
vehicles, typed with Arabic or Latin digits and any dash; the office sees the car asked for (free, or with whom) and
keeps every request, which it can filter and export."""

import io

import pytest
from openpyxl import load_workbook

from app.modules.fleet.service import normalize_plate
from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle

ASK = "/api/v1/driver/vehicle-change-requests"
V = "/api/v1/vehicle-change-requests"


def holding(admin_client, client, company, plate=None):
    """A driver on his phone, holding a vehicle."""
    d = make_driver(admin_client, company["id"])
    v = make_vehicle(admin_client, company["id"], **({"plate_number": plate} if plate else {}))
    hand_over(admin_client, v, d)
    return d, v, bearer(bind_device(client, d["phone"]))


@pytest.mark.parametrize(
    ("typed", "plate"),
    [
        ("١٢-٣٤٥٦٧", "12-34567"),
        ("۱۲-۳۴۵۶۷", "12-34567"),
        ("12–34567", "12-34567"),
        ("12− 34567", "12- 34567"),
        ("  12   ab  ", "12 AB"),
    ],
)
def test_the_plate_is_normalized(typed, plate):
    assert normalize_plate(typed) == plate


def test_a_vehicle_added_with_arabic_digits_is_kept_in_latin(admin_client, company):
    v = make_vehicle(admin_client, company["id"], plate_number="٤٥–٦٧٨")
    assert v["plate_number"] == "45-678"


@pytest.mark.parametrize("typed", ["٣٣-٤٤٥٥٦", "33–44556", "33 44556", "3344556", "33/44556", " 33-44556 "])
def test_the_other_car_found_however_he_types_its_plate(admin_client, client, company, typed):
    other = make_vehicle(admin_client, company["id"], plate_number="33-44556")
    _, _, h = holding(admin_client, client, company)
    r = client.post(ASK, headers=h, json={"requested_plate": typed, "reason": "الفرامل ضعيفة"})
    assert r.status_code == 201, r.text
    assert r.json()["change_request"]["requested_plate"] == other["plate_number"]


def test_a_plate_not_found_his_own_car_and_another_companys_car_are_refused(admin_client, client, companies):
    a, b = companies["a"], companies["b"]
    make_vehicle(admin_client, b["id"], plate_number="55-12345")
    d, v, h = holding(admin_client, client, a, plate="77-1")

    def ask(plate):
        return client.post(ASK, headers=h, json={"requested_plate": plate, "reason": "الفرامل ضعيفة"})

    for plate in ("99-99999", "55-12345"):  # unknown, or another company's: the same answer, he types it again
        r = ask(plate)
        assert r.status_code == 422 and r.json()["code"] == "vehicle_plate_not_found", r.text
    r = ask("٧٧-١")
    assert r.status_code == 422 and r.json()["code"] == "vehicle_change_same_vehicle"
    assert client.get("/api/v1/driver/vehicle", headers=h).json()["change_request"] is None
    assert admin_client.get(V, params={"status": "all"}).json() == []


def test_the_office_list_shows_the_car_asked_for_and_stays_in_its_companies(
    admin_client, client, new_client, companies
):
    a, b = companies["a"], companies["b"]
    d1, v1, h1 = holding(admin_client, client, a)
    d2, v2, h2 = holding(admin_client, client, a)
    d3, v3, h3 = holding(admin_client, client, b)
    free = make_vehicle(admin_client, b["id"], plate_number="88-100")
    # d1 asks for d2's car; d2 asks for d1's; d3 (company B) for a free one
    assert (
        client.post(ASK, headers=h1, json={"requested_plate": v2["plate_number"], "reason": "أقرب لبيتي"}).status_code
        == 201
    )
    assert (
        client.post(ASK, headers=h2, json={"requested_plate": v1["plate_number"], "reason": "أكبر"}).status_code == 201
    )
    assert client.post(ASK, headers=h3, json={"requested_plate": "88-100", "reason": "أحدث"}).status_code == 201

    everything = admin_client.get(V, params={"status": "all"}).json()
    assert [x["driver"]["id"] for x in everything] == [d3["id"], d2["id"], d1["id"]]  # newest first
    assert [x["driver"]["id"] for x in admin_client.get(V).json()] == [d1["id"], d2["id"], d3["id"]]  # the queue
    first = everything[2]
    assert first["requested_vehicle"]["id"] == v2["id"]
    assert first["requested_vehicle"]["holder"]["id"] == d2["id"]
    assert first["requested_vehicle"]["status"] == "assigned"
    assert everything[0]["requested_vehicle"] == {
        "found": True,
        "id": free["id"],
        "plate": "88-100",
        "status": "available",
        "holder": None,
    }

    # filters: a driver's requests, a vehicle's (held or asked for)
    assert [x["driver"]["id"] for x in admin_client.get(V, params={"status": "all", "driver_id": d2["id"]}).json()] == [
        d2["id"]
    ]
    by_car = admin_client.get(V, params={"status": "all", "vehicle_id": v1["id"]}).json()
    assert sorted(x["driver"]["id"] for x in by_car) == sorted([d1["id"], d2["id"]])
    assert admin_client.get(V, params={"status": "nope"}).status_code == 422
    page = admin_client.get(V, params={"status": "all", "limit": 1, "offset": 1}).json()
    assert [x["driver"]["id"] for x in page] == [d2["id"]]

    # a supervisor of company A sees only its requests, and cannot filter on company B's
    make_user(admin_client, "sup_a", permissions=["custody.view", "custody.assign"], company_ids=[a["id"]])
    sup = new_client()
    login(sup, "sup_a")
    assert sorted(x["driver"]["id"] for x in sup.get(V, params={"status": "all"}).json()) == sorted(
        [d1["id"], d2["id"]]
    )
    assert sup.get(V, params={"status": "all", "driver_id": d3["id"]}).status_code == 404
    assert sup.get(V, params={"status": "all", "vehicle_id": v3["id"]}).status_code == 404

    # the export: the same rows, in Excel
    r = sup.get(f"{V}/export", headers={"Accept-Language": "ar"})
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.values)
    assert rows[0][:4] == ("التاريخ", "السائق", "السيارة التي معه", "السيارة المطلوبة")
    assert len(rows) == 3
    assert {row[3] for row in rows[1:]} == {v1["plate_number"], v2["plate_number"]}
    assert {row[6] for row in rows[1:]} == {"قيد المراجعة"}
    assert any(str(row[4]).startswith("مع ") for row in rows[1:])
    assert sup.get(f"{V}/export", params={"driver_id": d3["id"]}).status_code == 404
