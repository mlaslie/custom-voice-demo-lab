import { CheckCircle2, Circle, Clapperboard, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, videoUrl, type Settings } from "../../api";
import { JobStatus, useJob } from "../../components/hooks";
import { Alert, Button } from "../../components/ui";
import type { TabProps } from "../Project";

export default function RenderTab({ project: p, refresh, goto }: TabProps) {
  const [s, setS] = useState<Settings | null>(null);
  const [err, setErr] = useState("");
  const job = useJob(() => refresh());
  useEffect(() => { api.settings().then(setS); }, []);
  useEffect(() => { // pick up a render started elsewhere (e.g. from Claude or Antigravity)
    api.jobs(p.id).then((js) => { const r = js.find((j) => j.kind === "render" && j.state === "running"); if (r) job.start(Promise.resolve(r)); });
  }, [p.id]);

  const steps = p.segments.filter((x) => x.type === "step");
  const checks = [
    { ok: !!(s?.voice_id && (s.gemini_key_set || s.fake_gemini)), label: "Voice id and API key set", fix: <Link className="underline" to="/settings">Settings</Link> },
    { ok: p.segments.length > 0, label: "Script drafted", fix: <button className="underline" onClick={() => goto("sources")}>Sources</button> },
    { ok: p.script_approved, label: "Script approved", fix: <button className="underline" onClick={() => goto("script")}>Script</button> },
    ...(steps.length ? [
      { ok: steps.every((x) => x.actions.length > 0), label: "Every web step has actions", fix: <button className="underline" onClick={() => goto("rehearse")}>Rehearse</button> },
      { ok: p.checks.length > 0 && p.checks.every((c) => c.ok), label: "Dry run passed", fix: <button className="underline" onClick={() => goto("rehearse")}>Rehearse</button>, soft: true },
    ] : []),
  ];
  const blocking = checks.filter((c) => !c.ok && !("soft" in c && c.soft));

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <ul className="mb-5 space-y-2">
          {checks.map((c) => (
            <li key={c.label} className="flex items-center gap-2 text-sm">
              {c.ok ? <CheckCircle2 className="size-4 text-emerald-600" /> : <Circle className={`size-4 ${"soft" in c ? "text-amber-500" : "text-zinc-300"}`} />}
              <span className={c.ok ? "" : "text-zinc-500"}>{c.label}</span>
              {!c.ok && <span className="text-xs text-brand-700 dark:text-brand-100">· {c.fix}</span>}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" icon={<Clapperboard className="size-4" />} busy={job.running} disabled={blocking.length > 0}
            onClick={() => { setErr(""); job.start(api.render(p.id)).catch((e) => setErr(e.message)); }}>
            Render video
          </Button>
          <span className="text-sm text-zinc-500">Narration is cached, so re-renders after small edits are quick. Web steps are recorded live, in real time.</span>
        </div>
        {s && <p className="mt-3 text-xs text-zinc-500">Output: <code>{s.output_dir}</code></p>}
      </div>
      {err && <Alert>{err}</Alert>}
      <JobStatus job={job.job} />

      {p.renders.map((r, i) => (
        <div key={r.file} className="card overflow-hidden">
          <video src={videoUrl(p.id, i)} controls preload="metadata" className="aspect-video w-full bg-black" />
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <span className="font-medium">{new Date(r.created_at * 1000).toLocaleString()}</span>
            <span className="text-zinc-500">{Math.floor(r.seconds / 60)}:{String(Math.round(r.seconds % 60)).padStart(2, "0")} · {r.segments} segments</span>
            <span className="min-w-0 flex-1 truncate text-right font-mono text-xs text-zinc-500">{r.file}</span>
            <Button size="sm" icon={<FolderOpen className="size-3.5" />} onClick={() => api.reveal(p.id, i)}>Show in Finder</Button>
          </div>
        </div>
      ))}
    </div>
  );
}
