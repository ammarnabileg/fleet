"""A driver objects to his payslip from the app (all of it or one line, with a photo or a PDF if he has one); the
office reads it with payroll.view and answers it with payroll.prepare or payroll.approve; the driver is told; the
approved run never changes."""

import uuid

import pytest

from tests.conftest import bearer, bind_device, jpeg, login, make_driver, make_user, upload
from tests.test_payroll_decisions import run_lines, set_cap
from tests.test_schemes import IBAN, KEETA, MONTH, NEXT, P, assign, platform, scheme

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def driver_file(client, h, data=None, name="o.jpg", mime="image/jpeg") -> str:
    r = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": (name, data or jpeg(), mime)}
    )
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


@pytest.fixture
def payslip(admin_client, client, company):
    """A Keeta driver's approved month (400 orders, 3 marks: 140 - 7 - 10) with an advance installment taken."""
    set_cap(admin_client)
    keeta = platform(admin_client, "keeta")
    standard = scheme(admin_client, keeta["id"], KEETA)
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"], iban=IBAN, basic_salary="300")
    other = make_driver(admin_client, company["id"], platform_id=keeta["id"], iban=IBAN, basic_salary="300")
    assign(admin_client, standard, d, other)
    for x in (d, other):
        body = {
            "employee_id": x["id"],
            "month": str(MONTH),
            "orders": 400,
            "attendance_marks": 3,
            "star_day_failed": False,
        }
        assert admin_client.post(f"{P}/statements", json=body).status_code == 201
    adv = admin_client.post(
        "/api/v1/deductions",
        json={
            "employee_id": d["id"],
            "source_type": "sim",
            "reason": "شريحة",
            "total": "5.000",
            "installments": 1,
            "start_month": str(MONTH),
        },
    )
    assert adv.status_code == 201, adv.text
    run, _ = run_lines(admin_client, company)
    approved = admin_client.post(f"{P}/runs/{run['id']}/approve")
    assert approved.status_code == 200, approved.text
    h = bearer(bind_device(client, d["phone"]))
    return {"driver": d, "other": other, "run": approved.json(), "h": h, "sim": adv.json()}


def test_the_driver_objects_to_all_or_one_line_of_his_own_payslip(admin_client, client, payslip):
    h, run = payslip["h"], payslip["run"]
    slip = client.get("/api/v1/driver/payslips", headers=h).json()[0]
    assert slip["run_id"] == run["id"]
    url = f"/api/v1/driver/payslips/{run['id']}/objections"

    def send(**body):
        return client.post(
            url, headers=h, json={"reason": "الطلبات أكثر من المحسوب", "client_ref": str(uuid.uuid4())} | body
        )

    whole = send()
    assert whole.status_code == 201, whole.text
    assert (whole.json()["status"], whole.json()["item_code"], whole.json()["has_attachment"]) == ("open", None, False)

    shot = driver_file(client, h)
    line = send(item_code="missing_target", reason="عملت 425 طلب", attachment_sha256=shot)
    assert line.status_code == 201, line.text
    assert (line.json()["item_code"], line.json()["item_amount"], line.json()["has_attachment"]) == (
        "missing_target",
        "-7.000",
        True,
    )
    pdf = send(
        item_code=f"deduction:{payslip['sim']['id']}",
        attachment_sha256=driver_file(client, h, PDF, "o.pdf", "application/pdf"),
    )
    assert pdf.status_code == 201 and pdf.json()["item_amount"] == "5.000", pdf.text
    assert send(item_code="net").json()["item_amount"] == "118.000"  # a sheet column: 140 - 7 - 10 - 5

    # what is not on his payslip (no tier was reached), or not his file, or sent twice
    r = send(item_code="tier_bonus")
    assert r.status_code == 422 and r.json()["code"] == "objection_item_invalid"
    office_file = upload(admin_client)
    r = send(attachment_sha256=office_file)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    ref = str(uuid.uuid4())
    assert send(client_ref=ref).status_code == 201
    r = send(client_ref=ref)
    assert r.status_code == 409 and r.json()["code"] == "objection_exists"
    assert send(reason="  ").status_code == 422

    # only his own payslips: another driver of the same run is refused, and so is a run that is not approved
    oh = bearer(bind_device(client, payslip["other"]["phone"], device_uid="other-phone"))
    mine = [x["id"] for x in client.get("/api/v1/driver/objections", headers=h).json()]
    assert client.get("/api/v1/driver/objections", headers=oh).json() == []
    r = client.post(
        f"/api/v1/driver/payslips/{uuid.uuid4()}/objections",
        headers=oh,
        json={"reason": "خطأ في الكشف", "client_ref": str(uuid.uuid4())},
    )
    assert r.status_code == 404 and r.json()["code"] == "payslip_not_found"
    assert len(mine) == 5
    r = client.get(f"/api/v1/driver/objections/{line.json()['id']}/attachment", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"\xff\xd8")
    assert client.get(f"/api/v1/driver/objections/{line.json()['id']}/attachment", headers=oh).status_code == 404


