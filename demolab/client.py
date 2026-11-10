"""Talk to the local service, starting it in the background if it is not running.

The service listens on $DEMOLAB_PORT (default 8765). If another program already holds that port, it starts
on a free one instead and records it in ~/.demolab/port, so every MCP server and `demolab open` finds it.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import httpx

from . import config

PORT_FILE = config.HOME / "port"


def _saved_port() -> int:
    if "DEMOLAB_PORT" not in os.environ:
        try:
            return int(PORT_FILE.read_text().strip())
        except (OSError, ValueError):
            pass
    return config.PORT


BASE = f"http://127.0.0.1:{_saved_port()}"


def _in_use(port: int) -> bool:
    with socket.socket() as sk:
        sk.settimeout(0.5)
        return sk.connect_ex(("127.0.0.1", port)) == 0


def _free_port() -> int:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def running() -> bool:
    try:
        return httpx.get(f"{BASE}/api/health", timeout=1.5).json().get("app") == "demolab"
    except Exception:
        return False


def ensure_server(timeout: float = 30) -> str:
    global BASE
    if running():
        return BASE
    for port in dict.fromkeys([_saved_port(), config.PORT]):   # a service may already run on either
        BASE = f"http://127.0.0.1:{port}"
        if running():
            return BASE
    port = config.PORT
    if _in_use(port):
        if "DEMOLAB_PORT" in os.environ:
            raise RuntimeError(f"Port {port} (DEMOLAB_PORT) is in use by another program.")
        port = _free_port()
    BASE = f"http://127.0.0.1:{port}"
    config.HOME.mkdir(parents=True, exist_ok=True)
    log = open(config.HOME / "server.log", "ab")
    subprocess.Popen([sys.executable, "-m", "demolab", "serve", "--port", str(port)], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if running():
            if port == config.PORT:
                PORT_FILE.unlink(missing_ok=True)
            else:
                PORT_FILE.write_text(str(port))
            return BASE
        time.sleep(0.4)
    raise RuntimeError(f"The Voice Demo Lab service did not start; see {config.HOME / 'server.log'}")


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail):
        self.status, self.detail = status, detail
        super().__init__(f"{method} {path} -> {status}: {detail}")


def call(method: str, path: str, **kw):
    ensure_server()
    r = httpx.request(method, f"{BASE}{path}", timeout=kw.pop("timeout", 600), **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text[:400]
        raise ApiError(method, path, r.status_code, detail)
    return r.json() if "json" in r.headers.get("content-type", "") else r.content


def wait_job(job: dict, timeout: float = 900, poll: float = 1.5) -> dict:
    t0 = time.time()
    while job["state"] == "running" and time.time() - t0 < timeout:
        time.sleep(poll)
        job = call("GET", f"/api/jobs/{job['id']}")
    return job
