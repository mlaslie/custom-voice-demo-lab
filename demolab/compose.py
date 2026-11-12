"""Compose the final 1080p MP4 from stills (cards, slides), AGY browser step sequences, and narration clips.

Supports three visual piece types:
  - `Still`: 1080p title card or slide image timed to its narration clip(s).
  - `StepSequence`: live website walkthrough frames captured from Antigravity's built-in browser (`before`,
    `during`, `result`), with spotlight callouts (`HighlightBox`), smooth zoom-ins (`zoom_to`), fast-forward
    banners, and sample-accurate alignment for `narration` + `after_narration`.
  - `Recorded`: event-timeline segment composer kept for timing unit-test and raw-stream compatibility.
"""
from __future__ import annotations

import bisect
import math
import pathlib
import subprocess
import wave
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from .models import HighlightBox, StepFrame

W, H = 1920, 1080
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
SLIDE_XFADE = 0.25

FONTS_B = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONTS_R = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(paths: list[str], size: int):
    for f in paths:
        if pathlib.Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default(size)


@dataclass
class Still:
    image: pathlib.Path
    clips: list[tuple[pathlib.Path, float]] = field(default_factory=list)   # narration wavs, in order


@dataclass
class StepSequence:
    seg_id: str
    frames: list[StepFrame]
    frames_dir: pathlib.Path
    narration_clip: tuple[pathlib.Path, float] | None = None
    after_clip: tuple[pathlib.Path, float] | None = None


@dataclass
class Recorded:
    seg_id: str


# ---- timing helpers -----------------------------------------------------------------------------

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


# ---- visual overlays (fast-forward banner, spotlight highlight, smooth zoom) --------------------

def banner(img: Image.Image, elapsed: float, what: str, speed: float) -> Image.Image:
    im = img.convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    iw, ih = im.size
    d.rectangle([0, 0, iw, ih], fill=(0, 0, 0, 70))
    f1, f2, f3 = _font(FONTS_B, 44), _font(FONTS_R, 26), _font(FONTS_B, 26)
    title, spd = f"Fast-forwarding  ·  {int(elapsed)} s", f"×{speed:.0f}"
    tw = d.textlength("Fast-forwarding  ·  9999 s", font=f1)   # fixed width: the box doesn't jitter
    sw = d.textlength(spd, font=f3)
    bw = int(130 + tw + 30 + sw + 40)
    while what and d.textlength(what, font=f2) > bw - 130 - 40:
        what = what[:-2].rstrip() + "…"
    bh = 150
    x, y = (iw - bw) // 2, ih - bh - 70
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=28, fill=(16, 32, 64, 225), outline=(138, 180, 248, 255), width=3)
    gx, gy = x + 40, y + 45
    for k in (0, 34):
        d.polygon([(gx + k, gy), (gx + k + 32, gy + 30), (gx + k, gy + 60)], fill=(138, 180, 248, 255))
    d.text((x + 130, y + 26), title, font=f1, fill=(255, 255, 255, 255))
    d.text((x + 130, y + 88), what, font=f2, fill=(210, 227, 252, 255))
    d.text((x + bw - 40 - sw, y + 38), spd, font=f3, fill=(251, 188, 4, 255))
    return Image.alpha_composite(im, ov).convert("RGB")


def apply_highlight(img: Image.Image, box: HighlightBox) -> Image.Image:
    """Draw a spotlight callout over a browser screenshot region."""
    base = img.convert("RGBA")
    iw, ih = base.size
    nx, ny, nw, nh = box.normalized(iw, ih)
    pad = 10
    x0 = max(4, int(nx * iw) - pad)
    y0 = max(4, int(ny * ih) - pad)
    x1 = min(iw - 4, int((nx + nw) * iw) + pad)
    y1 = min(ih - 4, int((ny + nh) * ih) + pad)

    dim = Image.new("RGBA", (iw, ih), (16, 24, 40, 82))
    dd = ImageDraw.Draw(dim)
    dd.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(0, 0, 0, 0))
    comp = Image.alpha_composite(base, dim)

    ov = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], radius=16, outline=(251, 188, 4, 150), width=6)
    od.rounded_rectangle([x0, y0, x1, y1], radius=14, outline=(26, 115, 232, 255), width=4)

    if box.label.strip():
        f_lbl = _font(FONTS_B, 24)
        label = box.label.strip()
        tw = int(od.textlength(label, font=f_lbl))
        pw, ph = tw + 32, 42
        px = min(max(12, x0), iw - pw - 12)
        py = y0 - ph - 10 if y0 >= ph + 18 else min(ih - ph - 12, y1 + 10)
        od.rounded_rectangle([px, py, px + pw, py + ph], radius=21, fill=(26, 115, 232, 245))
        od.text((px + 16, py + 8), label, font=f_lbl, fill=(255, 255, 255, 255))

    return Image.alpha_composite(comp, ov).convert("RGB")


