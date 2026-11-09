"""Talk to the local service, starting it in the background if it is not running."""
from __future__ import annotations

import subprocess
import sys
import time

import httpx

from . import config

BASE = f"http://127.0.0.1:{config.PORT}"


def running() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=1.5).json().get("app") == "demolab"
    except Exception:
        return False


def ensure_server(timeout: float = 30) -> str:
    if running():
        return BASE
    config.HOME.mkdir(parents=True, exist_ok=True)
    log = open(config.HOME / "server.log", "ab")
    subprocess.Popen([sys.executable, "-m", "demolab", "serve"], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if running():
            return BASE
        time.sleep(0.4)
    raise RuntimeError(f"The Voice Demo Lab service did not start; see {config.HOME / 'server.log'}")


def call(method: str, path: str, **kw):
    ensure_server()
    r = httpx.request(method, f"{BASE}{path}", timeout=kw.pop("timeout", 600), **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text[:400]
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {detail}")
    return r.json() if "json" in r.headers.get("content-type", "") else r.content


def wait_job(job: dict, timeout: float = 900, poll: float = 1.5) -> dict:
    t0 = time.time()
    while job["state"] == "running" and time.time() - t0 < timeout:
        time.sleep(poll)
        job = call("GET", f"/api/jobs/{job['id']}")
    return job
