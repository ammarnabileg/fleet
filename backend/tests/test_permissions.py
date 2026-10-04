from tests.conftest import PASSWORD, login, make_user, name


def test_permission_is_required(admin_client, new_client):
    make_user(admin_client, "viewer")
    c = new_client()
    login(c, "viewer")
    r = c.get("/api/v1/users")
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert r.json()["params"] == {"permission": "users.view"}
    assert c.post("/api/v1/branches", json={"name": name("فرع", "Branch")}).status_code == 403


def test_nobody_grants_more_than_they_hold(admin_client, new_client, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    make_user(admin_client, "hrm", permissions=["users.view", "users.create", "roles.manage"], company_ids=[a])
    admin_client.post(
        "/api/v1/roles",
        json={"code": "settings_admin", "name": name("إعدادات", "Settings"), "permissions": ["settings.update"]},
    )
    hr = new_client()
    login(hr, "hrm")

    r = hr.post(
        "/api/v1/roles", json={"code": "sneaky", "name": name("دور", "Sneaky"), "permissions": ["settings.update"]}
    )
    assert r.status_code == 403 and r.json()["code"] == "cannot_grant_permissions"

    base = {"full_name": "New Person", "password": PASSWORD}
    r = hr.post("/api/v1/users", json={**base, "username": "user1", "all_companies": True})
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    r = hr.post("/api/v1/users", json={**base, "username": "user2", "all_companies": False, "company_ids": [b]})
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    r = hr.post(
        "/api/v1/users",
        json={
            **base,
            "username": "user3",
            "all_companies": False,
            "company_ids": [a],
            "role_codes": ["settings_admin"],
        },
    )
    assert r.status_code == 403 and r.json()["code"] == "cannot_grant_permissions"
    r = hr.post(
        "/api/v1/users",
        json={**base, "username": "user4", "all_companies": False, "company_ids": [a], "role_codes": ["role_hrm"]},
    )
    assert r.status_code == 201 and r.json()["must_change_password"] is True


def test_assigning_the_all_permissions_role_needs_all_permissions(admin_client, new_client):
    make_user(admin_client, "manager", permissions=["users.view", "users.create", "users.update"])
    m = new_client()
    login(m, "manager")
    r = m.post(
        "/api/v1/users",
        json={"username": "boss", "full_name": "Boss", "password": PASSWORD, "role_codes": ["system_admin"]},
    )
    assert r.status_code == 403 and r.json()["code"] == "cannot_grant_permissions"


def test_role_validation_localized_names_and_versioning(admin_client):
    r = admin_client.post(
        "/api/v1/roles", json={"code": "x_role", "name": name("دور", "Role"), "permissions": ["no.such.permission"]}
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_permission"
    r = admin_client.post("/api/v1/roles", json={"code": "x_role", "name": {"en": "Only English"}})
    assert r.status_code == 422 and r.json()["code"] == "default_language_required"
    r = admin_client.post("/api/v1/roles", json={"code": "x_role", "name": {"ar": "دور", "fr": "Rôle"}})
    assert r.status_code == 422 and r.json()["code"] == "unknown_language"
    role = admin_client.post(
        "/api/v1/roles", json={"code": "auditor", "name": name("مدقق", "Auditor"), "permissions": ["audit.view"]}
    ).json()
    r = admin_client.patch(
        "/api/v1/roles/auditor", json={"version": role["version"], "permissions": ["audit.view", "users.view"]}
    )
    assert r.status_code == 200 and r.json()["permissions"] == ["audit.view", "users.view"]
    r = admin_client.patch("/api/v1/roles/auditor", json={"version": role["version"], "name": name("س", "Stale")})
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    r = admin_client.patch("/api/v1/roles/system_admin", json={"version": 1, "permissions": []})
    assert r.status_code == 403 and r.json()["code"] == "system_role"


def test_role_templates_from_the_brd_are_ready(admin_client):
    roles = {r["code"]: r for r in admin_client.get("/api/v1/roles").json()}
    assert {
        "system_admin",
        "management",
        "supervisor",
        "accountant",
        "hr",
        "maintenance_manager",
        "maintenance_center",
        "support",
    } <= roles.keys()
    assert roles["system_admin"]["is_system"] and roles["system_admin"]["all_permissions"]
    assert roles["supervisor"]["name"] == {"ar": "المشرف", "en": "Supervisor"}
    assert "employees.view_salary" in roles["hr"]["permissions"]
    assert "employees.view_salary" not in roles["supervisor"]["permissions"]
    assert set(roles["maintenance_center"]["permissions"]) == {
        "portal.vehicles",
        "portal.quotes",
        "portal.invoices",
        "portal.damage",
    }


def test_permissions_are_grouped_and_translated(admin_client):
    groups = admin_client.get("/api/v1/permissions", headers={"Accept-Language": "en-US,en;q=0.9"}).json()
    cash = next(g for g in groups if g["module"] == "cash")
    assert cash["label"] == "Cash"
    writeoff = next(p for p in cash["permissions"] if p["code"] == "cash.writeoff")
    assert writeoff == {"code": "cash.writeoff", "action": "writeoff", "label": "Write off amounts", "sensitive": True}
    ar = admin_client.get("/api/v1/permissions?lang=ar").json()
    assert next(g for g in ar if g["module"] == "cash")["label"] == "الكاش"


def test_username_is_unique_case_insensitively(admin_client):
    make_user(admin_client, "Sami")
    r = admin_client.post("/api/v1/users", json={"username": "sami", "full_name": "Other", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["code"] == "username_taken"
