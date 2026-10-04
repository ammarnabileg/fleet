from tests.conftest import PASSWORD, login, make_user


def test_permission_is_required(admin_client, new_client, org_setup):
    make_user(admin_client, "viewer", branch_ids=[org_setup["a"]["id"]])
    c = new_client()
    login(c, "viewer")
    r = c.get("/api/v1/users")
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert (
        c.post(
            "/api/v1/branches",
            json={"company_public_id": org_setup["company"]["public_id"], "name_ar": "فرع", "name_en": "Branch"},
        ).status_code
        == 403
    )


def test_nobody_grants_more_than_they_hold(admin_client, new_client, org_setup):
    a, b = org_setup["a"]["id"], org_setup["b"]["id"]
    make_user(admin_client, "hrm", permissions=["users.view", "users.manage", "roles.manage"], branch_ids=[a])
    admin_client.post(
        "/api/v1/roles",
        json={
            "code": "settings_admin",
            "name_ar": "إعدادات",
            "name_en": "Settings",
            "permissions": ["settings.manage"],
        },
    )
    hr = new_client()
    login(hr, "hrm")

    r = hr.post(
        "/api/v1/roles",
        json={"code": "sneaky", "name_ar": "دور", "name_en": "Sneaky", "permissions": ["settings.manage"]},
    )
    assert r.status_code == 403 and r.json()["code"] == "cannot_grant_permissions"

    base = {"full_name": "New Person", "password": PASSWORD}
    r = hr.post("/api/v1/users", json={**base, "username": "user1", "all_branches": True})
    assert r.status_code == 403 and r.json()["code"] == "branch_out_of_scope"
    r = hr.post("/api/v1/users", json={**base, "username": "user2", "branch_ids": [b]})
    assert r.status_code == 403 and r.json()["code"] == "branch_out_of_scope"
    r = hr.post(
        "/api/v1/users", json={**base, "username": "user3", "branch_ids": [a], "role_codes": ["settings_admin"]}
    )
    assert r.status_code == 403 and r.json()["code"] == "cannot_grant_permissions"
    r = hr.post("/api/v1/users", json={**base, "username": "user4", "branch_ids": [a], "role_codes": ["role_hrm"]})
    assert r.status_code == 201 and r.json()["must_change_password"] is True


def test_role_validation_and_versioning(admin_client):
    r = admin_client.post(
        "/api/v1/roles",
        json={"code": "x_role", "name_ar": "دور", "name_en": "Role", "permissions": ["no.such.permission"]},
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_permission"
    role = admin_client.post(
        "/api/v1/roles",
        json={"code": "auditor", "name_ar": "مدقق", "name_en": "Auditor", "permissions": ["audit.view"]},
    ).json()
    r = admin_client.patch(
        "/api/v1/roles/auditor", json={"version": role["version"], "permissions": ["audit.view", "users.view"]}
    )
    assert r.status_code == 200 and r.json()["permissions"] == ["audit.view", "users.view"]
    r = admin_client.patch("/api/v1/roles/auditor", json={"version": role["version"], "name_en": "Stale"})
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"


def test_username_is_unique_case_insensitively(admin_client):
    make_user(admin_client, "Sami", all_branches=True)
    r = admin_client.post("/api/v1/users", json={"username": "sami", "full_name": "Other", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["code"] == "username_taken"
