"""Draft and revise the narration script with Gemini.

The house style (intro card, card per section, explain / do / show-the-result per step, narrated recap,
no closing tagline) comes from demos the author already approved; per-project instructions override it.
"""
from __future__ import annotations

from . import config, gemini, store
from .models import Project, Segment

SEG_PROPS = {
    "type": {"type": "STRING", "enum": ["card", "slide", "step"]},
    "title": {"type": "STRING"}, "kicker": {"type": "STRING"}, "sub": {"type": "STRING"},
    "bullets": {"type": "ARRAY", "items": {"type": "STRING"}},
    "slide": {"type": "INTEGER"},
    "narration": {"type": "STRING"},
    "after_narration": {"type": "STRING"},
    "actions_at": {"type": "STRING", "enum": ["during", "after"]},
    "notes": {"type": "STRING"},
}
SEGMENT_SCHEMA = {"type": "OBJECT", "properties": SEG_PROPS, "required": ["type", "narration"]}
SCRIPT_SCHEMA = {"type": "OBJECT", "properties": {"segments": {"type": "ARRAY", "items": SEGMENT_SCHEMA}},
                 "required": ["segments"]}

SYSTEM = """You write narration scripts for demo videos read aloud by a text-to-speech voice.

Output a list of segments:
- card: a full-screen title card (title, optional kicker = small caps label above, sub, bullets).
- slide: shows slide number `slide` (0-based, project-wide index as given in the sources) while narrating.
- step: a live web-app step. `narration` is spoken first; the browser actions (planned later from your
  words) run during it (actions_at="during") or after it ("after"). `after_narration` is spoken once the
  actions are done and says how the result on screen shows the step worked. `notes` tells the action
  planner what to click or show (not spoken).

House style:
- Start with an intro card, then a spoken introduction of what will be shown and why it matters.
- A card before each major section or scenario.
- For each step: explain in plain terms what it does, do it, then say how the result matches the goal.
- End with a recap card whose bullets summarise the key points, narrated. No closing tagline or slogan.
- Write for the ear: short sentences, no markdown, no URLs read aloud, spell out symbols, avoid lists
  inside narration. Expand acronyms on first use.
- Slide decks: one slide segment per slide in order, unless the author asks otherwise; use speaker
  notes as the main source when present, and do not just read the slide text verbatim.
- SESSION sources come from the author's own working session with a coding agent: what was built or
  changed, why, and what to show. Build the story and its order from them, and use the other sources for
  detail. Where they conflict, the session is newer and wins. Leave out anything it marks as not working
  or not to be shown. Attached screenshots show the real UI.
- Only describe UI that exists in the sources. Do not invent features or results."""


def _sources_digest(p: Project, budget: int = 120_000) -> str:
    out = []
    for s in sorted(p.sources, key=lambda s: s.kind != "session"):   # session context leads
        head = f"### SOURCE [{s.kind.upper() if s.kind == 'session' else s.kind}] {s.label}"
        if s.slide_count:
            head += f" (slides {s.slide_offset}..{s.slide_offset + s.slide_count - 1})"
        out.append(f"{head}\n{s.text}")
    text = "\n\n".join(out)
    return text[:budget]


def _session_images(p: Project, limit: int = 8) -> list[bytes]:
    d = store.pdir(p.id) / "session"
    names = [n for s in p.sources if s.kind == "session" for n in s.images][:limit]
    return [(d / n).read_bytes() for n in names if (d / n).exists()]


def _kind(p: Project) -> str:
    has_web = bool(p.base_url) or any(s.kind == "url" for s in p.sources)
    has_slides = bool(p.slides)
    return "mixed (slides and live web app)" if has_web and has_slides else \
        "live web app" if has_web else "slide presentation" if has_slides else "narrated explainer"


def draft(job, pid: str) -> dict:
    p = store.get(pid)
    st = config.load()
    if not p.sources and not p.goal:
        raise ValueError("Add at least one source (or a goal) first.")
    job.say("Drafting the script", 0.1)
    if config.fake_gemini():
        segs = _fake_script(p)
    else:
        prompt = (f"Demo title: {p.name}\nDemo type: {_kind(p)}\nApp URL: {p.base_url or '(none)'}\n"
                  f"Number of slides available: {len(p.slides)}\nAudience: {st.audience}\n"
                  f"Goal: {p.goal or '(infer from the sources)'}\n"
                  f"Author instructions (override the house style): {p.instructions or '(none)'}\n\n"
                  f"SOURCES:\n{_sources_digest(p)}")
        d = gemini.generate_json(prompt, SCRIPT_SCHEMA, st.script_model, images=_session_images(p),
                                 system=SYSTEM)
        segs = [_clean(Segment.model_validate(x), p) for x in d["segments"]]
    store.mutate(pid, lambda q: (setattr(q, "segments", segs), setattr(q, "script_approved", False)))
    return {"segments": len(segs)}


def revise_segment(pid: str, sid: str, instruction: str) -> Segment:
    p = store.get(pid)
    seg = p.segment(sid)
    st = config.load()
    if config.fake_gemini():
        new = seg.model_copy(update={"narration": f"{seg.narration} ({instruction})"})
    else:
        i = p.segments.index(seg)
        ctx = "\n".join(f"[{j}] {s.type}: {s.title} | {s.narration[:200]}"
                        for j, s in enumerate(p.segments[max(0, i - 2):i + 3], start=max(0, i - 2)))
        prompt = (f"Revise segment [{i}] of this demo script following the instruction. Keep its type unless "
                  f"told otherwise.\n\nINSTRUCTION: {instruction}\n\nNEARBY SEGMENTS:\n{ctx}\n\n"
                  f"SEGMENT [{i}] AS JSON:\n{seg.model_dump_json(exclude={'actions', 'id', 'approved'})}\n\n"
                  f"SOURCES (for facts):\n{_sources_digest(p, 40_000)}")
        d = gemini.generate_json(prompt, SEGMENT_SCHEMA, st.script_model, system=SYSTEM)
        new = _clean(Segment.model_validate(d), p)
        new.actions = seg.actions
    new.id, new.approved = seg.id, False

    def apply(q: Project):
        q.segments[[s.id for s in q.segments].index(sid)] = new
        q.script_approved = False
    store.mutate(pid, apply)
    return new


def _clean(s: Segment, p: Project) -> Segment:
    if s.type == "slide" and (s.slide is None or not (0 <= s.slide < len(p.slides))):
        s.type, s.slide = "card", None
        s.title = s.title or "Slide"
    if s.type != "slide":
        s.slide = None
    return s


def _fake_script(p: Project) -> list[Segment]:
    segs = [Segment(type="card", kicker="Demo", title=p.name, sub=p.goal,
                    narration=f"In this demo we walk through {p.name}.")]
    for i in range(len(p.slides)):
        segs.append(Segment(type="slide", slide=i, narration=f"This is slide {i + 1}."))
    if p.base_url:
        segs.append(Segment(type="step", title="Open the app", narration="Here is the application's home page.",
                            after_narration="The page is loaded and ready."))
    segs.append(Segment(type="card", kicker="Recap", title="What we saw", bullets=["The main flow"],
                        narration="That covers the main flow."))
    return segs
