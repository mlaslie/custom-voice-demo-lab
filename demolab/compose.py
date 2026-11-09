"""Compose the final MP4 from stills (cards, slides), the step recording and narration clips.

Within a recorded step, narrated stretches play at 1x, silent stretches are tightened to a live
presenter's pace, and fast-forward windows (ff_start..ff_end) shrink to a few seconds behind a banner.
Pieces of different kinds are joined with a short crossfade.
"""
from __future__ import annotations

import bisect
import pathlib
import subprocess
import wave
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

FPS = 30
FF_FPS = 15
SR = 24000
GAP_KEEP = 0.9       # a silent stretch keeps this much at 1x ...
GAP_REST = 0.15      # ... and plays the rest sped up (8 s of silence -> ~2 s)
GAP_MAX = 3.5        # never longer than this
STILL_READ = 4.0     # an un-narrated card stays on screen this long
LEAD = 0.5           # still pieces: silence before narration starts
TAIL = 0.9           # still pieces: silence after narration ends
XFADE = 0.4

FONTS_B = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONTS_R = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font(paths: list[str], size: int):
    for f in paths:
        if pathlib.Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


@dataclass
class Still:
    image: pathlib.Path
    clips: list[tuple[pathlib.Path, float]] = field(default_factory=list)   # narration wavs, in order


@dataclass
class Recorded:
    seg_id: str


# ---- timing (ported from the approved narrated-demo-video compose) -------------------------------

def gap_out_len(raw: float) -> float:
    if raw <= GAP_KEEP:
        return raw
    return min(GAP_KEEP + (raw - GAP_KEEP) * GAP_REST, GAP_MAX)


def ff_out_len(raw: float) -> float:
    return max(3.0, min(8.0, 3.0 + raw / 40.0))


def build_segments(events, t0, t1):
    """[(raw_a, raw_b, out_len, label)] covering t0..t1; label None = 1x."""
    segs, cur, open_ff = [], t0, None
    for e in events:
        if e["kind"] == "ff_start":
            open_ff = e
        elif e["kind"] == "ff_end" and open_ff:
            a, b = max(open_ff["t"], cur), e["t"]
            if b - a <= ff_out_len(b - a):   # too short to be worth fast-forwarding: play it at 1x
                open_ff = None
                continue
            if a > cur:
                segs.append((cur, a, a - cur, None))
            if b > a:
                segs.append((a, b, ff_out_len(b - a), open_ff.get("what", "")))
            cur, open_ff = max(cur, b), None
    segs.append((cur, t1, t1 - cur, None))
    return [s for s in segs if s[1] > s[0]]


def tighten(segs, events):
    says = sorted((e["t"], e["t"] + e["dur"]) for e in events if e["kind"] == "say")
    out = []
    for a, b, ol, lab in segs:
        if lab is not None:
            out.append((a, b, ol, lab))
            continue
        cur = a
        for sa, sb in says + [(b, b)]:
            sa, sb = max(sa, a), min(sb, b)
            if sb < cur or sa > b:
                continue
            if sa > cur:
                out.append((cur, sa, gap_out_len(sa - cur), None))
            if sb > max(sa, cur):
                out.append((max(sa, cur), sb, sb - max(sa, cur), None))
            cur = max(cur, sb)
        if cur < b:
            out.append((cur, b, gap_out_len(b - cur), None))
    return [s for s in out if s[1] > s[0]]


def map_time(segs, t):
    out = 0.0
    for a, b, ol, lab in segs:
        if t <= b:
            return out + max(0.0, t - a) * (ol / (b - a))
        out += ol
    return out


def banner(img: Image.Image, elapsed: float, what: str, speed: float) -> Image.Image:
    im = img.convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    W, H = im.size
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 70))
    f1, f2, f3 = _font(FONTS_B, 44), _font(FONTS_R, 26), _font(FONTS_B, 26)
    title, spd = f"Fast-forwarding  ·  {int(elapsed)} s", f"×{speed:.0f}"
    tw = d.textlength("Fast-forwarding  ·  9999 s", font=f1)   # fixed width: the box doesn't jitter
    sw = d.textlength(spd, font=f3)
    bw = int(130 + tw + 30 + sw + 40)
    while what and d.textlength(what, font=f2) > bw - 130 - 40:
        what = what[:-2].rstrip() + "…"
    bh = 150
    x, y = (W - bw) // 2, H - bh - 70
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=28, fill=(16, 32, 64, 225), outline=(138, 180, 248, 255), width=3)
    gx, gy = x + 40, y + 45
    for k in (0, 34):
        d.polygon([(gx + k, gy), (gx + k + 32, gy + 30), (gx + k, gy + 60)], fill=(138, 180, 248, 255))
    d.text((x + 130, y + 26), title, font=f1, fill=(255, 255, 255, 255))
    d.text((x + 130, y + 88), what, font=f2, fill=(210, 227, 252, 255))
    d.text((x + bw - 40 - sw, y + 38), spd, font=f3, fill=(251, 188, 4, 255))
    return Image.alpha_composite(im, ov).convert("RGB")


