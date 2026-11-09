"""Title cards: white, Google Cloud colors. Rendered once per card with headless Chromium (Google Sans).

Cards are rendered at compose time, so a card's look can change without re-recording.
"""
from __future__ import annotations

import hashlib
import html
import json
import pathlib

W, H = 1920, 1080
BLUE, RED, YELLOW, GREEN = "#4285F4", "#EA4335", "#FBBC04", "#34A853"

CSS = f"""
html,body{{margin:0;width:{W}px;height:{H}px;background:#fff;overflow:hidden}}
body{{font-family:'Google Sans',Roboto,Arial,sans-serif;color:#202124;position:relative}}
.bar{{position:absolute;left:0;right:0;top:0;height:10px;display:flex}}
.bar i{{flex:1}}
.wrap{{position:absolute;left:160px;right:160px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center}}
.dots{{display:flex;gap:12px;margin-bottom:30px}}
.dots i{{width:18px;height:18px;border-radius:50%}}
.k{{font-size:28px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;color:#1A73E8;margin-bottom:18px}}
.t{{font-size:78px;font-weight:500;line-height:1.1;max-width:1500px;color:#202124}}
.s{{font-size:36px;color:#5F6368;margin-top:26px;max-width:1500px;line-height:1.35}}
ul{{list-style:none;margin:40px 0 0;padding:0;font-size:36px;line-height:1.5;color:#3C4043;max-width:1550px}}
li{{display:flex;align-items:baseline;gap:22px;margin:8px 0}}
li b{{flex:none;width:16px;height:16px;border-radius:50%;transform:translateY(-4px)}}
.foot{{position:absolute;left:0;right:0;bottom:0;height:6px;background:#E8F0FE}}
"""
COLORS = [BLUE, RED, YELLOW, GREEN]


def card_html(c: dict) -> str:
    e = html.escape
    bullets = c.get("bullets") or []
    return (f"<!doctype html><html><head><meta charset=utf-8>"
            "<link href='https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&display=swap' rel=stylesheet>"
            f"<style>{CSS}</style></head><body>"
            "<div class=bar>" + "".join(f"<i style='background:{x}'></i>" for x in COLORS) + "</div>"
            "<div class=wrap><div class=dots>" + "".join(f"<i style='background:{x}'></i>" for x in COLORS) + "</div>"
            + (f"<div class=k>{e(c['kicker'])}</div>" if c.get("kicker") else "")
            + f"<div class=t>{e(c['title'])}</div>"
            + (f"<div class=s>{e(c['sub'])}</div>" if c.get("sub") else "")
            + ("<ul>" + "".join(f"<li><b style='background:{COLORS[i % 4]}'></b><span>{e(b)}</span></li>"
                                for i, b in enumerate(bullets)) + "</ul>" if bullets else "")
            + "</div><div class=foot></div></body></html>")


def render_cards(cards: list[dict], out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    """Render each distinct card to out_dir/<hash>.png; returns {key: path}. Key = card_key(c)."""
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, todo = {}, []
    for c in cards:
        k = card_key(c)
        paths[k] = out_dir / f"{k}.png"
        if not paths[k].exists():
            todo.append(c)
    if todo:
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page(viewport={"width": W, "height": H})
            for c in todo:
                pg.set_content(card_html(c), wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                pg.screenshot(path=str(paths[card_key(c)]))
            br.close()
    return paths


def card_key(c: dict) -> str:
    sig = json.dumps({k: c.get(k) for k in ("title", "kicker", "sub", "bullets")}, sort_keys=True)
    return hashlib.sha1(sig.encode()).hexdigest()[:12]
