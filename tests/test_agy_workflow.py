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

    # 8. Direct download (?download=1 attachment header + local Downloads copy) & Google Drive link persistence
    r_att = c.get(f"/api/projects/{pid}/renders/0/video?download=1")
    assert r_att.status_code == 200
    assert "attachment" in r_att.headers.get("content-disposition", "")

    dl_dir = tmp_path / "downloads"
    r_dl = c.post(f"/api/projects/{pid}/renders/0/download", json={"dest_dir": str(dl_dir)})
    assert r_dl.status_code == 200
    assert r_dl.json()["canceled"] is False
    saved_dl = pathlib.Path(r_dl.json()["saved_to"])
    assert saved_dl.is_file() and saved_dl.stat().st_size == mp4.stat().st_size

    # Native Save-As dialog flow: user cancel vs user choosing custom folder + filename
    from demolab import gdrive_store

    monkeypatch.setattr(gdrive_store, "choose_save_path", lambda _name, _dir=None: None)
    r_cancel = c.post(f"/api/projects/{pid}/renders/0/download", json={"choose_location": True})
    assert r_cancel.status_code == 200 and r_cancel.json()["canceled"] is True

    chosen_target = tmp_path / "CustomChosenDir" / "custom-healthcare-demo.mp4"
    monkeypatch.setattr(gdrive_store, "choose_save_path", lambda _name, _dir=None: chosen_target)
    r_chosen = c.post(f"/api/projects/{pid}/renders/0/download", json={"choose_location": True})
    assert r_chosen.status_code == 200 and r_chosen.json()["canceled"] is False
    assert pathlib.Path(r_chosen.json()["saved_to"]) == chosen_target
    assert chosen_target.is_file() and chosen_target.stat().st_size == mp4.stat().st_size

    # Google Drive plugin status & graphical folder tree sync
    st_uninstalled = c.get("/api/gdrive/status?ls_installed=false&ls_disabled=false").json()
    assert st_uninstalled["status"] == "not_installed" and st_uninstalled["connected"] is False

    st_disabled = c.get("/api/gdrive/status?ls_installed=true&ls_disabled=true").json()
    assert st_disabled["status"] == "disabled" and st_disabled["connected"] is False

    st_needs_auth = c.get("/api/gdrive/status?ls_installed=true&ls_disabled=false").json()
    assert st_needs_auth["status"] == "needs_auth" and st_needs_auth["connected"] is False

    st_synced = c.post(
        "/api/gdrive/state",
        json={
            "connected": True,
            "account_email": "demo@example.com",
            "folders": [
                {"id": "fld_marketing", "name": "Marketing", "parents": ["0AP_opaque_my_drive_root"]},
                {"id": "fld_q4", "name": "Q4 Launches", "parents": ["fld_marketing"]},
                {"id": "fld_health", "name": "Healthcare Demos", "parents": ["fld_q4"], "shared": True},
            ],
        },
    ).json()
    assert st_synced["connected"] is True
    assert st_synced["account_email"] == "demo@example.com"
    folders_by_id = {f["id"]: f for f in st_synced["folders"]}
    assert folders_by_id["fld_marketing"]["parent_id"] == "root"
    assert folders_by_id["fld_q4"]["parent_id"] == "fld_marketing"
    assert folders_by_id["fld_health"]["parent_id"] == "fld_q4"
    assert folders_by_id["fld_health"]["shared"] is True

    r_drive = c.patch(
        f"/api/projects/{pid}/renders/0",
        json={
            "drive_file_id": "1AbCdEfGhIjKlMnOpQr",
            "drive_url": "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view",
            "drive_folder": "My Drive / Marketing / Q4 Launches",
        },
    )
    assert r_drive.status_code == 200
    r0 = r_drive.json()["renders"][0]
    assert r0["drive_file_id"] == "1AbCdEfGhIjKlMnOpQr"
    assert r0["drive_url"] == "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view"
    assert r0["drive_folder"] == "My Drive / Marketing / Q4 Launches"
    assert r0["drive_uploaded_at"] > 0


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


def test_1080p_and_4k_pptx_mp4_renders(tmp_path, monkeypatch):
    """Rendering both 1080p and 4k produces native 1920x1080 and 3840x2160 MP4s."""
    import json
    import subprocess
    from pathlib import Path
    from fastapi.testclient import TestClient
    from PIL import Image
    from pptx import Presentation
    from pptx.util import Inches
    from demolab import api, config, pipeline, store

    monkeypatch.setenv("DEMOLAB_FAKE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")

    c = TestClient(api.app, base_url="http://127.0.0.1")
    kid = c.post("/api/keys", json={"name": "AGY Test", "key": "AIzaFAKEFAKEFAKEFAKE9999"}).json()["key"]["id"]
    c.post(
        "/api/profiles",
        json={"name": "Custom Voice", "key_id": kid, "voice": "voice_test0001", "kind": "custom"},
    ).raise_for_status()
    c.put("/api/settings", json={"output_dir": str(tmp_path / "renders")}).raise_for_status()

    deck_path = tmp_path / "deck.pptx"
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    tb.text_frame.text = "Resolution Benchmark Slide"
    prs.save(str(deck_path))

    created = c.post(
        "/api/projects",
        json={"name": "Resolution Test", "project_type": "slides", "resolution": "1080p"},
    )
    created.raise_for_status()
    pid = created.json()["id"]

    attached = c.post(
        f"/api/projects/{pid}/decks",
        json={"ref": str(deck_path)},
    )
    attached.raise_for_status()

    script_resp = c.put(
        f"/api/projects/{pid}/segments",
        json=[
            {
                "type": "card",
                "kicker": "OVERVIEW",
                "title": "Intro Card",
                "subtitle": "Testing native 1080p and 4K composition.",
                "narration": "Welcome to this short test of both ten eighty p and four K output.",
            },
            {
                "type": "slide",
                "slide": 0,
                "narration": "This slide is rasterized directly at the chosen output resolution.",
            },
        ],
    )
    script_resp.raise_for_status()
    c.post(f"/api/projects/{pid}/approve", json={"approved": True}).raise_for_status()

    r_1080 = pipeline.render(DummyJob(), pid, resolution="1080p")
    mp4_1080 = Path(r_1080["file"])
    assert mp4_1080.is_file()
    assert r_1080["resolution"] == "1080p"
    assert r_1080["width"] == 1920
    assert r_1080["height"] == 1080

    r_4k = pipeline.render(DummyJob(), pid, resolution="4k")
    mp4_4k = Path(r_4k["file"])
    assert mp4_4k.is_file()
    assert r_4k["resolution"] == "4k"
    assert r_4k["width"] == 3840
    assert r_4k["height"] == 2160
    slide_4k = store.pdir(pid) / "slides_3840x2160" / store.get(pid).slides[0]
    assert slide_4k.is_file()
    with Image.open(slide_4k) as im:
        assert im.size == (3840, 2160)

    def _dims(mp4: Path) -> tuple[int, int]:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(mp4),
            ],
            text=True,
        )
        stream = json.loads(out)["streams"][0]
        return int(stream["width"]), int(stream["height"])

    assert _dims(mp4_1080) == (1920, 1080)
    assert _dims(mp4_4k) == (3840, 2160)

    proj = c.get(f"/api/projects/{pid}").json()
    assert proj["renders"][0]["resolution"] == "4k"
    assert proj["renders"][1]["resolution"] == "1080p"
