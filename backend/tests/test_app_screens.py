"""The office decides what the driver app shows: screens hidden for this client (the server refuses them too, so an
older app or a direct call cannot use them) and a splash screen it designs as one image."""

import os
import uuid

import pytest

from tests.conftest import bearer, bind_device, jpeg, login, make_driver, make_user, upload

CONFIG = "/api/v1/driver/app-config"
SCREENS = {
    "daily_report": "/api/v1/driver/reports",
    "cash": "/api/v1/driver/cash",
    "maintenance": "/api/v1/driver/maintenance",
    "accidents": "/api/v1/driver/accidents",
    "fines": "/api/v1/driver/fines",
    "statement": "/api/v1/driver/statements",
    "payslips": "/api/v1/driver/payslips",
    "schemes": "/api/v1/driver/schemes",
}
SOME = uuid.uuid4()
SENDS = [  # what the driver sends from each screen
    "/api/v1/driver/reports",
    f"/api/v1/driver/cash/receipts/{SOME}/confirm",
    "/api/v1/driver/maintenance",
    "/api/v1/driver/accidents",
    f"/api/v1/driver/accidents/{SOME}/police-report",
    "/api/v1/driver/statements",
    "/api/v1/driver/scheme-requests",
]


def save(client, **value):
    version = client.get("/api/v1/settings").json()["driver_app"]["version"]
    return client.put("/api/v1/settings/driver_app", json={"version": version, "value": value})


@pytest.fixture
def driver(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    return bearer(bind_device(client, d["phone"]))


def test_every_screen_shows_until_the_office_hides_it_and_the_server_refuses_it_then(admin_client, client, driver):
    assert client.get(CONFIG).json() == {"phone_codes": True, "hidden_screens": [], "splash": None, "push": None}
    listed = admin_client.get("/api/v1/app-screens").json()
    assert set(listed["screens"]) == set(SCREENS) and {"sign_in", "day"} <= set(listed["locked"])
    for key, path in SCREENS.items():
        assert client.get(path, headers=driver).status_code == 200, key

    r = save(admin_client, hidden_screens=["maintenance", "fines", "maintenance"])
    assert r.status_code == 200 and r.json()["value"]["hidden_screens"] == ["fines", "maintenance"], r.text
    assert client.get(CONFIG).json()["hidden_screens"] == ["fines", "maintenance"]
    for key, path in SCREENS.items():
        r = client.get(path, headers=driver)
        if key in ("fines", "maintenance"):
            assert r.status_code == 403 and r.json()["code"] == "screen_off", key
        else:
            assert r.status_code == 200, key
    r = client.post("/api/v1/driver/maintenance", json={}, headers=driver)  # sending too, not only reading
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
    assert client.get("/api/v1/driver/maintenance/form", headers=driver).json()["code"] == "screen_off"
    r = client.post(f"/api/v1/driver/maintenance/{uuid.uuid4()}/picked-up", json={}, headers=driver)
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
    assert client.get("/api/v1/driver/today", headers=driver).status_code == 200  # the day itself is never hidden

    save(admin_client, hidden_screens=list(SCREENS))
    assert all(client.get(path, headers=driver).status_code == 403 for path in SCREENS.values())
    for path in SENDS:
        r = client.post(path, json={}, headers=driver)
        assert r.status_code == 403 and r.json()["code"] == "screen_off", path
    save(admin_client, hidden_screens=[])
    assert all(client.get(path, headers=driver).status_code == 200 for path in SCREENS.values())
    assert all(client.post(path, json={}, headers=driver).status_code in (404, 422) for path in SENDS)


def test_the_day_and_sign_in_cannot_be_hidden(admin_client):
    for locked in ("day", "sign_in", "onboarding", "anything"):
        r = save(admin_client, hidden_screens=[locked])
        assert r.status_code == 422 and r.json()["code"] == "invalid_settings", locked


def test_only_whoever_edits_the_settings_changes_the_app(admin_client, new_client):
    make_user(admin_client, "viewer", permissions=["settings.view"])
    c = new_client()
    login(c, "viewer")
    assert c.get("/api/v1/app-screens").status_code == 200
    assert save(c, hidden_screens=["fines"]).status_code == 403
    assert c.post("/api/v1/files", files={"file": ("s.jpg", jpeg(), "image/jpeg")}).status_code == 403
    make_user(admin_client, "designer", permissions=["settings.view", "settings.update"])
    c2 = new_client()
    login(c2, "designer")
    sha = upload(c2)  # whoever edits the settings uploads the splash image
    assert save(c2, splash_enabled=True, splash_image=sha).status_code == 200


def test_the_splash_screen_is_one_image_the_office_designs(admin_client, client):
    r = save(admin_client, splash_enabled=True)
    assert r.status_code == 422 and r.json()["code"] == "invalid_settings"  # an image is needed

    pdf = upload(admin_client, b"%PDF-1.4 " + os.urandom(32), name="splash.pdf")
    assert save(admin_client, splash_enabled=True, splash_image=pdf).status_code == 200
    assert client.get(CONFIG).json()["splash"] is None  # not an image: no splash rather than a broken one

    image = jpeg()
    sha = upload(admin_client, image)
    r = save(admin_client, splash_enabled=True, splash_image=sha, splash_color="#0A6CFF", splash_seconds=3)
    assert r.status_code == 200, r.text
    assert client.get(CONFIG).json()["splash"] == {"image": sha, "color": "#0A6CFF", "seconds": 3}
    r = client.get(f"/api/v1/driver/splash/{sha}")  # before sign-in: the app shows it when it opens
    assert r.status_code == 200 and r.content == image and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/v1/driver/splash/{pdf}").status_code == 404  # only the image set now

    save(admin_client, splash_enabled=False, splash_image=sha)
    assert client.get(CONFIG).json()["splash"] is None
    assert client.get(f"/api/v1/driver/splash/{sha}").status_code == 404
