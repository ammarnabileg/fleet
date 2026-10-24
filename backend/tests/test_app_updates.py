"""The driver app's in-app updates: APK uploads read and checked, publish/unpublish, required, the app's check."""

import pytest

from app.modules.app_updates import apk
from tests.conftest import bearer, bind_device, make_driver, make_user

PKG = "com.example.fleet.driver"


@pytest.fixture(autouse=True)
def package(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "android_package", PKG)


def put_apk(client, code, *, package=PKG, name=None, data=None):
    body = data if data is not None else apk.build_apk(package, code, name or f"0.{code}.0")
    return client.post("/api/v1/app-releases", files={"file": ("app.apk", body, "application/octet-stream")})


def release(client, code, *, publish=True, required=False):
    r = put_apk(client, code)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    if required:
        assert client.patch(f"/api/v1/app-releases/{rid}", json={"required": True}).status_code == 200
    if publish:
        assert client.post(f"/api/v1/app-releases/{rid}/publish").status_code == 200
    return r.json()


def check(client, code, **params):
    r = client.get("/api/v1/driver/app-update", params={"version_code": code, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_manifest_reader_round_trip():
    info = apk.read(apk.build_apk(PKG, 123, "1.2.3"))
    assert (info.package, info.version_code, info.version_name) == (PKG, 123, "1.2.3")


def test_upload_reads_the_apk(admin_client):
    r = put_apk(admin_client, 7, name="0.2.0")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version_code"] == 7 and body["version_name"] == "0.2.0" and body["package"] == PKG
    assert body["status"] == "draft" and body["required"] is False and len(body["sha256"]) == 64
    f = admin_client.get(f"/api/v1/app-releases/{body['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"PK")


@pytest.mark.parametrize(
    "data,code",
    [
        (b"%PDF-1.4 not an apk", "apk_not_zip"),
        (b"PK\x03\x04broken zip", "apk_not_zip"),
        (None, "apk_no_manifest"),
        (b"garbage", "apk_not_zip"),
    ],
)
def test_upload_refuses_what_is_not_an_apk(admin_client, data, code):
    if data is None:  # a real zip without a manifest
        import io
        import zipfile

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("classes.dex", b"dex")
        data = out.getvalue()
    r = put_apk(admin_client, 1, data=data)
    assert r.status_code == 422 and r.json()["code"] == code


def test_upload_refuses_an_unreadable_manifest(admin_client):
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("AndroidManifest.xml", b"<manifest package='x'/>")  # text, not compiled
    r = put_apk(admin_client, 1, data=out.getvalue())
    assert r.status_code == 422 and r.json()["code"] == "apk_manifest_unreadable"


def test_upload_refuses_another_package(admin_client):
    r = put_apk(admin_client, 5, package="com.other.app")
    assert r.status_code == 422
    assert r.json()["code"] == "apk_wrong_package"
    assert r.json()["params"] == {"expected": PKG, "got": "com.other.app"}


def test_the_dashboard_setting_names_the_package(admin_client):
    s = admin_client.get("/api/v1/settings").json()["driver_app"]
    r = admin_client.put(
        "/api/v1/settings/driver_app",
        json={"version": s["version"], "value": s["value"] | {"android_package": "com.other.app"}},
    )
    assert r.status_code == 200, r.text
    assert put_apk(admin_client, 5).json()["code"] == "apk_wrong_package"
    assert put_apk(admin_client, 5, package="com.other.app").status_code == 201


def test_version_must_be_higher_than_the_latest_published(admin_client):
    release(admin_client, 10)
    for code in (9, 10):
        r = put_apk(admin_client, code)
        assert r.status_code == 422 and r.json()["code"] == "apk_version_not_higher", r.text
    assert put_apk(admin_client, 11).status_code == 201
    r = put_apk(admin_client, 11)
    assert r.status_code == 409 and r.json()["code"] == "app_release_exists"


def test_driver_check_without_and_with_a_newer_version(admin_client, client):
    assert check(client, 1) == {"latest": None, "required": False}
    draft = release(admin_client, 20, publish=False)
    assert check(client, 1)["latest"] is None  # a draft is not offered
    admin_client.patch(f"/api/v1/app-releases/{draft['id']}", json={"notes": {"ar": "إصلاحات", "en": "Fixes"}})
    admin_client.post(f"/api/v1/app-releases/{draft['id']}/publish")
    body = check(client, 19, lang="en")
    assert body["required"] is False
    latest = body["latest"]
    assert latest["version_code"] == 20 and latest["notes"] == "Fixes" and latest["sha256"] == draft["sha256"]
    assert latest["size"] == draft["size_bytes"] and latest["url"] == "/api/v1/driver/app-update/20.apk"
    assert check(client, 19, lang="ar")["latest"]["notes"] == "إصلاحات"
    assert check(client, 19, lang="fr")["latest"]["notes"] == "Fixes"  # no French notes: English
    assert check(client, 20) == {"latest": None, "required": False}
    assert check(client, 25) == {"latest": None, "required": False}

    f = client.get(latest["url"])
    assert f.status_code == 200 and len(f.content) == latest["size"]
    part = client.get(latest["url"], headers={"Range": "bytes=10-"})
    assert part.status_code == 206 and part.content == f.content[10:]  # a cut download resumes

    admin_client.post(f"/api/v1/app-releases/{draft['id']}/unpublish")
    assert check(client, 19)["latest"] is None
    assert client.get(latest["url"]).status_code == 404


def test_required_logic(admin_client, client):
    release(admin_client, 30, required=True)
    release(admin_client, 31)
    assert check(client, 29) == check(client, 29) and check(client, 29)["required"] is True
    assert check(client, 29)["latest"]["version_code"] == 31  # the newest, and required because 30 is
    assert check(client, 30)["required"] is False  # has the required one: 31 is optional
    assert check(client, 30)["latest"]["version_code"] == 31
    r = admin_client.get("/api/v1/app-releases").json()
    rid = next(x["id"] for x in r["releases"] if x["version_code"] == 30)
    admin_client.patch(f"/api/v1/app-releases/{rid}", json={"required": False})
    assert check(client, 29)["required"] is False


def test_a_draft_may_be_deleted_not_a_published_one(admin_client):
    d = release(admin_client, 40, publish=False)
    p = release(admin_client, 41)
    r = admin_client.delete(f"/api/v1/app-releases/{p['id']}")
    assert r.status_code == 409 and r.json()["code"] == "app_release_published"
    assert admin_client.delete(f"/api/v1/app-releases/{d['id']}").status_code == 204
    assert [x["version_code"] for x in admin_client.get("/api/v1/app-releases").json()["releases"]] == [41]


def test_installed_counts_and_drivers_behind(admin_client, client, company):
    release(admin_client, 50)
    on_new, on_old, too_old = (make_driver(admin_client, company["id"]) for _ in range(3))
    for d, version in ((on_new, "0.5.0+50"), (on_old, "0.4.0+49"), (too_old, "0.1.0")):
        tokens = bind_device(client, d["phone"])
        r = client.post("/api/v1/driver/status", headers=bearer(tokens), json={"app_version": version})
        assert r.status_code == 200, r.text
    body = admin_client.get("/api/v1/app-releases").json()
    assert body["latest"] == 50 and body["package"] == PKG
    assert body["releases"][0]["installed"] == 1 and body["unknown_version"] == 1
    by_id = {x["id"]: x for x in body["drivers"]}
    assert by_id[on_new["id"]]["outdated"] is False and by_id[on_new["id"]]["version_code"] == 50
    assert by_id[on_old["id"]]["outdated"] is True and by_id[on_old["id"]]["version_code"] == 49
    assert by_id[too_old["id"]]["outdated"] is True and by_id[too_old["id"]]["version_code"] is None
    assert body["drivers"][-1]["id"] == on_new["id"]  # the ones behind first


def test_permissions(admin_client, client, new_client):
    from tests.conftest import login

    rid = release(admin_client, 60, publish=False)["id"]
    make_user(admin_client, "viewer", permissions=["settings.view"])
    make_user(admin_client, "nobody", permissions=["vehicles.view"])
    viewer, nobody = new_client(), new_client()
    login(viewer, "viewer")
    login(nobody, "nobody")
    assert viewer.get("/api/v1/app-releases").status_code == 200
    assert viewer.get(f"/api/v1/app-releases/{rid}/file").status_code == 200
    assert put_apk(viewer, 61).status_code == 403
    assert viewer.post(f"/api/v1/app-releases/{rid}/publish").status_code == 403
    assert viewer.patch(f"/api/v1/app-releases/{rid}", json={"required": True}).status_code == 403
    assert viewer.delete(f"/api/v1/app-releases/{rid}").status_code == 403
    assert nobody.get("/api/v1/app-releases").status_code == 403
    assert new_client().get("/api/v1/app-releases").status_code == 401
    # the app asks before sign-in too
    assert client.get("/api/v1/driver/app-update", params={"version_code": 1}).status_code == 200


def test_the_check_is_rate_limited(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_app_update_per_15min", 3)
    codes = [client.get("/api/v1/driver/app-update", params={"version_code": 1}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
