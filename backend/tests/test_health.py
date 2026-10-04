def test_health_and_request_id(client):
    r = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["X-Request-ID"] == "abc123"
    assert client.get("/readyz").json() == {"status": "ready"}


def test_errors_are_problem_json(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "not_authenticated"
    r = client.post("/api/v1/auth/login", json={"username": "x"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and r.json()["errors"]
