"""The narration script is written by the coding session's own model (Claude, Gemini in Antigravity), which
already knows the code, slides or app it analyzed. This module gives that model the house style and format
(GUIDE) and checks what it writes (validate) before the user reviews it and TTS voices it.
"""
from __future__ import annotations

import re

from pydantic import ValidationError

from .models import Project, Segment

WORDS_PER_SECOND = 2.2     # measured on the approved narrator style, pauses included

GUIDE = """\
# Writing a Voice Demo Lab script

You write the narration for a demo video. A text-to-speech voice reads it aloud. Write it from what you
learned in this session (the code, slides, app or notes you analyzed with the user). Do not invent features,
numbers or results that the session did not establish.

## Format
Pass write_script a JSON list of segments, in playing order. Each segment is one of:

- card: a full-screen title card.
  {"type": "card", "kicker": "SMALL CAPS LABEL", "title": "Title", "sub": "optional subtitle",
   "bullets": ["optional", "bullets"], "narration": "spoken while it shows"}
- slide: shows slide N of the project's decks while narrating (0-based, project-wide; start_demo and
  get_project list the slides with their text and speaker notes).
  {"type": "slide", "slide": 0, "narration": "..."}
- step: a live web-app step, recorded in a real browser on the project's base_url.
  {"type": "step", "title": "short label", "narration": "said first: what this step does and why",
   "actions": [ ... ], "actions_at": "during" | "after",
   "after_narration": "said once the actions finish: how the result on screen shows it worked",
   "notes": "for the reviewer, not spoken"}

Actions (Playwright; selectors like role=button[name="Save"], text="Exact text", label=Email, or CSS):
  {"op": "goto", "value": "/path or full URL"}       {"op": "click", "selector": "..."}
  {"op": "fill", "selector": "...", "value": "text typed visibly"}
  {"op": "press", "value": "Enter"}                    {"op": "hover", "selector": "..."}
  {"op": "scroll", "selector": "... or empty for the page"}
  {"op": "wait", "seconds": 2}
  {"op": "wait_for", "selector": "... or empty", "value": "text to wait for", "seconds": 120,
   "ff": true, "what": "Deploying the agent"}    (ff: fast-forward a long wait behind a banner)
  {"op": "highlight", "selector": "..."} / {"op": "unhighlight"}  (draw attention to a result)
Take selectors from the source code you read, or from inspect_page; dry_run checks every one.

## House style (the user's approved defaults; project instructions override them)
- Open with an intro card, then a spoken introduction: what will be shown and why it matters.
- A card before each major section or scenario.
- Each step: say in plain terms what it does, do it, then say how the result matches the goal.
- End with a recap card whose bullets summarise the key points, narrated. No closing tagline or slogan.
- Decks: one slide segment per slide, in order, unless the user asks otherwise. Use what the slide
  and its speaker notes mean; do not read the slide text out verbatim.
- The audience is new to the subject unless told otherwise: full coverage, high level.

## Writing for the ear
- Short sentences. No markdown, bullets, emoji or URLs in narration. Spell out symbols and say numbers
  the way a person would ("twenty-eight hours", "version two point one").
- Expand an acronym the first time ("Electronic Health Record, or E H R"); spell out letters that are
  said one by one ("B M J").
- About 130 words a minute: a 5-minute video is roughly 650 words of narration.
- Keep each narration to one idea; split long passages into more segments.
"""

_URL = re.compile(r"https?://|www\.", re.I)
_MD = re.compile(r"(\*\*|__|^#+\s|^\s*[-*]\s|`|\[[^\]]+\]\()", re.M)


def seconds(segments: list[Segment], speed: float = 1.0) -> float:
    words = sum(len(f"{s.narration} {s.after_narration}".split()) for s in segments)
    return words / WORDS_PER_SECOND / speed


def validate(raw: list[dict], p: Project) -> tuple[list[Segment], list[str], list[str]]:
    """Parse and check a script. Returns (segments, errors, warnings); save only when errors is empty."""
    segs, errors, warnings = [], [], []
    if not raw:
        errors.append("The script is empty.")
    for i, item in enumerate(raw):
        where = f"segment {i + 1}"
        try:
            s = Segment.model_validate({k: v for k, v in item.items() if k != "approved"})
        except ValidationError as e:
            errors.append(f"{where}: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
            continue
        where += f" ({s.type}{': ' + s.title if s.title else ''})"
        if s.type == "slide":
            if s.slide is None or not 0 <= s.slide < len(p.slides):
                errors.append(f"{where}: slide must be 0 to {len(p.slides) - 1}" if p.slides
                              else f"{where}: the project has no slides; attach the deck with start_demo")
        else:
            s.slide = None
        if s.type == "step":
            if not p.base_url:
                errors.append(f"{where}: web steps need the project's base_url (the app to record)")
            if not s.actions:
                warnings.append(f"{where}: no actions yet; add them, or the step only shows the current page")
            for a in s.actions:
                if a.op in ("click", "fill", "hover", "highlight") and not a.selector:
                    errors.append(f"{where}: a {a.op} action needs a selector")
        else:
            s.actions = []
        if not s.narration.strip() and s.type != "step":
            warnings.append(f"{where}: no narration, so it shows only for a moment")
        for field in ("narration", "after_narration"):
            text = getattr(s, field)
            if _URL.search(text):
                warnings.append(f"{where}: {field} contains a URL, which the voice would read out")
            if _MD.search(text):
                warnings.append(f"{where}: {field} contains markdown, which the voice would read out")
        segs.append(s)
    if segs and segs[0].type != "card":
        warnings.append("The house style opens with an intro card.")
    if segs and segs[-1].type != "card":
        warnings.append("The house style ends with a narrated recap card.")
    return segs, errors, warnings
