"""Project document: sources, grounded research, AGY browser onboarding & frames, and narration script.

One script drives everything. A segment is a title card (`card`), a slide (`slide`), or a live website
walkthrough step (`step`) executed and captured inside Google Antigravity's built-in browser.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:10]


Scenario = Literal["slides", "website", "hybrid"]
SourceKind = Literal["url", "repo", "pptx", "pdf", "gslides", "text", "session"]


class Source(BaseModel):
    id: str = Field(default_factory=lambda: new_id("src_"))
    kind: SourceKind
    label: str = ""
    ref: str = ""              # url / path / presentation id
    text: str = ""             # extracted digest (slide text + speaker notes) used for script writing
    slide_count: int = 0       # slides rendered into the project's slides/ folder
    slide_offset: int = 0      # index of this source's first slide in the project's slide list
    files: list[str] = []      # session: attached files and folders that were read
    images: list[str] = []     # session: attached screenshots
    added_at: float = Field(default_factory=time.time)


class ResearchItem(BaseModel):
    """A verified technical source gathered during the research phase to ground the narration in reality."""
    id: str = Field(default_factory=lambda: new_id("res_"))
    title: str
    source_type: Literal["docs", "blog", "video", "slide", "webpage", "code", "context"] = "docs"
    url_or_path: str = ""
    summary: str = ""
    verified_claims: list[str] = []
    added_at: float = Field(default_factory=time.time)


class WebAuth(BaseModel):
    """Authentication & onboarding status inside Antigravity's built-in browser."""
    status: Literal["unchecked", "authenticated", "login_required", "not_needed"] = "unchecked"
    checked_url: str = ""
    account_hint: str = ""     # non-secret display label (e.g. "GCP project demo-prod"), never credentials
    notes: str = ""
    updated_at: float = 0


class HighlightBox(BaseModel):
    """Normalized (0..1) or pixel (0..1920, 0..1080) bounding box for spotlighting or zooming a UI region."""
    x: float
    y: float
    w: float
    h: float
    label: str = ""

    def normalized(self, width: int = 1920, height: int = 1080) -> tuple[float, float, float, float]:
        if max(abs(self.x), abs(self.y), abs(self.w), abs(self.h)) > 1.5:
            nx, ny, nw, nh = self.x / width, self.y / height, self.w / width, self.h / height
        else:
            nx, ny, nw, nh = self.x, self.y, self.w, self.h
        nx = max(0.0, min(0.98, nx))
        ny = max(0.0, min(0.98, ny))
        nw = max(0.02, min(1.0 - nx, nw))
        nh = max(0.02, min(1.0 - ny, nh))
        return nx, ny, nw, nh


class StepFrame(BaseModel):
    """A 1080p frame captured from Antigravity's built-in browser for a live website step."""
    id: str = Field(default_factory=lambda: new_id("frm_"))
    file: str                                                  # filename under projects/<pid>/frames/
    phase: Literal["before", "during", "result"] = "during"
    caption: str = ""
    highlight: HighlightBox | None = None
    zoom_to: HighlightBox | None = None
    ff_what: str = ""                                          # optional fast-forward banner label
    ff_elapsed: float = 0                                      # simulated/actual wait seconds shown on banner


ActionOp = Literal[
    "goto", "click", "fill", "press", "hover", "scroll",
    "wait", "wait_for", "highlight", "unhighlight", "verify",
]


class Action(BaseModel):
    """An interaction step executed in Antigravity's built-in browser."""
    op: ActionOp
    selector: str = ""         # UI element description or selector (e.g. 'role=button[name="Create"]' or 'APIs & Services')
    target: str = ""           # alias synced with selector for natural AGY browser prompts
    value: str = ""            # url (goto), text (fill), key (press), text to wait for (wait_for/verify)
    seconds: float = 0         # wait: duration; wait_for: timeout (default 30)
    ff: bool = False           # fast-forward this wait in the final video, with a banner
    what: str = ""             # banner text for a fast-forwarded wait
    label: str = ""            # human description shown in the Studio

    @model_validator(mode="after")
    def _sync_target_selector(self) -> "Action":
        if self.target and not self.selector:
            self.selector = self.target
        elif self.selector and not self.target:
            self.target = self.selector
        return self


class Segment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("seg_"))
    type: Literal["card", "slide", "step"]
    title: str = ""
    kicker: str = ""
    sub: str = ""
    bullets: list[str] = []
    slide: int | None = None   # slide segments: index into the project's slides
    narration: str = ""        # spoken first (steps: before/during frames play while spoken)
    actions: list[Action] = []
    actions_at: Literal["during", "after"] = "during"
    after_narration: str = ""  # steps: spoken once actions complete while showing result frame(s)
    frames: list[StepFrame] = []   # captured in-AGY browser frames for step segments
    citations: list[str] = []      # titles/URLs/IDs of ResearchItems or slides backing this segment
    notes: str = ""                # reviewer notes, not spoken
    approved: bool = False


class Check(BaseModel):
    segment_id: str
    index: int
    ok: bool
    error: str = ""
    shot: str = ""             # frame/screenshot file name under frames/ or checks/


class Render(BaseModel):
    file: str
    created_at: float
    seconds: float
    segments: int


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prj_"))
    name: str
    scenario: Scenario = "slides"
    base_url: str = ""
    goal: str = ""             # what the demo should show, in the author's words
    brief: str = ""            # session + user context the script is built around
    audience: str = ""         # who will watch; empty = the default audience in settings
    instructions: str = ""     # tone, length, things to stress or skip
    profile_id: str = ""       # voice profile for this project; empty = the active profile
    voice_id: str = ""         # overrides the profile's voice when set
    voice_style: str = ""      # overrides the profile's style when set
    speed: float = 0           # overrides the profile's narration speed when set (0 = the profile's)
    sources: list[Source] = []
    research_summary: str = ""
    research: list[ResearchItem] = []
    web_auth: WebAuth = Field(default_factory=WebAuth)
    segments: list[Segment] = []
    slides: list[str] = []     # file names under slides/
    script_approved: bool = False
    has_login: bool = False    # True when web_auth.status in ("authenticated", "not_needed")
    checks: list[Check] = []
    renders: list[Render] = []
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def segment(self, sid: str) -> Segment:
        for s in self.segments:
            if s.id == sid:
                return s
        raise KeyError(sid)
