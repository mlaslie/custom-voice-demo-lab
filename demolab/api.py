"""Local HTTP API + the web app. Binds to 127.0.0.1; rejects other Host headers (DNS-rebinding guard)."""
from __future__ import annotations

import pathlib
import subprocess
import sys
from urllib.parse import urljoin

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import browser, config, gemini, jobs, pipeline, script, sources, store
from .models import Project, Segment

STATIC = pathlib.Path(__file__).parent / "static"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

app = FastAPI(title="Voice Demo Lab", version="0.3.2")


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden host"}, status_code=403)
    # Writes only from this app's own pages (or non-browser clients, which send no Origin): another site
    # open in the browser cannot post a key or change settings through the local service.
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and \
            origin.split("://", 1)[-1].rsplit(":", 1)[0] not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden origin"}, status_code=403)
    return await call_next(request)


@app.exception_handler(KeyError)
async def not_found(_, e: KeyError):
    return JSONResponse({"detail": f"not found: {e}"}, status_code=404)


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
    return {"ok": True, "app": "demolab"}


@app.get("/api/settings")
def get_settings():
    return config.public_settings()


class SettingsIn(BaseModel):
    tts_model: str | None = None
    output_dir: str | None = None
    audience: str | None = None


@app.put("/api/settings")
def put_settings(b: SettingsIn):
    config.update(**b.model_dump(exclude_none=True))
    return config.public_settings()


# ---- API keys, voices and voice profiles ---------------------------------------------------------
# Keys arrive only here, from the local web app, and go straight to the keychain. Nothing returns them.

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
    return {"key": key, "custom_voices": sum(v["kind"] == "custom" for v in voices),
            "settings": config.public_settings()}


@app.delete("/api/keys/{kid}")
def delete_key(kid: str):
    config.delete_key(kid)
    return config.public_settings()


@app.get("/api/keys/{kid}/voices")
def key_voices(kid: str, locale: str = "", q: str = "", limit: int = 400):
    """Custom voices in full, the standard voices filtered by locale ("" = multilingual) and search."""
    config.load().key(kid)
    voices = gemini.list_voices(config.key_value(kid))
    locales: dict[str, int] = {}
    for v in voices:
        if v["kind"] == "standard" and v["locale"]:
            locales[v["locale"]] = locales.get(v["locale"], 0) + 1
    ql = q.lower().strip()
    std = [v for v in voices if v["kind"] == "standard" and (v["locale"] == locale or locale == "*")
           and (not ql or ql in v["name"].lower() or ql in v["id"])]
    return {"custom": [v for v in voices if v["kind"] == "custom"],
            "standard": std[:limit], "standard_total": len(std),
            "multilingual": sum(v["kind"] == "standard" and not v["locale"] for v in voices),
            "locales": sorted(({"code": c, "count": n} for c, n in locales.items()), key=lambda x: x["code"])}


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
    def add(s: config.Settings):
        s.key(b.key_id)
        v = config.VoiceProfile(**b.model_dump(exclude={"activate"}))
        s.profiles.append(v)
        if b.activate or not s.active_profile:
            s.active_profile = v.id
        added.append(v.id)
    added: list[str] = []
    config.mutate(add)
    pipeline.verify_profile(added[0])         # a short spoken test; the result shows next to the voice
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
    retest: list[str] = []
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
    key_id: str = ""             # with voice: try any voice the key can use, before saving a profile
    voice: str = ""
    style: str | None = None
    speed: float | None = None   # try a pace before saving it


@app.post("/api/voice/preview")
def voice_preview(v: PreviewIn):
    text = v.text.strip()[:2000]
    if not text:
        raise ValueError("Nothing to say.")
    wav = pipeline.preview(text, v.project_id, v.profile_id, v.key_id, v.voice, v.style, v.speed)
    secs = gemini.wav_seconds(wav)
    return FileResponse(wav, media_type="audio/wav", headers={   # so a test clip can report its pace
        "X-Seconds": f"{secs:.2f}", "X-Words-Per-Minute": f"{len(text.split()) / secs * 60:.0f}",
        "Access-Control-Expose-Headers": "X-Seconds, X-Words-Per-Minute"})


# ---- projects -----------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str
    base_url: str = ""
    goal: str = ""
    brief: str = ""
    audience: str = ""
    instructions: str = ""
    profile_id: str = ""


@app.get("/api/projects")
def list_projects():
    return [p.model_dump(include={"id", "name", "base_url", "goal", "updated_at", "script_approved"}) |
            {"segments": len(p.segments), "renders": len(p.renders), "sources": len(p.sources)}
            for p in store.list_projects()]


