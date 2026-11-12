"""MCP server (stdio) for Google Antigravity (primary) and Claude Code.

Plugin-only architecture:
  1. Research-grounded authoring: gather authoritative docs, blogs, videos, slide notes & live UI context,
     store citations via `save_research`, and draft narration via `script_guide` + `write_script`.
  2. Three automated scenarios (+ hybrid):
     - In-AGY created slides + AGY session context + user instructions
     - User-provided slides (Google Slides URL/ID, `.pdf` + `.gslides.json`, or `.pptx`) + context + directions
     - Live website (e.g. `console.cloud.google.com`) + user context + instructions, orchestrated 100% in
       Antigravity's built-in `browser` subagent with interactive login onboarding (`record_web_auth`) and
       1080p step frame capture (`record_step_frames`).
  3. Studio Sidecar UI: surface `[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)` so the user
     can review/approve scripts, preview voices, manage Gemini API keys in the OS keychain, and watch MP4s.
"""
from __future__ import annotations

import json
import webbrowser

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import client

READ = ToolAnnotations(readOnlyHint=True)
SIDECAR_PILL = "[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)"
PLUGIN_PILL = "[Voice Demo Lab](customization://custom-voice-demo-lab)"

mcp = MCPServer(
    "voice-demo-lab",
    version="0.4.0",
    instructions=(
        "Voice Demo Lab is an Antigravity-first plugin for automating grounded, narrated 1080p demo/overview "
        "videos from slides (in-AGY or user-provided Google Slides / PDF / PPTX) and live websites, voiced in "
        "the user's custom or standard Gemini TTS voice. "
        "Workflow: "
        "1) `get_settings()` — if `setup_needed` is true, call `open_studio(page='setup')`, give the user the "
        f"{SIDECAR_PILL} pill in chat so they can add their Gemini API key and choose a voice in the side pane, "
        "and wait (NEVER ask for, accept, or echo a Gemini API key in chat). "
        "2) For website/hybrid demos (`base_url`), run login onboarding FIRST in Antigravity's built-in `browser` "
        "subagent: check if the user is signed in at `base_url`; if a login screen appears, pause and ask the "
        "user to sign in inside the Antigravity Browser pane, then resume and call `record_web_auth`. "
        "3) `start_demo(...)` — attach slide decks and/or `base_url`. "
        "4) Research reality first (delegate to `demo-researcher` or use `search_web` / docs / slides / browser) "
        "and persist verified sources via `save_research(...)`. "
        "5) Read `script_guide()`, call `write_script(...)`, surface the Studio sidecar pill in chat, and wait "
        "for user approval (`approve_script` only when explicitly approved). "
        "6) For `step` segments, execute the walkthrough in Antigravity's `browser` subagent and save `before` / "
        "`during` / `result` screenshots via `record_step_frames(...)`. "
        "7) Verify with `check_demo_readiness(...)` and run `render(...)`."
    ),
)


def _decks(p: dict) -> list[dict]:
    """Each deck with its slides' text and speaker notes, so the script can explain what each slide means."""
    return [
        {
            "label": s["label"],
            "kind": s["kind"],
            "slides": f"{s['slide_offset']}..{s['slide_offset'] + s['slide_count'] - 1}"
            if s["slide_count"]
            else "none (text only)",
            "content": s["text"][:14000],
        }
        for s in p["sources"]
        if s["kind"] in ("pptx", "pdf", "gslides")
    ]


