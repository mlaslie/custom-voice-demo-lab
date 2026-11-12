from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import httpx
import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from demolab import cards, config, pipeline, store


class DummyJob:
    def __init__(self):
        self.messages: list[str] = []

    def say(self, msg: str, progress: float | None = None):
        self.messages.append(msg)


def _make_pdf(path: pathlib.Path) -> None:
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(1280, 720)
    page.close()
    with open(path, "wb") as f:
        pdf.save(f)
    pdf.close()


def _make_shot(path: pathlib.Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (1440, 900), color)
    img.save(path, format="PNG")


def test_plugin_only_cli_rejects_standalone_commands():
    repo = pathlib.Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-m", "demolab", "open"], cwd=repo, capture_output=True, text=True)
    assert r.returncode != 0
    assert "invalid choice: 'open'" in r.stderr


def test_pure_pillow_cards_render_1080p(tmp_path):
    out = cards.render_cards(
        [
            {
                "kicker": "GOOGLE CLOUD",
                "title": "Gemini for Healthcare",
                "sub": "Grounded clinical & operational intelligence",
                "bullets": ["HIPAA-ready architecture", "Native FHIR R4 integration"],
            }
        ],
        tmp_path / "cards",
    )
    assert len(out) == 1
    png = next(iter(out.values()))
    assert png.is_file()
    with Image.open(png) as im:
        assert im.size == (1920, 1080)
        # Top bar has Google Blue on the top-left pixel, body background is white
        assert im.getpixel((20, 4)) == cards.BLUE
        assert im.getpixel((20, 100)) == (255, 255, 255)


