"""Render: narration (TTS, cached) -> pure-Pillow title cards -> slides + AGY browser frames -> MP4."""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import time
from typing import NamedTuple

import httpx

from . import config, gemini, sources, store
from .cards import card_key, render_cards
from .compose import StepSequence, Still, compose
from .models import Project, RESOLUTION_DIMS, Render, Resolution, normalize_resolution


class Voicing(NamedTuple):
    voice: str
    style: str
    model: str
    key: str
    speed: float


def voice_for(p: Project | None = None, profile_id: str = "") -> Voicing:
    """How a project is narrated: its profile (else the active one), then the project's overrides."""
    v = config.resolve(profile_id or (p.profile_id if p else ""))
    speed = (p.speed if p and p.speed else v.profile.speed if v.profile else 1.0)
    return Voicing(
        (p and p.voice_id) or v.voice,
        (p and p.voice_style) or v.style,
        config.load().tts_model,
        v.key,
        config.clamp_speed(speed),
    )


def speed_for(p: Project) -> float:
    try:
        return voice_for(p).speed
    except config.SetupNeeded:
        return config.clamp_speed(p.speed or 1.0)


def _tempo(raw: pathlib.Path, speed: float) -> pathlib.Path:
    """The clip at `speed` (time-stretched, pitch kept), cached next to the original."""
    if abs(speed - 1) < 0.005:
        return raw
    out = raw.with_name(f"{raw.stem}@{speed:.2f}.wav")
    if not out.exists():
        tmp = out.with_suffix(".part.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                "-filter:a", f"atempo={speed}", "-ar", str(gemini.SR), "-ac", "1", "-c:a", "pcm_s16le",
                str(tmp),
            ],
            check=True,
        )
        tmp.replace(out)
    return out


def narrate(p: Project, text: str) -> tuple[pathlib.Path, float]:
    v = voice_for(p)
    raw = store.sub(p.id, "audio") / f"{gemini.tts_cache_key(text, v.voice, v.style, v.model)}.wav"
    if not raw.exists():
        gemini.synth(text, raw, v.voice, v.style, v.model, key=v.key)
    wav = _tempo(raw, v.speed)
    return wav, gemini.wav_seconds(wav)


def preview(
    text: str,
    pid: str | None = None,
    profile_id: str = "",
    key_id: str = "",
    voice: str = "",
    style: str | None = None,
    speed: float | None = None,
) -> pathlib.Path:
    """Speak text in a project's voice, a profile, or (while choosing) any voice with a saved key."""
    if key_id and voice:
        key, model, speed0 = config.key_value(key_id), config.load().tts_model, 1.0
        style = config.DEFAULT_STYLE if style is None else style
    else:
        v = voice_for(store.get(pid) if pid else None, profile_id)
        voice, model, key, speed0 = v.voice, v.model, v.key, v.speed
        style = v.style if style is None else style
    raw = config.HOME / "previews" / f"{gemini.tts_cache_key(text, voice, style, model)}.wav"
    if not raw.exists():
        gemini.synth(text, raw, voice, style, model, key=key)
    return _tempo(raw, config.clamp_speed(speed0 if speed is None else speed))


VERIFY_TEXT = "Voice check. This voice is ready to narrate your demos."


def verify_profile(vid: str) -> config.VoiceProfile:
    """Prove a saved key + voice pair works end to end and record the result."""
    s = config.load()
    v = s.profile(vid)
    err = ""
    try:
        key = config.key_value(v.key_id)
        ids = {x["id"] for x in gemini.list_voices(key)}
        if v.voice not in ids:
            raise gemini.GeminiError(
                f"This key's AI Studio project has no voice {v.voice!r}. Use a key from the "
                "project that created the voice, or pick another voice."
            )
        wav = config.HOME / "previews" / f"{gemini.tts_cache_key(VERIFY_TEXT, v.voice, v.style, s.tts_model)}.wav"
        if not wav.exists() and gemini.synth(VERIFY_TEXT, wav, v.voice, v.style, s.tts_model, key=key) < 0.5:
            raise gemini.GeminiError("The voice returned almost no audio.")
    except (gemini.GeminiError, config.SetupNeeded, httpx.HTTPError) as e:
        err = str(e)[:400] or e.__class__.__name__

    def record(q: config.Settings):
        prof = q.profile(vid)
        prof.verified_at, prof.verify_error = (0, err) if err else (time.time(), "")

    return config.mutate(record).profile(vid)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "demo"