def _summary(p: dict, decks: bool = False) -> dict:
    out = {
        "id": p["id"],
        "name": p["name"],
        "scenario": p.get("scenario", "slides"),
        "base_url": p["base_url"],
        "goal": p["goal"],
        "audience": p.get("audience", ""),
        "instructions": p["instructions"],
        "voice_profile": p.get("profile_id") or "(active profile)",
        "speed": p.get("speed") or "(the voice's)",
        "script_approved": p["script_approved"],
        "web_auth": p.get("web_auth", {"status": "unchecked"}),
        "research_summary": p.get("research_summary", ""),
        "research_count": len(p.get("research", [])),
        "research": [
            {
                "id": r["id"],
                "title": r["title"],
                "source_type": r["source_type"],
                "url_or_path": r["url_or_path"],
                "verified_claims": r["verified_claims"],
            }
            for r in p.get("research", [])
        ],
        "slide_count": len(p["slides"]),
        "segments": [
            {
                k: (len(v) if k == "frames" else v)
                for k, v in s.items()
                if v not in ("", [], None) or k in ("type", "narration")
            }
            | ({"frame_files": [f["file"] for f in s.get("frames", [])]} if s.get("frames") else {})
            for s in p["segments"]
        ],
        "renders": [r["file"] for r in p["renders"]],
        "renders_detail": [
            {
                "index": idx,
                "file": r["file"],
                "seconds": r["seconds"],
                **({"drive_url": r["drive_url"]} if r.get("drive_url") else {}),
                **({"drive_file_id": r["drive_file_id"]} if r.get("drive_file_id") else {}),
                **({"drive_folder": r["drive_folder"]} if r.get("drive_folder") else {}),
            }
            for idx, r in enumerate(p["renders"])
        ],
        "studio_url": f"{client.BASE}/projects/{p['id']}",
        "sidecar_pill": SIDECAR_PILL,
    }
    if decks:
        out["decks"] = _decks(p)
    return out


def _job(j: dict) -> dict:
    return {k: j[k] for k in ("id", "kind", "state", "message", "result", "error")} | {"log": j["log"][-12:]}


@mcp.tool()
def open_studio(project_id: str = "", open_browser: bool = False, page: str = "") -> dict:
    """Ensure the local Voice Demo Studio backend is running and return its Antigravity Sidecar pill + URL.
    - `page`: `""` (project view or project list), `"setup"` (first-time Gemini API key + voice setup), or
      `"settings"` (voice profiles, pacing, output folder).
    - `open_browser`: defaults to `False` because Voice Demo Studio runs inside Google Antigravity's sidecar
      auxiliary pane (`[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)`). Pass `True` only if
      running in a host without sidecar panels and the user asks for an external browser tab."""
    base = client.ensure_server()
    url = (
        f"{base}/{page}"
        if page in ("setup", "settings")
        else f"{base}/projects/{project_id}"
        if project_id
        else base
    )
    if open_browser:
        webbrowser.open(url)
    return {
        "studio_url": url,
        "sidecar_pill": SIDECAR_PILL,
        "plugin_pill": PLUGIN_PILL,
        "opened_system_browser": open_browser,
        "hint": f"Include {SIDECAR_PILL} verbatim in your chat reply so the user can open Voice Demo Studio in the Antigravity side pane.",
    }


@mcp.tool(annotations=READ)
def get_settings() -> dict:
    """Setup state (`setup_needed`, `setup_url`, `sidecar_pill`), active voice profile, saved profiles,
    saved key hints (never raw keys), TTS model, and output directory."""
    st = client.call("GET", "/api/settings")
    return {
        **{k: st[k] for k in ("setup_needed", "tts_model", "output_dir", "audience", "fake_gemini")},
        "setup_url": f"{client.BASE}/setup",
        "sidecar_pill": SIDECAR_PILL,
        "active_profile": _profile(st["active"]) if st["active"] else None,
        "profiles": [_profile(v) for v in st["profiles"]],
        "keys": [{"id": k["id"], "name": k["name"], "ends_with": k["hint"]} for k in st["keys"]],
    }


def _profile(v: dict) -> dict:
    return (
        {k: v[k] for k in ("id", "name", "description", "voice_name", "voice", "kind", "style", "speed")}
        | {
            "verified": bool(v.get("verified_at")),
            **({"verify_error": v["verify_error"]} if v.get("verify_error") else {}),
        }
    )


