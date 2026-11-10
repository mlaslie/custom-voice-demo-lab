"""MCP server (stdio) for Claude Code and Google Antigravity.

The coding session is the context: its model has analyzed the code, slides or app with the user, and it
writes the narration script itself (script_guide, write_script). The plugin checks the script, the user
reviews and approves it in the studio (shown in the session's side panel), and only then does Gemini TTS
voice it and the video get rendered. The service holds all state; these tools are thin calls to it. The
Gemini API key is never accepted or returned here: users enter it on the studio's setup page.
"""
from __future__ import annotations

import json
import webbrowser

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import client

READ = ToolAnnotations(readOnlyHint=True)

mcp = MCPServer("voice-demo-lab", version="0.3.3", instructions=(
    "Voice Demo Lab turns what this coding session analyzed (code, slides, a running app) into a narrated "
    "demo video, in the user's custom or a standard Gemini TTS voice. YOU write the script from the session; "
    "the plugin checks it, voices it and renders it. Flow: get_settings (if setup_needed: "
    "open_studio(page='setup', open_browser=false), show it in your side panel / built-in browser, and wait "
    "for the user to add a key and choose a voice) -> start_demo (attach the decks the session used; set "
    "base_url for a live app) -> open the returned studio_url in your side panel -> script_guide -> "
    "write_script (fix its errors; consider its warnings) -> summarise it in chat; the user reviews, edits "
    "and approves in the side panel (call approve_script only if they approve in chat) -> for web steps: "
    "capture_login if needed, inspect_page for selectors, dry_run until it passes -> render. Voices: "
    "list_voice_profiles, use_voice_profile. Never ask for, accept or repeat a Gemini API key in chat or "
    "tool calls, even if offered: send the user to the setup page."))


def _decks(p: dict) -> list[dict]:
    """Each deck with its slides' text and speaker notes, so the script can say what each slide means."""
    return [{"label": s["label"], "slides": f"{s['slide_offset']}..{s['slide_offset'] + s['slide_count'] - 1}"
             if s["slide_count"] else "none (text only)", "content": s["text"][:12000]}
            for s in p["sources"] if s["kind"] in ("pptx", "pdf", "gslides")]   # gslides: older projects


def _summary(p: dict, decks: bool = False) -> dict:
    out = {
        "id": p["id"], "name": p["name"], "base_url": p["base_url"], "goal": p["goal"],
        "audience": p.get("audience", ""), "instructions": p["instructions"],
        "voice_profile": p.get("profile_id") or "(active profile)", "speed": p.get("speed") or "(the voice's)",
        "script_approved": p["script_approved"], "has_login": p["has_login"],
        "slide_count": len(p["slides"]),
        "segments": [{k: v for k, v in s.items() if v not in ("", [], None) or k in ("type", "narration")}
                     for s in p["segments"]],
        "failed_checks": [c for c in p["checks"] if not c["ok"]],
        "renders": [r["file"] for r in p["renders"]],
        "studio_url": f"{client.BASE}/projects/{p['id']}",
    }
    if decks:
        out["decks"] = _decks(p)
    return out


def _job(j: dict) -> dict:
    return {k: j[k] for k in ("id", "kind", "state", "message", "result", "error")} | {"log": j["log"][-12:]}


@mcp.tool()
def open_studio(project_id: str = "", open_browser: bool = True, page: str = "") -> str:
    """Start the Voice Demo Lab web app (if needed) and return its URL, so the user can review and edit the
    script, preview the voice, and manage voices and keys. page: "" (a project, or the project list), "setup"
    (first run: the user adds a Gemini API key and picks a voice) or "settings" (voice profiles and keys).
    If your host has a built-in browser or preview pane beside the chat (the Claude desktop app's browser
    pane, Antigravity's browser), pass open_browser=false and open the returned URL there yourself, so the
    studio sits beside the conversation. With open_browser=true it opens in the system browser instead."""
    base = client.ensure_server()
    url = f"{base}/{page}" if page in ("setup", "settings") else f"{base}/projects/{project_id}" if project_id else base
    if open_browser:
        webbrowser.open(url)
    return url


