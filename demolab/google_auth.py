"""Google sign-in for the Slides/Drive APIs (installed-app OAuth flow, token kept in the keychain)."""
from __future__ import annotations

import json
import pathlib

from . import config

SCOPES = ["https://www.googleapis.com/auth/presentations.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]


def connect() -> None:
    """Opens the consent screen in the default browser and waits for the redirect to localhost."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    path = config.load().google_client_secret
    if not path or not pathlib.Path(path).expanduser().exists():
        raise RuntimeError("Set the path to your OAuth client_secret.json (Desktop app) in Settings first. "
                           "See docs/google-oauth.md.")
    flow = InstalledAppFlow.from_client_secrets_file(str(pathlib.Path(path).expanduser()), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    config.set_secret("google_token", creds.to_json())


def disconnect() -> None:
    config.delete_secret("google_token")


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    raw = config.get_secret("google_token")
    if not raw:
        raise RuntimeError("Google is not connected. Connect it in Settings.")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        config.set_secret("google_token", creds.to_json())
    return creds
