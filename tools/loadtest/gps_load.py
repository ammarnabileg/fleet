#!/usr/bin/env python3
"""A load test that behaves like N phones of the driver app sending their positions to the server at once.

Two steps (Python 3.10+, the standard library only: nothing to install):

1. setup: signs in as an office user, creates a test company with N drivers and N cars, hands each driver a car (the server keeps
   positions only while a car is in the driver's custody), turns on their app access, makes each an activation link
   and opens it as the app does (POST /driver/auth/activate): N phones bound, their tokens saved to a file.

       python3 gps_load.py setup --base https://staging.example.com --user admin --drivers 300

   The office password is read from the FLEET_ADMIN_PASSWORD environment variable (never on the command line).

2. run: N phones at once, each driving its own route around Kuwait City.

       python3 gps_load.py run --base https://staging.example.com --minutes 10              # like the app
       python3 gps_load.py run --base https://staging.example.com --minutes 3 --mode burst  # all together

   app   : as the real app does: a point every 30 s, a batch every 60 s, a heartbeat every 5 min; the phones start
           spread over the first minute (as real phones do).
   burst : the worst case: every phone sends its batch in the same second, every --every seconds.

   At the end (and every 30 s) it prints the requests per second, the answer times (p50/p95/p99/max), and the
   errors by kind; then the points the server stored against those sent (none may be lost).

Run it against a staging server or your own copy, not the live one: it creates a company, drivers and positions
that stay (the company is named «LOADTEST …» and the plates start with LT, so they can be found and removed).
"""

import argparse
import json
import math
import os
import random
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.cookiejar import CookieJar

KUWAIT = (29.3759, 47.9774)  # Kuwait City: every phone drives a loop around it
POINT_EVERY = 30  # seconds between two fixes while moving (the app: Tracker.moving)
SEND_EVERY = 60  # seconds between two uploads (the app: Tracker.syncEvery)
HEARTBEAT_EVERY = 300  # (the app: Tracker.heartbeatEvery)
REFRESH_BEFORE = 120  # seconds before the 15-minute access token expires


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Http:
    """JSON over HTTP(S) with keep-alive-free urllib: one request per call, cookies when asked (the office)."""

    def __init__(self, base: str, timeout: float, insecure: bool = False, cookies: bool = False):
        self.base = base.rstrip("/") + "/api/v1"
        self.timeout = timeout
        handlers = [urllib.request.HTTPCookieProcessor(CookieJar())] if cookies else []
        if insecure:  # a staging server with a self-signed certificate only
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        self.opener = urllib.request.build_opener(*handlers)
        self.headers = {"Content-Type": "application/json", "Accept": "application/json", "Accept-Language": "en"}

    def upload_photo(self) -> str:
        """A small photo (a JPEG's first bytes are all the server checks), each one different; returns its sha256."""
        boundary = uuid.uuid4().hex
        jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + os.urandom(64)
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"o.jpg\"\r\n"
                f"Content-Type: image/jpeg\r\n\r\n").encode() + jpeg + f"\r\n--{boundary}--\r\n".encode()
        headers = {**self.headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
        req = urllib.request.Request(self.base + "/files", data=body, method="POST", headers=headers)
        with self.opener.open(req, timeout=self.timeout) as r:
            return json.loads(r.read())["sha256"]

    def call(self, method: str, path: str, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={**self.headers, **(headers or {})})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw[:200].decode(errors="replace")}


# ------------------------------------------------------------------ setup