@mcp.tool(annotations=READ)
def get_settings() -> dict:
    """Setup state (setup_needed, setup_url), the active voice profile, saved profiles, key names (never
    the keys), models, output folder and Google sign-in."""
    st = client.call("GET", "/api/settings")
    return {**{k: st[k] for k in ("setup_needed", "tts_model", "output_dir", "audience",
                                  "fake_gemini")},
            "setup_url": f"{client.BASE}/setup",
            "active_profile": _profile(st["active"]) if st["active"] else None,
            "profiles": [_profile(v) for v in st["profiles"]],
            "keys": [{"id": k["id"], "name": k["name"], "ends_with": k["hint"]} for k in st["keys"]]}


def _profile(v: dict) -> dict:
    return {k: v[k] for k in ("id", "name", "description", "voice_name", "voice", "kind", "style", "speed")} | \
        {"verified": bool(v.get("verified_at")), **({"verify_error": v["verify_error"]} if v.get("verify_error") else {})}


@mcp.tool()
def update_settings(tts_model: str | None = None, output_dir: str | None = None,
                    audience: str | None = None) -> dict:
    """Change non-secret settings. Keys and voices are managed by the user on the setup/settings pages."""
    body = {k: v for k, v in dict(tts_model=tts_model, output_dir=output_dir,
                                  audience=audience).items()
            if v is not None}
    client.call("PUT", "/api/settings", json=body)
    return get_settings()


@mcp.tool(annotations=READ)
def list_voice_profiles() -> dict:
    """The saved voice profiles (each a saved API key paired with a custom or standard voice and a delivery
    style) and which one is active."""
    st = client.call("GET", "/api/settings")
    return {"active": st["active_profile"], "profiles": [_profile(v) for v in st["profiles"]],
            "setup_needed": st["setup_needed"], "settings_url": f"{client.BASE}/settings"}


def _find_profile(st: dict, profile: str) -> dict:
    want = profile.lower().strip()
    for v in st["profiles"]:
        if want in (v["id"].lower(), v["name"].lower()):
            return v
    names = ", ".join(v["name"] for v in st["profiles"]) or "none yet"
    raise ValueError(f"No voice profile called {profile!r}. Saved profiles: {names}. The user can add one "
                     f"at {client.BASE}/settings.")


@mcp.tool()
def verify_voice_profile(profile: str = "") -> dict:
    """Test a saved voice profile end to end (key accepted, voice available to that key, a short phrase
    spoken). profile: a name or id; default the active one. Takes a few seconds. If it fails, tell the user
    the error and point them to the settings page to fix the key or voice."""
    st = client.call("GET", "/api/settings")
    v = _find_profile(st, profile) if profile else st["active"]
    if not v:
        return {"verified": False, "error": "No voice set up yet.", "setup_url": f"{client.BASE}/setup"}
    r = client.call("POST", f"/api/profiles/{v['id']}/verify", timeout=120)
    return {"profile": v["name"], "verified": r["ok"], **({"error": r["error"],
            "settings_url": f"{client.BASE}/settings"} if not r["ok"] else {})}


@mcp.tool()
def use_voice_profile(profile: str, project_id: str = "") -> dict:
    """Switch voices. profile: a saved profile's name or id (case-insensitive; list_voice_profiles shows each
    one's description). With project_id, only that project uses it (its narration is re-recorded at the
    next render); without, it becomes the active profile for all projects that have not picked one. To add
    a new voice or key, send the user to the settings page."""
    v = _find_profile(client.call("GET", "/api/settings"), profile)
    if project_id:
        return _summary(client.call("PATCH", f"/api/projects/{project_id}", json={"profile_id": v["id"]})) | \
            {"voice_profile": _profile(v)}
    st = client.call("POST", f"/api/profiles/{v['id']}/activate")
    return {"active": _profile(st["active"])}


@mcp.tool(annotations=READ)
def list_projects() -> list:
    """All demo projects, most recently updated first."""
    return client.call("GET", "/api/projects")


