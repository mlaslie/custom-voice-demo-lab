"""Gemini REST calls: TTS (custom or standard voices), model and voice listing.

Custom voices belong to the AI Studio project that created them; the API key must come from that same
project or the voice returns 404. Each call takes the key to use (the caller resolves it from the voice
profile); without one, the active profile's key is used. Keys are never logged.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import threading
import time
import wave

import httpx

from . import config

API = "https://generativelanguage.googleapis.com/v1beta"
SR = 24000


class GeminiError(RuntimeError):
    pass


def _key(key: str | None = None) -> str:
    return key or config.resolve().key


def _post(path: str, body: dict, timeout: float = 180, key: str | None = None) -> dict:
    r = httpx.post(f"{API}/{path}", json=body, timeout=timeout,
                   headers={"x-goog-api-key": _key(key), "Content-Type": "application/json"})
    if r.status_code >= 400:
        msg = r.text[:600]
        if r.status_code == 404 and "voice" in msg.lower():
            msg += " (Is the API key from the same AI Studio project that created the voice?)"
        raise GeminiError(f"Gemini HTTP {r.status_code}: {msg}")
    return r.json()


# ---- TTS ----------------------------------------------------------------------------------------

def tts_cache_key(text: str, voice: str, style: str, model: str) -> str:
    return hashlib.sha1(json.dumps([text, voice, style, model]).encode()).hexdigest()[:16]


def synth(text: str, out: pathlib.Path, voice: str, style: str, model: str, key: str | None = None) -> float:
    """Write a 24 kHz mono 16-bit WAV of `text` in `voice`; returns its duration in seconds."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if config.fake_gemini():
        secs = max(1.0, len(text.split()) / 2.6)   # ~156 wpm of silence
        _write_pcm(out, b"\0\0" * int(secs * SR))
        return secs
    if not voice:
        raise GeminiError("No voice chosen. Pick one on the setup page.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": text, **({"speechMetadata": {"style": style}} if style else {})}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"voice": voice}}},
    }
    d = _post(f"models/{model}:generateContent", body, key=key)
    try:
        data = base64.b64decode(d["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except (KeyError, IndexError):
        raise GeminiError(f"No audio in TTS response: {json.dumps(d)[:300]}")
    if data[:4] == b"RIFF":
        out.write_bytes(_to_24k_mono(data))
    else:
        _write_pcm(out, data)
    return wav_seconds(out)


def _write_pcm(out: pathlib.Path, pcm: bytes) -> None:
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm)


def _to_24k_mono(riff: bytes) -> bytes:
    with wave.open(io.BytesIO(riff)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 1, 2):
            return riff
    raise GeminiError("TTS returned a WAV that is not 24 kHz mono 16-bit")


def wav_seconds(p: pathlib.Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# ---- text ---------------------------------------------------------------------------------------

def list_models(key: str | None = None) -> list[dict]:
    if config.fake_gemini():
        return [{"name": "gemini-flash-latest", "methods": ["generateContent"]},
                {"name": "gemini-3.8-flash-tts", "methods": ["generateContent"]}]
    r = httpx.get(f"{API}/models", params={"pageSize": 200}, headers={"x-goog-api-key": _key(key)}, timeout=30)
    if r.status_code >= 400:
        raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    return [{"name": m["name"].removeprefix("models/"), "display": m.get("displayName", ""),
             "methods": m.get("supportedGenerationMethods", [])} for m in r.json().get("models", [])]


# ---- voices -------------------------------------------------------------------------------------

_voices: dict[str, tuple[float, list[dict]]] = {}
_voices_lock = threading.Lock()
VOICE_TTL = 600

FAKE_VOICES = [
    {"id": "voice_test0001", "display_name": "Test custom voice", "type": "replicated"},
    {"id": "kore", "display_name": "Kore", "type": "prebuilt"},
    {"id": "puck", "display_name": "Puck", "type": "prebuilt"},
    {"id": "en-us-podcaster-1", "display_name": "Podcaster 1", "type": "prebuilt"},
    {"id": "en-gb-storyteller-2", "display_name": "Storyteller 2", "type": "prebuilt"},
]


def list_voices(key: str) -> list[dict]:
    """Every voice the key can use: its project's custom voices and the standard ones, as
    {id, name, kind: custom|standard, locale}. Also proves the key works. Cached for ten minutes."""
    if config.fake_gemini():
        raw = FAKE_VOICES
    else:
        h = hashlib.sha256(key.encode()).hexdigest()
        with _voices_lock:
            hit = _voices.get(h)
        if hit and time.time() - hit[0] < VOICE_TTL:
            return hit[1]
        raw, token = [], None
        for _ in range(20):
            r = httpx.get(f"{API}/voices", headers={"x-goog-api-key": key}, timeout=30,
                          params={"pageSize": 1000, **({"pageToken": token} if token else {})})
            if r.status_code in (400, 401, 403):
                raise GeminiError("Gemini rejected this API key. Check that it is complete and active.")
            if r.status_code >= 400:
                raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            d = r.json()
            raw += d.get("voices", [])
            token = d.get("next_page_token") or d.get("nextPageToken")
            if not token:
                break
    out = [{"id": v["id"], "name": v.get("display_name") or v["id"],
            "kind": "standard" if v.get("type") == "prebuilt" else "custom",
            "locale": "-".join(v["id"].split("-")[:2]) if v["id"].count("-") >= 2 else ""} for v in raw]
    if not config.fake_gemini():
        with _voices_lock:
            _voices[h] = (time.time(), out)
    return out
