"""In-Antigravity (AGY) Browser onboarding, frame ingestion, and pre-render readiness checks.

All live website demos (e.g. Google Cloud Console, SaaS dashboards, localhost apps) run 100% inside
Antigravity's built-in `browser` subagent — zero external Playwright windows:
  1. Onboarding check: AGY's browser navigates to `base_url`, checks if the user is signed in, pauses for
     interactive sign-in inside the AGY Browser Pane if needed, and records status via `record_web_auth`.
  2. Live step execution & capture: AGY's browser performs each `step` segment's actions and captures
     `before` / `during` / `result` screenshots, which are normalized to 1080p here via `record_step_frames`.
"""
from __future__ import annotations

import pathlib
import time

from PIL import Image

from . import config, store
from .models import Check, HighlightBox, Project, StepFrame, WebAuth, new_id

W, H = 1920, 1080


def _fit_1080p(img: Image.Image) -> Image.Image:
    """Normalize a browser screenshot to 1920x1080 (or 3840x2160 if Retina HiDPI >=2560px) RGB."""
    rgb = img.convert("RGB")
    tw, th = (3840, 2160) if rgb.width >= 2560 else (W, H)
    if rgb.size == (tw, th):
        return rgb
    ratio = rgb.width / max(1, rgb.height)
    target = tw / th
    if abs(ratio - target) < 0.03:
        return rgb.resize((tw, th), Image.LANCZOS)
    # Sample top-left pixel for subtle neutral pad if viewport had non-16:9 chrome
    bg = rgb.getpixel((0, 0))
    fitted = rgb.copy()
    fitted.thumbnail((tw, th), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), bg)
    canvas.paste(fitted, ((tw - fitted.width) // 2, (th - fitted.height) // 2))
    return canvas


def record_web_auth(
    pid: str,
    status: str,
    checked_url: str = "",
    account_hint: str = "",
    notes: str = "",
) -> Project:
    """Record the result of checking/completing user login in Antigravity's built-in browser."""
    def apply(p: Project):
        auth = WebAuth(
            status=status,  # type: ignore[arg-type]
            checked_url=checked_url or p.base_url,
            account_hint=account_hint.strip(),
            notes=notes.strip(),
            updated_at=time.time(),
        )
        p.web_auth = auth
        p.has_login = auth.status in ("authenticated", "not_needed")

    return store.mutate(pid, apply)


def record_step_frames(
    pid: str,
    seg_id: str,
    frames_in: list[dict],
    append: bool = False,
) -> Project:
    """Ingest 1+ screenshots captured by Antigravity's browser subagent for a `step` segment."""
    if not frames_in:
        raise ValueError("Provide at least one captured screenshot in `frames`.")

    p0 = store.get(pid)
    seg0 = p0.segment(seg_id)
    if seg0.type != "step":
        raise ValueError(f"Segment {seg_id} is type {seg0.type!r}; only 'step' segments accept browser frames.")

    frames_dir = store.sub(pid, "frames")
    start_idx = len(seg0.frames) if append else 0
    built: list[StepFrame] = []

    for offset, raw in enumerate(frames_in):
        src_str = str(raw.get("path") or raw.get("file") or "").strip()
        if not src_str:
            raise ValueError(f"Frame {offset + 1} is missing `path` (local screenshot file path).")
        src = pathlib.Path(src_str).expanduser()
        if not src.is_file():
            cand = frames_dir / src.name
            if cand.is_file():
                src = cand
            else:
                raise FileNotFoundError(f"Screenshot file not found: {src}")

        fid = new_id("frm_")
        out_name = f"{seg_id}_{start_idx + offset + 1:02d}_{fid[-6:]}.png"
        with Image.open(src) as im:
            _fit_1080p(im).save(frames_dir / out_name, format="PNG")

        hl = HighlightBox.model_validate(raw["highlight"]) if raw.get("highlight") else None
        zm = HighlightBox.model_validate(raw["zoom_to"]) if raw.get("zoom_to") else None
        built.append(
            StepFrame(
                id=fid,
                file=out_name,
                phase=raw.get("phase") or "during",
                caption=str(raw.get("caption") or "").strip(),
                highlight=hl,
                zoom_to=zm,
                ff_what=str(raw.get("ff_what") or "").strip(),
                ff_elapsed=float(raw.get("ff_elapsed") or 0),
            )
        )

    def apply(p: Project):
        s = p.segment(seg_id)
        if not append:
            for old in s.frames:
                (frames_dir / old.file).unlink(missing_ok=True)
            s.frames = built
        else:
            s.frames.extend(built)
        p.checks = [c for c in p.checks if c.segment_id != seg_id]
        p.checks.append(Check(segment_id=seg_id, index=0, ok=True, shot=s.frames[-1].file))

    return store.mutate(pid, apply)


def check_readiness(p: Project) -> dict:
    """Verify whether a project is completely ready for final MP4 rendering."""
    try:
        config.resolve(p.profile_id)
        voice_ready = True
    except config.SetupNeeded:
        voice_ready = False

    steps = [s for s in p.segments if s.type == "step"]
    web_auth_ok = True if not steps else (p.web_auth.status in ("authenticated", "not_needed") or p.has_login)
    missing_frames = [
        {"segment_id": s.id, "title": s.title or f"Step {i + 1}"}
        for i, s in enumerate(p.segments)
        if s.type == "step" and not s.frames
    ]
    has_research = bool(p.research) or bool(p.research_summary.strip())

    blockers: list[str] = []
    warnings: list[str] = []

    if not voice_ready:
        blockers.append("Voice setup needed: open Voice Demo Studio (/setup) to add a Gemini API key and pick a voice.")
    if not p.segments:
        blockers.append("No script segments exist yet (`write_script`).")
    elif not p.script_approved:
        blockers.append("Script has not been approved yet (`approve_script` or Approve button in Studio).")

    if steps:
        if not p.base_url:
            blockers.append("Script includes live website steps (`step`), but project `base_url` is empty.")
        if not web_auth_ok:
            blockers.append(
                f"Website login onboarding is `{p.web_auth.status}` — verify login in Antigravity's browser "
                "and call `record_web_auth(status='authenticated' | 'not_needed')` first."
            )
        if missing_frames:
            labels = ", ".join(f"{m['title']} ({m['segment_id']})" for m in missing_frames)
            blockers.append(f"Missing captured AGY browser frames (`record_step_frames`) for: {labels}.")

    if not has_research:
        warnings.append(
            "No grounded research items saved (`save_research`). Ensure every technical claim is backed by docs, blogs, or slides."
        )

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "voice_ready": voice_ready,
        "script_approved": p.script_approved,
        "has_research": has_research,
        "research_count": len(p.research),
        "step_count": len(steps),
        "web_auth_status": p.web_auth.status,
        "missing_step_frames": missing_frames,
    }
