from sqlalchemy import text

from tests.conftest import login, make_user


def test_public_languages_and_catalog_with_etag(client):
    langs = client.get("/api/v1/i18n/languages").json()
    assert [(lang["code"], lang["direction"], lang["is_default"]) for lang in langs] == [
        ("ar", "rtl", True),
        ("en", "ltr", False),
    ]
    r = client.get("/api/v1/i18n/catalog/ar", params={"ns": "errors,common"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["messages"]) == {"common", "errors"} and body["direction"] == "rtl"
    assert body["messages"]["errors"]["invalid_credentials"] == "اسم المستخدم أو كلمة المرور غير صحيحة"
    again = client.get(
        "/api/v1/i18n/catalog/ar", params={"ns": "errors,common"}, headers={"If-None-Match": r.headers["ETag"]}
    )
    assert again.status_code == 304
    assert client.get("/api/v1/i18n/catalog/xx").status_code == 404


def test_overrides_change_text_and_revision(admin_client, client, db):
    before = client.get("/api/v1/i18n/catalog/en").json()
    r = admin_client.put(
        "/api/v1/i18n/admin/overrides/en", json={"items": [{"namespace": "common", "key": "save", "value": "Store"}]}
    )
    assert r.status_code == 200 and r.json()["revision"] == before["revision"] + 1
    after = client.get("/api/v1/i18n/catalog/en").json()
    assert after["messages"]["common"]["save"] == "Store"
    assert db.execute(text("SELECT count(*) FROM audit.events WHERE action = 'translations.saved'")).scalar() == 1
    assert admin_client.delete("/api/v1/i18n/admin/overrides/en/common/save").status_code == 204
    assert client.get("/api/v1/i18n/catalog/en").json()["messages"]["common"]["save"] == "Save"


def test_overrides_are_validated(admin_client):
    r = admin_client.put(
        "/api/v1/i18n/admin/overrides/en", json={"items": [{"namespace": "common", "key": "no_such_key", "value": "x"}]}
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_translation_key"
    r = admin_client.put(
        "/api/v1/i18n/admin/overrides/en", json={"items": [{"namespace": "common", "key": "welcome", "value": "Hello"}]}
    )
    assert r.status_code == 422 and r.json()["code"] == "placeholder_mismatch"
    assert r.json()["params"]["placeholders"] == "{name}"
    r = admin_client.put(
        "/api/v1/i18n/admin/overrides/en",
        json={"items": [{"namespace": "common", "key": "welcome", "value": "Hello {name}"}]},
    )
    assert r.status_code == 200


def test_new_language_without_deploy_falls_back(admin_client, client):
    r = admin_client.post(
        "/api/v1/i18n/admin/languages",
        json={"code": "ur", "name_native": "اردو", "name_en": "Urdu", "direction": "rtl", "fallback_code": "en"},
    )
    assert r.status_code == 201, r.text
    ur = client.get("/api/v1/i18n/catalog/ur").json()["messages"]
    assert ur["common"]["save"] == "Save"  # nothing translated yet: English, its fallback
    missing = admin_client.get("/api/v1/i18n/admin/entries/ur", params={"missing": True}).json()
    assert len(missing) > 100 and all(e["override"] is None for e in missing)
    admin_client.post("/api/v1/i18n/admin/import/ur", json={"common": {"save": "محفوظ کریں"}})
    assert client.get("/api/v1/i18n/catalog/ur").json()["messages"]["common"]["save"] == "محفوظ کریں"
    still_missing = admin_client.get("/api/v1/i18n/admin/entries/ur", params={"missing": True}).json()
    assert len(still_missing) == len(missing) - 1
    exported = admin_client.get("/api/v1/i18n/admin/export/ur").json()
    assert exported["common"]["save"] == "محفوظ کریں" and exported["common"]["cancel"] == "Cancel"
    groups = admin_client.get("/api/v1/permissions", headers={"Accept-Language": "ur"}).json()
    assert next(g for g in groups if g["module"] == "cash")["label"] == "Cash"


def test_language_rules(admin_client):
    r = admin_client.patch("/api/v1/i18n/admin/languages/ar", json={"version": 1, "is_active": False})
    assert r.status_code == 422 and r.json()["code"] == "cannot_deactivate_default"
    admin_client.post(
        "/api/v1/i18n/admin/languages",
        json={"code": "ur", "name_native": "اردو", "name_en": "Urdu", "direction": "rtl", "fallback_code": "en"},
    )
    r = admin_client.patch("/api/v1/i18n/admin/languages/en", json={"version": 1, "fallback_code": "ur"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_fallback"  # en -> ur -> en
    r = admin_client.patch("/api/v1/i18n/admin/languages/en", json={"version": 1, "is_default": True})
    assert r.status_code == 200 and r.json()["is_default"]
    langs = {lang["code"]: lang for lang in admin_client.get("/api/v1/i18n/admin/languages").json()}
    assert [c for c, lang in langs.items() if lang["is_default"]] == ["en"]
    r = admin_client.post("/api/v1/roles", json={"code": "ar_only", "name": {"ar": "عربي فقط"}})
    assert r.status_code == 422 and r.json()["code"] == "default_language_required"  # the default is now English


def test_user_locale(admin_client, new_client):
    make_user(admin_client, "driver_sup")
    c = new_client()
    login(c, "driver_sup")
    assert c.put("/api/v1/auth/me/locale", json={"locale": "en"}).status_code == 204
    assert c.get("/api/v1/auth/me").json()["locale"] == "en"
    r = c.put("/api/v1/auth/me/locale", json={"locale": "fr"})
    assert r.status_code == 404 and r.json()["code"] == "unknown_language"
    groups = c.get("/api/v1/permissions").json()  # no Accept-Language: the user's own language
    assert next(g for g in groups if g["module"] == "cash")["label"] == "Cash"


def test_only_i18n_managers_edit_translations(admin_client, new_client):
    make_user(admin_client, "plain")
    c = new_client()
    login(c, "plain")
    r = c.put("/api/v1/i18n/admin/overrides/en", json={"items": [{"namespace": "common", "key": "save", "value": "x"}]})
    assert r.status_code == 403
