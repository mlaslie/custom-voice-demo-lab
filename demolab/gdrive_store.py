"""Local filesystem Save-As dialog + Google Drive plugin state & graphical folder tree cache."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from typing import Literal

from pydantic import BaseModel, Field

from . import config

GDriveStatusKind = Literal["not_installed", "disabled", "needs_auth", "connected"]


class GDriveFolder(BaseModel):
    id: str
    name: str
    parent_id: str = "root"
    shared: bool = False


class GDriveState(BaseModel):
    connected: bool = False
    account_email: str = ""
    root_id: str = ""
    folders: list[GDriveFolder] = Field(default_factory=list)
    updated_at: float = 0


def _state_file() -> pathlib.Path:
    return config.HOME / "gdrive.json"


def _default_plugins_dirs() -> list[pathlib.Path]:
    home = pathlib.Path.home()
    return [
        home / ".gemini" / "config" / "plugins",
        home / ".claude" / "plugins",
    ]


def detect_gdrive_plugin(plugins_dirs: list[pathlib.Path] | None = None) -> tuple[bool, bool]:
    """Return `(installed, disabled)` by inspecting local Antigravity plugin directories."""
    dirs = plugins_dirs if plugins_dirs is not None else _default_plugins_dirs()
    for base in dirs:
        if not base.is_dir():
            continue
        direct = base / "gdrive" / "plugin.json"
        candidates = [direct] if direct.is_file() else list(base.glob("*/plugin.json"))
        for pjson in candidates:
            try:
                data = json.loads(pjson.read_text())
            except Exception:
                continue
            if data.get("name") == "gdrive" or pjson.parent.name == "gdrive":
                return True, bool(data.get("disabled", False))
    return False, False


def load_state() -> GDriveState:
    f = _state_file()
    if not f.is_file():
        return GDriveState()
    try:
        return GDriveState.model_validate_json(f.read_text())
    except Exception:
        return GDriveState()


def normalize_folders(raw_folders: list[dict], root_id: str = "") -> list[GDriveFolder]:
    """Normalize Drive API / `gdrive --json` folder objects (`{id, name, parent_id | parents}`) into a clean tree.

    In Google Drive v3, top-level folders inside My Drive report `parents: ["<opaqueMyDriveRootId>"]`.
    Any parent ID that is neither `"root"` nor present in the folder set (when syncing the top-level tree)
    is mapped to `"root"` unless `preserve_unknown_parents` is needed.
    """
    prelim: list[tuple[str, str, str, bool]] = []
    seen_ids: set[str] = set()
    for item in raw_folders:
        fid = str(item.get("id") or item.get("fileId") or "").strip()
        name = str(item.get("name") or item.get("title") or "").strip()
        if not fid or not name or fid in seen_ids:
            continue
        mime = str(item.get("mimeType") or item.get("mime_type") or "")
        if mime and "folder" not in mime.lower():
            continue
        if item.get("trashed") is True:
            continue
        parent = str(item.get("parent_id") or item.get("parentId") or "").strip()
        if not parent:
            parents = item.get("parents")
            if isinstance(parents, list) and parents:
                parent = str(parents[0]).strip()
        shared = bool(item.get("shared", False))
        seen_ids.add(fid)
        prelim.append((fid, name, parent, shared))

    out: list[GDriveFolder] = []
    for fid, name, parent, shared in prelim:
        if not parent or parent == "root" or (root_id and parent == root_id) or parent not in seen_ids:
            norm_parent = "root"
        else:
            norm_parent = parent
        out.append(GDriveFolder(id=fid, name=name, parent_id=norm_parent, shared=shared))

    out.sort(key=lambda x: x.name.lower())
    return out


def save_state(
    connected: bool,
    account_email: str = "",
    folders: list[dict] | None = None,
    root_id: str = "",
    merge_folders: bool = False,
    parent_override: str = "",
) -> GDriveState:
    cur = load_state()
    cur.connected = connected
    if account_email.strip():
        cur.account_email = account_email.strip()
    elif not connected:
        cur.account_email = ""
    if root_id.strip():
        cur.root_id = root_id.strip()

    if not connected:
        cur.folders = []
    elif folders is not None:
        if merge_folders:
            by_id = {f.id: f for f in cur.folders}
            for item in folders:
                fid = str(item.get("id") or item.get("fileId") or "").strip()
                name = str(item.get("name") or item.get("title") or "").strip()
                if not fid or not name:
                    continue
                parent = parent_override or str(item.get("parent_id") or "").strip()
                if not parent:
                    parents = item.get("parents")
                    parent = str(parents[0]).strip() if isinstance(parents, list) and parents else "root"
                by_id[fid] = GDriveFolder(
                    id=fid,
                    name=name,
                    parent_id=parent or "root",
                    shared=bool(item.get("shared", False)),
                )
            # Re-normalize top-level unknown root IDs while preserving known parent IDs
            known = set(by_id.keys())
            merged = []
            for f in by_id.values():
                p = "root" if (not f.parent_id or f.parent_id == cur.root_id or (f.parent_id != "root" and f.parent_id not in known)) else f.parent_id
                merged.append(f.model_copy(update={"parent_id": p}))
            merged.sort(key=lambda x: x.name.lower())
            cur.folders = merged
        else:
            cur.folders = normalize_folders(folders, root_id=cur.root_id)

    cur.updated_at = time.time()
    config.HOME.mkdir(parents=True, exist_ok=True)
    _state_file().write_text(cur.model_dump_json(indent=2))
    return cur


def get_status(
    ls_installed: bool | None = None,
    ls_disabled: bool | None = None,
    plugins_dirs: list[pathlib.Path] | None = None,
) -> dict:
    fs_installed, fs_disabled = detect_gdrive_plugin(plugins_dirs)
    st = load_state()
    installed = ls_installed if ls_installed is not None else (fs_installed or st.connected)
    disabled = ls_disabled if ls_disabled is not None else fs_disabled

    if not installed:
        status: GDriveStatusKind = "not_installed"
        connected = False
    elif disabled:
        status = "disabled"
        connected = False
    elif st.connected:
        status = "connected"
        connected = True
    else:
        status = "needs_auth"
        connected = False

    return {
        "status": status,
        "installed": installed,
        "disabled": disabled,
        "connected": connected,
        "account_email": st.account_email if connected else "",
        "folders": [f.model_dump() for f in st.folders] if connected else [],
        "updated_at": st.updated_at,
    }


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def choose_save_path(default_filename: str, default_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    """Open a native OS Save-As file picker dialog so the user chooses where to save the MP4.

    Returns `None` if the user cancels the dialog.
    """
    start_dir = default_dir or (pathlib.Path.home() / "Downloads")
    start_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "darwin":
        safe_name = _escape_applescript(default_filename)
        safe_dir = _escape_applescript(str(start_dir))
        apple_script = (
            f'set defLoc to POSIX file "{safe_dir}" as alias\n'
            f'tell application (path to frontmost application as text)\n'
            f'    set chosenFile to choose file name with prompt "Save Demo Video MP4 As:" '
            f'default name "{safe_name}" default location defLoc\n'
            f'    return POSIX path of chosenFile\n'
            f'end tell'
        )
        res = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode != 0:
            if "-128" in (res.stderr or "") or "canceled" in (res.stderr or "").lower():
                return None
            # Fallback without frontmost tell block if frontmost app blocked ScriptingAdditions
            fallback_script = (
                f'POSIX path of (choose file name with prompt "Save Demo Video MP4 As:" '
                f'default name "{safe_name}" default location (POSIX file "{safe_dir}" as alias))'
            )
            res2 = subprocess.run(["osascript", "-e", fallback_script], capture_output=True, text=True, timeout=300)
            if res2.returncode != 0:
                return None
            chosen = res2.stdout.strip()
        else:
            chosen = res.stdout.strip()

        if not chosen:
            return None
        out = pathlib.Path(chosen)
        if out.suffix.lower() != ".mp4":
            out = out.with_suffix(".mp4")
        return out

    if sys.platform.startswith("win"):
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.SaveFileDialog; "
            f"$d.InitialDirectory = '{str(start_dir)}'; "
            f"$d.FileName = '{default_filename}'; "
            "$d.Filter = 'MP4 Video (*.mp4)|*.mp4|All Files (*.*)|*.*'; "
            "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.FileName }"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=300)
        chosen = res.stdout.strip()
        return pathlib.Path(chosen) if chosen else None

    # Linux zenity fallback
    if shutil_which("zenity"):
        res = subprocess.run(
            ["zenity", "--file-selection", "--save", "--confirm-overwrite", f"--filename={start_dir / default_filename}"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0 and res.stdout.strip():
            out = pathlib.Path(res.stdout.strip())
            return out if out.suffix.lower() == ".mp4" else out.with_suffix(".mp4")
        return None

    return start_dir / default_filename


def choose_directory(default_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    """Open a native OS folder picker dialog so the user can choose an output directory."""
    start_dir = default_dir if (default_dir and default_dir.exists()) else pathlib.Path.home()

    if sys.platform == "darwin":
        safe_dir = _escape_applescript(str(start_dir))
        apple_script = (
            f'set defLoc to POSIX file "{safe_dir}" as alias\n'
            f'tell application (path to frontmost application as text)\n'
            f'    set chosenFolder to choose folder with prompt "Select Output Folder for Rendered MP4s:" default location defLoc\n'
            f'    return POSIX path of chosenFolder\n'
            f'end tell'
        )
        res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            if "-128" in (res.stderr or "") or "canceled" in (res.stderr or "").lower():
                return None
            fallback = (
                f'POSIX path of (choose folder with prompt "Select Output Folder for Rendered MP4s:" '
                f'default location (POSIX file "{safe_dir}" as alias))'
            )
            res2 = subprocess.run(["osascript", "-e", fallback], capture_output=True, text=True, timeout=300)
            if res2.returncode != 0:
                return None
            chosen = res2.stdout.strip()
        else:
            chosen = res.stdout.strip()
        return pathlib.Path(chosen.rstrip("/")) if chosen else None

    if sys.platform.startswith("win"):
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.SelectedPath = '{str(start_dir)}'; "
            "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.SelectedPath }"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=300)
        chosen = res.stdout.strip()
        return pathlib.Path(chosen) if chosen else None

    if shutil_which("zenity"):
        res = subprocess.run(
            ["zenity", "--file-selection", "--directory", f"--filename={start_dir}/"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0 and res.stdout.strip():
            return pathlib.Path(res.stdout.strip())
        return None

    return start_dir


def shutil_which(cmd: str) -> str | None:
    import shutil
    return shutil.which(cmd)