def setup(a) -> None:
    password = os.environ.get("FLEET_ADMIN_PASSWORD")
    if not password:
        sys.exit("set FLEET_ADMIN_PASSWORD (the office user's password) in the environment first")
    office = Http(a.base, a.timeout, a.insecure, cookies=True)
    st, me = office.call("POST", "/auth/login", {"username": a.user, "password": password})
    if st != 200:
        sys.exit(f"sign-in failed ({st}): {me}")
    if me.get("mfa_required"):
        sys.exit("this user needs a second factor: use an office user without it on the test server")
    office.headers["X-CSRF-Token"] = me["csrf_token"]

    tag = datetime.now().strftime("%m%d%H%M%S")  # unique per run: setup may be run again
    st, company = office.call("POST", "/companies", {"name": {"ar": f"LOADTEST {tag}", "en": f"LOADTEST {tag}"}})
    if st not in (200, 201):
        sys.exit(f"could not create the test company ({st}): {company}")
    print(f"company LOADTEST {tag} (id {company['id']})", flush=True)

    # one handover photo for every car: the server limits uploads per user (600 an hour by default)
    photo = office.upload_photo()
    phones, failed, lock = [], [0], threading.Lock()

    def save():  # after every phone: a setup cut short keeps what it bound
        tmp = a.file + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"base": a.base, "company_id": company["id"], "phones": phones}, f)
        os.chmod(tmp, 0o600)  # the tokens sign in as these drivers
        os.replace(tmp, a.file)

    def one(i: int) -> None:
        def fail(what, st, r):
            with lock:
                failed[0] += 1
            print(f"  {what} {i + 1}: {st} {r}", flush=True)

        n = f"{tag}{i:04d}"
        st, emp = office.call("POST", "/employees", {
            "employee_number": f"LT{n}",
            "name": {"ar": f"سائق اختبار {i + 1}", "en": f"Load driver {i + 1}"},
            "company_id": company["id"],
            "is_driver": True,
            "phone": f"+9659{random.randint(1000000, 9999999)}",
        })
        if st not in (200, 201):
            return fail("driver", st, emp)
        # a car handed over to him: the server keeps a driver's positions only while a car is in his custody
        st, car = office.call("POST", "/vehicles", {"plate_number": f"LT{n}", "company_id": company["id"],
                                                     "make": "LoadTest", "last_odometer_km": 1000})
        if st not in (200, 201):
            return fail("car", st, car)
        st, cust = office.call("POST", "/custodies", {
            "vehicle_id": car["id"], "driver_id": emp["id"], "odometer_km": 1000, "photo_sha256": photo,
            "started_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        })
        if st not in (200, 201):
            return fail("handover", st, cust)
        st, r = office.call("PUT", f"/employees/{emp['id']}/app-access", {"app_access": "active"})
        if st != 200:
            return fail("app access", st, r)
        st, link = office.call("POST", f"/employees/{emp['id']}/activation-link", {"channel": "manual", "onboarding": False})
        if st != 201 or not link.get("url") or "#" not in link["url"]:
            return fail("link", st, link)
        device_uid = "loadtest-" + uuid.uuid4().hex
        st, tokens = Http(a.base, a.timeout, a.insecure).call("POST", "/driver/auth/activate", {
            "token": link["url"].split("#", 1)[1].split("=")[-1],
            "device_uid": device_uid, "platform": "android", "model": "LoadTest", "app_version": "loadtest",
        })
        if st != 200:
            return fail("activate", st, tokens)
        with lock:
            phones.append({"device_uid": device_uid, "access": tokens["access_token"], "refresh": tokens["refresh_token"]})
            save()
            if len(phones) % 25 == 0:
                print(f"  {len(phones)}/{a.drivers} phones bound", flush=True)

    def guarded(i: int) -> None:  # one driver that fails (a timeout, a dropped connection) does not stop the others
        try:
            one(i)
        except Exception as e:  # noqa: BLE001
            with lock:
                failed[0] += 1
            print(f"  driver {i + 1}: {type(e).__name__} {e}", flush=True)

    # several drivers at a time: over a long distance each request takes about a second
    with ThreadPoolExecutor(a.parallel) as pool:
        list(pool.map(guarded, range(a.drivers)))
    print(f"{len(phones)} phones saved to {a.file}" + (f", {failed[0]} failed" if failed[0] else ""), flush=True)


# ------------------------------------------------------------------ run


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.times, self.errors = [], {}
        self.made_points = self.stored_points = self.rejected_points = self.requests = 0
        self.queued = lambda: 0  # points still waiting on the phones (set by run)
        self.window_start, self.window_requests = time.monotonic(), 0

    def made(self):
        with self.lock:
            self.made_points += 1

    def ok(self, ms: float, stored: int, rejected: int):
        with self.lock:
            self.times.append(ms)
            self.requests += 1
            self.window_requests += 1
            self.stored_points += stored
            self.rejected_points += rejected

    def fail(self, kind: str, ms: float | None = None):
        with self.lock:
            self.errors[kind] = self.errors.get(kind, 0) + 1
            self.requests += 1
            self.window_requests += 1
            if ms is not None:
                self.times.append(ms)

    def report(self, final: bool = False) -> str:
        with self.lock:
            t = sorted(self.times)
            span = time.monotonic() - self.window_start
            rps = self.window_requests / span if span else 0
            self.window_start, self.window_requests = time.monotonic(), 0
            pct = lambda p: t[min(len(t) - 1, int(len(t) * p))] if t else 0  # noqa: E731
            errs = sum(self.errors.values())
            line = (f"requests {self.requests}  ~{rps:.1f}/s  ms p50 {pct(.5):.0f}  p95 {pct(.95):.0f}  p99 {pct(.99):.0f}"
                    f"  max {t[-1] if t else 0:.0f}  errors {errs}")
            if final:
                queued = self.queued()
                lost = self.made_points - self.stored_points - self.rejected_points - queued
                line += (f"\npoints recorded {self.made_points}, stored {self.stored_points}, rejected"
                         f" {self.rejected_points}, still queued on the phones {queued}, lost {lost}")
                if t:
                    line += f"\nmean {statistics.mean(t):.0f} ms"
                for k, v in sorted(self.errors.items(), key=lambda x: -x[1]):
                    line += f"\n  {v:6d}  {k}"
            return line


class Phone(threading.Thread):
    def __init__(self, i: int, p: dict, a, stats: Stats, stop: threading.Event, start_at: float):
        super().__init__(daemon=True)
        self.i, self.p, self.a, self.stats, self.stop, self.start_at = i, p, a, stats, stop, start_at
        self.http = Http(a.base, a.timeout, a.insecure)
        self.seq = int(time.time()) * 10  # new seqs each run: the server keeps the last one per phone
        self.queue: list[dict] = []
        r = random.uniform(0.01, 0.06)  # a loop 1-6 km around the city, each phone its own
        self.center = (KUWAIT[0] + random.uniform(-.08, .08), KUWAIT[1] + random.uniform(-.08, .08))
        self.radius, self.angle, self.speed = r, random.uniform(0, 2 * math.pi), random.uniform(25, 70)
        self.token_until = 0.0  # unknown age (a setup minutes or days ago): refresh before the first request

    def fix(self) -> None:
        self.angle += self.speed / 3600 * POINT_EVERY / (self.radius * 111) if self.radius else 0
        lat = self.center[0] + self.radius * math.sin(self.angle)
        lng = self.center[1] + self.radius * math.cos(self.angle)
        self.seq += 1
        self.queue.append({"seq": self.seq, "recorded_at": now_iso(), "lat": round(lat, 6), "lng": round(lng, 6),
                           "accuracy_m": round(random.uniform(4, 15), 1), "speed_kmh": round(self.speed, 1),
                           "heading": int(math.degrees(self.angle)) % 360})
        self.stats.made()

    def auth(self, force: bool = False) -> dict:
        if force or time.monotonic() > self.token_until:
            st, t = self.http.call("POST", "/driver/auth/refresh", {"refresh_token": self.p["refresh"]})
            if st == 200:
                self.p["access"], self.p["refresh"] = t["access_token"], t["refresh_token"]
                self.token_until = time.monotonic() + t["expires_in"] - REFRESH_BEFORE
            else:
                self.stats.fail(f"refresh {st}")
        return {"Authorization": "Bearer " + self.p["access"]}

    def send(self) -> None:
        if not self.queue:
            return
        batch = self.queue[:500]
        t0 = time.monotonic()
        try:  # a refresh that fails on the way counts like a failed send: the points stay queued
            st, r = self.http.call("POST", "/driver/positions", {"sent_at": now_iso(), "points": batch}, self.auth())
            if st == 401:  # expired early (as the app does: refresh once and send again)
                st, r = self.http.call("POST", "/driver/positions", {"sent_at": now_iso(), "points": batch}, self.auth(True))
        except Exception as e:  # timeout, refused, reset: the app keeps the points and tries again
            self.stats.fail(type(e).__name__)
            return
        ms = (time.monotonic() - t0) * 1000
        if st == 200:
            done = set(r["stored_seqs"]) | {x["seq"] for x in r["rejected"]}
            self.queue = [x for x in self.queue if x["seq"] not in done]
            self.stats.ok(ms, len(r["stored_seqs"]), len(r["rejected"]))
        else:
            self.stats.fail(f"HTTP {st} {(r or {}).get('code', '')}".strip(), ms)

    def heartbeat(self) -> None:
        try:
            self._heartbeat()
        except Exception as e:  # noqa: BLE001 - a dropped connection: the next one goes as usual
            self.stats.fail(f"heartbeat {type(e).__name__}")

    def _heartbeat(self) -> None:
        st, _ = self.http.call("POST", "/driver/status", {"gps_enabled": True, "tracking_service_running": True,
                                                         "location_permission": "always", "app_version": "loadtest",
                                                         "battery_level": random.randint(20, 100), "queue_size": len(self.queue),
                                                         "last_upload_at": now_iso()}, self.auth())
        if st != 200:
            self.stats.fail(f"heartbeat {st}")

    def run(self) -> None:
        if self.a.mode == "app":
            send_every = self.a.send_every or SEND_EVERY
            point_every = min(POINT_EVERY, send_every)
            self.stop.wait(random.uniform(0, send_every))  # real phones are not in step
            last_send = last_beat = 0.0
            while not self.stop.is_set():
                self.fix()
                t = time.monotonic()
                if t - last_beat >= HEARTBEAT_EVERY:
                    self.heartbeat()
                    last_beat = t
                if t - last_send >= send_every:
                    self.send()
                    last_send = t
                self.stop.wait(point_every)
        else:  # burst: everyone fires in the same instant, every --every seconds
            while not self.stop.is_set():
                self.fix()
                self.fix()
                time.sleep(max(0, self.start_at - time.time()))
                self.send()
                self.start_at += self.a.every
                self.stop.wait(max(0, self.start_at - time.time() - 0.05))
        self.send()  # what is left before stopping


def run(a) -> None:
    with open(a.file) as f:
        saved = json.load(f)
    phones = saved["phones"][: a.vehicles] if a.vehicles else saved["phones"]
    if not phones:
        sys.exit("no phones in " + a.file + ": run setup first")
    print(f"{len(phones)} phones -> {a.base}  mode {a.mode}  {a.minutes} min")
    stats, stop = Stats(), threading.Event()
    first = time.time() + 2
    threads = [Phone(i, p, a, stats, stop, first) for i, p in enumerate(phones)]
    stats.queued = lambda: sum(len(t.queue) for t in threads)
    for t in threads:
        t.start()
    def save():  # the server rotates a token on each refresh: the file must hold the latest, even if stopped midway
        tmp = a.file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(saved, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, a.file)

    end = time.monotonic() + a.minutes * 60
    try:
        while time.monotonic() < end:
            time.sleep(min(30, max(0, end - time.monotonic())))
            print(time.strftime("%H:%M:%S"), stats.report(), flush=True)
            save()
    except KeyboardInterrupt:
        print("stopping…")
    stop.set()
    for t in threads:
        t.join(timeout=a.timeout + 5)
    print("\n=== result\n" + stats.report(final=True))
    save()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "run"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="the server, e.g. https://staging.example.com")
        p.add_argument("--file", default="loadtest_phones.json", help="where the phones' tokens are kept")
        p.add_argument("--timeout", type=float, default=30, help="seconds before a request counts as failed")
        p.add_argument("--insecure", action="store_true", help="accept a self-signed certificate (test server)")
    s = sub.choices["setup"]
    s.add_argument("--user", required=True, help="an office user who may add employees and bind phones")
    s.add_argument("--drivers", type=int, default=300)
    s.add_argument("--parallel", type=int, default=10, help="drivers prepared at a time")
    r = sub.choices["run"]
    r.add_argument("--vehicles", type=int, default=0, help="how many of the saved phones (default: all)")
    r.add_argument("--minutes", type=float, default=10)
    r.add_argument("--mode", choices=("app", "burst"), default="app")
    r.add_argument("--every", type=float, default=10, help="burst: seconds between two volleys")
    r.add_argument("--send-every", type=float, default=0, help="app: seconds between two uploads of a phone (default 60, as the app)")
    a = ap.parse_args()
    setup(a) if a.cmd == "setup" else run(a)


if __name__ == "__main__":
    main()