def effective_resolution(p: Project, override: str = "", st: config.Settings | None = None) -> Resolution:
    if (override or "").strip():
        return normalize_resolution(override)
    if (p.resolution or "").strip():
        return normalize_resolution(p.resolution)
    return normalize_resolution((st or config.load()).default_resolution)


def render(job, pid: str, force: bool = False, keep_build: bool = False, resolution: str = "") -> dict:
    p = store.get(pid)
    if not p.segments:
        raise ValueError("The project has no script yet.")
    if not p.script_approved and not force:
        raise ValueError("Approve the script before rendering (or pass force).")
    steps = [s for s in p.segments if s.type == "step"]
    if steps:
        if not p.base_url:
            raise ValueError("The script has website steps (`step`) but the project has no `base_url`.")
        missing = [s.title or s.id for s in steps if not s.frames]
        if missing:
            raise ValueError(
                "Capture AGY browser frames (`record_step_frames`) before rendering for step(s): "
                + ", ".join(missing)
            )
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed (`brew install ffmpeg`).")

    st = config.load()
    res = effective_resolution(p, resolution, st)
    w, h = RESOLUTION_DIMS[res]
    out_root = pathlib.Path(st.output_dir).expanduser()
    vol = out_root.parts[:3] if out_root.parts[1:2] == ("Volumes",) else None
    if vol and not pathlib.Path(*vol).exists():   # don't silently write to the internal disk instead
        raise RuntimeError(f"The render folder's drive {pathlib.Path(*vol)} is not mounted.")
    build = out_root / ".build" / p.id
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)

    # 1. narration (Gemini TTS, cached by text+voice+style+model)
    texts = [(s.id, s.narration) for s in p.segments if s.narration.strip()] + \
            [(f"{s.id}:after", s.after_narration) for s in steps if s.after_narration.strip()]
    audio: dict[str, tuple[pathlib.Path, float]] = {}
    for n, (key, text) in enumerate(texts):
        job.say(f"Narrating {n + 1}/{len(texts)}", 0.45 * n / max(1, len(texts)))
        audio[key] = narrate(p, text.strip())

    # 2. title cards (pure Pillow, supersampled)
    job.say(f"Rendering {res.upper()} title cards", 0.50)
    cards = [s.model_dump(include={"title", "kicker", "sub", "bullets"}) for s in p.segments if s.type == "card"]
    card_png = render_cards(cards, config.HOME / "cards", width=w, height=h) if cards else {}

    # 3. compose MP4 from cards, slides (re-rendered natively at target res if >1080p), and captured AGY browser frames
    job.say(f"Composing {res.upper()} ({w}x{h}) video", 0.65)
    pieces: list[Still | StepSequence] = []
    slides_dir = sources.slides_for_resolution(p, width=w, height=h)
    step_frames_dir = store.sub(p.id, "frames")
    for s in p.segments:
        clip = [audio[s.id]] if s.id in audio else []
        if s.type == "card":
            pieces.append(Still(card_png[card_key(s.model_dump())], clip))
        elif s.type == "slide" and s.slide is not None and s.slide < len(p.slides):
            pieces.append(Still(slides_dir / p.slides[s.slide], clip))
        elif s.type == "step":
            pieces.append(
                StepSequence(
                    seg_id=s.id,
                    frames=s.frames,
                    frames_dir=step_frames_dir,
                    narration_clip=audio.get(s.id),
                    after_clip=audio.get(f"{s.id}:after"),
                )
            )
    name = f"{_slug(p.name)}-{res}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    out = out_root / name
    secs = compose(pieces, [], [], build / "frames", build / "work", out, width=w, height=h)
    if not keep_build:
        shutil.rmtree(build, ignore_errors=True)

    r = Render(
        file=str(out),
        created_at=time.time(),
        seconds=secs,
        segments=len(p.segments),
        resolution=res,
        width=w,
        height=h,
    )
    store.mutate(pid, lambda q: q.renders.insert(0, r))
    job.say(f"Rendered {secs / 60:.1f} min -> {out}", 1.0)
    return {"file": str(out), "seconds": secs, "resolution": res, "width": w, "height": h}
