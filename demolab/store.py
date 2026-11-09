"""Projects on disk: ~/.demolab/projects/<id>/{project.json, uploads/, slides/, audio/, checks/, build/}."""
from __future__ import annotations

import pathlib
import shutil
import threading
import time

from . import config
from .models import Project

ROOT = config.HOME / "projects"
_lock = threading.RLock()


def pdir(pid: str) -> pathlib.Path:
    if not pid.startswith("prj_") or "/" in pid or ".." in pid:
        raise KeyError(pid)
    return ROOT / pid


def list_projects() -> list[Project]:
    if not ROOT.exists():
        return []
    out = []
    for f in ROOT.glob("prj_*/project.json"):
        try:
            out.append(Project.model_validate_json(f.read_text()))
        except Exception:
            continue
    return sorted(out, key=lambda p: -p.updated_at)


def get(pid: str) -> Project:
    f = pdir(pid) / "project.json"
    if not f.exists():
        raise KeyError(pid)
    return Project.model_validate_json(f.read_text())


def save(p: Project) -> Project:
    with _lock:
        p.updated_at = time.time()
        d = pdir(p.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "project.json.tmp"
        tmp.write_text(p.model_dump_json(indent=1))
        tmp.replace(d / "project.json")
    return p


def mutate(pid: str, fn) -> Project:
    """Read-modify-write under the store lock (background jobs and the API both write projects)."""
    with _lock:
        p = get(pid)
        fn(p)
        return save(p)


def create(name: str, **kw) -> Project:
    return save(Project(name=name, **kw))


def delete(pid: str) -> None:
    shutil.rmtree(pdir(pid), ignore_errors=True)


def sub(pid: str, name: str) -> pathlib.Path:
    d = pdir(pid) / name
    d.mkdir(parents=True, exist_ok=True)
    return d
