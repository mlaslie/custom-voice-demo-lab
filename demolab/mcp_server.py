"""MCP server (stdio) for Claude Code and Google Antigravity: the same operations as the web app.

The service holds all state; these tools are thin calls to it, so the agent and the web app always see the
same project. The Gemini API key is never accepted or returned here: users set it in the web app.
"""
from __future__ import annotations

import json
import pathlib
import webbrowser

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import client

READ = ToolAnnotations(readOnlyHint=True)

mcp = MCPServer("voice-demo-lab", version="0.1.4", instructions=(
    "Voice Demo Lab makes narrated demo videos (custom Gemini TTS voice) of web apps and slide decks. "
    "Flow: create_project -> add_session_context (when the request comes out of a working session) -> "
    "add_source (url/repo/pptx/pdf/gslides/text) -> draft_script (or set_segments) "
    "-> the user reviews in the web app (open_studio(open_browser=false), then show the URL in your host's "
    "side panel / built-in browser if it has one; open it as soon as the project exists) -> approve_script ONLY when the user says so -> "
    "plan_actions + dry_run for web steps -> render. Never ask for or handle the Gemini API key: tell the "
    "user to add it in the web app's Settings."))


def _summary(p: dict) -> dict:
    return {
        "id": p["id"], "name": p["name"], "base_url": p["base_url"], "goal": p["goal"],
        "instructions": p["instructions"], "script_approved": p["script_approved"], "has_login": p["has_login"],
        "slides": len(p["slides"]),
        "sources": [{"id": s["id"], "kind": s["kind"], "label": s["label"], "slides": s["slide_count"],
                     "first_slide": s["slide_offset"]} for s in p["sources"]],
        "segments": [{k: v for k, v in s.items() if v not in ("", [], None) or k in ("type", "narration")}
                     for s in p["segments"]],
        "failed_checks": [c for c in p["checks"] if not c["ok"]],
        "renders": [r["file"] for r in p["renders"]],
        "studio_url": f"{client.BASE}/projects/{p['id']}",
    }


def _job(j: dict) -> dict:
    return {k: j[k] for k in ("id", "kind", "state", "message", "result", "error")} | {"log": j["log"][-12:]}


@mcp.tool()
def open_studio(project_id: str = "", open_browser: bool = True) -> str:
    """Start the Voice Demo Lab web app (if needed) and return its URL, so the user can review and edit the
    script, preview the voice, and manage Settings (voice id, key).
    If your host has a built-in browser or preview pane beside the chat (the Claude desktop app's browser
    pane, Antigravity's browser), pass open_browser=false and open the returned URL there yourself, so the
    studio sits beside the conversation. With open_browser=true it opens in the system browser instead."""
    base = client.ensure_server()
    url = f"{base}/projects/{project_id}" if project_id else base
    if open_browser:
        webbrowser.open(url)
    return url


@mcp.tool(annotations=READ)
def get_settings() -> dict:
    """Voice id, style, models, output folder, and whether a Gemini key / Google sign-in is configured."""
    return client.call("GET", "/api/settings")


@mcp.tool()
def update_settings(voice_id: str | None = None, voice_style: str | None = None, tts_model: str | None = None,
                    script_model: str | None = None, output_dir: str | None = None,
                    google_client_secret: str | None = None, audience: str | None = None) -> dict:
    """Change non-secret settings. The API key is set by the user in the web app, never through this tool."""
    cur = client.call("GET", "/api/settings")
    keys = ("voice_id", "voice_style", "tts_model", "script_model", "output_dir", "google_client_secret", "audience")
    body = {k: cur[k] for k in keys}
    body.update({k: v for k, v in dict(voice_id=voice_id, voice_style=voice_style, tts_model=tts_model,
                                        script_model=script_model, output_dir=output_dir,
                                        google_client_secret=google_client_secret, audience=audience).items()
                 if v is not None})
    return client.call("PUT", "/api/settings", json=body)


@mcp.tool(annotations=READ)
def list_projects() -> list:
    """All demo projects, most recently updated first."""
    return client.call("GET", "/api/projects")


@mcp.tool()
def create_project(name: str, base_url: str = "", goal: str = "", instructions: str = "") -> dict:
    """Create a demo project. base_url: the web app to demo (if any). goal: what the demo must show.
    instructions: tone, length, emphasis; overrides the default narration style."""
    return _summary(client.call("POST", "/api/projects", json=dict(name=name, base_url=base_url, goal=goal,
                                                                    instructions=instructions)))


@mcp.tool(annotations=READ)
def get_project(project_id: str) -> dict:
    """The project with its full script (segments + actions), sources, failed checks and renders."""
    return _summary(client.call("GET", f"/api/projects/{project_id}"))


@mcp.tool()
def update_project(project_id: str, name: str | None = None, base_url: str | None = None, goal: str | None = None,
                   instructions: str | None = None, voice_id: str | None = None,
                   voice_style: str | None = None) -> dict:
    """Edit project fields; voice_id/voice_style override the global voice for this project."""
    body = {k: v for k, v in dict(name=name, base_url=base_url, goal=goal, instructions=instructions,
                                  voice_id=voice_id, voice_style=voice_style).items() if v is not None}
    return _summary(client.call("PATCH", f"/api/projects/{project_id}", json=body))


