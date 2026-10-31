"""Load test against a running server (BRD NFR: the dashboard within 3 seconds with 500 vehicles).

It seeds a company with N vehicles, each in custody of a driver whose phone is signed in through an activation link;
then, for the given minutes, every phone sends a GPS point every 30 seconds (the app's interval while moving) and
some office users load the dashboard and the live map every few seconds. It prints the latency of each endpoint
(median, 95th percentile, slowest) and the errors, and fails when the dashboard's 95th percentile is over the target.

Run it against a staging server, never production (it creates real records):
    RATE_LIMIT_EXEMPT=<this machine> on the server, then
    python deploy/loadtest/load.py --base https://staging.example --user admin --password ... --vehicles 500 --minutes 3
"""

# ruff: noqa: S311  (random spreads the load and the positions; nothing here is a secret)

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import httpx

TARGET_MS = 3000


def jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + os.urandom(64)  # a photo the server has never seen


class Office:
    def __init__(self, base: str):
        self.c = httpx.AsyncClient(base_url=base + "/api/v1", timeout=60)

    async def login(self, user: str, password: str) -> None:
        r = await self.c.post("/auth/login", json={"username": user, "password": password})
        r.raise_for_status()
        self.c.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    async def call(self, method: str, path: str, **kw):
        r = await self.c.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        return r.json() if r.content else None


async def seed(office: Office, base: str, n: int, run: str) -> list[httpx.AsyncClient]:
    company = await office.call("POST", "/companies", json={"name": {"ar": f"حمل {run}", "en": f"Load {run}"}})
    sem = asyncio.Semaphore(20)

    async def one(i: int) -> httpx.AsyncClient:
        async with sem:
            v = await office.call(
                "POST",
                "/vehicles",
                json={"plate_number": f"L{run[-4:]}/{i}", "company_id": company["id"], "last_odometer_km": 1000},
            )
            d = await office.call(
                "POST",
                "/employees",
                json={
                    "employee_number": f"L{run}{i:04d}",
                    "name": {"ar": f"سائق {i}", "en": f"Driver {i}"},
                    "company_id": company["id"],
                    "is_driver": True,
                    "phone": f"+9659{run[-3:]}{i:04d}",
                },
            )
            photo = await office.call("POST", "/files", files={"file": ("odo.jpg", jpeg(), "image/jpeg")})
            await office.call(
                "POST",
                "/custodies",
                json={
                    "vehicle_id": v["id"],
                    "driver_id": d["id"],
                    "odometer_km": 1000,
                    "photo_sha256": photo["sha256"],
                },
            )
            await office.call("PUT", f"/employees/{d['id']}/app-access", json={"app_access": "active"})
            link = await office.call(
                "POST", f"/employees/{d['id']}/activation-link", json={"channel": "manual", "onboarding": False}
            )
            phone = httpx.AsyncClient(base_url=base + "/api/v1", timeout=60)
            r = await phone.post(
                "/driver/auth/activate",
                json={"token": link["url"].split("#t=")[1], "device_uid": uuid.uuid4().hex, "model": "Load"},
            )
            r.raise_for_status()
            phone.headers["Authorization"] = "Bearer " + r.json()["access_token"]
            return phone

    return await asyncio.gather(*(one(i) for i in range(n)))


async def run_load(office: Office, phones: list, minutes: float, offices: int, every: float) -> dict:
    times: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    end = time.monotonic() + minutes * 60

    async def timed(name: str, coro):
        t = time.perf_counter()
        try:
            r = await coro
            if r.status_code >= 400:
                errors[name] += 1
        except httpx.HTTPError:
            errors[name] += 1
        times[name].append((time.perf_counter() - t) * 1000)

    async def phone_loop(phone: httpx.AsyncClient, i: int):
        await asyncio.sleep(random.uniform(0, 30))  # spread over the interval, as real phones are
        seq = 0
        while time.monotonic() < end:
            seq += 1
            now = datetime.now(UTC).isoformat()
            point = {
                "seq": seq,
                "recorded_at": now,
                "lat": 29.3 + random.random() / 10,
                "lng": 47.9 + random.random() / 10,
                "speed_kmh": 40,
            }
            await timed(
                "POST /driver/positions", phone.post("/driver/positions", json={"sent_at": now, "points": [point]})
            )
            await asyncio.sleep(30)

    async def office_loop():
        await asyncio.sleep(random.uniform(0, every))
        while time.monotonic() < end:
            await timed("GET /dashboard", office.c.get("/dashboard"))
            await timed("GET /tracking/live", office.c.get("/tracking/live"))
            await asyncio.sleep(every)

    await asyncio.gather(*(phone_loop(p, i) for i, p in enumerate(phones)), *(office_loop() for _ in range(offices)))
    return {"times": times, "errors": errors}


def report(result: dict) -> bool:
    ok = True
    print(f"{'endpoint':28} {'calls':>6} {'errors':>6} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}")
    for name, values in sorted(result["times"].items()):
        values.sort()
        p95 = values[max(0, int(len(values) * 0.95) - 1)]
        p50, errors = statistics.median(values), result["errors"][name]
        print(f"{name:28} {len(values):6d} {errors:6d} {p50:8.0f} {p95:8.0f} {values[-1]:8.0f}")
        if name == "GET /dashboard" and p95 > TARGET_MS:
            ok = False
        if result["errors"][name]:
            ok = False
    print("PASS" if ok else f"FAIL (dashboard p95 over {TARGET_MS} ms, or errors)")
    return ok


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--vehicles", type=int, default=500)
    p.add_argument("--minutes", type=float, default=3)
    p.add_argument("--offices", type=int, default=10, help="office users loading the dashboard and the live map")
    p.add_argument("--every", type=float, default=5, help="seconds between an office user's loads")
    a = p.parse_args()
    office = Office(a.base)
    await office.login(a.user, a.password)
    run = datetime.now(UTC).strftime("%H%M%S")
    t = time.monotonic()
    phones = await seed(office, a.base, a.vehicles, run)
    print(f"seeded {a.vehicles} vehicles in custody with signed-in phones in {time.monotonic() - t:.0f} s")
    result = await run_load(office, phones, a.minutes, a.offices, a.every)
    return 0 if report(result) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
