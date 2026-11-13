import { Mic, MicOff, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const BANDS = 48;
const CANVAS_SIZE = 208;
const LENS_R = 80;
const BEZEL_OUTER_R = LENS_R + 16;

export interface RemoteMicTelemetry {
  active: boolean;
  db: number;
  energy: number;
  bands: number[];
  deviceName?: string;
  digitalSilence?: boolean;
  error?: string;
}

export interface HalVoiceMeterProps {
  /** Live native-backend telemetry streamed while recording or testing a local input device. */
  telemetry?: RemoteMicTelemetry | null;
  /** True while actively recording audio from the microphone. */
  recording?: boolean;
  /** True while running a live microphone check without recording. */
  testingMic?: boolean;
  /** Handler wired to the local backend mic test button when running inside Voice Lab. */
  onToggleTestMic?: () => void;
  /** Optional external Web Audio AnalyserNode fallback when rendered without backend telemetry. */
  analyser?: AnalyserNode | null;
}

export interface MicAnalyserTap {
  audioCtx: AudioContext;
  source: MediaStreamAudioSourceNode;
  analyser: AnalyserNode;
  silentGain: GainNode;
  dispose: () => void;
}

/**
 * Connect a live microphone MediaStream into an AnalyserNode routed through a muted GainNode
 * to `audioCtx.destination`, keeping Chromium's WebAudio graph actively pulling frames without
 * acoustic feedback or premature `MediaStreamAudioSourceNode` garbage collection.
 */
export async function attachMicAnalyser(ac: AudioContext, stream: MediaStream): Promise<MicAnalyserTap> {
  if (ac.state !== "running") {
    await ac.resume().catch(() => {});
  }
  const source = ac.createMediaStreamSource(stream);
  const analyser = ac.createAnalyser();
  analyser.fftSize = 1024;
  analyser.minDecibels = -85;
  analyser.maxDecibels = -18;
  analyser.smoothingTimeConstant = 0.6;

  const silentGain = ac.createGain();
  silentGain.gain.value = 0;

  source.connect(analyser);
  analyser.connect(silentGain);
  silentGain.connect(ac.destination);

  const dispose = () => {
    try {
      source.disconnect();
    } catch {
      /* already disconnected */
    }
    try {
      analyser.disconnect();
    } catch {
      /* already disconnected */
    }
    try {
      silentGain.disconnect();
    } catch {
      /* already disconnected */
    }
    ac.close().catch(() => {});
  };

  return { audioCtx: ac, source, analyser, silentGain, dispose };
}

/**
 * Encode any browser-recorded audio Blob into 24 kHz 16-bit mono PCM RIFF WAV base64
 * for Gemini `/v1beta/voices` custom voice creation.
 */
export async function blobToMonoWav24kBase64(blob: Blob): Promise<string> {
  const arr = await blob.arrayBuffer();
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const decodeCtx = new AudioCtx();
  let decoded: AudioBuffer;
  try {
    decoded = await decodeCtx.decodeAudioData(arr.slice(0));
  } finally {
    await decodeCtx.close().catch(() => {});
  }

  const targetSr = 24000;
  const frameCount = Math.max(1, Math.ceil(decoded.duration * targetSr));
  const offline = new OfflineAudioContext(1, frameCount, targetSr);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start(0);
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);

  const dataLen = samples.length * 2;
  const wav = new ArrayBuffer(44 + dataLen);
  const view = new DataView(wav);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataLen, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, targetSr, true);
  view.setUint32(28, targetSr * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataLen, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  const bytes = new Uint8Array(wav);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/**
 * Standalone circular HAL 9000 voice meter on a transparent HiDPI canvas (no stage background box),
 * matching the brushed silver/grey outer ring + convex glass lens + swirling crimson/amber plasma core.
 */
export function HalVoiceMeter({
  telemetry = null,
  recording = false,
  testingMic = false,
  onToggleTestMic,
  analyser = null,
}: HalVoiceMeterProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bandValuesRef = useRef(new Float32Array(BANDS));
  const phaseRef = useRef(0);
  const energyRef = useRef(0.14);
  const pausedRef = useRef(false);

  const [paused, setPaused] = useState(false);
  const [levelDb, setLevelDb] = useState("Standby");
  const [meterPct, setMeterPct] = useState(0);
  const [liveAnalyser, setLiveAnalyser] = useState<AnalyserNode | null>(null);
  const [micNote, setMicNote] = useState("");
  const localStreamRef = useRef<MediaStream | null>(null);
  const localTapRef = useRef<MicAnalyserTap | null>(null);

  const telemetryRef = useRef<RemoteMicTelemetry | null>(telemetry);
  const activeAnalyser = analyser ?? liveAnalyser;
  const activeAnalyserRef = useRef<AnalyserNode | null>(null);
  const freqBinsRef = useRef<Uint8Array | null>(null);
  const timeBufRef = useRef<Float32Array | null>(null);

  useEffect(() => {
    telemetryRef.current = telemetry;
    if (telemetry?.active || recording || testingMic) {
      setPaused(false);
    }
  }, [telemetry, recording, testingMic]);

  useEffect(() => {
    activeAnalyserRef.current = activeAnalyser;
    freqBinsRef.current = activeAnalyser
      ? new Uint8Array(activeAnalyser.frequencyBinCount)
      : null;
    timeBufRef.current = activeAnalyser
      ? new Float32Array(activeAnalyser.fftSize)
      : null;
    if (activeAnalyser) {
      setPaused(false);
    }
  }, [activeAnalyser]);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    return () => {
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
      localTapRef.current?.dispose();
    };
  }, []);

  const toggleLiveMic = async () => {
    if (liveAnalyser || localTapRef.current) {
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
      localTapRef.current?.dispose();
      localTapRef.current = null;
      setLiveAnalyser(null);
      setMicNote("");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicNote("Live microphone access is unavailable in this browser view.");
      return;
    }
    const AudioCtx =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ac = new AudioCtx();
    ac.resume().catch(() => {});
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const tap = await attachMicAnalyser(ac, stream);
      localStreamRef.current = stream;
      localTapRef.current = tap;
      setLiveAnalyser(tap.analyser);
      setMicNote("");
      setPaused(false);
    } catch {
      ac.close().catch(() => {});
      setMicNote("Microphone permission denied.");
    }
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = CANVAS_SIZE * dpr;
    canvas.height = CANVAS_SIZE * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    let rafId = 0;
    let lastTime = performance.now();
    let lastUiPush = 0;

    const sampleBands = (): { energy: number; dbLabel: string; pct: number } => {
      const bandValues = bandValuesRef.current;
      const ph = phaseRef.current;
      const remote = telemetryRef.current;

      if (remote && remote.active) {
        const targetEnergy = Math.max(0, Math.min(1, remote.energy));
        const prevEnergy = energyRef.current;
        const coeff = targetEnergy > prevEnergy ? 0.5 : 0.22;
        const smoothEnergy = prevEnergy + (targetEnergy - prevEnergy) * coeff;
        energyRef.current = smoothEnergy;

        const bandSmooth = reducedMotionQuery.matches ? 0.22 : 0.42;
        const srcBands = remote.bands || [];
        for (let i = 0; i < BANDS; i++) {
          const specNorm = Math.max(0, Math.min(1, srcBands[i] ?? 0));
          const ripple = 0.78 + 0.22 * Math.sin(ph * 4.4 + i * 0.46);
          const target = Math.min(1, Math.max(specNorm, smoothEnergy * ripple * 0.7));
          bandValues[i] += (target - bandValues[i]) * bandSmooth;
        }
        return {
          energy: smoothEnergy,
          dbLabel: remote.db <= -62 ? "-∞ dBFS" : `${remote.db.toFixed(1)} dBFS`,
          pct: Math.round(smoothEnergy * 100),
        };
      }

      const node = activeAnalyserRef.current;
      const freqBins = freqBinsRef.current;
      const timeBuf = timeBufRef.current;

      if (node && freqBins && timeBuf) {
        if (node.context.state === "suspended") {
          (node.context as AudioContext).resume().catch(() => {});
        }
        node.getFloatTimeDomainData(timeBuf);
        node.getByteFrequencyData(freqBins);

        let sqSum = 0;
        let peak = 0;
        for (let i = 0; i < timeBuf.length; i++) {
          const sample = timeBuf[i];
          sqSum += sample * sample;
          const abs = sample < 0 ? -sample : sample;
          if (abs > peak) peak = abs;
        }
        const rms = Math.sqrt(sqSum / timeBuf.length);
        const level = Math.max(rms * 1.35, peak * 0.45);
        const rawDb = 20 * Math.log10(Math.max(1e-4, level));
        const clampedDb = Math.max(-60, Math.min(0, rawDb));
        const shaped = Math.pow(Math.max(0, Math.min(1, (clampedDb + 52) / 38)), 0.82);

        const prevEnergy = energyRef.current;
        const coeff = shaped > prevEnergy ? 0.55 : 0.18;
        const smoothEnergy = prevEnergy + (shaped - prevEnergy) * coeff;
        energyRef.current = smoothEnergy;

        const sampleRate = node.context.sampleRate || 48000;
        const hzPerBin = sampleRate / node.fftSize;
        const maxBin = freqBins.length - 1;
        const fMin = 85;
        const fMax = 4800;
        const bandSmooth = reducedMotionQuery.matches ? 0.2 : 0.42;

        for (let i = 0; i < BANDS; i++) {
          const loHz = fMin * Math.pow(fMax / fMin, i / BANDS);
          const hiHz = fMin * Math.pow(fMax / fMin, (i + 1) / BANDS);
          const b0 = Math.max(1, Math.min(maxBin, Math.floor(loHz / hzPerBin)));
          const b1 = Math.max(b0, Math.min(maxBin, Math.ceil(hiHz / hzPerBin)));
          let binMax = 0;
          for (let b = b0; b <= b1; b++) {
            if (freqBins[b] > binMax) binMax = freqBins[b];
          }
          const specNorm = binMax / 255;
          const ripple = 0.72 + 0.28 * Math.sin(ph * 4.2 + i * 0.48);
          const target = Math.min(1, Math.max(specNorm * 1.15, smoothEnergy * ripple * 0.85));
          bandValues[i] += (target - bandValues[i]) * bandSmooth;
        }

        return {
          energy: smoothEnergy,
          dbLabel: clampedDb <= -58 ? "-∞ dBFS" : `${clampedDb.toFixed(1)} dBFS`,
          pct: Math.round(smoothEnergy * 100),
        };
      }

      const breath = 0.14 + 0.04 * Math.sin(ph * 1.5);
      energyRef.current += (breath - energyRef.current) * 0.14;
      for (let i = 0; i < BANDS; i++) {
        const idleRipple = 0.05 + 0.03 * Math.sin(ph * 1.3 + i * 0.35);
        bandValues[i] += (idleRipple - bandValues[i]) * 0.14;
      }
      return {
        energy: energyRef.current,
        dbLabel: "Standby",
        pct: 0,
      };
    };

    const drawHalEye = (cx: number, cy: number, energy: number, tPhase: number, isLight: boolean) => {
      const bandValues = bandValuesRef.current;

      // Machined brushed-silver/grey outer ring (strictly circular, no background box or outer bloom)
      const chromeGrad = ctx.createLinearGradient(
        cx - BEZEL_OUTER_R,
        cy - BEZEL_OUTER_R,
        cx + BEZEL_OUTER_R,
        cy + BEZEL_OUTER_R,
      );
      chromeGrad.addColorStop(0, "#f8fafc");
      chromeGrad.addColorStop(0.25, "#cbd5e1");
      chromeGrad.addColorStop(0.5, "#94a3b8");
      chromeGrad.addColorStop(0.78, "#e2e8f0");
      chromeGrad.addColorStop(1, "#64748b");
      ctx.fillStyle = chromeGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, BEZEL_OUTER_R, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = isLight ? "#64748b" : "#94a3b8";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      const innerRimGrad = ctx.createLinearGradient(
        cx + LENS_R + 5,
        cy + LENS_R + 5,
        cx - LENS_R - 5,
        cy - LENS_R - 5,
      );
      innerRimGrad.addColorStop(0, "#475569");
      innerRimGrad.addColorStop(0.5, "#334155");
      innerRimGrad.addColorStop(1, "#1e293b");
      ctx.fillStyle = innerRimGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, LENS_R + 5, 0, Math.PI * 2);
      ctx.fill();

      // 36 precision optical calibration ticks around inner rim
      ctx.save();
      ctx.strokeStyle = "rgba(203, 213, 225, 0.35)";
      ctx.lineWidth = 1;
      for (let t = 0; t < 36; t++) {
        const a = (t / 36) * Math.PI * 2;
        const rA = LENS_R + 1.5;
        const rB = LENS_R + (t % 3 === 0 ? 5 : 3.5);
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * rA, cy + Math.sin(a) * rA);
        ctx.lineTo(cx + Math.cos(a) * rB, cy + Math.sin(a) * rB);
        ctx.stroke();
      }
      ctx.restore();

      // Clipped convex obsidian glass chamber + internal radial spectrum + plasma iris
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, LENS_R, 0, Math.PI * 2);
      ctx.clip();

      const abyss = ctx.createRadialGradient(cx, cy, 4, cx, cy, LENS_R);
      abyss.addColorStop(0, "#140205");
      abyss.addColorStop(1, "#050103");
      ctx.fillStyle = abyss;
      ctx.fillRect(cx - LENS_R, cy - LENS_R, LENS_R * 2, LENS_R * 2);

      // 48 radial voice-spectrum ticks inside lens rim
      ctx.lineWidth = 1.6;
      ctx.lineCap = "round";
      for (let i = 0; i < BANDS; i++) {
        const theta = (i / BANDS) * Math.PI * 2 - Math.PI / 2;
        const amp = bandValues[i];
        const rOuter = LENS_R - 2;
        const rInner = rOuter - (2 + amp * 16);
        ctx.strokeStyle = `rgba(248, 113, 113, ${(0.2 + amp * 0.7).toFixed(2)})`;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(theta) * rOuter, cy + Math.sin(theta) * rOuter);
        ctx.lineTo(cx + Math.cos(theta) * rInner, cy + Math.sin(theta) * rInner);
        ctx.stroke();
      }

      const plasmaLayers = [
        { rRatio: 0.84, rgb: "185, 28, 28", amp: 7.5, speed: 1.3 },
        { rRatio: 0.67, rgb: "239, 68, 68", amp: 6.2, speed: -1.8 },
        { rRatio: 0.5, rgb: "249, 115, 22", amp: 4.8, speed: 2.4 },
      ];

      plasmaLayers.forEach((layer, li) => {
        ctx.beginPath();
        const pts = 64;
        for (let p = 0; p <= pts; p++) {
          const theta = (p / pts) * Math.PI * 2;
          const b = bandValues[(p + li * 7) % BANDS];
          const lobe = Math.sin(theta * (3 + li) + tPhase * layer.speed) * Math.cos(theta * 2 - tPhase * 1.1);
          const r =
            LENS_R * layer.rRatio * (0.72 + energy * 0.3) + lobe * (layer.amp * (0.3 + energy * 1.35)) + b * 14;
          const px = cx + Math.cos(theta) * r;
          const py = cy + Math.sin(theta) * r;
          if (p === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.strokeStyle = `rgba(${layer.rgb}, ${(0.32 + energy * 0.58).toFixed(2)})`;
        ctx.lineWidth = 1.8 + energy * 1.3;
        ctx.stroke();
      });

      const coreR = LENS_R * (0.28 + energy * 0.56);
      const halCore = ctx.createRadialGradient(cx, cy, 1, cx, cy, coreR);
      halCore.addColorStop(0, energy > 0.38 ? "#ffffff" : "#fef08a");
      halCore.addColorStop(0.14, "#fde047");
      halCore.addColorStop(0.3, "#f59e0b");
      halCore.addColorStop(0.58, "#ef4444");
      halCore.addColorStop(0.84, "#991b1b");
      halCore.addColorStop(1, "rgba(127, 29, 29, 0)");
      ctx.fillStyle = halCore;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();

      // Coated Nikkor fisheye glass specular reflections
      ctx.strokeStyle = "rgba(255, 255, 255, 0.28)";
      ctx.lineWidth = 3.2;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(cx, cy, LENS_R * 0.76, -Math.PI * 0.82, -Math.PI * 0.42);
      ctx.stroke();

      ctx.strokeStyle = "rgba(186, 230, 253, 0.14)";
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(cx, cy, LENS_R * 0.82, Math.PI * 0.15, Math.PI * 0.42);
      ctx.stroke();

      ctx.restore();
    };

    const drawFrame = (now: number) => {
      const dt = Math.min(0.05, (now - lastTime) / 1000);
      lastTime = now;
      ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

      let telemetry = { energy: energyRef.current, dbLabel: "Standby", pct: 0 };
      if (!pausedRef.current) {
        const speed = reducedMotionQuery.matches ? 0.35 : 1.0;
        phaseRef.current += dt * speed;
        telemetry = sampleBands();
      }

      if (now - lastUiPush > 65) {
        lastUiPush = now;
        setLevelDb(telemetry.dbLabel);
        setMeterPct(telemetry.pct);
      }

      const isLight = !document.documentElement.classList.contains("dark");
      drawHalEye(CANVAS_SIZE / 2, CANVAS_SIZE / 2, telemetry.energy, phaseRef.current, isLight);
      rafId = requestAnimationFrame(drawFrame);
    };

    rafId = requestAnimationFrame(drawFrame);
    return () => cancelAnimationFrame(rafId);
  }, []);

  const isLiveInputActive = Boolean(telemetry?.active || activeAnalyser);
  const micTestActive = onToggleTestMic ? testingMic : Boolean(liveAnalyser);

  return (
    <div className="flex flex-col items-center gap-3 py-1">
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        className="mx-auto block size-52"
        aria-label="Circular HAL 9000 speaking level meter"
      />

      <div className="flex flex-wrap items-center justify-center gap-2.5 text-xs">
        <div className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-2.5 py-1 dark:border-zinc-800 dark:bg-zinc-900">
          <span className="inline-flex items-center gap-1.5 font-mono text-zinc-700 dark:text-zinc-200">
            <span
              className={`pulse-dot size-2 rounded-full ${
                paused ? "bg-zinc-400" : recording || isLiveInputActive ? "bg-red-500" : "bg-red-500/60"
              }`}
            />
            {levelDb}
          </span>
          <div
            className="h-2 w-28 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
            role="meter"
            aria-label="Voice input level"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={meterPct}
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-red-500 transition-[width] duration-75"
              style={{ width: `${meterPct}%` }}
            />
          </div>
          {telemetry?.active && telemetry.deviceName && (
            <span className="max-w-44 truncate text-zinc-500 dark:text-zinc-400" title={telemetry.deviceName}>
              · {telemetry.deviceName}
            </span>
          )}
        </div>

        {!analyser && !recording && (
          <button
            type="button"
            onClick={onToggleTestMic ?? toggleLiveMic}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {micTestActive ? (
              <MicOff className="size-3.5 text-red-500" aria-hidden="true" />
            ) : (
              <Mic className="size-3.5" aria-hidden="true" />
            )}
            {micTestActive ? "Stop Mic Test" : "Test Live Mic"}
          </button>
        )}

        {!recording && (
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {paused ? <Play className="size-3.5" aria-hidden="true" /> : <Pause className="size-3.5" aria-hidden="true" />}
            {paused ? "Resume Meter" : "Pause Meter"}
          </button>
        )}
      </div>

      {telemetry?.error && <p className="text-center text-xs text-red-600 dark:text-red-400">{telemetry.error}</p>}
      {telemetry?.digitalSilence && !telemetry.error && (
        <p className="max-w-md text-center text-xs text-amber-600 dark:text-amber-400">
          Selected device ({telemetry.deviceName || "mic"}) is sending digital silence (0 signal — e.g. closed laptop lid
          or hardware mute). Choose another Recording Input Device above.
        </p>
      )}
      {micNote && <p className="text-center text-xs text-zinc-500">{micNote}</p>}
    </div>
  );
}
