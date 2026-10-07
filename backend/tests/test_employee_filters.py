"""The employees list filtered by branch, department, job title and whether the employee holds a vehicle now (BRD
FR-HR-03), with the departments and job titles in use offered for the filters, each within the user's companies."""

from tests.conftest import hand_over, login, make_driver, make_employee, make_user, make_vehicle, name, upload

E = "/api/v1/employees"


def ids(client, **params):
    r = client.get(E, params={"limit": 200} | params)
    assert r.status_code == 200, r.text
    return {e["id"] for e in r.json()}


def test_by_branch_department_job_and_vehicle(admin_client, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    fahaheel = admin_client.post("/api/v1/branches", json={"name": name("فرع الفحيحيل", "Fahaheel")}).json()["id"]
    clerk = make_employee(admin_client, a, department="المالية", job_title="محاسب")
    boss = make_employee(admin_client, a, department="المالية", job_title="مدير", branch_id=fahaheel)
    driving, idle, returned = (make_driver(admin_client, a, department="التشغيل", job_title="سائق") for _ in range(3))
    other = make_employee(admin_client, b, department="الموارد البشرية", job_title="محاسب")
    hand_over(admin_client, make_vehicle(admin_client, a), driving)
    car = make_vehicle(admin_client, a)
    c = hand_over(admin_client, car, returned)
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return", json={"odometer_km": 10_010, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text

    assert ids(admin_client, branch_id=fahaheel) == {boss["id"]}
    assert ids(admin_client, department="المالية") == {clerk["id"], boss["id"]}
    assert ids(admin_client, job_title="محاسب") == {clerk["id"], other["id"]}
    assert ids(admin_client, job_title="محاسب", company_id=a) == {clerk["id"]}
    mine = {clerk["id"], boss["id"], driving["id"], idle["id"], returned["id"]}
    assert ids(admin_client, has_vehicle=True) & mine == {driving["id"]}  # the returned car is no longer his
    assert ids(admin_client, has_vehicle=False, is_driver=True) & mine == {idle["id"], returned["id"]}
    assert ids(admin_client, has_vehicle=False, department="التشغيل") == {idle["id"], returned["id"]}

    facets = admin_client.get(f"{E}/facets").json()
    assert {"المالية", "التشغيل", "الموارد البشرية"} <= set(facets["departments"])
    assert {"محاسب", "مدير", "سائق"} <= set(facets["job_titles"])
    assert facets["departments"] == sorted(facets["departments"])


def test_facets_stay_within_the_users_companies(admin_client, new_client, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    make_employee(admin_client, a, department="قسم أ فقط", job_title="وظيفة أ فقط")
    make_employee(admin_client, b, department="قسم ب فقط", job_title="وظيفة ب فقط")
    make_user(admin_client, "hr_a", permissions=["employees.view"], company_ids=[a])
    c = new_client()
    login(c, "hr_a")
    facets = c.get(f"{E}/facets").json()
    assert "قسم أ فقط" in facets["departments"] and "قسم ب فقط" not in facets["departments"]
    assert "وظيفة ب فقط" not in facets["job_titles"]
    assert ids(c, department="قسم ب فقط") == set()
