"""Everything that drives Chromium: page snapshots, saved logins, the action runner, AI exploration,
dry runs, and the screencast recorder used for renders.

Frames come from the DevTools screencast (sharper than Playwright's video). Each step segment is bracketed
by seg_start/seg_end marks on a timeline, with say and ff_start/ff_end marks inside; compose.py cuts the
recording by those marks.
"""
from __future__ import annotations

import base64
import json
import pathlib
import time
from contextlib import contextmanager
from urllib.parse import urljoin

from . import store
from .models import Action, Check, Project, Segment

W, H = 1920, 1080
PAD = 0.6            # silence after each narration clip (s)

OVERLAY_CSS = """
.vd-hl{outline:5px solid #fbbc04 !important;outline-offset:6px;border-radius:12px;
 box-shadow:0 0 0 14px rgba(251,188,4,.25) !important;transition:outline .2s}
"""

ELEMENTS_JS = r"""
() => {
  const q = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=switch],'
          + '[role=checkbox],[role=menuitem],[role=option],[role=combobox],[contenteditable=true]';
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const roleOf = e => e.getAttribute('role') || ({A:'link',BUTTON:'button',SELECT:'combobox',TEXTAREA:'textbox',
     SUMMARY:'button'}[e.tagName]) || (e.tagName==='INPUT' ? ({checkbox:'checkbox',radio:'radio',submit:'button',
     button:'button'}[e.type] || 'textbox') : e.tagName.toLowerCase());
  const nameOf = e => (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder ||
     e.getAttribute('title') || e.getAttribute('alt') || '').trim().replace(/\s+/g,' ').slice(0,80);
  const esc = s => s.replace(/"/g,'\\"');
  const seen = new Set(), out = [];
  for (const e of document.querySelectorAll(q)) {
    if (!vis(e)) continue;
    const role = roleOf(e), name = nameOf(e);
    let sel;
    const tid = e.getAttribute('data-testid') || e.getAttribute('data-test');
    if (tid) sel = `[data-testid="${esc(tid)}"]`;
    else if (e.id && /^[A-Za-z][\w-]*$/.test(e.id) && document.querySelectorAll('#'+e.id).length===1) sel = '#'+e.id;
    else if (name) sel = `role=${role}[name="${esc(name)}"]`;
    else if (e.name) sel = `${e.tagName.toLowerCase()}[name="${esc(e.name)}"]`;
    else continue;
    if (seen.has(sel)) continue; seen.add(sel);
    const st = e.getAttribute('aria-checked') ?? e.getAttribute('aria-selected') ?? (e.checked ? 'true' : null);
    out.push(`${role} "${name}"${st!==null ? ' state='+st : ''} -> ${sel}`);
    if (out.length >= 250) break;
  }
  return out.join('\n');
}
"""

RIPPLE_JS = """([x,y]) => {const d=document.createElement('div');
  d.style.cssText=`position:fixed;left:${x-22}px;top:${y-22}px;width:44px;height:44px;border-radius:50%;
  background:rgba(26,115,232,.35);border:3px solid #1a73e8;z-index:2147483646;pointer-events:none;transition:all .6s`;
  document.body.appendChild(d); setTimeout(()=>{d.style.transform='scale(1.8)';d.style.opacity='0'},50);
  setTimeout(()=>d.remove(),700)}"""


def login_state(p: Project) -> pathlib.Path:
    return store.pdir(p.id) / "storage_state.json"


@contextmanager
def session(p: Project, headless: bool = True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=headless)
        st = login_state(p)
        ctx = br.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                             storage_state=str(st) if st.exists() else None)
        ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                            f"s.textContent={json.dumps(OVERLAY_CSS)};document.head.appendChild(s)}})")
        page = ctx.new_page()
        try:
            yield page
        finally:
            br.close()


