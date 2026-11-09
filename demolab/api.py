"""Local HTTP API + the web app. Binds to 127.0.0.1; rejects other Host headers (DNS-rebinding guard)."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import threading

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import browser, config, gemini, google_auth, jobs, pipeline, scriptgen, sources, store
from .models import Project, Segment

STATIC = pathlib.Path(__file__).parent / "static"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

app = FastAPI(title="Voice Demo Lab", version="0.1.0")


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden host"}, status_code=403)
    return await call_next(request)


@app.exception_handler(KeyError)
async def not_found(_, e: KeyError):
    return JSONResponse({"detail": f"not found: {e}"}, status_code=404)


@app.exception_handler(ValueError)
async def bad_request(_, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


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


@app.put("/api/settings")
def put_settings(s: config.Settings):
    config.save(s)
    return config.public_settings()


class KeyIn(BaseModel):
    key: str


@app.put("/api/settings/gemini-key")
def set_key(k: KeyIn):
    if len(k.key.strip()) < 20:
        raise ValueError("That does not look like a Gemini API key.")
    config.set_secret("gemini_api_key", k.key.strip())
    return config.public_settings()


@app.delete("/api/settings/gemini-key")
def del_key():
    config.delete_secret("gemini_api_key")
    return config.public_settings()


@app.get("/api/models")
def models():
    return gemini.list_models()


class PreviewIn(BaseModel):
    text: str
    project_id: str | None = None


@app.post("/api/voice/preview")
def voice_preview(v: PreviewIn):
    if not v.text.strip():
        raise ValueError("Nothing to say.")
    return FileResponse(pipeline.preview(v.text.strip()[:2000], v.project_id), media_type="audio/wav")


_google = {"state": "idle", "error": ""}


@app.post("/api/google/connect")
def google_connect():
    def run():
        _google.update(state="waiting", error="")
        try:
            google_auth.connect()
            _google["state"] = "connected"
        except Exception as e:
            _google.update(state="error", error=str(e))
    threading.Thread(target=run, daemon=True).start()
    return _google


@app.get("/api/google/status")
def google_status():
    return {**_google, "connected": config.has_secret("google_token")}


@app.delete("/api/google")
def google_disconnect():
    google_auth.disconnect()
    _google.update(state="idle", error="")
    return {"connected": False}


# ---- projects -----------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str
    base_url: str = ""
    goal: str = ""
    instructions: str = ""


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
    instructions: str | None = None
    voice_id: str | None = None
    voice_style: str | None = None


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, b: ProjectPatch):
    return store.mutate(pid, lambda p: [setattr(p, k, v) for k, v in b.model_dump(exclude_none=True).items()])


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    store.get(pid)
    store.delete(pid)
    return {"deleted": pid}


# ---- sources ------------------------------------------------------------------------------------

class SourceIn(BaseModel):
    kind: str            # url | repo | gslides | text
    ref: str = ""
    text: str = ""
    label: str = ""


def _add(pid: str, fn) -> Project:
    p = store.get(pid)
    src = fn(p)            # may append slides to p
    p.sources.append(src)
    return store.save(p)


@app.post("/api/projects/{pid}/sources")
def add_source(pid: str, b: SourceIn):
    add = {"url": lambda p: sources.add_url(p, b.ref, b.label),
           "repo": lambda p: sources.add_repo(p, b.ref, b.label),
           "gslides": lambda p: sources.add_gslides(p, b.ref, b.label),
           "text": lambda p: sources.add_text(p, b.label, b.text)}.get(b.kind)
    if not add:
        raise ValueError(f"Unknown source kind {b.kind}")
    return _add(pid, add)


@app.post("/api/projects/{pid}/sources/upload")
async def upload_source(pid: str, file: UploadFile = File(...), label: str = Form("")):
    data = await file.read()
    return _add(pid, lambda p: sources.add_upload(p, file.filename or "upload", data, label))


@app.delete("/api/projects/{pid}/sources/{sid}")
def delete_source(pid: str, sid: str):
    def drop(p: Project):
        src = next(s for s in p.sources if s.id == sid)
        lo, n = src.slide_offset, src.slide_count
        for name in p.slides[lo:lo + n]:
            (store.pdir(pid) / "slides" / name).unlink(missing_ok=True)
        del p.slides[lo:lo + n]
        p.sources.remove(src)
        for s in p.sources:
            if s.slide_offset >= lo + n and n:
                s.slide_offset -= n
        for seg in p.segments:   # keep slide segments pointing at the same images
            if seg.slide is not None and n:
                if lo <= seg.slide < lo + n:
                    seg.type, seg.slide = "card", None
                elif seg.slide >= lo + n:
                    seg.slide -= n
    return store.mutate(pid, drop)


@app.get("/api/projects/{pid}/slides/{n}")
def slide_image(pid: str, n: int):
    p = store.get(pid)
    return FileResponse(store.pdir(pid) / "slides" / p.slides[n], media_type="image/png")


# ---- script -------------------------------------------------------------------------------------

@app.post("/api/projects/{pid}/script/draft")
def draft_script(pid: str):
    store.get(pid)
    return jobs.start(pid, "draft", scriptgen.draft, pid).public()


@app.put("/api/projects/{pid}/segments")
def put_segments(pid: str, segs: list[Segment]):
    def apply(p: Project):
        p.segments, p.script_approved = segs, False
    return store.mutate(pid, apply)


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


class ReviseIn(BaseModel):
    instruction: str


@app.post("/api/projects/{pid}/segments/{sid}/revise")
def revise_segment(pid: str, sid: str, b: ReviseIn):
    scriptgen.revise_segment(pid, sid, b.instruction)
    return store.get(pid)


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

class ExploreIn(BaseModel):
    segment_ids: list[str] | None = None


@app.post("/api/projects/{pid}/explore")
def explore(pid: str, b: ExploreIn = Body(default=ExploreIn())):
    store.get(pid)
    return jobs.start(pid, "explore", browser.explore, pid, b.segment_ids).public()


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