@mcp.tool()
def update_settings(
    tts_model: str | None = None,
    output_dir: str | None = None,
    audience: str | None = None,
) -> dict:
    """Update non-secret settings (`tts_model`, `output_dir`, `audience`). API keys and voices are configured in Voice Demo Studio."""
    body = {
        k: v
        for k, v in dict(tts_model=tts_model, output_dir=output_dir, audience=audience).items()
        if v is not None
    }
    client.call("PUT", "/api/settings", json=body)
    return get_settings()


@mcp.tool(annotations=READ)
def list_voice_profiles() -> dict:
    """List saved voice profiles (each pairing an OS-keychain API key with a custom or standard Gemini TTS voice) and the active profile."""
    st = client.call("GET", "/api/settings")
    return {
        "active": st["active_profile"],
        "profiles": [_profile(v) for v in st["profiles"]],
        "setup_needed": st["setup_needed"],
        "settings_url": f"{client.BASE}/settings",
        "sidecar_pill": SIDECAR_PILL,
    }


def _find_profile(st: dict, profile: str) -> dict:
    want = profile.lower().strip()
    for v in st["profiles"]:
        if want in (v["id"].lower(), v["name"].lower()):
            return v
    names = ", ".join(v["name"] for v in st["profiles"]) or "none yet"
    raise ValueError(
        f"No voice profile called {profile!r}. Saved profiles: {names}. "
        f"Open {SIDECAR_PILL} ({client.BASE}/settings) to add one."
    )


@mcp.tool()
def verify_voice_profile(profile: str = "") -> dict:
    """Test a saved voice profile end-to-end (key valid, voice accessible, short phrase synthesized)."""
    st = client.call("GET", "/api/settings")
    v = _find_profile(st, profile) if profile else st["active"]
    if not v:
        return {"verified": False, "error": "No voice set up yet.", "setup_url": f"{client.BASE}/setup", "sidecar_pill": SIDECAR_PILL}
    r = client.call("POST", f"/api/profiles/{v['id']}/verify", timeout=120)
    return {
        "profile": v["name"],
        "verified": r["ok"],
        **(
            {"error": r["error"], "settings_url": f"{client.BASE}/settings", "sidecar_pill": SIDECAR_PILL}
            if not r["ok"]
            else {}
        ),
    }


@mcp.tool()
def use_voice_profile(profile: str, project_id: str = "") -> dict:
    """Switch narrator voice profile globally (when `project_id` is empty) or for a single project."""
    v = _find_profile(client.call("GET", "/api/settings"), profile)
    if project_id:
        return _summary(client.call("PATCH", f"/api/projects/{project_id}", json={"profile_id": v["id"]})) | {
            "voice_profile": _profile(v)
        }
    st = client.call("POST", f"/api/profiles/{v['id']}/activate")
    return {"active": _profile(st["active"])}


@mcp.tool(annotations=READ)
def list_projects() -> list:
    """List all demo video projects, most recently updated first."""
    return client.call("GET", "/api/projects")