@mcp.tool()
def start_demo(title: str, goal: str, brief: str, audience: str = "", instructions: str = "",
               base_url: str = "", decks: list[str] | None = None, voice_profile: str = "") -> dict:
    """Start a demo video from this session. Call it when the user asks for a demo of what the session
    analyzed. Then open studio_url in your side panel, read script_guide and call write_script.
    - title: the video's title.  goal: what the video must get across, in one or two sentences.
    - brief: what this session established, in plain prose: what was analyzed or built, how it works, what
      matters, decisions, what is unfinished or must not be shown. Shown to the user beside the script.
    - audience: who will watch (default: new to the subject).  instructions: tone, length, emphasis.
    - base_url: the running app to record, for live web steps (empty for slides-only videos).
    - decks: the slide decks the session used, as local .pptx or .pdf paths (export a Google Slides deck to
      one of these with your own Google Drive / Slides tools first). Their slides
      become images for slide segments; the result lists each slide's text and speaker notes.
    - voice_profile: a saved profile's name or id (default: the active one)."""
    st = client.call("GET", "/api/settings")
    if st["setup_needed"]:
        return {"setup_needed": True, "setup_url": f"{client.BASE}/setup",
                "next": "Open setup_url in your side panel and ask the user to add a Gemini API key and choose "
                        "a voice there; call start_demo again once they are done."}
    body = dict(name=title, goal=goal, brief=brief, audience=audience, instructions=instructions, base_url=base_url)
    if voice_profile:
        body["profile_id"] = _find_profile(st, voice_profile)["id"]
    p = client.call("POST", "/api/projects", json=body)
    problems = []
    for ref in decks or []:
        try:
            p = client.call("POST", f"/api/projects/{p['id']}/decks", json={"ref": ref})
        except RuntimeError as e:
            problems.append(f"{ref}: {e}")
    out = _summary(p, decks=True)
    if problems:
        out["deck_problems"] = problems
    out["next"] = "Open studio_url in your side panel, read script_guide, then write_script."
    return out


@mcp.tool(annotations=READ)
def script_guide() -> str:
    """How to write the script: the segment format, actions for web steps, the user's house style, and
    writing for a text-to-speech voice. Read it before write_script."""
    from .script import GUIDE
    return GUIDE


@mcp.tool()
def write_script(project_id: str, segments: list[dict]) -> dict:
    """Save the narration script you wrote (the whole thing, in playing order; see script_guide). It is
    checked first: if `errors` comes back, nothing was saved; fix them and call again. `warnings` are
    style or reading-aloud issues worth fixing. Saving un-approves the script. Returns the estimated
    length and the studio link, where the user reviews it beside the chat."""
    try:
        r = client.call("PUT", f"/api/projects/{project_id}/segments", json=segments)
    except client.ApiError as e:
        if isinstance(e.detail, dict) and "errors" in e.detail:
            return {"saved": False, **e.detail}
        raise
    return {"saved": True, "warnings": r["warnings"], "estimated_minutes": round(r["seconds"] / 60, 1),
            "segments": len(r["project"]["segments"]),
            "segment_ids": [s["id"] for s in r["project"]["segments"]],
            "studio_url": f"{client.BASE}/projects/{project_id}?tab=script",
            "next": "Summarise the script in chat and ask the user to review and approve it in the side panel."}


@mcp.tool(annotations=READ)
def get_project(project_id: str) -> dict:
    """The project: brief, full script (segments + actions), decks with slide text and notes, failed
    checks and renders. Read it again before revising: the user may have edited the script in the studio."""
    return _summary(client.call("GET", f"/api/projects/{project_id}"), decks=True)


@mcp.tool()
def update_project(project_id: str, name: str | None = None, base_url: str | None = None, goal: str | None = None,
                   brief: str | None = None, audience: str | None = None, instructions: str | None = None,
                   voice_style: str | None = None, speed: float | None = None, decks: list[str] | None = None) -> dict:
    """Edit project fields, or attach more decks. voice_style overrides the voice profile's delivery style
    for this project ("" clears it). speed sets this demo's narration pace, 0.7 to 1.4 (1.1 = 10% faster;
    0 = the voice profile's pace); try it first with preview_voice(text, project_id, speed). To give the
    project another voice, use use_voice_profile."""
    body = {k: v for k, v in dict(name=name, base_url=base_url, goal=goal, brief=brief, audience=audience,
                                  instructions=instructions, voice_style=voice_style, speed=speed).items()
            if v is not None}
    p = client.call("PATCH", f"/api/projects/{project_id}", json=body)
    for ref in decks or []:
        p = client.call("POST", f"/api/projects/{project_id}/decks", json={"ref": ref})
    return _summary(p, decks=bool(decks))