def _wav_len(p: pathlib.Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# ---- compose ------------------------------------------------------------------------------------

def compose(pieces: list[Still | Recorded], events: list[dict], frames: list[tuple[float, str]],
            frames_dir: pathlib.Path, work: pathlib.Path, out: pathlib.Path) -> float:
    """Returns the video length in seconds."""
    work.mkdir(parents=True, exist_ok=True)
    fts = [f[0] for f in frames]
    entries: list[tuple[pathlib.Path, float]] = []
    placed: list[tuple[pathlib.Path, float]] = []
    T = 0.0
    nblend = 0

    jpgs: dict[pathlib.Path, pathlib.Path] = {}

    def add(f: pathlib.Path, d: float):
        nonlocal T
        if f.suffix.lower() != ".jpg":   # the concat demuxer needs one codec: stills become JPEGs too
            if f not in jpgs:
                jpgs[f] = work / f"still{len(jpgs):04d}.jpg"
                Image.open(f).convert("RGB").resize((1920, 1080)).save(jpgs[f], quality=95)
            f = jpgs[f]
        if entries and entries[-1][0] == f:
            entries[-1] = (f, entries[-1][1] + d)
        else:
            entries.append((f, d))
        T += d

    def raw_frame(t):
        i = max(0, bisect.bisect_right(fts, t) - 1)
        return frames_dir / frames[i][1]

    def crossfade(a: pathlib.Path, b: pathlib.Path):
        nonlocal nblend
        n = round(XFADE * FF_FPS)
        ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
        for k in range(1, n):
            g = work / f"x{nblend:05d}_{k}.jpg"
            Image.blend(ia, ib.resize(ia.size), k / n).save(g, quality=90)
            add(g, XFADE / n)
        nblend += 1

    prev_kind, prev_last = None, None
    for pc in pieces:
        if isinstance(pc, Still):
            first = pc.image
            if prev_last is not None and prev_kind == "rec":
                crossfade(prev_last, first)
            if not pc.clips:
                add(pc.image, STILL_READ)
            else:
                t = T + LEAD
                for wav, _ in pc.clips:
                    placed.append((wav, t))
                    t += _wav_len(wav) + 0.6
                add(pc.image, (t - T) - 0.6 + TAIL)
            prev_kind, prev_last = "still", pc.image
            continue

        win = [e for e in events if e.get("seg") == pc.seg_id and e["kind"] in ("seg_start", "seg_end")]
        if len(win) < 2:
            continue
        a, b = win[0]["t"], win[1]["t"]
        evs = [e for e in events if a <= e["t"] <= b]
        segs = tighten(build_segments(evs, a, b), evs)
        if prev_last is not None and prev_kind == "still":
            crossfade(prev_last, raw_frame(a + 0.05))
        T0 = T
        for e in evs:
            if e["kind"] == "say":
                placed.append((pathlib.Path(e["wav"]), T0 + map_time(segs, e["t"])))
        for sa, sb, ol, lab in segs:
            n = max(1, round(ol * (FF_FPS if lab is not None else FPS)))
            step, speed = ol / n, (sb - sa) / ol
            for k in range(n):
                raw = sa + (k + 0.5) * step * speed
                f = raw_frame(raw)
                if lab is not None:
                    g = work / f"ff{len(entries):06d}.jpg"
                    banner(Image.open(f), raw - sa, lab, speed).save(g, quality=90)
                    f = g
                add(f, step)
        prev_kind, prev_last = "rec", raw_frame(b)

    if not entries:
        raise ValueError("Nothing to render: the script has no segments.")
    lst = work / "concat.txt"
    lst.write_text("ffconcat version 1.0\n" + "".join(f"file '{p}'\nduration {d:.4f}\n" for p, d in entries)
                   + f"file '{entries[-1][0]}'\n")

    pcm = bytearray(int(T * SR + SR) * 2)
    for wav, t in placed:
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
        off = int(t * SR) * 2
        pcm[off:off + len(data)] = data[:max(0, len(pcm) - off)]
    narr = work / "narration.wav"
    with wave.open(str(narr), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(bytes(pcm))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(narr), "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{T:.2f}", str(tmp)],
                   check=True)
    tmp.replace(out)   # no half-written MP4 under the final name if ffmpeg fails
    return T