def _settle(page, ms: int = 5000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass


def snapshot(page) -> dict:
    _settle(page, 3000)
    text = page.evaluate("() => document.body ? document.body.innerText : ''")[:8000]
    return {"title": page.title(), "url": page.url, "text": text, "elements": page.evaluate(ELEMENTS_JS)}


def snapshot_url(p: Project, url: str) -> dict:
    with session(p) as page:
        page.goto(url, wait_until="load", timeout=60000)
        return snapshot(page)


def capture_login(p: Project, url: str, timeout: float = 900) -> None:
    """Open a visible browser at url; the user signs in and closes the window; the session is saved."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=False)
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(url)
        t0, st = time.time(), ctx.storage_state()
        while time.time() - t0 < timeout and not page.is_closed():
            try:   # poll: once the user closes the window the context may already be gone
                st = ctx.storage_state()
                page.wait_for_timeout(1000)
            except Exception:
                break
        login_state(p).write_text(json.dumps(st))
        try:
            br.close()
        except Exception:
            pass
    store.mutate(p.id, lambda q: setattr(q, "has_login", True))


# ---- action runner ------------------------------------------------------------------------------

class Runner:
    """Executes Actions on a page. With a Recorder attached it paces for video (ripples, typing, idles)."""

    def __init__(self, page, base_url: str, rec: "Recorder | None" = None):
        self.page, self.base_url, self.rec = page, base_url, rec

    def idle(self, s: float) -> None:
        if self.rec:
            self.rec.idle(s)
        elif s > 0:
            self.page.wait_for_timeout(int(s * 1000))

    def loc(self, a: Action):
        return self.page.locator(a.selector).first

    def run(self, a: Action) -> None:
        pg = self.page
        if a.op == "goto":
            pg.goto(urljoin(self.base_url or pg.url, a.value or a.selector), wait_until="load", timeout=60000)
            _settle(pg)
            self.idle(1.0)
        elif a.op == "click":
            el = self.loc(a)
            el.scroll_into_view_if_needed(timeout=15000)
            if self.rec:
                box = el.bounding_box()
                if box:
                    pg.evaluate(RIPPLE_JS, [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
                    self.idle(0.4)
            el.click(timeout=15000)
            self.idle(0.8)
        elif a.op == "fill":
            el = self.loc(a)
            el.scroll_into_view_if_needed(timeout=15000)
            if self.rec:
                el.click(timeout=15000)
                el.fill("")
                el.press_sequentially(a.value, delay=45)
            else:
                el.fill(a.value, timeout=15000)
            self.idle(0.5)
        elif a.op == "press":
            (self.loc(a).press(a.value, timeout=15000) if a.selector else pg.keyboard.press(a.value))
            self.idle(0.6)
        elif a.op == "hover":
            self.loc(a).hover(timeout=15000)
            self.idle(0.6)
        elif a.op == "scroll":
            if a.selector:
                self.loc(a).scroll_into_view_if_needed(timeout=15000)
            else:
                pg.mouse.wheel(0, float(a.value or 600))
            self.idle(0.8)
        elif a.op == "wait":
            self._ff(a, lambda: self.idle(a.seconds or 1), long=(a.seconds or 0) > 12)
        elif a.op == "wait_for":
            tgt = self.loc(a) if a.selector else pg.get_by_text(a.value).first
            self._ff(a, lambda: tgt.wait_for(state="visible", timeout=int((a.seconds or 30) * 1000)), long=False)
            self.idle(0.8)
        elif a.op == "highlight":
            pg.evaluate("()=>document.querySelectorAll('.vd-hl').forEach(e=>e.classList.remove('vd-hl'))")
            el = self.loc(a)
            el.scroll_into_view_if_needed(timeout=15000)
            el.evaluate("e => e.classList.add('vd-hl')")
            self.idle(0.4)
        elif a.op == "unhighlight":
            pg.evaluate("()=>document.querySelectorAll('.vd-hl').forEach(e=>e.classList.remove('vd-hl'))")

    def _ff(self, a: Action, fn, long: bool) -> None:
        if self.rec and (a.ff or long):
            self.rec.mark("ff_start", what=a.what or a.label or "Waiting")
            fn()   # no repaints needed: compose holds the last frame through a static screen
            self.rec.mark("ff_end")
        else:
            fn()


# ---- dry run ------------------------------------------------------------------------------------

def dry_run(job, pid: str) -> dict:
    p = store.get(pid)
    if not p.base_url:
        raise ValueError("Set the project's app URL first.")
    out = store.sub(pid, "checks")
    for f in out.glob("*.jpg"):
        f.unlink()
    checks: list[Check] = []
    steps = [s for s in p.segments if s.type == "step"]
    with session(p) as page:
        page.goto(p.base_url, wait_until="load", timeout=60000)
        run = Runner(page, p.base_url)
        for n, seg in enumerate(steps):
            job.say(f"Checking step {n + 1}/{len(steps)}: {seg.title or seg.narration[:40]}", n / max(1, len(steps)))
            for i, a in enumerate(seg.actions):
                try:
                    run.run(a)
                    checks.append(Check(segment_id=seg.id, index=i, ok=True))
                except Exception as e:
                    shot = f"{seg.id}_{i}.jpg"
                    page.screenshot(path=str(out / shot), type="jpeg", quality=70)
                    checks.append(Check(segment_id=seg.id, index=i, ok=False, error=str(e)[:400], shot=shot))
                    break
            shot = f"{seg.id}.jpg"
            page.screenshot(path=str(out / shot), type="jpeg", quality=70)
            checks.append(Check(segment_id=seg.id, index=-1, ok=True, shot=shot))
    store.mutate(pid, lambda q: setattr(q, "checks", checks))
    bad = [c for c in checks if not c.ok]
    return {"ok": not bad, "failures": len(bad)}


# ---- recorder -----------------------------------------------------------------------------------

class Recorder:
    def __init__(self, page, out: pathlib.Path):
        self.page, self.out = page, out
        self.events: list[dict] = []
        self.frames: list[tuple[float, str]] = []
        self.fdir = out / "frames"
        self.fdir.mkdir(parents=True, exist_ok=True)
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)

    def _frame(self, ev) -> None:
        ts = ev["metadata"].get("timestamp") or time.time()
        f = self.fdir / f"{len(self.frames):06d}.jpg"
        f.write_bytes(base64.b64decode(ev["data"]))
        self.frames.append((ts, f.name))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def start(self) -> None:
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H,
                                               "everyNthFrame": 1})

    def stop(self) -> None:
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass

    def mark(self, kind: str, **kw) -> dict:
        e = {"t": time.time(), "kind": kind, **kw}
        self.events.append(e)
        return e

    def idle(self, secs: float) -> None:
        # Keep the screencast alive: an invisible style change forces a repaint every ~0.5 s.
        end = time.time() + secs
        while time.time() < end:
            try:
                self.page.evaluate("document.documentElement.style.setProperty('--vd-tick', Math.random())")
            except Exception:
                pass
            self.page.wait_for_timeout(min(500, max(1, int((end - time.time()) * 1000))))

    def until(self, t_end: float) -> None:
        if t_end > time.time():
            self.idle(t_end - time.time())

    def say(self, wav: pathlib.Path, dur: float) -> float:
        self.mark("say", wav=str(wav), dur=dur)
        return time.time() + dur + PAD


def record_steps(job, p: Project, steps: list[Segment], audio: dict[str, tuple[pathlib.Path, float]],
                 out: pathlib.Path) -> tuple[list[dict], list[tuple[float, str]]]:
    """Record all step segments in one browser session. audio maps '<seg_id>' / '<seg_id>:after' to clips."""
    with session(p) as page:
        page.goto(p.base_url, wait_until="load", timeout=60000)
        _settle(page)
        rec = Recorder(page, out)
        rec.start()
        rec.idle(0.8)
        run = Runner(page, p.base_url, rec)
        try:
            for n, seg in enumerate(steps):
                job.say(f"Recording step {n + 1}/{len(steps)}: {seg.title or seg.narration[:40]}",
                        0.3 + 0.4 * n / max(1, len(steps)))
                rec.mark("seg_start", seg=seg.id)
                t_end = time.time()
                if seg.id in audio:
                    t_end = rec.say(*audio[seg.id])
                    if seg.actions_at == "after":
                        rec.until(t_end)
                for a in seg.actions:
                    run.run(a)
                rec.until(t_end)
                if f"{seg.id}:after" in audio:
                    rec.until(rec.say(*audio[f"{seg.id}:after"]))
                rec.idle(0.4)
                rec.mark("seg_end", seg=seg.id)
        finally:
            rec.idle(0.5)
            rec.stop()
    return rec.events, rec.frames
