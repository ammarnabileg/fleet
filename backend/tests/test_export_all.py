"""The full export the contract promises at termination: every table as a CSV Excel reads, the stored files under
their sha256, a manifest; and nothing that opens an account (password and code hashes, tokens, encrypted keys)."""

import csv
import hashlib
import io
import json
import zipfile

from app.ops.export_all import export
from tests.conftest import bind_device, login, make_driver, make_user, upload


def table(z, name) -> list[list[str]]:
    return list(csv.reader(io.TextIOWrapper(z.open(f"data/{name}.csv"), encoding="utf-8-sig")))


def test_everything_the_client_owns_and_no_access_secret(admin_client, client, new_client, db, company):
    driver = make_driver(admin_client, company["id"])
    bind_device(client, driver["phone"])
    make_user(admin_client, "exported", permissions=["vehicles.view"])
    login(new_client(), "exported")  # a session and a password hash exist
    sha = upload(admin_client)

    buf = io.BytesIO()
    manifest = export(db, buf, with_files=True)
    z = zipfile.ZipFile(buf)
    names = set(z.namelist())
    assert json.loads(z.read("manifest.json")) == manifest

    assert z.read("data/people.employees.csv").startswith(b"\xef\xbb\xbf")  # Excel reads the Arabic by it
    employees = table(z, "people.employees")
    assert "employee_number" in employees[0]
    assert any(driver["employee_number"] in row and driver["name"]["ar"] in ",".join(row) for row in employees[1:])
    assert manifest["tables"]["people.employees"] == len(employees) - 1

    users = table(z, "identity.users")
    assert "exported" in [row[users[0].index("username")] for row in users[1:]]
    assert not {"password_hash", "totp_secret_enc"} & set(users[0])
    assert "identity.users.password_hash" in manifest["left_out"]
    for skipped in ("identity.sessions", "identity.device_tokens", "identity.otp_challenges"):
        assert f"data/{skipped}.csv" not in names and skipped in manifest["left_out"]
    devices = table(z, "identity.devices")
    assert not [c for c in devices[0] if c.endswith("_hash")]

    # the GPS points as one table, not one per month; the audit trail kept
    assert "data/tracking.positions.csv" in names and not [n for n in names if "positions_20" in n]
    assert manifest["tables"]["audit.events"] > 0

    [stored] = [n for n in names if n.startswith(f"files/{sha}")]
    assert hashlib.sha256(z.read(stored)).hexdigest() == sha and stored.endswith(".jpg")
