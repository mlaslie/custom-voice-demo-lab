"""Script authoring guide (`GUIDE`) and validator (`validate`).

The narration script is authored by Google Antigravity (or Claude Code) after researching the topic against
authoritative technical docs, recent blogs/announcements, videos, slide decks, and live website state.
"""
from __future__ import annotations

import re

from pydantic import ValidationError

from .models import Project, Segment

WORDS_PER_SECOND = 2.2     # measured on the approved narrator style, pauses included

GUIDE = """\
# Writing a Grounded Voice Demo Lab Script (Google Antigravity First)

You write the narration and visual choreography for an automated 1080p demo/overview video voiced by Gemini TTS.

## 1. Ground Every Claim in Reality First (`save_research`)
Before calling `write_script`, verify technical capabilities, product names, architecture details, CLI/API
syntax, release dates, and metrics against authoritative sources:
- Official technical documentation & API references
- Recent launch announcements, Google Cloud / engineering blogs, and release notes
- Walkthrough videos, session context, slide text & speaker notes, and live UI state
Save your verified findings with `save_research(project_id, summary, items)` and attach short source labels
in each segment's `"citations": ["Official Docs: ...", "Slide 3"]` list. Never invent features, benchmarks,
UI buttons, or URLs that were not verified.

## 2. Supported Scenarios
- `slides` (Scenario 1 & 2): In-AGY created slides or user-provided slides (Google Slides URL/ID, `.pptx`, `.pdf`)
  paired with AGY session context and user directions.
- `website` (Scenario 3): Live website walkthrough (e.g. `https://console.cloud.google.com`, SaaS console, or
  `localhost` app) orchestrated 100% inside Antigravity's built-in `browser` subagent — after running the
  login onboarding check (`record_web_auth`).
- `hybrid`: Combines title cards, slide segments, and live website `step` segments in one cohesive video.

## 3. Segment Format (`write_script`)
Pass `write_script` a JSON list of segments in playing order. Each segment is one of:

- `card` — Full-screen Google Cloud styled title/section/recap card (rendered crisp at 1080p):
  ```json
  {
    "type": "card",
    "kicker": "SMALL CAPS LABEL",
    "title": "Main Title",
    "sub": "Optional subtitle",
    "bullets": ["Optional key point 1", "Optional key point 2"],
    "narration": "Spoken while this card is on screen.",
    "citations": ["Launch Blog"]
  }
  ```

- `slide` — Displays slide `N` (0-based project-wide index from `start_demo` / `get_project`) while narrating:
  ```json
  {
    "type": "slide",
    "slide": 0,
    "title": "Architecture Overview",
    "narration": "Explain what the slide and speaker notes mean — never read bullet text verbatim.",
    "citations": ["Slide 1"]
  }
  ```

- `step` — Live website walkthrough step executed & captured in Antigravity's built-in `browser` subagent:
  ```json
  {
    "type": "step",
    "title": "Enable Cloud Healthcare API",
    "narration": "Spoken while showing the `before` / `during` frames: what we are doing and why.",
    "actions": [
      {"op": "goto", "value": "https://console.cloud.google.com/apis/library/healthcare.googleapis.com"},
      {"op": "click", "target": "Enable button"},
      {"op": "wait_for", "value": "API enabled", "seconds": 45, "ff": true, "what": "Enabling Healthcare API"}
    ],
    "after_narration": "Spoken while showing the `result` frame(s): how the screen confirms success.",
    "citations": ["Cloud Healthcare API Docs"],
    "notes": "Reviewer note (not spoken)"
  }
  ```

### Actions for In-AGY Browser Steps
Each action guides Antigravity's `browser` subagent (and shows in Voice Demo Studio for review):
- `{"op": "goto", "value": "/path or full URL"}`
- `{"op": "click", "target": "Button or nav item label"}` (alias `"selector"` also accepted)
- `{"op": "fill", "target": "Input field", "value": "text typed visibly"}`
- `{"op": "press", "value": "Enter"}` | `{"op": "hover", "target": "..."}` | `{"op": "scroll", "target": "..."}`
- `{"op": "wait", "seconds": 2}`
- `{"op": "wait_for", "value": "text/state to wait for", "seconds": 60, "ff": true, "what": "Deploying service"}`
- `{"op": "highlight", "target": "Result panel"}` | `{"op": "verify", "value": "Expected text on page"}`

When executing a `step` in Antigravity's `browser` subagent, capture clean 16:9 screenshots (`before`,
`during`, `result`) and attach them via `record_step_frames(project_id, segment_id, frames=[...])` with
optional `highlight` (`{"x": 0.12, "y": 0.25, "w": 0.45, "h": 0.18, "label": "Active endpoint"}`),
`zoom_to`, or `ff_what` / `ff_elapsed` for fast-forwarded waits.

## 4. House Style (Project `instructions` Override Defaults)
- Open with an intro `card`: introduce what will be shown and why it matters.
- Use a section `card` before major transitions (e.g. moving from slides into the live console demo).
- For slide decks: cover slides in logical order, synthesizing slide visuals + speaker notes + grounded research
  rather than reading slide bullets word-for-word.
- For live web `step`s: state clearly what the step will accomplish (`narration`), show the interaction, then
  point out the concrete outcome on screen (`after_narration`).
- End with a narrated recap `card` whose `bullets` summarize 3–4 key takeaways. Skip cheesy taglines.

## 5. Writing for the Ear (Gemini TTS)
- Short, conversational sentences. **Zero markdown, bullet symbols, backticks, emoji, or raw URLs** in
  `narration` or `after_narration`.
- Write numbers, versions, and symbols the way a human speaker says them ("version two point five",
  "ninety-nine point nine percent", "Google Cloud Console").
- Expand acronyms on first mention ("Fast Healthcare Interoperability Resources, or F H I R").
- Pace: ~130 words per minute (~2.2 words/sec). A crisp 3-minute overview is ~390 words; 5 minutes is ~650 words.
- Keep each segment focused on one clear idea; split long explanations across segments.
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
                errors.append(
                    f"{where}: slide must be 0 to {len(p.slides) - 1}"
                    if p.slides
                    else f"{where}: the project has no slides; attach the deck with start_demo"
                )
        else:
            s.slide = None
        if s.type == "step":
            if not p.base_url:
                errors.append(f"{where}: web steps need the project's base_url (the app to record)")
            if not s.actions and not s.frames:
                warnings.append(f"{where}: no actions yet; add them, or the step only shows the current page")
            for a in s.actions:
                if a.op in ("click", "fill", "hover", "highlight") and not a.selector:
                    errors.append(f"{where}: a {a.op} action needs a selector or target")
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