@mcp.tool()
def update_segment(project_id: str, segment_id: str, changes_json: str) -> dict:
    """Patch one segment with a JSON object of fields (see script_guide), e.g. to apply a change the user
    asked for in chat. Un-approves the script."""
    return _summary(client.call("PATCH", f"/api/projects/{project_id}/segments/{segment_id}",
                                json=json.loads(changes_json)))


@mcp.tool()
def approve_script(project_id: str, approved: bool = True) -> dict:
    """Mark the script approved for rendering. Call ONLY when the user has explicitly approved it."""
    return _summary(client.call("POST", f"/api/projects/{project_id}/approve", json={"approved": approved}))


@mcp.tool()
def capture_login(project_id: str, url: str = "") -> dict:
    """Open a visible browser at the app (or url) so the USER signs in; the session is saved for exploration,
    dry runs and recording when they close the window. Never type credentials yourself."""
    j = client.wait_job(client.call("POST", f"/api/projects/{project_id}/login", json={"url": url}), timeout=900)
    return _job(j)


@mcp.tool()
def inspect_page(project_id: str, url: str = "") -> dict:
    """Open a page of the app the way the recorder will (saved login included) and return its title,
    visible text and interactive elements with ready-to-use selectors. url: a path or full URL (default:
    the project's base_url). Use it to write or fix step actions."""
    return client.call("POST", f"/api/projects/{project_id}/inspect", json={"url": url}, timeout=180)


@mcp.tool()
def dry_run(project_id: str) -> dict:
    """Run every web step's actions headless (no narration) and report which fail, with a screenshot of
    the page at each failure (view it to see what went wrong). Fix with update_segment. Waits."""
    from . import config
    j = client.wait_job(client.call("POST", f"/api/projects/{project_id}/dryrun"), timeout=1800)
    p = client.call("GET", f"/api/projects/{project_id}")
    shots = config.HOME / "projects" / project_id / "checks"
    return {"job": _job(j), "failed_checks": [c | ({"screenshot": str(shots / c["shot"])} if c.get("shot") else {})
                                              for c in p["checks"] if not c["ok"]],
            "passed": sum(c["ok"] for c in p["checks"])}


@mcp.tool()
def preview_voice(text: str, project_id: str = "", speed: float | None = None) -> dict:
    """Speak text in the project's voice (else the active profile) as a test clip: returns the WAV's path,
    its length and its measured words per minute. speed (0.7 to 1.4) tries a pace without saving it."""
    import httpx
    from . import config
    client.ensure_server()
    r = httpx.post(f"{client.BASE}/api/voice/preview", timeout=180,
                   json={"text": text, "project_id": project_id or None, "speed": speed})
    if r.status_code >= 400:
        raise client.ApiError("POST", "/api/voice/preview", r.status_code, r.json().get("detail"))
    out = config.HOME / "previews" / "last_preview.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return {"wav": str(out), "seconds": float(r.headers["X-Seconds"]),
            "words_per_minute": int(r.headers["X-Words-Per-Minute"])}


@mcp.tool()
def render(project_id: str, wait: bool = False, force: bool = False) -> dict:
    """Render the approved script to MP4 (narration, cards, slides, recorded web steps). Takes minutes:
    by default returns the job at once; poll with get_job. force renders an unapproved script (only if the
    user asked)."""
    j = client.call("POST", f"/api/projects/{project_id}/render", json={"force": force})
    return _job(client.wait_job(j, timeout=3600) if wait else j)


@mcp.tool(annotations=READ)
def get_job(job_id: str) -> dict:
    """Status, progress message and log tail of a background job."""
    return _job(client.call("GET", f"/api/jobs/{job_id}"))


def main() -> None:
    mcp.run()
