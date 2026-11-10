"""Render: narration (TTS, cached) -> title cards -> one recording of all web steps -> MP4."""
from __future__ import annotations

import pathlib
import re
import shutil
import time

from . import browser, config, gemini, store
from .cards import card_key, render_cards
from .compose import Recorded, Still, compose
from .models import Project, Render


def voice_for(p: Project | None = None, profile_id: str = "") -> tuple[str, str, str, str]:
    """(voice, style, tts model, key) for a project: its profile (else the active one), then its overrides."""
    v = config.resolve(profile_id or (p.profile_id if p else ""))
    return ((p and p.voice_id) or v.voice, (p and p.voice_style) or v.style, config.load().tts_model, v.key)


def narrate(p: Project, text: str) -> tuple[pathlib.Path, float]:
    voice, style, model, key = voice_for(p)
    wav = store.sub(p.id, "audio") / f"{gemini.tts_cache_key(text, voice, style, model)}.wav"
    if wav.exists():
        return wav, gemini.wav_seconds(wav)
    return wav, gemini.synth(text, wav, voice, style, model, key=key)


def preview(text: str, pid: str | None = None, profile_id: str = "", key_id: str = "", voice: str = "",
            style: str | None = None) -> pathlib.Path:
    """Speak text in a project's voice, a profile, or (while choosing) any voice with a saved key."""
    if key_id and voice:
        key, model = config.key_value(key_id), config.load().tts_model
        style = config.DEFAULT_STYLE if style is None else style
    else:
        voice, style0, model, key = voice_for(store.get(pid) if pid else None, profile_id)
        style = style0 if style is None else style
    wav = config.HOME / "previews" / f"{gemini.tts_cache_key(text, voice, style, model)}.wav"
    if not wav.exists():
        gemini.synth(text, wav, voice, style, model, key=key)
    return wav


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "demo"


def render(job, pid: str, force: bool = False, keep_build: bool = False) -> dict:
    p = store.get(pid)
    if not p.segments:
        raise ValueError("The project has no script yet.")
    if not p.script_approved and not force:
        raise ValueError("Approve the script before rendering (or pass force).")
    steps = [s for s in p.segments if s.type == "step"]
    if steps and not p.base_url:
        raise ValueError("The script has web steps but the project has no app URL.")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed (brew install ffmpeg).")

    st = config.load()
    out_root = pathlib.Path(st.output_dir).expanduser()
    vol = out_root.parts[:3] if out_root.parts[1:2] == ("Volumes",) else None
    if vol and not pathlib.Path(*vol).exists():   # don't silently write to the internal disk instead
        raise RuntimeError(f"The render folder's drive {pathlib.Path(*vol)} is not mounted.")
    build =out_root / ".build" / p.id
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)

    # 1. narration
    texts = [(s.id, s.narration) for s in p.segments if s.narration.strip()] + \
            [(f"{s.id}:after", s.after_narration) for s in steps if s.after_narration.strip()]
    audio: dict[str, tuple[pathlib.Path, float]] = {}
    for n, (key, text) in enumerate(texts):
        job.say(f"Narrating {n + 1}/{len(texts)}", 0.25 * n / max(1, len(texts)))
        audio[key] = narrate(p, text.strip())

    # 2. title cards
    job.say("Rendering title cards", 0.27)
    cards = [s.model_dump(include={"title", "kicker", "sub", "bullets"}) for s in p.segments if s.type == "card"]
    card_png = render_cards(cards, config.HOME / "cards") if cards else {}

    # 3. web steps
    events, frames = [], []
    if steps:
        events, frames = browser.record_steps(job, p, steps, audio, build)

    # 4. compose
    job.say("Composing video", 0.75)
    pieces = []
    slides = store.sub(p.id, "slides")
    for s in p.segments:
        clip = [audio[s.id]] if s.id in audio else []
        if s.type == "card":
            pieces.append(Still(card_png[card_key(s.model_dump())], clip))
        elif s.type == "slide" and s.slide is not None and s.slide < len(p.slides):
            pieces.append(Still(slides / p.slides[s.slide], clip))
        elif s.type == "step":
            pieces.append(Recorded(s.id))
    name = f"{_slug(p.name)}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    out = out_root / name
    secs = compose(pieces, events, frames, build / "frames", build / "work", out)
    if not keep_build:
        shutil.rmtree(build, ignore_errors=True)

    r = Render(file=str(out), created_at=time.time(), seconds=secs, segments=len(p.segments))
    store.mutate(pid, lambda q: q.renders.insert(0, r))
    job.say(f"Rendered {secs / 60:.1f} min -> {out}")
    return {"file": str(out), "seconds": secs}