@mcp.tool()
def start_demo(
    title: str,
    goal: str,
    brief: str,
    scenario: str = "",
    audience: str = "",
    instructions: str = "",
    base_url: str = "",
    decks: list[str] | None = None,
    gslides_jsons: list[str] | None = None,
    voice_profile: str = "",
) -> dict:
    """Create a new automated demo video project in Google Antigravity (or Claude Code).
    Supports:
    1) In-AGY created slides + AGY context + user instructions (`scenario='slides'`, pass exported PDF/PPTX or Google Slides URL in `decks`)
    2) User-provided slides + context + directions (`scenario='slides'`, pass Google Slides URL, `.pdf`, or `.pptx` in `decks`)
    3) Live website + user context + instructions (`scenario='website'`, pass `base_url` e.g. `'https://console.cloud.google.com'`)
    4) Hybrid slides + live website (`scenario='hybrid'`, pass both `decks` and `base_url`)

    Tip for Google Slides in Antigravity: run `gslides readonly export <ID> deck.pdf --format pdf` and
    `gslides readonly info <ID> --json > deck.gslides.json` in your shell first so both 1080p slide visuals
    AND speaker notes are ingested cleanly, then pass `decks=['/abs/path/deck.pdf']`."""
    st = client.call("GET", "/api/settings")
    if st["setup_needed"]:
        return {
            "setup_needed": True,
            "setup_url": f"{client.BASE}/setup",
            "sidecar_pill": SIDECAR_PILL,
            "next": f"Include {SIDECAR_PILL} in your reply and ask the user to add their Gemini API key and choose a voice on the Setup page; call `start_demo` again once done.",
        }

    inferred_scenario = scenario.strip().lower()
    if inferred_scenario not in ("slides", "website", "hybrid"):
        if base_url.strip() and decks:
            inferred_scenario = "hybrid"
        elif base_url.strip():
            inferred_scenario = "website"
        else:
            inferred_scenario = "slides"

    body: dict = dict(
        name=title,
        scenario=inferred_scenario,
        goal=goal,
        brief=brief,
        audience=audience,
        instructions=instructions,
        base_url=base_url,
    )
    if voice_profile:
        body["profile_id"] = _find_profile(st, voice_profile)["id"]
    p = client.call("POST", "/api/projects", json=body)

    problems = []
    json_list = gslides_jsons or []
    for idx, ref in enumerate(decks or []):
        gjson = json_list[idx] if idx < len(json_list) else ""
        try:
            p = client.call(
                "POST",
                f"/api/projects/{p['id']}/decks",
                json={"ref": ref, "gslides_json": gjson},
            )
        except Exception as e:
            problems.append(f"{ref}: {e}")

    out = _summary(p, decks=True)
    if problems:
        out["deck_problems"] = problems
    if base_url.strip():
        out["next"] = (
            "1) Check login onboarding in Antigravity's `browser` subagent at `base_url` and call `record_web_auth`. "
            "2) Research technical docs/blogs/slides (`demo-researcher`) and call `save_research`. "
            f"3) Read `script_guide`, call `write_script`, and share {SIDECAR_PILL} with the user."
        )
    else:
        out["next"] = (
            "1) Research authoritative docs/blogs/videos for the slide topics (`demo-researcher`) and call `save_research`. "
            f"2) Read `script_guide`, call `write_script`, and share {SIDECAR_PILL} with the user."
        )
    return out


@mcp.tool()
def save_research(
    project_id: str,
    summary: str,
    items: list[dict],
    append: bool = False,
) -> dict:
    """Save verified research findings so the narration script is grounded in reality (technical docs, recent
    blogs/announcements, release notes, videos, slide speaker notes, and live UI facts).
    Each item in `items`:
      `{"title": "...", "source_type": "docs"|"blog"|"video"|"slide"|"webpage"|"code"|"context",
        "url_or_path": "...", "summary": "...", "verified_claims": ["claim 1", "claim 2"]}`."""
    p = client.call(
        "POST",
        f"/api/projects/{project_id}/research",
        json={"summary": summary, "items": items, "append": append},
    )
    return _summary(p)


@mcp.tool()
def record_web_auth(
    project_id: str,
    status: str,
    checked_url: str = "",
    account_hint: str = "",
    notes: str = "",
) -> dict:
    """Record the outcome of the in-Antigravity browser login onboarding check for a website/hybrid demo.
    - `status`: `"authenticated"` (signed in and ready), `"login_required"` (paused waiting for user to sign in
      inside the Antigravity Browser pane), `"not_needed"` (public site requiring no login), or `"unchecked"`.
    - `account_hint`: non-secret display label (e.g. `'Google Cloud Console — project demo-prod'`). Never pass passwords or tokens."""
    p = client.call(
        "POST",
        f"/api/projects/{project_id}/web-auth",
        json={
            "status": status,
            "checked_url": checked_url,
            "account_hint": account_hint,
            "notes": notes,
        },
    )
    return _summary(p)


