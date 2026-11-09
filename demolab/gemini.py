"""Gemini REST calls: custom-voice TTS, JSON text generation, model listing.

Custom voices belong to the AI Studio project that created them; the API key must come from that same
project or the voice returns 404. The key is read from the keychain/env on each call and never logged.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import pathlib
import wave

import httpx

from . import config

API = "https://generativelanguage.googleapis.com/v1beta"
SR = 24000


class GeminiError(RuntimeError):
    pass


def _key() -> str:
    k = config.get_secret("gemini_api_key")
    if not k:
        raise GeminiError("No Gemini API key set. Add one in Settings (it must come from the AI Studio "
                          "project that owns the custom voice).")
    return k


def _post(path: str, body: dict, timeout: float = 180) -> dict:
    r = httpx.post(f"{API}/{path}", json=body, timeout=timeout,
                   headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    if r.status_code >= 400:
        msg = r.text[:600]
        if r.status_code == 404 and "voice" in msg.lower():
            msg += " (Is the API key from the same AI Studio project that created the voice?)"
        raise GeminiError(f"Gemini HTTP {r.status_code}: {msg}")
    return r.json()


# ---- TTS ----------------------------------------------------------------------------------------

def tts_cache_key(text: str, voice: str, style: str, model: str) -> str:
    return hashlib.sha1(json.dumps([text, voice, style, model]).encode()).hexdigest()[:16]


def synth(text: str, out: pathlib.Path, voice: str, style: str, model: str) -> float:
    """Write a 24 kHz mono 16-bit WAV of `text` in the custom voice; returns its duration in seconds."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if config.fake_gemini():
        secs = max(1.0, len(text.split()) / 2.6)   # ~156 wpm of silence
        _write_pcm(out, b"\0\0" * int(secs * SR))
        return secs
    if not voice:
        raise GeminiError("No voice id set. Add your custom voice id in Settings.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": text, **({"speechMetadata": {"style": style}} if style else {})}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"voice": voice}}},
    }
    d = _post(f"models/{model}:generateContent", body)
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

def generate_json(prompt: str, schema: dict, model: str, images: list[bytes] | None = None,
                  system: str = "") -> dict | list:
    """Structured output: the response is parsed JSON matching `schema` (OpenAPI subset)."""
    parts: list[dict] = [{"text": prompt}]
    for img in images or []:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(img).decode()}})
    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                             "temperature": 0.4},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    d = _post(f"models/{model}:generateContent", body, timeout=300)
    try:
        txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        return json.loads(txt)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GeminiError(f"Unexpected response from {model}: {e}: {json.dumps(d)[:300]}")


def list_models() -> list[dict]:
    if config.fake_gemini():
        return [{"name": "gemini-flash-latest", "methods": ["generateContent"]},
                {"name": "gemini-3.8-flash-tts", "methods": ["generateContent"]}]
    r = httpx.get(f"{API}/models", params={"pageSize": 200}, headers={"x-goog-api-key": _key()}, timeout=30)
    if r.status_code >= 400:
        raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    return [{"name": m["name"].removeprefix("models/"), "display": m.get("displayName", ""),
             "methods": m.get("supportedGenerationMethods", [])} for m in r.json().get("models", [])]