@app.post("/api/projects")
def create_project(b: ProjectIn):
    return store.create(**b.model_dump())


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> Project:
    return store.get(pid)


class ProjectPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    goal: str | None = None
    brief: str | None = None
    audience: str | None = None
    instructions: str | None = None
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


# ---- decks --------------------------------------------------------------------------------------

class DeckIn(BaseModel):
    ref: str             # a .pptx or .pdf path
    label: str = ""


@app.post("/api/projects/{pid}/decks")
def add_deck(pid: str, b: DeckIn):
    p = store.get(pid)
    p.sources.append(sources.add_deck(p, b.ref, b.label))   # appends its slides to p.slides
    return store.save(p)


@app.get("/api/projects/{pid}/slides/{n}")
def slide_image(pid: str, n: int):
    p = store.get(pid)
    return FileResponse(store.pdir(pid) / "slides" / p.slides[n], media_type="image/png")


# ---- script -------------------------------------------------------------------------------------

@app.put("/api/projects/{pid}/segments")
def put_segments(pid: str, segs: list[dict] = Body(...)):
    """Replace the script (from the session's model, or the studio's editor). Checked first: errors reject it."""
    p = store.get(pid)
    parsed, errors, warnings = script.validate(segs, p)
    if errors:
        raise HTTPException(400, {"errors": errors, "warnings": warnings})

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


# ---- browser ------------------------------------------------------------------------------------

class InspectIn(BaseModel):
    url: str = ""        # empty = the project's base_url; a path is resolved against it


@app.post("/api/projects/{pid}/inspect")
def inspect(pid: str, b: InspectIn):
    """The page as the recorder sees it (saved login included): title, visible text, controls with selectors."""
    p = store.get(pid)
    url = urljoin(p.base_url or "", b.url) if b.url else p.base_url
    if not url.startswith(("http://", "https://")):
        raise ValueError("Give a full URL, or set the project's base_url so a path can be resolved against it.")
    snap = browser.snapshot_url(p, url)
    return {"url": url, "title": snap["title"], "text": snap["text"][:6000], "elements": snap["elements"]}


@app.post("/api/projects/{pid}/dryrun")
def dryrun(pid: str):
    store.get(pid)
    return jobs.start(pid, "dryrun", browser.dry_run, pid).public()


@app.get("/api/projects/{pid}/checks/{name}")
def check_shot(pid: str, name: str):
    f = store.pdir(pid) / "checks" / pathlib.Path(name).name
    if not f.exists():
        raise KeyError(name)
    return FileResponse(f, media_type="image/jpeg")


class LoginIn(BaseModel):
    url: str = ""


@app.post("/api/projects/{pid}/login")
def login(pid: str, b: LoginIn = Body(default=LoginIn())):
    p = store.get(pid)
    url = b.url or p.base_url
    if not url:
        raise ValueError("Set the app URL first.")
    def run(job):
        job.say("Sign in in the browser window, then close it")
        browser.capture_login(p, url)
    return jobs.start(pid, "login", run).public()


@app.delete("/api/projects/{pid}/login")
def forget_login(pid: str):
    p = store.get(pid)
    browser.login_state(p).unlink(missing_ok=True)
    return store.mutate(pid, lambda q: setattr(q, "has_login", False))


# ---- render -------------------------------------------------------------------------------------

class RenderIn(BaseModel):
    force: bool = False


@app.post("/api/projects/{pid}/render")
def render(pid: str, b: RenderIn = Body(default=RenderIn())):
    store.get(pid)
    return jobs.start(pid, "render", pipeline.render, pid, b.force).public()


@app.get("/api/projects/{pid}/jobs")
def project_jobs(pid: str):
    return [j.public() for j in jobs.for_project(pid)]


@app.get("/api/jobs/{jid}")
def job(jid: str):
    return jobs.get(jid).public()


@app.get("/api/projects/{pid}/renders/{i}/video")
def render_video(pid: str, i: int):
    f = pathlib.Path(store.get(pid).renders[i].file)
    if not f.exists():
        raise KeyError(str(f))
    return FileResponse(f, media_type="video/mp4")


@app.post("/api/projects/{pid}/renders/{i}/reveal")
def reveal(pid: str, i: int):
    f = store.get(pid).renders[i].file
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", f])
    return {"file": f}


# ---- web app ------------------------------------------------------------------------------------

if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (STATIC / path).resolve()
        if path and f.is_file() and STATIC.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
