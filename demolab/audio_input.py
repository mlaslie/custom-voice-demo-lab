"""Local system microphone enumeration, live native PCM capture, and 48-band voice telemetry."""
from __future__ import annotations

import array
import atexit
import base64
import cmath
from dataclasses import dataclass, field
import io
import math
import re
import subprocess
import sys
import threading
import time
import uuid
import wave

from . import config

SR = 24000
BANDS = 48
FFT_N = 512
CHUNK_SAMPLES = 1024
CHUNK_BYTES = CHUNK_SAMPLES * 2
F_MIN = 85.0
F_MAX = 4800.0

_HANN = [0.5 * (1.0 - math.cos(2.0 * math.pi * n / (FFT_N - 1))) for n in range(FFT_N)]
_BIT_REV = [int(f"{i:09b}"[::-1], 2) for i in range(FFT_N)]


def _build_twiddles() -> list[tuple[int, int, list[complex]]]:
    rows: list[tuple[int, int, list[complex]]] = []
    step = 2
    while step <= FFT_N:
        half = step // 2
        w_step = cmath.exp(-2j * math.pi / step)
        w = 1 + 0j
        tw: list[complex] = []
        for _ in range(half):
            tw.append(w)
            w *= w_step
        rows.append((step, half, tw))
        step *= 2
    return rows