def test_the_office_answers_and_the_run_never_changes(admin_client, client, payslip, new_client):
    h, run, d = payslip["h"], payslip["run"], payslip["driver"]
    before = admin_client.get(f"{P}/runs/{run['id']}").json()
    url = f"/api/v1/driver/payslips/{run['id']}/objections"
    shot = driver_file(client, h)
    body = {"item_code": "missing_target", "reason": "عملت 425 طلب", "attachment_sha256": shot}
    oid = client.post(url, headers=h, json=body | {"client_ref": str(uuid.uuid4())}).json()["id"]

    # payroll.view reads (the alert, the list, the detail with the payslip line, the photo) but does not answer
    make_user(admin_client, "acc1", permissions=["payroll.view"])
    viewer = new_client()
    login(viewer, "acc1")
    alerts = viewer.get("/api/v1/alerts").json()
    items = alerts["items"] if isinstance(alerts, dict) else alerts
    assert [a["kind"] for a in items] == ["payroll_objection"]
    assert viewer.get(f"{P}/objections/counts").json()["open"] == 1
    listed = viewer.get(f"{P}/objections", params={"status": "open,in_review", "month": str(MONTH)}).json()
    assert [x["id"] for x in listed] == [oid] and listed[0]["employee"]["id"] == d["id"]
    one = viewer.get(f"{P}/objections/{oid}").json()
    assert one["payslip"]["net"] == "118.000" and one["payslip"]["item_now"] == "-7.000"
    assert viewer.get(f"{P}/objections/{oid}/attachment").content.startswith(b"\xff\xd8")
    r = viewer.post(f"{P}/objections/{oid}/respond", json={"status": "in_review"})
    assert r.status_code == 403

    # who prepares payroll answers; the driver is told at each change of status
    make_user(admin_client, "hr1", permissions=["payroll.view", "payroll.prepare"])
    hr = new_client()
    login(hr, "hr1")
    r = hr.post(f"{P}/objections/{oid}/respond", json={"status": "in_review", "response": "نراجع تقرير المنصة"})
    assert r.status_code == 200 and r.json()["status"] == "in_review" and r.json()["handled_by"], r.text
    assert viewer.get("/api/v1/alerts/summary").json()["open"] == 0  # taken up: the alert closed itself

    # the settlement: a manual deduction for next month, linked; another driver's deduction is refused
    other = admin_client.post(
        "/api/v1/deductions",
        json={"employee_id": payslip["other"]["id"], "source_type": "other", "reason": "تسوية أخرى", "total": "1.000",
              "installments": 1, "start_month": str(NEXT)},
    ).json()  # fmt: skip
    r = admin_client.post(f"{P}/objections/{oid}/respond", json={"status": "closed", "deduction_id": other["id"]})
    assert r.status_code == 422 and r.json()["code"] == "objection_deduction_invalid"
    r = admin_client.post(
        f"{P}/objections/{oid}/respond", json={"status": "closed", "action_taken": "تُصرف 1.750 مع الشهر القادم"}
    )
    assert r.status_code == 200 and r.json()["status"] == "closed"
    r = admin_client.post(f"{P}/objections/{oid}/respond", json={"status": "open"})
    assert r.status_code == 409 and r.json()["code"] == "objection_status_invalid"

    told = client.get("/api/v1/driver/notifications", headers=h).json()["items"]
    kinds = [n["kind"] for n in told]
    assert kinds.count("objection_updated") >= 2
    mine = client.get("/api/v1/driver/objections", headers=h).json()[0]
    assert (mine["status"], mine["action_taken"]) == ("closed", "تُصرف 1.750 مع الشهر القادم")

    # the approved run and its payslip are exactly as approved
    assert admin_client.get(f"{P}/runs/{run['id']}").json() == before


def test_accept_or_reject_needs_the_answer_and_a_settlement_is_linked(admin_client, client, payslip):
    h, run, d = payslip["h"], payslip["run"], payslip["driver"]
    url = f"/api/v1/driver/payslips/{run['id']}/objections"
    oid = client.post(url, headers=h, json={"reason": "خصم العلامات خطأ", "item_code": "marks_deduction",
                                            "client_ref": str(uuid.uuid4())}).json()["id"]  # fmt: skip
    r = admin_client.post(f"{P}/objections/{oid}/respond", json={"status": "rejected"})
    assert r.status_code == 422 and r.json()["params"] == {"field": "response"}
    settle = admin_client.post(
        "/api/v1/deductions",
        json={"employee_id": d["id"], "source_type": "other", "reason": "تسوية اعتراض", "total": "2.000",
              "installments": 1, "start_month": str(NEXT)},
    ).json()  # fmt: skip
    r = admin_client.post(
        f"{P}/objections/{oid}/respond",
        json={"status": "accepted", "response": "تُصحح الشهر القادم", "deduction_id": settle["id"]},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["deduction"]["id"], r.json()["deduction"]["start_month"]) == (
        "accepted",
        settle["id"],
        str(NEXT),
    )
    told = client.get("/api/v1/driver/notifications", headers=h).json()["items"][0]
    assert told["kind"] == "objection_updated" and "تُصحح الشهر القادم" in told["message"] and "مقبول" in told["message"]
