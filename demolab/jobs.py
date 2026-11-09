"""Background jobs (script drafting, exploration, dry runs, renders) with progress and a log tail."""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field

from .models import new_id


@dataclass
class Job:
    id: str
    project_id: str
    kind: str
    state: str = "running"          # running | done | error
    progress: float = 0.0
    message: str = ""
    log: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    def say(self, msg: str, progress: float | None = None) -> None:
        self.message = msg
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        del self.log[:-300]
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "project_id", "kind", "state", "progress", "message",
                                               "result", "error", "started_at", "ended_at")} | {
            "log": self.log[-60:]}


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def start(project_id: str, kind: str, fn, *args) -> Job:
    """Run fn(job, *args) in a thread. One running job per project+kind."""
    with _lock:
        for j in _jobs.values():
            if j.project_id == project_id and j.kind == kind and j.state == "running":
                return j
        job = Job(new_id("job_"), project_id, kind)
        _jobs[job.id] = job

    def run():
        try:
            job.result = fn(job, *args) or {}
            job.state, job.progress = "done", 1.0
            job.say("Done")
        except Exception as e:   # surfaced to the UI / MCP caller
            job.state, job.error = "error", f"{type(e).__name__}: {e}"
            job.say(f"Failed: {job.error}")
            job.log.append(traceback.format_exc()[-1500:])
        finally:
            job.ended_at = time.time()

    threading.Thread(target=run, daemon=True, name=f"{kind}-{job.id}").start()
    return job


def get(jid: str) -> Job:
    return _jobs[jid]


def for_project(pid: str) -> list[Job]:
    return sorted((j for j in _jobs.values() if j.project_id == pid), key=lambda j: -j.started_at)
