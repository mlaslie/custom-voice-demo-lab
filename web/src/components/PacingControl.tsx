import { Gauge, Loader2, Minus, Pause, Play, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type PreviewWith } from "../api";

export const PACE_SAMPLE = "Here is how this pace sounds in a real demo. First we open the dashboard and pick a project. " +
  "Then we run the policy check, and a few seconds later the results appear, each finding linked to its source.";
const MIN = 0.7, MAX = 1.4, STEP = 0.05;
const fix = (x: number) => Math.round(Math.min(MAX, Math.max(MIN, x)) * 100) / 100;

/** Narration speed with - / + (5% steps) and a test clip that reports its measured length and pace. */
export function PacingControl({ value, onChange, with: w, text = PACE_SAMPLE, label = "Pace", inherited }: {
  value: number; onChange: (speed: number) => void; with: PreviewWith; text?: string; label?: string;
  inherited?: { speed: number; onReset: () => void } | null;   // projects: the voice's own pace, and a way back to it
}) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [result, setResult] = useState<{ seconds: number; wpm: number; speed: number } | null>(null);
  const [err, setErr] = useState("");
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => audio.current?.pause(), []);

  const step = (d: number) => onChange(fix(value + d * STEP));
  const test = async () => {
    if (state === "playing") { audio.current?.pause(); setState("idle"); return; }
    setErr(""); setState("loading");
    try {
      const r = await api.testClip(text, { ...w, speed: value });
      setResult({ seconds: r.seconds, wpm: r.wpm, speed: value });
      const a = new Audio(URL.createObjectURL(r.blob));
      audio.current = a;
      a.onended = () => setState("idle");
      await a.play();
      setState("playing");
    } catch (e) { setErr((e as Error).message); setState("idle"); }
  };
  const btn = "grid size-8 place-items-center rounded-lg border border-zinc-300 bg-white text-zinc-700 transition hover:border-brand-500 hover:text-brand-700 disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200";

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-500"><Gauge className="size-4" />{label}</span>
      <div className="inline-flex items-center gap-1.5">
        <button type="button" className={btn} onClick={() => step(-1)} disabled={value <= MIN} aria-label="Slower" title="Slower (5%)"><Minus className="size-4" /></button>
        <span className="w-14 text-center font-mono text-sm font-semibold tabular-nums">{value.toFixed(2)}×</span>
        <button type="button" className={btn} onClick={() => step(1)} disabled={value >= MAX} aria-label="Faster" title="Faster (5%)"><Plus className="size-4" /></button>
      </div>
      <span className="w-24 text-xs text-zinc-500">{value === 1 ? "natural pace" : `${Math.round(Math.abs(value - 1) * 100)}% ${value > 1 ? "faster" : "slower"}`}</span>
      {value !== 1 && !inherited && <button type="button" className="text-xs text-zinc-500 underline-offset-2 hover:underline" onClick={() => onChange(1)}>Reset</button>}
      {inherited && <button type="button" className="text-xs text-zinc-500 underline-offset-2 hover:underline" onClick={inherited.onReset}>Use the voice's pace ({inherited.speed.toFixed(2)}×)</button>}
      <button type="button" onClick={test}
        className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:text-brand-100 dark:hover:bg-brand-700/25">
        {state === "loading" ? <Loader2 className="size-3.5 animate-spin" /> : state === "playing" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
        Test clip
      </button>
      {result && !err && (
        <span className="text-xs text-zinc-500" title="Measured on the generated clip">
          {result.seconds.toFixed(1)} s · <b className="font-medium text-zinc-700 dark:text-zinc-300">{result.wpm} words/min</b> at {result.speed.toFixed(2)}×
        </span>
      )}
      {err && <span className="max-w-xs truncate text-xs text-red-600" title={err}>{err}</span>}
    </div>
  );
}