@mcp.tool()
def add_source(project_id: str, kind: str, ref: str = "", text: str = "", label: str = "") -> dict:
    """Add demo material. kind:
    - "url": a live page (ref = URL; captured with Playwright, uses the saved login if any)
    - "repo": a local source folder (ref = path)
    - "file": a local .pptx / .pdf / .md / .txt (ref = path); slides become slide images
    - "gslides": a Google Slides URL or id (needs Google connected in Settings)
    - "text": notes or an existing script (text = content)"""
    if kind == "file":
        f = pathlib.Path(ref).expanduser()
        with f.open("rb") as fh:
            p = client.call("POST", f"/api/projects/{project_id}/sources/upload",
                            files={"file": (f.name, fh)}, data={"label": label})
    else:
        p = client.call("POST", f"/api/projects/{project_id}/sources",
                        json=dict(kind=kind, ref=ref, text=text, label=label))
    return _summary(p)


@mcp.tool()
def add_session_context(project_id: str, goal: str, built: str = "", decisions: str = "",
                        highlights: str = "", caveats: str = "", audience: str = "",
                        files: list[str] | None = None, workspace: str = "", label: str = "") -> dict:
    """Give the script writer what this conversation knows. Call it before draft_script whenever the
    demo is about work done or discussed in the current session; the script is built around it.
    Write each field in plain prose from the conversation (facts, not instructions to the writer):
    - goal: what the work is for and who it helps
    - built: what was built or changed, including names of features, screens and commands
    - decisions: notable choices and why they were made
    - highlights: what the demo should show, in a sensible order
    - caveats: what is unfinished, broken or must not be shown
    - audience: who will watch, if the user said
    files: paths of the files and folders that matter most (docs, specs, key source files, screenshots,
    decks); relative paths resolve against `workspace` (the session's working folder). Keep it focused:
    a few to a couple of dozen entries. Never include secrets such as .env files or keys."""
    parts = [("Goal", goal), ("What was built or changed", built), ("Decisions and why", decisions),
             ("What to show", highlights), ("Caveats (do not show or claim)", caveats), ("Audience", audience)]
    brief = "\n\n".join(f"{h}:\n{v.strip()}" for h, v in parts if v and v.strip())
    return _summary(client.call("POST", f"/api/projects/{project_id}/sources", json=dict(
        kind="session", text=brief, files=files or [], ref=workspace, label=label or "Session context")))


@mcp.tool()
def draft_script(project_id: str) -> dict:
    """Have Gemini draft the narration script from the sources (replaces the current script). Waits."""
    j = client.wait_job(client.call("POST", f"/api/projects/{project_id}/script/draft"), timeout=600)
    return {"job": _job(j), "project": _summary(client.call("GET", f"/api/projects/{project_id}"))}


@mcp.tool()
def set_segments(project_id: str, segments_json: str) -> dict:
    """Replace the whole script (use when you write it yourself). JSON list of segments:
    {"type": "card"|"slide"|"step", "title", "kicker", "sub", "bullets": [], "slide": <0-based index>,
     "narration", "after_narration", "actions_at": "during"|"after", "notes", "actions": [...]}.
    Action: {"op": goto|click|fill|press|hover|scroll|wait|wait_for|highlight|unhighlight, "selector"
    (Playwright selector), "value", "seconds", "ff" (fast-forward long waits), "what", "label"}.
    Existing segments keep their ids if you pass "id". Un-approves the script."""
    segs = json.loads(segments_json)
    return _summary(client.call("PUT", f"/api/projects/{project_id}/segments", json=segs))


@mcp.tool()
def update_segment(project_id: str, segment_id: str, changes_json: str) -> dict:
    """Patch one segment with a JSON object of fields (see set_segments). Un-approves the script."""
    return _summary(client.call("PATCH", f"/api/projects/{project_id}/segments/{segment_id}",
                                json=json.loads(changes_json)))


@mcp.tool()
def revise_segment(project_id: str, segment_id: str, instruction: str) -> dict:
    """Ask Gemini to rewrite one segment, e.g. "shorter", "explain what an API gateway is first"."""
    return _summary(client.call("POST", f"/api/projects/{project_id}/segments/{segment_id}/revise",
                                json={"instruction": instruction}))


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
def plan_actions(project_id: str, segment_ids: list[str] | None = None) -> dict:
    """AI-explore the web app: plan browser actions for step segments (all, or the given ids), executing
    as it goes so each step is planned against the real page. Waits."""
    j = client.wait_job(client.call("POST", f"/api/projects/{project_id}/explore",
                                    json={"segment_ids": segment_ids}), timeout=1800)
    return {"job": _job(j), "project": _summary(client.call("GET", f"/api/projects/{project_id}"))}


@mcp.tool()
def dry_run(project_id: str) -> dict:
    """Run every step's actions headless (no narration) and report which ones fail. Waits."""
    j = client.wait_job(client.call("POST", f"/api/projects/{project_id}/dryrun"), timeout=1800)
    p = client.call("GET", f"/api/projects/{project_id}")
    return {"job": _job(j), "failed_checks": [c for c in p["checks"] if not c["ok"]]}


@mcp.tool()
def preview_voice(text: str, project_id: str = "") -> str:
    """Synthesize text in the configured custom voice; returns the path of the WAV file."""
    from . import config
    data = client.call("POST", "/api/voice/preview", json={"text": text, "project_id": project_id or None})
    out = config.HOME / "previews" / "last_preview.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return str(out)


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