@mcp.tool(annotations=READ)
def script_guide() -> str:
    """Authoring guide: segment types (`card`, `slide`, `step`), research grounding rules, in-AGY browser step
    actions & frame choreography, house style, and writing natural narration for Gemini TTS."""
    from .script import GUIDE
    return GUIDE


@mcp.tool()
def write_script(project_id: str, segments: list[dict]) -> dict:
    """Validate and save the complete narration script (in playing order; read `script_guide` first).
    If validation `errors` occur, nothing is saved — fix them and retry. Saving resets `script_approved`."""
    try:
        r = client.call("PUT", f"/api/projects/{project_id}/segments", json=segments)
    except client.ApiError as e:
        if isinstance(e.detail, dict) and "errors" in e.detail:
            return {"saved": False, **e.detail}
        raise
    return {
        "saved": True,
        "warnings": r["warnings"],
        "estimated_minutes": round(r["seconds"] / 60, 1),
        "segments": len(r["project"]["segments"]),
        "segment_ids": [s["id"] for s in r["project"]["segments"]],
        "studio_url": f"{client.BASE}/projects/{project_id}?tab=script",
        "sidecar_pill": SIDECAR_PILL,
        "next": (
            f"Share {SIDECAR_PILL} in chat with a concise outline of the script so the user can review, "
            "preview the voice, and approve. If the script has `step` segments, capture their AGY browser frames "
            "via `record_step_frames` before rendering."
        ),
    }


@mcp.tool(annotations=READ)
def get_project(project_id: str) -> dict:
    """Return full project state: scenario, brief, grounded research, AGY browser auth status, decks with slide
    text & speaker notes, script segments (including captured frame counts), and renders."""
    return _summary(client.call("GET", f"/api/projects/{project_id}"), decks=True)


@mcp.tool()
def update_project(
    project_id: str,
    name: str | None = None,
    scenario: str | None = None,
    base_url: str | None = None,
    goal: str | None = None,
    brief: str | None = None,
    audience: str | None = None,
    instructions: str | None = None,
    research_summary: str | None = None,
    voice_style: str | None = None,
    speed: float | None = None,
    decks: list[str] | None = None,
) -> dict:
    """Update project metadata, pacing (`speed` 0.7..1.4, or 0 for profile default), `voice_style`, or attach more decks."""
    body = {
        k: v
        for k, v in dict(
            name=name,
            scenario=scenario,
            base_url=base_url,
            goal=goal,
            brief=brief,
            audience=audience,
            instructions=instructions,
            research_summary=research_summary,
            voice_style=voice_style,
            speed=speed,
        ).items()
        if v is not None
    }
    p = client.call("PATCH", f"/api/projects/{project_id}", json=body)
    for ref in decks or []:
        p = client.call("POST", f"/api/projects/{project_id}/decks", json={"ref": ref})
    return _summary(p, decks=bool(decks))


@mcp.tool()
def update_segment(project_id: str, segment_id: str, changes_json: str) -> dict:
    """Patch one segment with a JSON object of fields (see `script_guide`). Resets `script_approved`."""
    return _summary(
        client.call(
            "PATCH",
            f"/api/projects/{project_id}/segments/{segment_id}",
            json=json.loads(changes_json),
        )
    )


@mcp.tool()
def approve_script(project_id: str, approved: bool = True) -> dict:
    """Mark the script approved for rendering. Call ONLY after explicit user approval in chat or Voice Demo Studio."""
    return _summary(client.call("POST", f"/api/projects/{project_id}/approve", json={"approved": approved}))


