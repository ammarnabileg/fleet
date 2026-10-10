"""What the driver sees and asks for about himself in the app (BRD FR-APP-01/02/03/05, FR-ASG-04): his profile, the
vehicle he holds with its last reading and a change of vehicle asked for with his reason, his cash movements and a
warning before the limit, his documents and a renewal the office checks before it counts."""

from datetime import timedelta

from app.core.clock import today
from tests.conftest import (
    bearer,
    bind_device,
    hand_over,
    jpeg,
    login,
    make_driver,
    make_user,
    make_vehicle,
    upload,
)
from tests.test_payroll_runs import IBAN

V = "/api/v1/vehicle-change-requests"
RN = "/api/v1/documents/renewals"


def phone(admin_client, client, company, **extra):
    d = make_driver(admin_client, company["id"], **extra)
    return d, bearer(bind_device(client, d["phone"]))


def told(client, h) -> list[str]:
    return [n["kind"] for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"]]


def test_his_profile_without_the_full_iban(admin_client, client, company):
    platform = admin_client.post("/api/v1/payroll/platforms", json={"code": "px1", "name": {"ar": "منصة س", "en": "X"}})
    assert platform.status_code == 201, platform.text
    d, h = phone(
        admin_client,
        client,
        company,
        iban=IBAN,
        bank_name="الوطني",
        platform_id=platform.json()["id"],
        platform_driver_id="KT-77",
        civil_id="290010112345",
    )
    r = client.get("/api/v1/driver/profile", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["name"], p["employee_number"], p["civil_id"], p["platform_driver_id"]) == (
        d["name"],
        d["employee_number"],
        "290010112345",
        "KT-77",
    )
    assert p["company"] == company["name"] and p["platform"] == {"ar": "منصة س", "en": "X"}
    assert (p["bank_name"], p["iban_last4"]) == ("الوطني", IBAN[-4:])
    assert IBAN not in r.text
    assert client.get("/api/v1/driver/profile").status_code == 401


def test_my_car_and_a_change_of_vehicle_asked_for(admin_client, client, new_client, company):
    d, h = phone(admin_client, client, company)
    other = make_vehicle(admin_client, company["id"], plate_number="12-34567")
    assert client.get("/api/v1/driver/vehicle", headers=h).json() == {
        "vehicle": None,
        "change_request": None,
        "claim": None,
    }
    ask = {"requested_plate": "12-34567", "reason": "المكيف لا يعمل"}
    r = client.post("/api/v1/driver/vehicle-change-requests", headers=h, json=ask)
    assert r.status_code == 409 and r.json()["code"] == "no_open_custody"

    v = make_vehicle(admin_client, company["id"], km=33_000, make="Kia", model="Pegas", year=2023, color="أبيض")
    admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "vehicle",
            "owner_id": v["id"],
            "type_code": "registration",
            "expiry_date": str(today() + timedelta(days=200)),
            "file_sha256": upload(admin_client),
        },
    )
    hand_over(admin_client, v, d, km=33_010)
    mine = client.get("/api/v1/driver/vehicle", headers=h).json()
    car = mine["vehicle"]
    assert (car["plate_number"], car["make"], car["model"], car["year"], car["color"]) == (
        v["plate_number"],
        "Kia",
        "Pegas",
        2023,
        "أبيض",
    )
    assert car["last_odometer_km"] == 33_010 and car["last_reading_at"] is not None
    assert car["registration_expiry"] == str(today() + timedelta(days=200))

    # asked once, naming the other car, with the reason; the supervisor sees it
    url = "/api/v1/driver/vehicle-change-requests"
    assert client.post(url, headers=h, json={**ask, "reason": "x"}).status_code == 422
    assert client.post(url, headers=h, json={"reason": "المكيف لا يعمل"}).status_code == 422  # the plate is required
    assert client.post(url, headers=h, json={**ask, "requested_plate": "  "}).status_code == 422
    assert client.post(url, headers=h, json={**ask, "extra": 1}).status_code == 422
    r = client.post(url, headers=h, json=ask)
    assert r.status_code == 201, r.text
    assert (r.json()["change_request"]["status"], r.json()["change_request"]["requested_plate"]) == (
        "pending",
        "12-34567",
    )
    assert client.get("/api/v1/driver/vehicle", headers=h).json()["change_request"]["requested_plate"] == "12-34567"
    again = client.post(url, headers=h, json={**ask, "reason": "مرة ثانية"})
    assert again.status_code == 409 and again.json()["code"] == "vehicle_change_exists"
    make_user(admin_client, "sup5", permissions=["custody.view", "custody.assign"])
    sup = new_client()
    login(sup, "sup5")
    (alert,) = [a for a in sup.get("/api/v1/alerts").json() if a["kind"] == "vehicle_change_requested"]
    assert "المكيف لا يعمل" in alert["message"] and v["plate_number"] in alert["message"]
    assert "12-34567" in alert["message"]
    (req,) = sup.get(V).json()
    assert (req["vehicle_plate"], req["driver"]["id"], req["reason"]) == (v["plate_number"], d["id"], "المكيف لا يعمل")
    assert req["requested_plate"] == "12-34567"
    assert req["requested_vehicle"] == {
        "found": True,
        "id": other["id"],
        "plate": "12-34567",
        "status": "available",
        "holder": None,
    }

    # refused with the note the driver reads
    assert sup.post(f"{V}/{req['id']}/reject", json={}).json()["code"] == "reason_required"
    r = sup.post(f"{V}/{req['id']}/reject", json={"note": "يُصلح المكيف غداً"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert sup.post(f"{V}/{req['id']}/done", json={}).json()["code"] == "vehicle_change_decided"
    assert told(client, h)[0] == "vehicle_change_rejected"
    assert [a for a in sup.get("/api/v1/alerts").json() if a["kind"] == "vehicle_change_requested"] == []

    # asked again: the vehicle returned closes it as done
    client.post(url, headers=h, json={**ask, "reason": "المكيف ما زال معطلاً"})
    custody = admin_client.get("/api/v1/custodies", params={"open": "true"}).json()
    (c,) = [x for x in custody if x["vehicle"]["id"] == v["id"]]
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return", json={"odometer_km": 33_100, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text
    # every request, newest first, with who closed it
    history = sup.get(V, params={"status": ""}).json()
    assert [x["status"] for x in history] == ["done", "rejected"]
    assert [x["status"] for x in sup.get(V, params={"status": "all"}).json()] == ["done", "rejected"]
    assert history[1]["decided_by"] == "User sup5 (sup5)" and history[1]["note"] == "يُصلح المكيف غداً"
    assert history[0]["decided_by"] is not None and history[0]["decided_at"] is not None
    assert sup.get(V).json() == []
    assert told(client, h)[0] == "vehicle_change_done"


def test_his_cash_movements_and_the_warning_before_the_limit(admin_client, client, company):
    d, h = phone(admin_client, client, company)
    adjust = lambda amount, reason: admin_client.post(  # noqa: E731
        "/api/v1/cash/adjustments", json={"driver_id": d["id"], "amount": amount, "reason": reason}
    )
    assert adjust("50", "رصيد مرحّل").status_code == 201
    cash = client.get("/api/v1/driver/cash", headers=h).json()
    assert (cash["total"], cash["near_limit"]) == ("50.000", False)
    assert [(x["kind"], x["amount"], x["reason"]) for x in cash["lines"]] == [("adjustment", "50.000", "رصيد مرحّل")]
    adjust("14", "فرق عد")
    cash = client.get("/api/v1/driver/cash", headers=h).json()
    assert (cash["total"], cash["near_limit"]) == ("64.000", True)  # 80% of 80.000
    assert [x["amount"] for x in cash["lines"]] == ["14.000", "50.000"]  # newest first
    adjust("20", "فرق آخر")
    cash = client.get("/api/v1/driver/cash", headers=h).json()
    assert (cash["total"], cash["near_limit"]) == ("84.000", False)  # over it: the office is alerted instead


def test_his_documents_and_a_renewal_the_office_checks(admin_client, client, new_client, company):
    d, h = phone(admin_client, client, company)

    def add(type_code, days):
        r = admin_client.post(
            "/api/v1/documents",
            json={
                "owner_type": "employee",
                "owner_id": d["id"],
                "type_code": type_code,
                "number": type_code[:3].upper() + "-1",
                "expiry_date": str(today() + timedelta(days=days)),
                "file_sha256": upload(admin_client),
            },
        )
        assert r.status_code == 201, r.text

    add("residence", 10)
    add("passport", 900)
    docs = {x["type_code"]: x for x in client.get("/api/v1/driver/documents", headers=h).json()}
    assert (docs["residence"]["state"], docs["residence"]["days_left"]) == ("expiring", 10)
    assert docs["passport"]["state"] == "valid" and docs["driving_license"]["state"] == "missing"
    assert "contract" not in docs  # not his to send

    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("r.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    body = {"type_code": "residence", "number": "RES-2", "expiry_date": str(today() + timedelta(days=365))}
    send = lambda **b: client.post("/api/v1/driver/documents/renewals", headers=h, json=body | b)  # noqa: E731
    assert send(file_sha256=shot, expiry_date=str(today())).json()["code"] == "expiry_in_past"
    assert send(file_sha256=upload(admin_client)).json()["code"] == "file_not_yours"
    assert send(file_sha256=shot, type_code="registration").json()["code"] == "document_type_not_found"
    r = send(file_sha256=shot)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert send(file_sha256=shot).json()["code"] == "renewal_exists"
    assert client.get("/api/v1/driver/documents", headers=h).json()[0]["renewal"]["status"] == "pending"

    make_user(admin_client, "hr5", permissions=["documents.view", "documents.manage"])
    hr = new_client()
    login(hr, "hr5")
    assert [a["kind"] for a in hr.get("/api/v1/alerts").json()] == ["document_renewal_submitted"]
    (pending,) = hr.get(RN).json()
    assert (pending["driver"]["id"], pending["number"]) == (d["id"], "RES-2")
    assert hr.get(f"{RN}/{pending['id']}/file").status_code == 200
    assert hr.post(f"{RN}/{pending['id']}/reject", json={}).json()["code"] == "reason_required"
    r = hr.post(f"{RN}/{pending['id']}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert hr.post(f"{RN}/{pending['id']}/approve", json={}).json()["code"] == "renewal_decided"

    # it is now his current residence; the old one kept as history
    docs = {x["type_code"]: x for x in client.get("/api/v1/driver/documents", headers=h).json()}
    assert (docs["residence"]["state"], docs["residence"]["number"]) == ("valid", "RES-2")
    history = admin_client.get(
        "/api/v1/documents", params={"owner_type": "employee", "owner_id": d["id"], "history": "true"}
    ).json()
    assert sorted((x["number"], x["is_current"]) for x in history if x["type_code"] == "residence") == [
        ("RES-1", False),
        ("RES-2", True),
    ]
    assert told(client, h)[0] == "document_renewal_approved"
    assert hr.get("/api/v1/alerts").json() == []

    # a refused one: the driver reads why
    passport = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("p.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = send(type_code="passport", file_sha256=passport)
    hr.post(f"{RN}/{r.json()['id']}/reject", json={"note": "الصورة غير واضحة"})
    notice = client.get("/api/v1/driver/notifications", headers=h).json()["items"][0]
    assert notice["kind"] == "document_renewal_rejected" and "الصورة غير واضحة" in notice["message"]
