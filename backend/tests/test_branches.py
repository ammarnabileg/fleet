from sqlalchemy import text

from tests.conftest import login, make_user


def test_branch_scope_uat17(admin_client, new_client, org_setup):
    """BRD UAT-17: a branch (A) user cannot see branch (B) data."""
    a, b = org_setup["a"], org_setup["b"]
    make_user(admin_client, "a_user", branch_ids=[a["id"]])
    c = new_client()
    login(c, "a_user")
    assert [x["public_id"] for x in c.get("/api/v1/branches").json()] == [a["public_id"]]
    assert c.get(f"/api/v1/branches/{a['public_id']}").status_code == 200
    r = c.get(f"/api/v1/branches/{b['public_id']}")
    assert r.status_code == 404 and r.json()["code"] == "branch_not_found"  # not even its existence leaks
    assert c.get("/api/v1/branches/not-a-uuid").status_code == 422


def test_branch_update_is_versioned_and_audited(admin_client, org_setup, db):
    a = org_setup["a"]
    r = admin_client.patch(f"/api/v1/branches/{a['public_id']}", json={"version": a["version"], "name_en": "Hawally"})
    assert r.status_code == 200 and r.json()["version"] == a["version"] + 1
    r = admin_client.patch(f"/api/v1/branches/{a['public_id']}", json={"version": a["version"], "name_en": "Again"})
    assert r.status_code == 409
    row = db.execute(
        text(
            "SELECT before->>'name_en', after->>'name_en', branch_id FROM audit.events WHERE action = 'branch.updated'"
        )
    ).one()
    assert row == ("Branch A", "Hawally", a["id"])
