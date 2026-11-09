"""Settings (voice id, style, models, folders) and secrets (API key, Google token).

Settings live in ~/.demolab/settings.json (override the folder with $DEMOLAB_HOME). Secrets go to the OS
keychain via `keyring`; $GEMINI_API_KEY wins when set. Secrets are never returned by the API or MCP tools:
callers only learn whether one is set.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading

from pydantic import BaseModel

HOME = pathlib.Path(os.environ.get("DEMOLAB_HOME", pathlib.Path.home() / ".demolab"))
SETTINGS = HOME / "settings.json"
KEYRING_SERVICE = "demolab"
PORT = int(os.environ.get("DEMOLAB_PORT", "8765"))

_lock = threading.Lock()


class Settings(BaseModel):
    voice_id: str = ""
    voice_style: str = "clear, warm, confident product-demo narrator; unhurried pace"
    tts_model: str = "gemini-3.8-flash-tts"
    script_model: str = "gemini-flash-latest"
    # Renders can be large; point this at an external drive if you have one.
    output_dir: str = str(HOME / "renders")
    # Path to a Google OAuth "Desktop app" client_secret.json (needed for Google Slides only).
    google_client_secret: str = ""
    audience: str = "slightly or not at all familiar with the product; full but high-level explanations"


def load() -> Settings:
    with _lock:
        if SETTINGS.exists():
            return Settings.model_validate_json(SETTINGS.read_text())
        return Settings()


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


def get_secret(name: str) -> str | None:
    if name == "gemini_api_key" and os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    try:
        return _kr().get_password(KEYRING_SERVICE, name)
    except Exception:
        return _file_secrets().get(name)


def set_secret(name: str, value: str) -> None:
    try:
        _kr().set_password(KEYRING_SERVICE, name, value)
    except Exception:   # no keychain backend (e.g. headless Linux): fall back to a 0600 file
        d = _file_secrets()
        d[name] = value
        _write_file_secrets(d)


def delete_secret(name: str) -> None:
    try:
        _kr().delete_password(KEYRING_SERVICE, name)
    except Exception:
        pass
    d = _file_secrets()
    if d.pop(name, None) is not None:
        _write_file_secrets(d)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def secret_source(name: str) -> str | None:
    if name == "gemini_api_key" and os.environ.get("GEMINI_API_KEY"):
        return "env"
    return "keychain" if has_secret(name) else None


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
    return {**s.model_dump(),
            "gemini_key_set": has_secret("gemini_api_key"),
            "gemini_key_source": secret_source("gemini_api_key"),
            "google_connected": has_secret("google_token"),
            "fake_gemini": fake_gemini()}


def fake_gemini() -> bool:
    """Test mode: no network calls to Gemini (silent audio, template scripts)."""
    return os.environ.get("DEMOLAB_FAKE_GEMINI") == "1"