def test_end_to_end_research_agy_browser_onboarding_and_hybrid_mp4_render(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_FAKE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")

    from demolab.api import app
    c = TestClient(app, base_url="http://127.0.0.1")

    # 1. Configure fake Gemini key & voice profile + output_dir
    out_dir = tmp_path / "renders"
    c.put("/api/settings", json={"output_dir": str(out_dir)})
    kid = c.post("/api/keys", json={"name": "AGY Test", "key": "AIzaFAKEFAKEFAKEFAKE9999"}).json()["key"]["id"]
    c.post("/api/profiles", json={"name": "Custom Voice", "key_id": kid, "voice": "voice_test0001", "kind": "custom"})

    # 2. Create hybrid demo project (slides + live Cloud Console URL)
    p = c.post(
        "/api/projects",
        json={
            "name": "Healthcare Cloud Demo",
            "base_url": "https://console.cloud.google.com/healthcare",
            "goal": "Show Gemini for Healthcare architecture and live FHIR dataset setup.",
            "brief": "Built deck in AGY and verified Cloud Healthcare API setup.",
        },
    ).json()
    pid = p["id"]
    assert p["scenario"] == "website"

    pdf_path = tmp_path / "slides.pdf"
    _make_pdf(pdf_path)
    p = c.post(f"/api/projects/{pid}/decks", json={"ref": str(pdf_path), "label": "Architecture Slides"}).json()
    assert p["scenario"] == "hybrid" and len(p["slides"]) == 1

    # 3. Save grounded technical research
    p = c.post(
        f"/api/projects/{pid}/research",
        json={
            "summary": "Verified Cloud Healthcare API FHIR R4 store capabilities and HIPAA controls.",
            "items": [
                {
                    "title": "Cloud Healthcare API FHIR Guide",
                    "source_type": "docs",
                    "url_or_path": "https://cloud.google.com/healthcare-api/docs/how-tos/fhir",
                    "summary": "FHIR R4 dataset and store creation.",
                    "verified_claims": ["Supports FHIR R4 resources", "Supports BigQuery streaming export"],
                }
            ],
        },
    ).json()
    assert len(p["research"]) == 1

    # 4. Write grounded hybrid script (intro card + slide + live AGY browser step + recap card)
    segs = [
        {
            "type": "card",
            "kicker": "OVERVIEW",
            "title": "Gemini for Healthcare",
            "narration": "Welcome to this overview of Gemini for Healthcare on Google Cloud.",
            "citations": ["Cloud Healthcare API FHIR Guide"],
        },
        {
            "type": "slide",
            "slide": 0,
            "title": "Architecture",
            "narration": "Our architecture connects clinical data stores with grounded reasoning.",
            "citations": ["Slide 1"],
        },
        {
            "type": "step",
            "title": "Create FHIR R4 Store",
            "narration": "Inside Google Cloud Console, we open the Healthcare browser and provision a F H I R store.",
            "actions": [
                {"op": "goto", "value": "https://console.cloud.google.com/healthcare/browser"},
                {"op": "click", "target": "Create dataset"},
            ],
            "after_narration": "The F H I R version four store is now active and ready for clinical search.",
            "citations": ["Cloud Healthcare API FHIR Guide"],
        },
        {
            "type": "card",
            "title": "Key Takeaways",
            "bullets": ["Grounded in official docs", "Live console walkthrough"],
            "narration": "That wraps up our walkthrough.",
        },
    ]
    put_res = c.put(f"/api/projects/{pid}/segments", json=segs)
    assert put_res.status_code == 200
    saved_segs = put_res.json()["project"]["segments"]
    step_id = next(s["id"] for s in saved_segs if s["type"] == "step")

    # 5. Readiness check must flag unapproved script, unchecked login, and missing step frames
    r0 = c.get(f"/api/projects/{pid}/readiness").json()
    assert not r0["ready"]
    assert r0["has_research"] is True
    assert len(r0["missing_step_frames"]) == 1

    # 6. Complete In-AGY Browser login onboarding + step frame capture
    c.post(
        f"/api/projects/{pid}/web-auth",
        json={
            "status": "login_required",
            "checked_url": "https://console.cloud.google.com/healthcare",
            "notes": "Waiting for user login in AGY Browser",
        },
    )
    assert not c.get(f"/api/projects/{pid}/readiness").json()["ready"]

    p_auth = c.post(
        f"/api/projects/{pid}/web-auth",
        json={
            "status": "authenticated",
            "checked_url": "https://console.cloud.google.com/healthcare",
            "account_hint": "GCP project health-demo",
        },
    ).json()
    assert p_auth["has_login"] is True

    shot_before = tmp_path / "before.png"
    shot_during = tmp_path / "during.png"
    shot_result = tmp_path / "result.png"
    _make_shot(shot_before, (240, 244, 250))
    _make_shot(shot_during, (230, 238, 252))
    _make_shot(shot_result, (225, 246, 234))

    p_frames = c.post(
        f"/api/projects/{pid}/segments/{step_id}/frames",
        json={
            "frames": [
                {"path": str(shot_before), "phase": "before", "caption": "Healthcare datasets view"},
                {
                    "path": str(shot_during),
                    "phase": "during",
                    "caption": "Provisioning FHIR store",
                    "ff_what": "Provisioning FHIR R4 store",
                    "ff_elapsed": 35,
                },
                {
                    "path": str(shot_result),
                    "phase": "result",
                    "caption": "FHIR store ready",
                    "highlight": {"x": 0.15, "y": 0.25, "w": 0.5, "h": 0.2, "label": "FHIR R4 Active"},
                    "zoom_to": {"x": 0.12, "y": 0.2, "w": 0.6, "h": 0.35},
                },
            ]
        },
    ).json()
    step_seg = next(s for s in p_frames["segments"] if s["id"] == step_id)
    assert len(step_seg["frames"]) == 3
    assert c.get(f"/api/projects/{pid}/frames/{step_seg['frames'][0]['file']}").status_code == 200

    # Re-putting script without `frames` preserves captured frames on matching step title/id
    segs[0]["narration"] = "Welcome to this grounded overview of Gemini for Healthcare."
    put_res2 = c.put(f"/api/projects/{pid}/segments", json=segs).json()
    step_seg2 = next(s for s in put_res2["project"]["segments"] if s["type"] == "step")
    assert len(step_seg2["frames"]) == 3

    # Approve script -> readiness is now 100% green!
    c.post(f"/api/projects/{pid}/approve", json={"approved": True})
    r_ok = c.get(f"/api/projects/{pid}/readiness").json()
    assert r_ok["ready"] is True and r_ok["blockers"] == [] and r_ok["warnings"] == []

    # 7. Render real 1080p MP4 with ffmpeg
    res = pipeline.render(DummyJob(), pid)
    mp4 = pathlib.Path(res["file"])
    assert mp4.is_file() and mp4.stat().st_size > 10_000
    assert res["seconds"] > 6.0


@pytest.mark.skipif(
    not pathlib.Path.home().joinpath(".gemini/antigravity/lib/node_modules/sidecar_sdk/register_loader.js").exists(),
    reason="Antigravity sidecar_sdk not installed on this machine",
)
def test_antigravity_sidecar_proxy_auth_and_preload(tmp_path):
    repo = pathlib.Path(__file__).resolve().parent.parent
    loader = pathlib.Path.home() / ".gemini/antigravity/lib/node_modules/sidecar_sdk/register_loader.js"

    def free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    backend_port = free_port()
    sidecar_port = free_port()
    env = {
        **os.environ,
        "DEMOLAB_HOME": str(tmp_path / "home"),
        "DEMOLAB_PORT": str(backend_port),
        "DEMOLAB_FAKE_GEMINI": "1",
        "ANTIGRAVITY_LS_ADDRESS": "127.0.0.1:9999",
        "ANTIGRAVITY_CSRF_TOKEN": "csrf-test",
        "ANTIGRAVITY_SIDECAR_WEB_PORT": str(sidecar_port),
        "ANTIGRAVITY_SIDECAR_UI_TOKEN": "secret-sidecar-token",
    }

    backend = subprocess.Popen(
        [sys.executable, "-m", "demolab", "serve", "--port", str(backend_port)],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    sidecar = subprocess.Popen(
        ["node", "--import", str(loader), str(repo / "sidecars/studio/main.mjs")],
        cwd=repo / "sidecars/studio",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        base = f"http://127.0.0.1:{sidecar_port}"
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/api/health", timeout=1.0).status_code == 200:
                    break
            except Exception:
                time.sleep(0.25)

        # 1. /preload.js served from Antigravity SDK
        r_pre = httpx.get(f"{base}/preload.js", timeout=3.0)
        assert r_pre.status_code == 200 and "window.sidecar" in r_pre.text

        # 2. SPA HTML injects <script src="/preload.js"></script>
        r_html = httpx.get(f"{base}/projects/prj_123?token=secret-sidecar-token", timeout=3.0)
        assert r_html.status_code == 200 and '<script src="/preload.js"></script>' in r_html.text

        # 3. Unauthenticated POST is rejected with 401; token-authenticated POST succeeds!
        r_unauth = httpx.post(f"{base}/api/projects", json={"name": "Blocked"}, timeout=3.0)
        assert r_unauth.status_code == 401

        r_auth = httpx.post(
            f"{base}/api/projects",
            headers={"X-Sidecar-Token": "secret-sidecar-token"},
            json={"name": "Allowed via Sidecar"},
            timeout=5.0,
        )
        assert r_auth.status_code == 200 and r_auth.json()["name"] == "Allowed via Sidecar"
    finally:
        sidecar.terminate()
        backend.terminate()
        sidecar.wait(timeout=5)
        backend.wait(timeout=5)
