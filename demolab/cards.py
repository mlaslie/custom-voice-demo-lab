"""Title cards: white background, Google Cloud colors, rendered in pure Pillow at 2x supersampling.

Zero browser/Playwright dependency — cards render in ~30 ms offline with crisp antialiased typography.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SCALE = 2
SW, SH = W * SCALE, H * SCALE

BLUE = (66, 133, 244)       # #4285F4
RED = (234, 67, 53)         # #EA4335
YELLOW = (251, 188, 4)      # #FBBC04
GREEN = (52, 168, 83)       # #34A853
COLORS = [BLUE, RED, YELLOW, GREEN]

KICKER_BLUE = (26, 115, 232)    # #1A73E8
INK_TITLE = (32, 33, 36)        # #202124
INK_BODY = (60, 64, 67)         # #3C4043
INK_SUB = (95, 99, 104)         # #5F6368
FOOT_BLUE = (232, 240, 254)     # #E8F0FE

BOLD_FONTS = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
REG_FONTS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in paths:
        if pathlib.Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            if draw.textlength(trial, font=font) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def render_card_image(c: dict, width: int = W, height: int = H) -> Image.Image:
    """Render a single Google Cloud styled title card at `width`x`height` with supersampling."""
    ss = 2.0 if width <= 1920 else 1.5
    sw, sh = int(round(width * ss)), int(round(height * ss))
    u = sw / 1920.0
    sc = lambda v: max(1, int(round(v * u)))

    img = Image.new("RGB", (sw, sh), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Top 4-color Google Cloud bar
    bar_h = sc(12)
    seg_w = sw // 4
    for i, col in enumerate(COLORS):
        x0 = i * seg_w
        x1 = sw if i == 3 else (i + 1) * seg_w
        d.rectangle([x0, 0, x1, bar_h], fill=col)

    # Bottom subtle tint bar
    d.rectangle([0, sh - sc(8), sw, sh], fill=FOOT_BLUE)

    margin_x = sc(160)
    max_w = sw - 2 * margin_x

    f_kicker = _font(BOLD_FONTS, sc(26))
    bullets = [b.strip() for b in (c.get("bullets") or []) if str(b).strip()]
    title_pt = sc(64 if bullets else 74)
    f_title = _font(BOLD_FONTS, title_pt)
    f_sub = _font(REG_FONTS, sc(34))
    f_bullet = _font(REG_FONTS, sc(33))

    kicker = (c.get("kicker") or "").strip().upper()
    title_lines = _wrap(d, (c.get("title") or "").strip(), f_title, max_w)
    sub_lines = _wrap(d, (c.get("sub") or "").strip(), f_sub, max_w) if c.get("sub") else []
    bullet_blocks = [_wrap(d, b, f_bullet, max_w - sc(42)) for b in bullets]

    # Measure total vertical height to center cleanly
    dots_h = sc(18 + 30)
    kicker_h = sc(38) if kicker else 0
    title_line_h = int(title_pt * 1.18)
    title_h = len(title_lines) * title_line_h
    sub_line_h = int(sc(34) * 1.38)
    sub_h = (sc(24) + len(sub_lines) * sub_line_h) if sub_lines else 0
    bul_line_h = int(sc(33) * 1.42)
    bul_h = 0
    if bullet_blocks:
        bul_h = sc(36) + sum(len(bl) * bul_line_h + sc(14) for bl in bullet_blocks)

    total_h = dots_h + kicker_h + title_h + sub_h + bul_h
    y = max(sc(90), (sh - total_h) // 2)

    # 4 Google Cloud dots
    dot_r = sc(9)
    for i, col in enumerate(COLORS):
        cx = margin_x + i * sc(30) + dot_r
        cy = y + dot_r
        d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=col)
    y += dots_h

    # Kicker
    if kicker:
        d.text((margin_x, y), kicker, font=f_kicker, fill=KICKER_BLUE)
        y += kicker_h

    # Title
    for line in title_lines:
        d.text((margin_x, y), line, font=f_title, fill=INK_TITLE)
        y += title_line_h

    # Subtitle
    if sub_lines:
        y += sc(24)
        for line in sub_lines:
            d.text((margin_x, y), line, font=f_sub, fill=INK_SUB)
            y += sub_line_h

    # Bullets
    if bullet_blocks:
        y += sc(36)
        b_rad = sc(8)
        for i, bl in enumerate(bullet_blocks):
            col = COLORS[i % 4]
            cy = y + int(bul_line_h * 0.48)
            cx = margin_x + b_rad
            d.ellipse([cx - b_rad, cy - b_rad, cx + b_rad, cy + b_rad], fill=col)
            for line in bl:
                d.text((margin_x + sc(38), y), line, font=f_bullet, fill=INK_BODY)
                y += bul_line_h
            y += sc(14)

    return img.resize((width, height), Image.LANCZOS)


def render_cards(cards: list[dict], out_dir: pathlib.Path, width: int = W, height: int = H) -> dict[str, pathlib.Path]:
    """Render each distinct card to out_dir/<hash>.png; returns {key: path}. Key = card_key(c)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, pathlib.Path] = {}
    suffix = "" if (width, height) == (W, H) else f"_{width}x{height}"
    for c in cards:
        k = card_key(c)
        out = out_dir / f"{k}{suffix}.png"
        paths[k] = out
        if not out.exists():
            render_card_image(c, width=width, height=height).save(out, format="PNG")
    return paths


def card_key(c: dict) -> str:
    sig = json.dumps({k: c.get(k) for k in ("title", "kicker", "sub", "bullets")}, sort_keys=True)
    return hashlib.sha1(sig.encode()).hexdigest()[:12]