@mcp.tool()
def record_step_frames(
    project_id: str,
    segment_id: str,
    frames: list[dict],
    append: bool = False,
) -> dict:
    """Attach 1+ screenshots captured from Antigravity's built-in `browser` subagent to a `step` segment.
    Each dict in `frames`:
      - `path`: absolute path to the screenshot PNG/JPEG saved by the `browser` subagent (required)
      - `phase`: `"before"` | `"during"` | `"result"` (`before`/`during` play during `narration`; `result` plays during `after_narration`)
      - `caption`: short description shown in Studio
      - `highlight`: optional `{"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.2, "label": "Enabled status"}` (0..1 normalized or 1920x1080 px)
      - `zoom_to`: optional `{"x": ..., "y": ..., "w": ..., "h": ...}` for smooth camera zoom-in
      - `ff_what` / `ff_elapsed`: optional fast-forward banner text & simulated wait seconds (e.g. `45`)."""
    p = client.call(
        "POST",
        f"/api/projects/{project_id}/segments/{segment_id}/frames",
        json={"frames": frames, "append": append},
    )
    return _summary(p)


@mcp.tool(annotations=READ)
def check_demo_readiness(project_id: str) -> dict:
    """Check whether the project is ready to render: voice profile configured, script approved, grounded
    research recorded, AGY browser login verified (for website/hybrid demos), and every `step` segment has frames."""
    return client.call("GET", f"/api/projects/{project_id}/readiness")


@mcp.tool()
def preview_voice(text: str, project_id: str = "", speed: float | None = None) -> dict:
    """Synthesize a short test clip in the project's voice (or active profile) and return WAV path, seconds, and WPM."""
    import httpx
    from . import config

    client.ensure_server()
    r = httpx.post(
        f"{client.BASE}/api/voice/preview",
        timeout=180,
        json={"text": text, "project_id": project_id or None, "speed": speed},
    )
    if r.status_code >= 400:
        raise client.ApiError("POST", "/api/voice/preview", r.status_code, r.json().get("detail"))
    out = config.HOME / "previews" / "last_preview.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return {
        "wav": str(out),
        "seconds": float(r.headers["X-Seconds"]),
        "words_per_minute": int(r.headers["X-Words-Per-Minute"]),
    }


@mcp.tool()
def render(project_id: str, wait: bool = False, force: bool = False) -> dict:
    """Render the approved project to a 1080p MP4 (Gemini TTS narration, 2x supersampled title cards, slides,
    and AGY browser step sequences). Pass `wait=True` for short/medium demos or poll with `get_job`."""
    j = client.call("POST", f"/api/projects/{project_id}/render", json={"force": force})
    return _job(client.wait_job(j, timeout=3600) if wait else j)


@mcp.tool(annotations=READ)
def get_job(job_id: str) -> dict:
    """Get status, progress message, result, and recent log lines of a background render job."""
    return _job(client.call("GET", f"/api/jobs/{job_id}"))


@mcp.tool()
def record_render_drive_upload(
    project_id: str,
    drive_url: str,
    drive_file_id: str = "",
    drive_folder: str = "",
    render_index: int = -1,
) -> dict:
    """Record the Google Drive shareable URL and file ID on a rendered MP4 after uploading it via Antigravity's
    official Google Drive (`gdrive`) plugin, so Voice Demo Studio displays an 'Open in Google Drive' button.
    `render_index`: 0-based index into `project.renders` (defaults to `-1` for the most recent render)."""
    p = client.call("GET", f"/api/projects/{project_id}")
    renders = p.get("renders", [])
    if not renders:
        raise ValueError(f"Project {project_id} has no rendered videos yet.")
    idx = len(renders) - 1 if render_index < 0 else render_index
    updated = client.call(
        "PATCH",
        f"/api/projects/{project_id}/renders/{idx}",
        json={
            "drive_url": drive_url,
            "drive_file_id": drive_file_id,
            "drive_folder": drive_folder,
        },
    )
    return _summary(updated)


def main() -> None:
    mcp.run()