def _zoom_crop(img: Image.Image, box: HighlightBox, progress: float) -> Image.Image:
    """Smooth cosine-eased pan/zoom from full 1080p frame toward `box` (clamped to <=1.65x zoom)."""
    iw, ih = img.size
    nx, ny, nw, nh = box.normalized(iw, ih)
    cx = (nx + nw / 2.0) * iw
    cy = (ny + nh / 2.0) * ih
    # Leave generous breathing room around target box and preserve 16:9 aspect
    target_scale = max(nw * 1.45, nh * 1.45, 1.0 / 1.65)
    target_scale = min(1.0, target_scale)
    ease = 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, progress)))
    cur_scale = 1.0 + (target_scale - 1.0) * ease
    cw, ch = iw * cur_scale, ih * cur_scale
    left = max(0.0, min(iw - cw, cx - cw / 2.0))
    top = max(0.0, min(ih - ch, cy - ch / 2.0))
    return img.crop((int(left), int(top), int(left + cw), int(top + ch))).resize((W, H), Image.LANCZOS)


def _wav_len(p: pathlib.Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


# ---- compose ------------------------------------------------------------------------------------

def compose(
    pieces: list[Still | StepSequence | Recorded],
    events: list[dict],
    frames: list[tuple[float, str]],
    frames_dir: pathlib.Path,
    work: pathlib.Path,
    out: pathlib.Path,
) -> float:
    """Returns the rendered MP4 video length in seconds."""
    work.mkdir(parents=True, exist_ok=True)
    fts = [f[0] for f in frames]
    entries: list[tuple[pathlib.Path, float]] = []
    placed: list[tuple[pathlib.Path, float]] = []
    T = 0.0
    nblend = 0
    nstep = 0

    jpgs: dict[pathlib.Path, pathlib.Path] = {}

    def to_jpg(f: pathlib.Path) -> pathlib.Path:
        if f.suffix.lower() in (".jpg", ".jpeg") and f.parent == work:
            return f
        if f not in jpgs:
            jpgs[f] = work / f"still{len(jpgs):04d}.jpg"
            Image.open(f).convert("RGB").resize((W, H), Image.LANCZOS).save(jpgs[f], quality=95)
        return jpgs[f]

    def add(f: pathlib.Path, d: float):
        nonlocal T
        if d <= 0:
            return
        jf = to_jpg(f)
        if entries and entries[-1][0] == jf:
            entries[-1] = (jf, entries[-1][1] + d)
        else:
            entries.append((jf, d))
        T += d

    def raw_frame(t):
        i = max(0, bisect.bisect_right(fts, t) - 1)
        return frames_dir / frames[i][1]

    def crossfade(a: pathlib.Path, b: pathlib.Path, dur: float = XFADE):
        nonlocal nblend
        ja, jb = to_jpg(a), to_jpg(b)
        if ja == jb:
            return
        n = max(2, round(dur * FF_FPS))
        ia, ib = Image.open(ja).convert("RGB"), Image.open(jb).convert("RGB")
        for k in range(1, n):
            g = work / f"x{nblend:05d}_{k}.jpg"
            Image.blend(ia, ib.resize(ia.size), k / n).save(g, quality=92)
            add(g, dur / n)
        nblend += 1

    def prepare_step_base(sf: StepFrame, sdir: pathlib.Path) -> pathlib.Path:
        nonlocal nstep
        raw_p = sdir / sf.file
        im = Image.open(raw_p).convert("RGB").resize((W, H), Image.LANCZOS)
        if sf.highlight:
            im = apply_highlight(im, sf.highlight)
        nstep += 1
        out_p = work / f"stepbase{nstep:05d}.jpg"
        im.save(out_p, quality=95)
        return out_p

    def emit_step_frames(
        sfs: list[StepFrame],
        sdir: pathlib.Path,
        total_dur: float,
        prev: pathlib.Path | None,
        lead_xfade: float = XFADE,
    ) -> pathlib.Path | None:
        nonlocal nstep
        if not sfs:
            return prev
        bases = [prepare_step_base(sf, sdir) for sf in sfs]
        if prev is not None:
            crossfade(prev, bases[0], lead_xfade)

        inner_xfades = max(0, len(sfs) - 1) * 0.24
        usable = max(0.6 * len(sfs), total_dur - inner_xfades)
        per = usable / len(sfs)

        last_emitted = bases[0]
        for idx, (sf, base_jpg) in enumerate(zip(sfs, bases)):
            if idx > 0:
                crossfade(last_emitted, base_jpg, 0.24)
            dur = ff_out_len(sf.ff_elapsed or 30.0) if (sf.ff_what and total_dur <= 2.0) else per
            if sf.ff_what:
                raw_wait = max(dur * 2.0, sf.ff_elapsed or 30.0)
                n = max(2, round(dur * FF_FPS))
                step_dt = dur / n
                speed = raw_wait / dur
                src_im = Image.open(base_jpg).convert("RGB")
                for k in range(n):
                    nstep += 1
                    g = work / f"stepff{nstep:06d}.jpg"
                    im_k = _zoom_crop(src_im, sf.zoom_to, k / max(1, n - 1)) if sf.zoom_to else src_im
                    banner(im_k, (k + 0.5) * step_dt * speed, sf.ff_what, speed).save(g, quality=92)
                    add(g, step_dt)
                    last_emitted = g
            elif sf.zoom_to:
                n = max(2, round(dur * FF_FPS))
                step_dt = dur / n
                src_im = Image.open(base_jpg).convert("RGB")
                for k in range(n):
                    nstep += 1
                    g = work / f"stepzm{nstep:06d}.jpg"
                    _zoom_crop(src_im, sf.zoom_to, min(1.0, (k / max(1, n - 1)) * 1.25)).save(g, quality=93)
                    add(g, step_dt)
                    last_emitted = g
            else:
                add(base_jpg, dur)
                last_emitted = base_jpg
        return last_emitted

    prev_kind, prev_last = None, None
    for pc in pieces:
        if isinstance(pc, Still):
            first = pc.image
            if prev_last is not None:
                crossfade(prev_last, first, XFADE if prev_kind == "rec" else SLIDE_XFADE)
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

        if isinstance(pc, StepSequence):
            if not pc.frames:
                continue
            if pc.after_clip:
                res_frames = [f for f in pc.frames if f.phase == "result"]
                act_frames = [f for f in pc.frames if f.phase != "result"]
                if not res_frames:
                    if len(pc.frames) >= 2:
                        act_frames, res_frames = pc.frames[:-1], [pc.frames[-1]]
                    else:
                        act_frames, res_frames = pc.frames, pc.frames
                if not act_frames:
                    act_frames = [res_frames[0]]
            else:
                act_frames, res_frames = pc.frames, []

            # Phase 1: action frames + primary narration
            # First crossfade from previous piece so T reflects exact post-crossfade start
            first_act_preview = prepare_step_base(act_frames[0], pc.frames_dir)
            if prev_last is not None:
                crossfade(prev_last, first_act_preview, XFADE)
            if pc.narration_clip:
                wav1, _ = pc.narration_clip
                dur1 = _wav_len(wav1)
                placed.append((wav1, T + 0.35))
                act_dur = 0.35 + dur1 + (0.45 if res_frames else TAIL)
            else:
                act_dur = 1.6 if res_frames else STILL_READ
            cur_last = emit_step_frames(act_frames, pc.frames_dir, act_dur, prev=None)

            # Phase 2: result frames + after_narration (if present)
            if pc.after_clip and res_frames:
                first_res_preview = prepare_step_base(res_frames[0], pc.frames_dir)
                if cur_last is not None:
                    crossfade(cur_last, first_res_preview, 0.28)
                wav2, _ = pc.after_clip
                dur2 = _wav_len(wav2)
                placed.append((wav2, T + 0.25))
                res_dur = 0.25 + dur2 + TAIL
                cur_last = emit_step_frames(res_frames, pc.frames_dir, res_dur, prev=None)

            prev_kind, prev_last = "rec", cur_last
            continue

        # Legacy Recorded event-stream piece
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
        raise ValueError("Nothing to render: the script has no renderable segments.")
    lst = work / "concat.txt"
    lst.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{p}'\nduration {d:.4f}\n" for p, d in entries)
        + f"file '{entries[-1][0]}'\n"
    )

    pcm = bytearray(int(T * SR + SR) * 2)
    for wav, t in placed:
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
        off = int(t * SR) * 2
        pcm[off:off + len(data)] = data[:max(0, len(pcm) - off)]
    narr = work / "narration.wav"
    with wave.open(str(narr), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(pcm))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(lst),
            "-i", str(narr),
            "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{T:.2f}", str(tmp),
        ],
        check=True,
    )
    tmp.replace(out)   # no half-written MP4 under the final name if ffmpeg fails
    return T
