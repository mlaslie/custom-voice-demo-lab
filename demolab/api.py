"""Local HTTP API + Studio static assets. Binds to 127.0.0.1; rejects non-local Host/Origin headers."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agy_browser, config, gdrive_store, gemini, jobs, pipeline, script, sources, store
from .models import Project, ProjectResolution, ResearchItem, Resolution, Scenario, Segment

STATIC = pathlib.Path(__file__).parent / "static"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
_RECENT_DOWNLOADS: dict[tuple[str, int], pathlib.Path] = {}

app = FastAPI(title="Voice Demo Lab", version="0.4.0")


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden host"}, status_code=403)
    # Writes only from local pages (including AGY sidecar proxy) or non-browser local clients.
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and \
            origin.split("://", 1)[-1].rsplit(":", 1)[0] not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden origin"}, status_code=403)
    return await call_next(request)


@app.exception_handler(KeyError)
async def not_found(_, e: KeyError):
    return JSONResponse({"detail": f"not found: {e}"}, status_code=404)


@app.exception_handler(FileNotFoundError)
async def file_missing(_, e: FileNotFoundError):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(ValueError)
async def bad_request(_, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(config.SetupNeeded)
async def setup_needed(request: Request, e: config.SetupNeeded):
    url = f"{str(request.base_url).rstrip('/')}/setup"
    return JSONResponse({"detail": f"{e} Open {url}", "setup_url": url}, status_code=428)


@app.exception_handler(StopIteration)
async def missing(_, e: StopIteration):
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.exception_handler(gemini.GeminiError)
async def gemini_error(_, e: gemini.GeminiError):
    return JSONResponse({"detail": str(e)}, status_code=502)


# ---- settings -----------------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "app": "demolab", "version": "0.4.0"}


@app.get("/api/settings")
def get_settings():
    return config.public_settings()


class SettingsIn(BaseModel):
    tts_model: str | None = None
    output_dir: str | None = None
    default_resolution: Resolution | None = None
    audience: str | None = None


@app.put("/api/settings")
def put_settings(b: SettingsIn):
    config.update(**b.model_dump(exclude_none=True))
    return config.public_settings()


# ---- API keys, voices and voice profiles ---------------------------------------------------------
# Keys arrive only here, from the local Studio UI, and go straight to the OS keychain. Nothing returns them.

class KeyIn(BaseModel):
    name: str = ""
    key: str


@app.post("/api/keys")
def add_key(k: KeyIn):
    value = k.key.strip()
    if len(value) < 20 or any(c.isspace() for c in value):
        raise ValueError("That does not look like a Gemini API key.")
    voices = gemini.list_voices(value)      # proves the key works before it is saved
    key = config.add_key(k.name, value)
    return {
        "key": key,
        "custom_voices": sum(v["kind"] == "custom" for v in voices),
        "settings": config.public_settings(),
    }


@app.delete("/api/keys/{kid}")
def delete_key(kid: str):
    config.delete_key(kid)
    return config.public_settings()


@app.get("/api/keys/{kid}/voices")
def key_voices(kid: str, locale: str = "", q: str = "", limit: int = 400):
    """Custom voices in full, standard voices filtered by locale ("" = multilingual) and search."""
    config.load().key(kid)
    voices = gemini.list_voices(config.key_value(kid))
    locales: dict[str, int] = {}
    for v in voices:
        if v["kind"] == "standard" and v["locale"]:
            locales[v["locale"]] = locales.get(v["locale"], 0) + 1
    ql = q.lower().strip()
    std = [
        v for v in voices
        if v["kind"] == "standard"
        and (v["locale"] == locale or locale == "*")
        and (not ql or ql in v["name"].lower() or ql in v["id"])
    ]
    return {
        "custom": [v for v in voices if v["kind"] == "custom"],
        "standard": std[:limit],
        "standard_total": len(std),
        "multilingual": sum(v["kind"] == "standard" and not v["locale"] for v in voices),
        "locales": sorted(({"code": c, "count": n} for c, n in locales.items()), key=lambda x: x["code"]),
    }


class ProfileIn(BaseModel):
    name: str
    description: str = ""
    speed: float = 1.0
    key_id: str
    voice: str
    voice_name: str = ""
    kind: str = "custom"
    style: str = config.DEFAULT_STYLE
    activate: bool = True


@app.post("/api/profiles")
def add_profile(b: ProfileIn):
    added: list[str] = []

    def add(s: config.Settings):
        s.key(b.key_id)
        v = config.VoiceProfile(**b.model_dump(exclude={"activate"}))
        s.profiles.append(v)
        if b.activate or not s.active_profile:
            s.active_profile = v.id
        added.append(v.id)

    config.mutate(add)
    pipeline.verify_profile(added[0])
    return config.public_settings()


class ProfilePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    speed: float | None = None
    key_id: str | None = None
    voice: str | None = None
    voice_name: str | None = None
    kind: str | None = None
    style: str | None = None


@app.patch("/api/profiles/{vid}")
def patch_profile(vid: str, b: ProfilePatch):
    retest: list[str] = []

    def patch(s: config.Settings):
        v = s.profile(vid)
        changes = b.model_dump(exclude_none=True)
        if "key_id" in changes:
            s.key(changes["key_id"])
        if "speed" in changes:
            changes["speed"] = config.clamp_speed(changes["speed"])
        if {"key_id", "voice"} & changes.keys():
            changes.update(verified_at=0, verify_error="")
            retest.append(vid)
        s.profiles[s.profiles.index(v)] = v.model_copy(update=changes)

    config.mutate(patch)
    for x in retest:
        pipeline.verify_profile(x)
    return config.public_settings()


@app.post("/api/profiles/{vid}/verify")
def verify_profile(vid: str):
    v = pipeline.verify_profile(vid)
    return {"ok": not v.verify_error, "error": v.verify_error, "settings": config.public_settings()}


@app.delete("/api/profiles/{vid}")
def delete_profile(vid: str):
    def drop(s: config.Settings):
        s.profile(vid)
        s.profiles = [v for v in s.profiles if v.id != vid]
        if s.active_profile == vid:
            s.active_profile = s.profiles[0].id if s.profiles else ""

    config.mutate(drop)
    return config.public_settings()


@app.post("/api/profiles/{vid}/activate")
def activate_profile(vid: str):
    config.mutate(lambda s: (s.profile(vid), setattr(s, "active_profile", vid)))
    return config.public_settings()


@app.get("/api/models")
def models():
    return [] if config.setup_needed() else gemini.list_models()


class PreviewIn(BaseModel):
    text: str
    project_id: str | None = None
    profile_id: str = ""
    key_id: str = ""
    voice: str = ""
    style: str | None = None
    speed: float | None = None


@app.post("/api/voice/preview")
def voice_preview(v: PreviewIn):
    text = v.text.strip()[:2000]
    if not text:
        raise ValueError("Nothing to say.")
    wav = pipeline.preview(text, v.project_id, v.profile_id, v.key_id, v.voice, v.style, v.speed)
    secs = gemini.wav_seconds(wav)
    return FileResponse(
        wav,
        media_type="audio/wav",
        headers={
            "X-Seconds": f"{secs:.2f}",
            "X-Words-Per-Minute": f"{len(text.split()) / secs * 60:.0f}",
            "Access-Control-Expose-Headers": "X-Seconds, X-Words-Per-Minute",
        },
    )


# ---- projects -----------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str
    scenario: Scenario | None = None
    base_url: str = ""
    goal: str = ""
    brief: str = ""
    audience: str = ""
    instructions: str = ""
    resolution: ProjectResolution = ""
    profile_id: str = ""


@app.get("/api/projects")
def list_projects():
    return [
        p.model_dump(include={"id", "name", "scenario", "base_url", "goal", "resolution", "updated_at", "script_approved"})
        | {
            "segments": len(p.segments),
            "renders": len(p.renders),
            "sources": len(p.sources),
            "research_count": len(p.research),
            "web_auth_status": p.web_auth.status,
        }
        for p in store.list_projects()
    ]


@app.post("/api/projects")
def create_project(b: ProjectIn):
    data = b.model_dump(exclude_none=True)
    if "scenario" not in data:
        data["scenario"] = "website" if b.base_url.strip() else "slides"
    return store.create(**data)


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> Project:
    return store.get(pid)


class ProjectPatch(BaseModel):
    name: str | None = None
    scenario: Scenario | None = None
    base_url: str | None = None
    goal: str | None = None
    brief: str | None = None
    audience: str | None = None
    instructions: str | None = None
    research_summary: str | None = None
    resolution: ProjectResolution | None = None
    profile_id: str | None = None
    speed: float | None = None
    voice_id: str | None = None
    voice_style: str | None = None


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, b: ProjectPatch):
    changes = b.model_dump(exclude_none=True)
    if changes.get("speed"):              # 0 = use the voice profile's speed
        changes["speed"] = config.clamp_speed(changes["speed"])
    return store.mutate(pid, lambda p: [setattr(p, k, v) for k, v in changes.items()])


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    store.get(pid)
    store.delete(pid)
    return {"deleted": pid}


# ---- decks (Google Slides, PDF, PowerPoint) -----------------------------------------------------

class DeckIn(BaseModel):
    ref: str                 # Google Slides URL / `gslides:<ID>`, `.pdf`, or `.pptx`
    label: str = ""
    gslides_json: str = ""   # optional `.gslides.json` AST sidecar with speaker notes


@app.post("/api/projects/{pid}/decks")
def add_deck(pid: str, b: DeckIn):
    p = store.get(pid)
    src = sources.add_deck(p, b.ref, b.label, gslides_json=b.gslides_json)
    p.sources.append(src)
    if p.base_url.strip() and p.scenario == "website":
        p.scenario = "hybrid"
    return store.save(p)


@app.get("/api/projects/{pid}/slides/{n}")
def slide_image(pid: str, n: int):
    p = store.get(pid)
    return FileResponse(store.pdir(pid) / "slides" / p.slides[n], media_type="image/png")


# ---- grounded research --------------------------------------------------------------------------

class ResearchIn(BaseModel):
    summary: str = ""
    items: list[dict] = []
    append: bool = False


@app.post("/api/projects/{pid}/research")
def save_research(pid: str, b: ResearchIn):
    parsed = [ResearchItem.model_validate(x) for x in b.items]

    def apply(p: Project):
        if b.summary.strip() or not b.append:
            p.research_summary = b.summary.strip()
        if b.append:
            p.research.extend(parsed)
        else:
            p.research = parsed

    return store.mutate(pid, apply)


# ---- script -------------------------------------------------------------------------------------

@app.put("/api/projects/{pid}/segments")
def put_segments(pid: str, segs: list[dict] = Body(...)):
    """Replace the script. Checked first: errors reject it. Preserves captured frames on matching steps."""
    p = store.get(pid)
    parsed, errors, warnings = script.validate(segs, p)
    if errors:
        raise HTTPException(400, {"errors": errors, "warnings": warnings})

    old_by_id = {s.id: s for s in p.segments if s.type == "step" and s.frames}
    old_steps_by_title = {s.title.strip().lower(): s for s in p.segments if s.type == "step" and s.frames and s.title.strip()}
    for raw_item, seg in zip(segs, parsed):
        if seg.type == "step" and "frames" not in raw_item and not seg.frames:
            match = old_by_id.get(seg.id) or old_steps_by_title.get(seg.title.strip().lower())
            if match:
                seg.frames = match.frames

    def apply(q: Project):
        q.segments, q.script_approved = parsed, False

    q = store.mutate(pid, apply)
    return {"project": q, "warnings": warnings, "seconds": script.seconds(parsed, pipeline.speed_for(q))}


@app.patch("/api/projects/{pid}/segments/{sid}")
def patch_segment(pid: str, sid: str, changes: dict = Body(...)):
    def apply(p: Project):
        i = [s.id for s in p.segments].index(sid)
        cur = p.segments[i].model_dump()
        cur.update({k: v for k, v in changes.items() if k != "id"})
        p.segments[i] = Segment.model_validate(cur)
        if set(changes) - {"approved"}:
            p.segments[i].approved = bool(changes.get("approved", False))
            p.script_approved = False
        elif not p.segments[i].approved:
            p.script_approved = False

    return store.mutate(pid, apply)


class ApproveIn(BaseModel):
    approved: bool = True


@app.post("/api/projects/{pid}/approve")
def approve(pid: str, b: ApproveIn):
    def apply(p: Project):
        if b.approved and not p.segments:
            raise ValueError("Nothing to approve yet.")
        p.script_approved = b.approved
        for s in p.segments:
            s.approved = b.approved

    return store.mutate(pid, apply)


# ---- In-AGY Browser login onboarding, captured frames & readiness -------------------------------

class WebAuthIn(BaseModel):
    status: Literal["unchecked", "authenticated", "login_required", "not_needed"]
    checked_url: str = ""
    account_hint: str = ""
    notes: str = ""


@app.post("/api/projects/{pid}/web-auth")
def set_web_auth(pid: str, b: WebAuthIn):
    return agy_browser.record_web_auth(
        pid,
        status=b.status,
        checked_url=b.checked_url,
        account_hint=b.account_hint,
        notes=b.notes,
    )


@app.delete("/api/projects/{pid}/login")
def reset_web_auth(pid: str):
    return agy_browser.record_web_auth(pid, status="unchecked", notes="Reset in Studio")


class StepFramesIn(BaseModel):
    frames: list[dict]
    append: bool = False


@app.post("/api/projects/{pid}/segments/{sid}/frames")
def add_step_frames(pid: str, sid: str, b: StepFramesIn):
    return agy_browser.record_step_frames(pid, sid, b.frames, append=b.append)


@app.get("/api/projects/{pid}/frames/{name}")
def step_frame_image(pid: str, name: str):
    safe = pathlib.Path(name).name
    f = store.pdir(pid) / "frames" / safe
    if not f.exists():
        raise KeyError(safe)
    media = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(f, media_type=media)


@app.get("/api/projects/{pid}/checks/{name}")
def check_shot(pid: str, name: str):
    safe = pathlib.Path(name).name
    for folder in ("frames", "checks"):
        f = store.pdir(pid) / folder / safe
        if f.exists():
            media = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
            return FileResponse(f, media_type=media)
    raise KeyError(safe)


@app.get("/api/projects/{pid}/readiness")
def project_readiness(pid: str):
    return agy_browser.check_readiness(store.get(pid))


# ---- render -------------------------------------------------------------------------------------

class RenderIn(BaseModel):
    force: bool = False
    resolution: ProjectResolution = ""


@app.post("/api/projects/{pid}/render")
def render(pid: str, b: RenderIn = Body(default=RenderIn())):
    store.get(pid)
    return jobs.start(pid, "render", pipeline.render, pid, b.force, False, b.resolution).public()


@app.get("/api/projects/{pid}/jobs")
def project_jobs(pid: str):
    return [j.public() for j in jobs.for_project(pid)]


@app.get("/api/jobs/{jid}")
def job(jid: str):
    return jobs.get(jid).public()


@app.get("/api/projects/{pid}/renders/{i}/video")
def render_video(pid: str, i: int, download: bool = False):
    f = pathlib.Path(store.get(pid).renders[i].file)
    if not f.exists():
        raise KeyError(str(f))
    if download:
        return FileResponse(f, media_type="video/mp4", filename=f.name)
    return FileResponse(f, media_type="video/mp4")


class DownloadIn(BaseModel):
    dest_dir: str = ""
    dest_file: str = ""
    choose_location: bool = True


@app.post("/api/projects/{pid}/renders/{i}/download")
def download_render_local(pid: str, i: int, b: DownloadIn = Body(default=DownloadIn())):
    src = pathlib.Path(store.get(pid).renders[i].file)
    if not src.exists():
        raise KeyError(str(src))

    if b.dest_file.strip():
        dest = pathlib.Path(b.dest_file.strip()).expanduser()
        if dest.suffix.lower() != ".mp4":
            dest = dest.with_suffix(".mp4")
        dest.parent.mkdir(parents=True, exist_ok=True)
    elif b.dest_dir.strip():
        downloads_dir = pathlib.Path(b.dest_dir).expanduser()
        downloads_dir.mkdir(parents=True, exist_ok=True)
        dest = downloads_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve() and dest.stat().st_size != src.stat().st_size:
            n = 2
            while (downloads_dir / f"{src.stem}-{n}{src.suffix}").exists():
                n += 1
            dest = downloads_dir / f"{src.stem}-{n}{src.suffix}"
    elif b.choose_location:
        chosen = gdrive_store.choose_save_path(src.name)
        if chosen is None:
            return {"canceled": True, "saved_to": "", "filename": ""}
        dest = chosen
        dest.parent.mkdir(parents=True, exist_ok=True)
    else:
        downloads_dir = pathlib.Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        dest = downloads_dir / src.name

    if dest.resolve() != src.resolve():
        shutil.copy2(src, dest)
    _RECENT_DOWNLOADS[(pid, i)] = dest
    return {"canceled": False, "saved_to": str(dest), "filename": dest.name}


class RenderPatch(BaseModel):
    drive_file_id: str | None = None
    drive_url: str | None = None
    drive_folder: str | None = None


@app.patch("/api/projects/{pid}/renders/{i}")
def patch_render(pid: str, i: int, b: RenderPatch):
    def apply(p: Project):
        if i < 0 or i >= len(p.renders):
            raise KeyError(f"render {i}")
        r = p.renders[i]
        changes = b.model_dump(exclude_none=True)
        for k, v in changes.items():
            setattr(r, k, v)
        if changes.get("drive_url") or changes.get("drive_file_id"):
            r.drive_uploaded_at = time.time()

    return store.mutate(pid, apply)


@app.post("/api/projects/{pid}/renders/{i}/reveal")
def reveal(pid: str, i: int, downloaded: bool = False):
    render_file = pathlib.Path(store.get(pid).renders[i].file)
    recent_dl = _RECENT_DOWNLOADS.get((pid, i))
    dl_candidate = recent_dl if (recent_dl and recent_dl.exists()) else (pathlib.Path.home() / "Downloads" / render_file.name)
    f = str(dl_candidate if downloaded and dl_candidate.exists() else render_file)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", f])
    return {"file": f}


# ---- Google Drive plugin status & graphical folder tree -----------------------------------------

@app.get("/api/gdrive/status")
def gdrive_status(ls_installed: bool | None = None, ls_disabled: bool | None = None):
    return gdrive_store.get_status(ls_installed=ls_installed, ls_disabled=ls_disabled)


class GDriveStateIn(BaseModel):
    connected: bool
    account_email: str = ""
    folders: list[dict] | None = None
    root_id: str = ""
    merge_folders: bool = False
    parent_override: str = ""


@app.post("/api/gdrive/state")
def set_gdrive_state(b: GDriveStateIn):
    gdrive_store.save_state(
        connected=b.connected,
        account_email=b.account_email,
        folders=b.folders,
        root_id=b.root_id,
        merge_folders=b.merge_folders,
        parent_override=b.parent_override,
    )
    return gdrive_store.get_status()


# ---- Studio SPA ---------------------------------------------------------------------------------

if (STATIC / "index.html").exists():
    if (STATIC / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (STATIC / path).resolve()
        if path and f.is_file() and STATIC.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
