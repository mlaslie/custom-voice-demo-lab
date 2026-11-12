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


def render_card_image(c: dict) -> Image.Image:
    """Render a single Google Cloud styled title card to a 1920x1080 RGB Image."""
    img = Image.new("RGB", (SW, SH), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Top 4-color Google Cloud bar
    bar_h = 12 * SCALE
    seg_w = SW // 4
    for i, col in enumerate(COLORS):
        x0 = i * seg_w
        x1 = SW if i == 3 else (i + 1) * seg_w
        d.rectangle([x0, 0, x1, bar_h], fill=col)

    # Bottom subtle tint bar
    d.rectangle([0, SH - 8 * SCALE, SW, SH], fill=FOOT_BLUE)

    margin_x = 160 * SCALE
    max_w = SW - 2 * margin_x

    f_kicker = _font(BOLD_FONTS, 26 * SCALE)
    bullets = [b.strip() for b in (c.get("bullets") or []) if str(b).strip()]
    title_pt = (64 if bullets else 74) * SCALE
    f_title = _font(BOLD_FONTS, title_pt)
    f_sub = _font(REG_FONTS, 34 * SCALE)
    f_bullet = _font(REG_FONTS, 33 * SCALE)

    kicker = (c.get("kicker") or "").strip().upper()
    title_lines = _wrap(d, (c.get("title") or "").strip(), f_title, max_w)
    sub_lines = _wrap(d, (c.get("sub") or "").strip(), f_sub, max_w) if c.get("sub") else []
    bullet_blocks = [_wrap(d, b, f_bullet, max_w - 42 * SCALE) for b in bullets]

    # Measure total vertical height to center cleanly
    dots_h = (18 + 30) * SCALE
    kicker_h = (38 * SCALE) if kicker else 0
    title_line_h = int(title_pt * 1.18)
    title_h = len(title_lines) * title_line_h
    sub_line_h = int(34 * SCALE * 1.38)
    sub_h = (24 * SCALE + len(sub_lines) * sub_line_h) if sub_lines else 0
    bul_line_h = int(33 * SCALE * 1.42)
    bul_h = 0
    if bullet_blocks:
        bul_h = 36 * SCALE + sum(len(bl) * bul_line_h + 14 * SCALE for bl in bullet_blocks)

    total_h = dots_h + kicker_h + title_h + sub_h + bul_h
    y = max(90 * SCALE, (SH - total_h) // 2)

    # 4 Google Cloud dots
    dot_r = 9 * SCALE
    for i, col in enumerate(COLORS):
        cx = margin_x + i * (30 * SCALE) + dot_r
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
        y += 24 * SCALE
        for line in sub_lines:
            d.text((margin_x, y), line, font=f_sub, fill=INK_SUB)
            y += sub_line_h

    # Bullets
    if bullet_blocks:
        y += 36 * SCALE
        b_rad = 8 * SCALE
        for i, bl in enumerate(bullet_blocks):
            col = COLORS[i % 4]
            cy = y + int(bul_line_h * 0.48)
            cx = margin_x + b_rad
            d.ellipse([cx - b_rad, cy - b_rad, cx + b_rad, cy + b_rad], fill=col)
            for line in bl:
                d.text((margin_x + 38 * SCALE, y), line, font=f_bullet, fill=INK_BODY)
                y += bul_line_h
            y += 14 * SCALE

    return img.resize((W, H), Image.LANCZOS)


def render_cards(cards: list[dict], out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    """Render each distinct card to out_dir/<hash>.png; returns {key: path}. Key = card_key(c)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, pathlib.Path] = {}
    for c in cards:
        k = card_key(c)
        out = out_dir / f"{k}.png"
        paths[k] = out
        if not out.exists():
            render_card_image(c).save(out, format="PNG")
    return paths


def card_key(c: dict) -> str:
    sig = json.dumps({k: c.get(k) for k in ("title", "kicker", "sub", "bullets")}, sort_keys=True)
    return hashlib.sha1(sig.encode()).hexdigest()[:12]
