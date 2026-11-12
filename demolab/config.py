"""Settings (voice profiles, models, folders) and secrets (API keys).

Settings live in ~/.demolab/settings.json (override the folder with $DEMOLAB_HOME). A voice profile pairs a
saved Gemini API key with a voice (one of the key's custom voices, or a standard voice) and a delivery style;
one profile is active, and a project may pick another. Keys go to the OS keychain via `keyring`, entered only
in the local web app; $GEMINI_API_KEY overrides the profile's key when set. Secrets are never returned by the
API or MCP tools: callers see a key's name and its last four characters.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, field_validator

DEFAULT_HOME = pathlib.Path.home() / ".demolab"
HOME = pathlib.Path(os.environ.get("DEMOLAB_HOME", DEFAULT_HOME))
SETTINGS = HOME / "settings.json"
KEYRING_SERVICE = "demolab"
PORT = int(os.environ.get("DEMOLAB_PORT", "8765"))

_lock = threading.Lock()


DEFAULT_STYLE = "clear, warm, confident product-demo narrator; unhurried pace"
SPEED_MIN, SPEED_MAX = 0.7, 1.4   # narration speed range (1.0 = the voice's natural pace)


def clamp_speed(x: float) -> float:
    return round(min(SPEED_MAX, max(SPEED_MIN, x)), 2)


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]


class ApiKey(BaseModel):
    id: str = Field(default_factory=lambda: _id("key_"))
    name: str
    hint: str = ""             # last four characters, so keys can be told apart
    created_at: float = Field(default_factory=time.time)


class VoiceProfile(BaseModel):
    id: str = Field(default_factory=lambda: _id("vp_"))
    name: str                  # the label shown everywhere
    description: str = ""      # when to use it ("formal, for customer-facing launches"); agents read this
    key_id: str
    voice: str                 # a custom voice id (voice_...) or a standard voice id (kore, en-us-...)
    voice_name: str = ""       # its display name
    kind: Literal["custom", "standard"] = "custom"
    style: str = DEFAULT_STYLE
    speed: float = 1.0         # narration speed, applied by time-stretching the audio (pitch unchanged)
    verified_at: float = 0     # when a test phrase was last spoken successfully with this key and voice
    verify_error: str = ""     # why the last test failed ("" when it passed or never ran)

    @field_validator("speed")
    @classmethod
    def _speed(cls, x: float) -> float:
        return clamp_speed(x)


class Settings(BaseModel):
    keys: list[ApiKey] = []
    profiles: list[VoiceProfile] = []
    active_profile: str = ""
    tts_model: str = "gemini-3.8-flash-tts"
    # Renders can be large; point this at an external drive if you have one.
    output_dir: str = str(HOME / "renders")
    default_resolution: Literal["1080p", "4k"] = "1080p"
    audience: str = "slightly or not at all familiar with the product; full but high-level explanations"
    # Before voice profiles: one voice id and the "gemini_api_key" secret. Migrated on load.
    voice_id: str = Field(default="", exclude=True)
    voice_style: str = Field(default="", exclude=True)

    def key(self, kid: str) -> ApiKey:
        return next(k for k in self.keys if k.id == kid)

    def profile(self, pid: str) -> VoiceProfile:
        return next(v for v in self.profiles if v.id == pid)


def load() -> Settings:
    with _lock:
        raw = SETTINGS.read_text() if SETTINGS.exists() else ""
        s = Settings.model_validate_json(raw) if raw else Settings()
        if '"voice_id"' in raw and _migrate(s):     # only files written before voice profiles
            SETTINGS.write_text(s.model_dump_json(indent=2))
        return s


def _migrate(s: Settings) -> bool:
    """Turn the old single voice id + key into a saved key and an active profile."""
    old_key = None if s.keys else _raw_get("gemini_api_key")
    if not old_key and not s.voice_id:
        return False
    if old_key:
        k = ApiKey(name="My Gemini key", hint=old_key[-4:])
        _raw_set(key_secret(k.id), old_key)
        if HOME == DEFAULT_HOME:     # a test or scratch folder must never take the real key away
            _raw_delete("gemini_api_key")
        s.keys.append(k)
    if s.voice_id and s.keys and not s.profiles:
        v = VoiceProfile(name="My voice", key_id=s.keys[0].id, voice=s.voice_id,
                         kind="custom" if s.voice_id.startswith("voice_") else "standard",
                         style=s.voice_style or DEFAULT_STYLE)
        s.profiles.append(v)
        s.active_profile = v.id
    s.voice_id = s.voice_style = ""
    return True


def save(s: Settings) -> Settings:
    with _lock:
        HOME.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(s.model_dump_json(indent=2))
    return s


def update(**changes) -> Settings:
    s = load().model_copy(update={k: v for k, v in changes.items() if v is not None})
    return save(s)


# ---- secrets ------------------------------------------------------------------------------------

def _kr():
    import keyring
    return keyring


def _raw_get(name: str) -> str | None:
    try:
        return _kr().get_password(KEYRING_SERVICE, name)
    except Exception:
        return _file_secrets().get(name)


def _raw_set(name: str, value: str) -> None:
    try:
        _kr().set_password(KEYRING_SERVICE, name, value)
    except Exception:   # no keychain backend (e.g. headless Linux): fall back to a 0600 file
        d = _file_secrets()
        d[name] = value
        _write_file_secrets(d)


def _raw_delete(name: str) -> None:
    try:
        _kr().delete_password(KEYRING_SERVICE, name)
    except Exception:
        pass
    d = _file_secrets()
    if d.pop(name, None) is not None:
        _write_file_secrets(d)


get_secret, set_secret, delete_secret = _raw_get, _raw_set, _raw_delete


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def key_secret(kid: str) -> str:
    return f"gemini_key:{kid}"


# ---- keys and voice profiles --------------------------------------------------------------------

class SetupNeeded(RuntimeError):
    """No usable voice profile yet: the user must add a key and pick a voice in the web app."""


class Voice(NamedTuple):
    key: str
    voice: str
    style: str
    profile: VoiceProfile | None


def env_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def add_key(name: str, value: str) -> ApiKey:
    k = ApiKey(name=name.strip() or "Gemini key", hint=value[-4:])
    _raw_set(key_secret(k.id), value)

    def add(s: Settings):
        s.keys.append(k)
    mutate(add)
    return k


def delete_key(kid: str) -> None:
    def drop(s: Settings):
        used = [v.name for v in s.profiles if v.key_id == kid]
        if used:
            raise ValueError(f"This key is used by: {', '.join(used)}. Delete or change those profiles first.")
        s.keys = [k for k in s.keys if k.id != kid]
    mutate(drop)
    _raw_delete(key_secret(kid))


def key_value(kid: str) -> str:
    v = env_key() or _raw_get(key_secret(kid))
    if not v:
        raise SetupNeeded("The saved API key is missing from the keychain. Add it again in Settings.")
    return v


def mutate(fn) -> Settings:
    s = load()
    fn(s)
    return save(s)


def resolve(profile_id: str = "") -> Voice:
    """The key, voice and style to use: the given profile, else the active one."""
    s = load()
    pid = profile_id if any(v.id == profile_id for v in s.profiles) else s.active_profile
    prof = next((v for v in s.profiles if v.id == pid), None)
    if prof:
        return Voice(key_value(prof.key_id), prof.voice, prof.style, prof)
    if env_key() and s.voice_id:
        return Voice(env_key(), s.voice_id, s.voice_style or DEFAULT_STYLE, None)
    raise SetupNeeded("Voice Demo Lab needs a voice first: add a Gemini API key and choose a voice on the "
                      "setup page.")


def setup_needed() -> bool:
    try:
        resolve()
        return False
    except SetupNeeded:
        return True


def _file_secrets() -> dict:
    f = HOME / "secrets.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _write_file_secrets(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    f = HOME / "secrets.json"
    f.write_text(json.dumps(d))
    f.chmod(0o600)


def public_settings() -> dict:
    s = load()
    active = next((v for v in s.profiles if v.id == s.active_profile), None)
    return {**s.model_dump(),
            "setup_needed": setup_needed(),
            "active": active.model_dump() if active else None,
            "key_source": "env" if env_key() else "keychain",
            # kept for older clients
            "voice_id": active.voice if active else "",
            "gemini_key_set": bool(s.keys) or bool(env_key()),
            "fake_gemini": fake_gemini()}


def fake_gemini() -> bool:
    """Test mode: no network calls to Gemini (silent audio, template scripts)."""
    return os.environ.get("DEMOLAB_FAKE_GEMINI") == "1"
