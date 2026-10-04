"""Driver self-registration: after the activation link the driver sends his data, documents, the vehicle he holds and
its photos; nothing is official until a reviewer approves, and approval applies everything at once or nothing."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core import messaging
from tests.conftest import bearer, hand_over, jpeg, login, make_driver, make_user, make_vehicle

PDF = b"%PDF-1.7\n" + b"1" * 50


def in_days(n):
    return str(date.today() + timedelta(days=n))


def activate(admin_client, client, driver, **link):
    out = admin_client.post(
        f"/api/v1/employees/{driver['id']}/activation-link", json={"channel": "manual", **link}
    ).json()
    r = client.post(
        "/api/v1/driver/auth/activate", json={"token": out["url"].split("#t=")[1], "device_uid": uuid.uuid4().hex}
    )
    assert r.status_code == 200, r.text
    return bearer(r.json()), out


def up(client, headers, *, source="camera", data=None):
    r = client.post(
        "/api/v1/driver/files",
        params={"source": source},
        headers=headers,
        files={"file": ("f", data or (jpeg() if source == "camera" else PDF), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def full_draft(client, h, plate, *, km=40_000, positions=("front", "back", "left", "right")):
    return {
        "civil_id": "290010112399",
        "nationality": "India",
        "documents": [
            {
                "type_code": t,
                "number": f"N-{t}",
                "expiry_date": in_days(300),
                "front_sha256": up(client, h, source="upload"),
                "back_sha256": up(client, h, source="upload"),
            }
            for t in ("residence", "driving_license", "passport")
        ],
        "vehicle": {
            "plate_number": plate,
            "odometer_km": km,
            "odometer_photo": up(client, h),
            "photos": [{"position": p, "sha256": up(client, h)} for p in positions],
        },
    }


def save(client, h, draft):
    r = client.put("/api/v1/driver/onboarding", json=draft, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def setup(admin_client, client, company):
    driver = make_driver(admin_client, company["id"])
    vehicle = make_vehicle(admin_client, company["id"], km=39_000, plate_number="45 678")
    h, link = activate(admin_client, client, driver)
    return {"driver": driver, "vehicle": vehicle, "h": h, "link": link}


def submission_id(admin_client):
    return admin_client.get("/api/v1/onboarding").json()[0]["id"]


def test_the_whole_registration_from_link_to_approval(admin_client, client, setup, db):
    d, v, h = setup["driver"], setup["vehicle"], setup["h"]
    assert setup["link"]["onboarding"] is True
    view = client.get("/api/v1/driver/onboarding", headers=h).json()
    assert view["required"] and view["status"] == "draft"
    assert view["required_documents"] == ["residence", "driving_license", "passport"]
    assert view["vehicle_photos"] == ["front", "back", "left", "right"]
    assert {t["code"] for t in view["document_types"]} >= {"residence", "civil_id", "driving_license"}
    save(client, h, full_draft(client, h, "45678"))  # spaces and case do not matter
    r = client.post("/api/v1/driver/onboarding/submit", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "submitted" and not r.json()["required"]
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["onboarding_submitted"]
    # nothing official yet
    assert admin_client.get(f"/api/v1/employees/{d['id']}").json()["civil_id"] is None
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["custody"] is None

    sid = submission_id(admin_client)
    detail = admin_client.get(f"/api/v1/onboarding/{sid}").json()
    assert detail["vehicle"] == {"found": True, "id": v["id"], "status": "available", "held_by_other": False}
    photo = detail["data"]["vehicle"]["photos"][0]["sha256"]
    assert admin_client.get(f"/api/v1/onboarding/{sid}/files/{photo}").status_code == 200
    assert admin_client.get(f"/api/v1/onboarding/{sid}/files/{'0' * 64}").status_code == 404

    r = admin_client.post(f"/api/v1/onboarding/{sid}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    emp = admin_client.get(f"/api/v1/employees/{d['id']}").json()
    assert (emp["civil_id"], emp["nationality"]) == ("290010112399", "India")
    docs = admin_client.get("/api/v1/documents", params={"owner_type": "employee", "owner_id": d["id"]}).json()
    assert sorted(x["type_code"] for x in docs) == ["driving_license", "passport", "residence"]
    assert all(x["has_file"] and x["has_back_file"] for x in docs)
    back = admin_client.get(f"/api/v1/documents/{docs[0]['id']}/file", params={"side": "back"})
    assert back.status_code == 200 and back.content == PDF
    vehicle = admin_client.get(f"/api/v1/vehicles/{v['id']}").json()
    assert vehicle["status"] == "assigned" and vehicle["custody"]["driver"]["id"] == d["id"]
    custody = admin_client.get(f"/api/v1/custodies/{vehicle['custody']['id']}").json()
    submitted_at = db.execute(text("SELECT submitted_at FROM onboarding.submissions")).scalar()
    assert datetime.fromisoformat(custody["started_at"]) == submitted_at  # from when the driver sent it
    assert [(x["kind"], x["value_km"]) for x in custody["readings"]] == [("handover", 40_000)]
    assert sorted(p["position"] for p in custody["photos"]) == ["back", "front", "left", "right"]
    assert admin_client.get(f"/api/v1/custodies/{custody['id']}/photos/{photo}").status_code == 200
    assert admin_client.get("/api/v1/alerts").json() == []  # the review alert closed itself
    assert "اعتماد" in messaging.provider().sent[-1].text and messaging.provider().sent[-1].to == d["phone"]
    after = client.get("/api/v1/driver/onboarding", headers=h).json()
    assert after["status"] == "approved" and not after["required"]
    assert client.post("/api/v1/driver/status", headers=h, json={}).json()["tracking_required"] is True


def test_submit_lists_what_is_missing(client, setup):
    h = setup["h"]
    draft = full_draft(client, h, "45678", positions=("front", "back"))
    draft["documents"] = draft["documents"][:2]  # no passport
    draft["documents"][0]["expiry_date"] = None
    save(client, h, draft)
    r = client.post("/api/v1/driver/onboarding/submit", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "onboarding_incomplete"
    assert (
        r.json()["params"]["missing"]
        == "document.passport, document.residence, vehicle.photo.left, vehicle.photo.right"
    )


def test_files_must_come_from_this_phone_and_vehicle_photos_from_its_camera(admin_client, client, setup, company):
    h = setup["h"]
    other = make_driver(admin_client, company["id"])
    h2, _ = activate(admin_client, client, other)
    foreign = up(client, h2)
    draft = full_draft(client, h, "45678")
    r = client.put(
        "/api/v1/driver/onboarding", headers=h, json=draft | {"vehicle": draft["vehicle"] | {"odometer_photo": foreign}}
    )
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    gallery = up(client, h, source="upload", data=jpeg())
    r = client.put(
        "/api/v1/driver/onboarding", headers=h, json=draft | {"vehicle": draft["vehicle"] | {"odometer_photo": gallery}}
    )
    assert r.status_code == 422 and r.json()["code"] == "photo_not_from_camera"
    r = client.post(
        "/api/v1/driver/files",
        params={"source": "camera"},
        headers=h,
        files={"file": ("x.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 415  # the camera gives images only


def test_the_vehicle_is_checked_when_the_driver_submits(admin_client, client, setup, company):
    h = setup["h"]
    save(client, h, full_draft(client, h, "99 999"))
    r = client.post("/api/v1/driver/onboarding/submit", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "plate_not_found" and r.json()["params"]["plate"] == "99 999"
    hand_over(admin_client, setup["vehicle"], make_driver(admin_client, company["id"]))
    save(client, h, full_draft(client, h, "45 678"))
    r = client.post("/api/v1/driver/onboarding/submit", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "vehicle_has_custody"


def test_reject_goes_back_to_the_driver_who_fixes_and_resends(admin_client, client, setup):
    h = setup["h"]
    save(client, h, full_draft(client, h, "45678"))
    client.post("/api/v1/driver/onboarding/submit", headers=h)
    r = client.put("/api/v1/driver/onboarding", json={}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "onboarding_not_open"  # under review
    sid = submission_id(admin_client)
    r = admin_client.post(f"/api/v1/onboarding/{sid}/reject", json={"reason": "صورة الإقامة غير واضحة"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    message = messaging.provider().sent[-1]
    assert message.to == setup["driver"]["phone"] and "صورة الإقامة غير واضحة" in message.text
    view = client.get("/api/v1/driver/onboarding", headers=h).json()
    assert view["required"] and view["status"] == "rejected" and view["review_note"] == "صورة الإقامة غير واضحة"
    save(client, h, full_draft(client, h, "45678"))
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).json()["status"] == "submitted"
    assert admin_client.post(f"/api/v1/onboarding/{sid}/approve").status_code == 200
    assert admin_client.post(f"/api/v1/onboarding/{sid}/reject", json={"reason": "late"}).status_code == 409


def test_approval_is_all_or_nothing(admin_client, client, setup, company, db):
    h, d = setup["h"], setup["driver"]
    draft = full_draft(client, h, "45678")
    draft["documents"][1]["expiry_date"] = in_days(-3)  # an expired driving licence
    save(client, h, draft)
    client.post("/api/v1/driver/onboarding/submit", headers=h)
    sid = submission_id(admin_client)
    r = admin_client.post(f"/api/v1/onboarding/{sid}/approve")
    assert r.status_code == 422 and r.json()["code"] == "driving_license_expired"
    assert admin_client.get(f"/api/v1/employees/{d['id']}").json()["civil_id"] is None
    assert db.execute(text("SELECT count(*) FROM documents.documents")).scalar() == 0
    assert admin_client.get(f"/api/v1/vehicles/{setup['vehicle']['id']}").json()["custody"] is None
    assert admin_client.get(f"/api/v1/onboarding/{sid}").json()["status"] == "submitted"


def test_photos_older_than_the_handover_limit_must_be_taken_again(admin_client, client, setup, db):
    h = setup["h"]
    save(client, h, full_draft(client, h, "45678"))
    client.post("/api/v1/driver/onboarding/submit", headers=h)
    db.execute(text("UPDATE onboarding.submissions SET submitted_at = now() - interval '8 days'"))
    db.commit()
    r = admin_client.post(f"/api/v1/onboarding/{submission_id(admin_client)}/approve")
    assert r.status_code == 422 and r.json()["code"] == "time_too_old"
    assert db.execute(text("SELECT count(*) FROM documents.documents")).scalar() == 0


def test_a_driver_without_a_vehicle_yet(admin_client, client, setup):
    h = setup["h"]
    draft = full_draft(client, h, "45678")
    save(client, h, draft | {"vehicle": None, "no_vehicle": True})
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).status_code == 200
    sid = submission_id(admin_client)
    assert admin_client.post(f"/api/v1/onboarding/{sid}/approve").status_code == 200
    assert admin_client.get(f"/api/v1/vehicles/{setup['vehicle']['id']}").json()["custody"] is None


def test_a_vehicle_already_handed_over_at_the_office_is_not_handed_over_twice(admin_client, client, setup):
    h = setup["h"]
    hand_over(
        admin_client, setup["vehicle"], setup["driver"], started_at=(datetime.now(UTC) - timedelta(hours=2)).isoformat()
    )
    save(client, h, full_draft(client, h, "45678"))
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).status_code == 200
    assert admin_client.post(f"/api/v1/onboarding/{submission_id(admin_client)}/approve").status_code == 200
    assert len(admin_client.get("/api/v1/custodies").json()) == 1


def test_required_items_come_from_the_settings(admin_client, client, setup):
    h = setup["h"]
    r = admin_client.put(
        "/api/v1/settings/onboarding",
        json={"version": 0, "value": {"required_documents": ["residence"], "vehicle_photos": ["front"]}},
    )
    assert r.status_code == 200
    from app.modules.org import service as org

    org._cache.clear()
    draft = full_draft(client, h, "45678", positions=("front",))
    draft["documents"] = draft["documents"][:1]
    save(client, h, draft)
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).status_code == 200


def test_a_phone_change_link_skips_registration(admin_client, client, setup):
    h = setup["h"]
    save(client, h, full_draft(client, h, "45678"))
    client.post("/api/v1/driver/onboarding/submit", headers=h)
    admin_client.post(f"/api/v1/onboarding/{submission_id(admin_client)}/approve")
    out = admin_client.post(f"/api/v1/employees/{setup['driver']['id']}/activation-link", json={}).json()
    assert out["onboarding"] is False  # registered already: a new phone only
    assert "أكمل بياناتك" not in messaging.provider().sent[-1].text


def test_review_needs_the_permission_and_follows_company_scope(admin_client, client, new_client, companies, db):
    d = make_driver(admin_client, companies["b"]["id"])
    activate(admin_client, client, d)
    sid = admin_client.get("/api/v1/onboarding", params={"status": "draft"}).json()[0]["id"]
    make_user(admin_client, "reviewer_a", permissions=["employees.onboarding"], company_ids=[companies["a"]["id"]])
    make_user(admin_client, "hr_view", permissions=["employees.view"])
    c = new_client()
    login(c, "reviewer_a")
    assert c.get("/api/v1/onboarding", params={"status": "draft"}).json() == []
    assert c.get(f"/api/v1/onboarding/{sid}").status_code == 404
    assert c.post(f"/api/v1/onboarding/{sid}/approve").status_code == 404
    c = new_client()
    login(c, "hr_view")
    assert c.get("/api/v1/onboarding").status_code == 403
    granted = (
        db.execute(
            text(
                "SELECT r.code FROM identity.role_permissions p JOIN identity.roles r ON r.id = p.role_id "
                "WHERE p.permission = 'employees.onboarding' AND r.code NOT LIKE 'role_%' ORDER BY r.code"
            )
        )
        .scalars()
        .all()
    )
    assert granted == ["hr", "supervisor"]