def _build_band_bins() -> list[tuple[int, int]]:
    hz_per_bin = SR / FFT_N
    max_bin = (FFT_N // 2) - 1
    out: list[tuple[int, int]] = []
    for i in range(BANDS):
        lo_hz = F_MIN * ((F_MAX / F_MIN) ** (i / BANDS))
        hi_hz = F_MIN * ((F_MAX / F_MIN) ** ((i + 1) / BANDS))
        b0 = max(1, min(max_bin, int(math.floor(lo_hz / hz_per_bin))))
        b1 = max(b0, min(max_bin, int(math.ceil(hi_hz / hz_per_bin))))
        out.append((b0, b1))
    return out


_TWIDDLES = _build_twiddles()
_BAND_BINS = _build_band_bins()
_LOCK = threading.RLock()


def _fft512_voice_bands(samples_f: list[float], energy: float = 0.0) -> list[float]:
    """Return 48 normalized voice-band magnitudes across 85 Hz - 4,800 Hz from 512 mono samples."""
    if len(samples_f) < FFT_N:
        return [0.0] * BANDS
    tail = samples_f[-FFT_N:]
    buf = [complex(tail[idx] * _HANN[idx], 0.0) for idx in _BIT_REV]
    for step, half, tw in _TWIDDLES:
        for k in range(0, FFT_N, step):
            for j in range(half):
                t = tw[j] * buf[k + j + half]
                u = buf[k + j]
                buf[k + j] = u + t
                buf[k + j + half] = u - t
    scale = FFT_N * 0.5
    mags = [abs(buf[b]) / scale for b in range(FFT_N // 2)]

    out: list[float] = []
    for i, (b0, b1) in enumerate(_BAND_BINS):
        bin_max = max(mags[b0 : b1 + 1])
        band_db = max(-65.0, 20.0 * math.log10(max(1e-5, bin_max)))
        spec = max(0.0, min(1.0, (band_db + 58.0) / 42.0))
        ripple = 0.72 + 0.28 * math.sin(i * 0.45)
        out.append(round(min(1.0, max(spec, energy * ripple * 0.45)), 4))
    return out


def _pick_recommended_id(devices: list[dict]) -> str:
    if not devices:
        return ""
    for d in devices:
        low = d["name"].lower()
        if "iphone" not in low and "macbook" not in low and "monitor" not in low:
            return d["id"]
    for d in devices:
        if "iphone" not in d["name"].lower():
            return d["id"]
    return devices[0]["id"]


def list_input_devices() -> dict:
    """List local OS audio input devices and highlight the recommended microphone."""
    if config.fake_gemini():
        devices = [
            {"id": "fake:0", "name": "External Studio USB Mic", "backend": "fake", "recommended": True},
            {"id": "fake:1", "name": "Built-in Laptop Mic", "backend": "fake", "recommended": False},
        ]
        return {"devices": devices, "recommended_id": "fake:0"}

    devices: list[dict] = []
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            text = (proc.stderr or "") + "\n" + (proc.stdout or "")
            in_audio = False
            for line in text.splitlines():
                if "AVFoundation audio devices:" in line:
                    in_audio = True
                    continue
                if not in_audio:
                    continue
                if "[in#" in line or line.startswith("Error opening"):
                    break
                m = re.search(r"\[(\d+)\]\s+(.+)$", line)
                if m:
                    idx, name = m.group(1), m.group(2).strip()
                    devices.append({"id": f"avf:{idx}", "name": name, "backend": "avfoundation", "recommended": False})
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            text = (proc.stderr or "") + "\n" + (proc.stdout or "")
            for line in text.splitlines():
                if "(audio)" not in line:
                    continue
                m = re.search(r'"([^"]+)"\s+\(audio\)', line)
                if m:
                    name = m.group(1).strip()
                    devices.append({"id": f"dshow:{name}", "name": name, "backend": "dshow", "recommended": False})
        except Exception:
            pass
    else:
        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            for line in (proc.stdout or "").splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and not parts[1].endswith(".monitor"):
                    name = parts[1].strip()
                    devices.append({"id": f"pulse:{name}", "name": name, "backend": "pulse", "recommended": False})
        except Exception:
            pass
        if not devices:
            devices.append({"id": "pulse:default", "name": "Default System Microphone", "backend": "pulse", "recommended": False})

    rec_id = _pick_recommended_id(devices)
    for d in devices:
        d["recommended"] = d["id"] == rec_id
    return {"devices": devices, "recommended_id": rec_id}


def _ffmpeg_input_args(device_id: str) -> list[str]:
    if device_id.startswith("avf:"):
        idx = device_id.split(":", 1)[1]
        return ["-f", "avfoundation", "-i", f":{idx}"]
    if device_id.startswith("dshow:"):
        name = device_id.split(":", 1)[1]
        return ["-f", "dshow", "-i", f"audio={name}"]
    if device_id.startswith("pulse:"):
        src = device_id.split(":", 1)[1]
        return ["-f", "pulse", "-i", src]
    raise ValueError(f"Unsupported audio device id: {device_id}")


@dataclass
class _CaptureSession:
    session_id: str
    device_id: str
    device_name: str
    record: bool
    max_bytes: int
    proc: subprocess.Popen[bytes] | None = None
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    started_at: float = field(default_factory=time.monotonic)
    active: bool = True
    elapsed: float = 0.0
    db: float = -65.0
    peak_db: float = -65.0
    energy: float = 0.0
    bands: list[float] = field(default_factory=lambda: [0.0] * BANDS)
    nonzero_seen: bool = False
    digital_silence: bool = False
    error: str = ""
    pcm_buf: bytearray = field(default_factory=bytearray)

    def snapshot(self) -> dict:
        return {
            "active": self.active,
            "recording": self.record,
            "session_id": self.session_id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "elapsed": round(self.elapsed, 2),
            "db": round(self.db, 1),
            "energy": round(self.energy, 4),
            "bands": list(self.bands),
            "digital_silence": self.digital_silence,
            "error": self.error,
        }


_SESSION: _CaptureSession | None = None


def _process_pcm_chunk(sess: _CaptureSession, raw: bytes) -> None:
    even_len = len(raw) - (len(raw) % 2)
    if even_len <= 0:
        return
    pcm = array.array("h")
    pcm.frombytes(raw[:even_len])
    samples_f = [s / 32768.0 for s in pcm]
    if not sess.nonzero_seen and any(s != 0 for s in pcm):
        sess.nonzero_seen = True

    sq_sum = 0.0
    peak = 0.0
    for val in samples_f:
        sq_sum += val * val
        av = -val if val < 0.0 else val
        if av > peak:
            peak = av
    rms = math.sqrt(sq_sum / max(1, len(samples_f)))
    level = max(rms * 1.45, peak * 0.48)
    db = max(-65.0, min(0.0, 20.0 * math.log10(max(1e-5, level))))
    energy = pow(max(0.0, min(1.0, (db + 56.0) / 42.0)), 0.8)
    bands = _fft512_voice_bands(samples_f, energy=energy)
    elapsed = time.monotonic() - sess.started_at

    with _LOCK:
        sess.elapsed = elapsed
        sess.db = db
        if db > sess.peak_db:
            sess.peak_db = db
        sess.energy = energy
        sess.bands = bands
        sess.digital_silence = elapsed > 1.2 and not sess.nonzero_seen
        if sess.record and len(sess.pcm_buf) < sess.max_bytes:
            take = min(even_len, sess.max_bytes - len(sess.pcm_buf))
            sess.pcm_buf.extend(raw[:take])


def _read_ffmpeg_loop(sess: _CaptureSession) -> None:
    proc = sess.proc
    assert proc is not None and proc.stdout is not None
    try:
        while not sess.stop_event.is_set():
            raw = proc.stdout.read(CHUNK_BYTES)
            if not raw:
                break
            _process_pcm_chunk(sess, raw)
    except Exception as exc:
        with _LOCK:
            if not sess.stop_event.is_set():
                sess.error = str(exc)
    finally:
        stderr_msg = ""
        if proc.stderr is not None and not sess.stop_event.is_set():
            try:
                stderr_msg = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception:
                stderr_msg = ""
        with _LOCK:
            if not sess.stop_event.is_set() and proc.poll() not in (None, 0) and not sess.error:
                sess.error = stderr_msg or f"ffmpeg exited with code {proc.returncode}"
            sess.active = False


def _read_fake_loop(sess: _CaptureSession) -> None:
    phase = 0.0
    step_s = CHUNK_SAMPLES / SR
    while not sess.stop_event.is_set():
        t0 = time.monotonic()
        pcm = array.array("h")
        env = 0.25 + 0.35 * (0.5 + 0.5 * math.sin(phase * 3.1))
        for i in range(CHUNK_SAMPLES):
            t = phase + (i / SR)
            val = env * (0.62 * math.sin(2.0 * math.pi * 220.0 * t) + 0.38 * math.sin(2.0 * math.pi * 660.0 * t))
            pcm.append(max(-32767, min(32767, int(val * 32767))))
        phase += step_s
        _process_pcm_chunk(sess, pcm.tobytes())
        spent = time.monotonic() - t0
        time.sleep(max(0.005, step_s - spent))
    with _LOCK:
        sess.active = False


def _build_wav_b64(pcm_bytes: bytes) -> tuple[str, float]:
    if not pcm_bytes:
        return "", 0.0
    even_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
    pcm = pcm_bytes[:even_len]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm)
    seconds = len(pcm) / (SR * 2)
    return base64.b64encode(buf.getvalue()).decode("ascii"), round(seconds, 2)


def start_capture(device_id: str = "", record: bool = True, max_seconds: float = 90.0) -> dict:
    """Start live microphone capture (and optional 24 kHz WAV buffering) on a local input device."""
    stop_capture()

    info = list_input_devices()
    devices = info["devices"]
    chosen_id = (device_id or "").strip() or info.get("recommended_id") or (devices[0]["id"] if devices else "")
    if not chosen_id:
        raise ValueError("No local audio input devices found.")
    matched = next((d for d in devices if d["id"] == chosen_id), None)
    device_name = matched["name"] if matched else chosen_id

    sess = _CaptureSession(
        session_id=uuid.uuid4().hex[:10],
        device_id=chosen_id,
        device_name=device_name,
        record=record,
        max_bytes=int(max(1.0, max_seconds) * SR) * 2,
    )

    if config.fake_gemini() or chosen_id.startswith("fake:"):
        thread = threading.Thread(target=_read_fake_loop, args=(sess,), daemon=True)
        sess.thread = thread
        with _LOCK:
            global _SESSION
            _SESSION = sess
        thread.start()
        return sess.snapshot()

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *_ffmpeg_input_args(chosen_id),
        "-ac",
        "1",
        "-ar",
        str(SR),
        "-f",
        "s16le",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sess.proc = proc
    thread = threading.Thread(target=_read_ffmpeg_loop, args=(sess,), daemon=True)
    sess.thread = thread
    with _LOCK:
        _SESSION = sess
    thread.start()
    return sess.snapshot()


def get_telemetry() -> dict:
    """Return latest 48-band level & dBFS telemetry for the active capture session."""
    with _LOCK:
        if _SESSION is None:
            return {
                "active": False,
                "recording": False,
                "session_id": "",
                "device_id": "",
                "device_name": "",
                "elapsed": 0.0,
                "db": -65.0,
                "energy": 0.0,
                "bands": [0.0] * BANDS,
                "digital_silence": False,
                "error": "",
            }
        return _SESSION.snapshot()


def stop_capture() -> dict:
    """Stop active capture session and return recorded 24 kHz mono WAV base64 when recording=True."""
    global _SESSION
    with _LOCK:
        sess = _SESSION
        if sess is None:
            return {
                "ok": True,
                "seconds": 0.0,
                "audio_b64": "",
                "peak_db": -65.0,
                "digital_silence": False,
                "device_name": "",
                "error": "",
            }
        sess.stop_event.set()
        proc = sess.proc
        thread = sess.thread

    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)

    with _LOCK:
        audio_b64, seconds = _build_wav_b64(bytes(sess.pcm_buf)) if sess.record else ("", 0.0)
        res = {
            "ok": not bool(sess.error),
            "seconds": seconds,
            "audio_b64": audio_b64,
            "peak_db": round(sess.peak_db, 1),
            "digital_silence": sess.elapsed > 1.2 and not sess.nonzero_seen,
            "device_name": sess.device_name,
            "error": sess.error,
        }
        _SESSION = None
        return res


atexit.register(stop_capture)
