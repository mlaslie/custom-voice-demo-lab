import { CheckCircle2, Loader2, Pause, Play, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job, type PreviewWith } from "../api";

/** Follow a background job until it finishes; onDone runs once when it does. */
export function useJob(onDone?: (j: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (!job || job.state !== "running") return;
    const t = setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.state !== "running") done.current?.(j);
      } catch { /* server restarting; keep polling */ setJob({ ...job }); }
    }, 1200);
    return () => clearTimeout(t);
  }, [job]);

  const start = useCallback(async (p: Promise<Job>) => {
    const j = await p;
    setJob(j);
    if (j.state !== "running") done.current?.(j);
    return j;
  }, []);
  return { job, start, running: job?.state === "running", clear: () => setJob(null) };
}

export function JobStatus({ job, compact }: { job: Job | null; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!job) return null;
  const icon = job.state === "running" ? <Loader2 className="size-4 animate-spin text-brand-600" />
    : job.state === "done" ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-red-600" />;
  return (
    <div className={`rounded-xl border border-zinc-200 bg-zinc-50/80 text-sm dark:border-zinc-800 dark:bg-zinc-900/60 ${compact ? "px-3 py-2" : "p-3"}`}>
      <div className="flex items-center gap-2">
        {icon}
        <span className="min-w-0 flex-1 truncate">{job.state === "error" ? job.error : job.message || job.kind}</span>
        <button className="text-xs text-zinc-500 hover:underline" onClick={() => setOpen(!open)}>{open ? "Hide log" : "Log"}</button>
      </div>
      {job.state === "running" && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${Math.max(4, job.progress * 100)}%` }} />
        </div>
      )}
      {open && (
        <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs leading-relaxed text-zinc-100">{job.log.join("\n")}</pre>
      )}
    </div>
  );
}

/** Speak text in a project's voice (else the active profile), a saved profile, or any voice of a saved key. */
export function VoiceButton({ text, projectId, with: w, label = "Preview", title = "Hear it in this voice" }:
  { text: string; projectId?: string; with?: PreviewWith; label?: string; title?: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [err, setErr] = useState("");
  const audio = useRef<HTMLAudioElement | null>(null);

  const play = async () => {
    if (state === "playing") { audio.current?.pause(); setState("idle"); return; }
    setErr(""); setState("loading");
    try {
      const blob = await api.preview(text, { project_id: projectId, ...w });
      const a = new Audio(URL.createObjectURL(blob));
      audio.current = a;
      a.onended = () => setState("idle");
      await a.play();
      setState("playing");
    } catch (e) { setErr((e as Error).message); setState("idle"); }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={!text.trim()}
        onClick={play}
        title={err || title}
        className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-40 dark:text-brand-100 dark:hover:bg-brand-700/25"
      >
        {state === "loading" ? <Loader2 className="size-3.5 animate-spin" /> : state === "playing" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
        {label}
      </button>
      {err && <span className="max-w-xs truncate text-xs text-red-600" title={err}>{err}</span>}
    </span>
  );
}
