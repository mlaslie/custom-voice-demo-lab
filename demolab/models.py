"""The project document: sources, the narration script (segments) and the shot list (actions per step).

One script drives everything. A segment is a title card, a slide, or a web step; a web step carries the
browser actions that run while (or after) its narration plays.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:10]


class Source(BaseModel):
    id: str = Field(default_factory=lambda: new_id("src_"))
    kind: Literal["url", "repo", "pptx", "pdf", "gslides", "text", "session"]
    label: str = ""
    ref: str = ""              # url / path / presentation id
    text: str = ""             # extracted digest used for script writing
    slide_count: int = 0       # pptx/pdf/gslides: slides rendered into the project's slides/ folder
    slide_offset: int = 0      # index of this source's first slide in the project's slide list
    files: list[str] = []      # session: the attached files and folders that were read
    images: list[str] = []     # session: attached screenshots, saved as JPEGs in the project's session/ folder
    added_at: float = Field(default_factory=time.time)


ActionOp = Literal["goto", "click", "fill", "press", "hover", "scroll", "wait", "wait_for", "highlight",
                   "unhighlight"]


class Action(BaseModel):
    op: ActionOp
    selector: str = ""         # any Playwright selector: css, text=..., role=button[name="Run"], ...
    value: str = ""            # url (goto), text (fill), key (press), text to wait for (wait_for, no selector)
    seconds: float = 0         # wait: duration; wait_for: timeout (default 30)
    ff: bool = False           # fast-forward this wait in the final video, with a banner
    what: str = ""             # banner text for a fast-forwarded wait
    label: str = ""            # human description, shown in the editor


class Segment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("seg_"))
    type: Literal["card", "slide", "step"]
    title: str = ""
    kicker: str = ""
    sub: str = ""
    bullets: list[str] = []
    slide: int | None = None   # slide segments: index into the project's slides
    narration: str = ""        # spoken first (steps: actions run while it plays, see actions_at)
    actions: list[Action] = []
    actions_at: Literal["during", "after"] = "during"
    after_narration: str = ""  # steps: spoken once the actions are done ("...and you can see that...")
    notes: str = ""            # reviewer notes, not spoken
    approved: bool = False


class Check(BaseModel):
    segment_id: str
    index: int
    ok: bool
    error: str = ""
    shot: str = ""             # screenshot file name under the project's checks/ folder


class Render(BaseModel):
    file: str
    created_at: float
    seconds: float
    segments: int


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prj_"))
    name: str
    base_url: str = ""
    goal: str = ""             # what the demo should show, in the author's words
    instructions: str = ""     # tone, length, things to stress or skip
    voice_id: str = ""         # overrides the global voice when set
    voice_style: str = ""
    sources: list[Source] = []
    segments: list[Segment] = []
    slides: list[str] = []     # file names under slides/
    script_approved: bool = False
    has_login: bool = False    # a saved browser session (storage_state.json) exists
    checks: list[Check] = []
    renders: list[Render] = []
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def segment(self, sid: str) -> Segment:
        for s in self.segments:
            if s.id == sid:
                return s
        raise KeyError(sid)
