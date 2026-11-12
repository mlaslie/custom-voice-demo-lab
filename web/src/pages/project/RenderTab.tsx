import { AlertTriangle, CheckCircle2, Circle, Clapperboard, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, videoUrl, type Readiness, type Settings } from "../../api";
import { JobStatus, useJob } from "../../components/hooks";
import { Alert, Button } from "../../components/ui";
import type { TabProps } from "../Project";

export default function RenderTab({ project: p, refresh, goto }: TabProps) {
  const [s, setS] = useState<Settings | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [err, setErr] = useState("");
  const job = useJob(() => {
    refresh();
    api.readiness(p.id).then(setReadiness).catch(() => {});
  });

  useEffect(() => { api.settings().then(setS).catch(() => {}); }, []);
  useEffect(() => { api.readiness(p.id).then(setReadiness).catch(() => {}); }, [p]);
  useEffect(() => {
    api.jobs(p.id).then((js) => {
      const r = js.find((j) => j.kind === "render" && j.state === "running");
      if (r) job.start(Promise.resolve(r));
    });
  }, [p.id]);

  const steps = p.segments.filter((x) => x.type === "step");
  const authOk = p.web_auth?.status === "authenticated" || p.web_auth?.status === "not_needed" || p.has_login;
  const checks = [
    {
      ok: !!s && !s.setup_needed,
      label: `Narrator voice: ${s?.profiles.find((v) => v.id === p.profile_id)?.name ?? s?.active?.name ?? "none"}`,
      fix: <Link className="underline" to="/setup">Setup</Link>,
    },
    {
      ok: (p.research?.length ?? 0) > 0 || Boolean(p.research_summary?.trim()),
      label: `Grounded technical research (${p.research?.length ?? 0} sources)`,
      soft: true,
    },
    {
      ok: p.segments.length > 0,
      label: "Script drafted",
      fix: <button className="underline" onClick={() => goto("script")}>Script</button>,
    },
    {
      ok: p.script_approved,
      label: "Script approved",
      fix: <button className="underline" onClick={() => goto("script")}>Approve on Script tab</button>,
    },
    ...(steps.length ? [
      {
        ok: authOk,
        label: `AGY Browser login verified (${p.web_auth?.status || "unchecked"})`,
        fix: <button className="underline" onClick={() => goto("rehearse")}>AGY Browser tab</button>,
        soft: true,
      },
      {
        ok: steps.every((x) => (x.frames?.length ?? 0) > 0),
        label: `Every web step has captured AGY Browser frames (${steps.filter((x) => (x.frames?.length ?? 0) > 0).length}/${steps.length})`,
        fix: <button className="underline" onClick={() => goto("rehearse")}>AGY Browser tab</button>,
      },
    ] : []),
  ];
  const blocking = checks.filter((c) => !c.ok && !("soft" in c && c.soft));

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <ul className="mb-4 space-y-2">
          {checks.map((c) => (
            <li key={c.label} className="flex items-center gap-2 text-xs sm:text-sm">
              {c.ok
                ? <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                : "soft" in c && c.soft
                  ? <AlertTriangle className="size-4 shrink-0 text-amber-500" />
                  : <Circle className="size-4 shrink-0 text-zinc-300" />}
              <span className={c.ok ? "" : "text-zinc-500"}>{c.label}</span>
              {!c.ok && "fix" in c && c.fix && <span className="text-xs text-brand-700 dark:text-brand-100">· {c.fix}</span>}
            </li>
          ))}
        </ul>

        {readiness?.warnings && readiness.warnings.length > 0 && (
          <div className="mb-4">
            <Alert tone="amber">{readiness.warnings[0]}</Alert>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            icon={<Clapperboard className="size-4" />}
            busy={job.running}
            disabled={blocking.length > 0}
            onClick={() => { setErr(""); job.start(api.render(p.id)).catch((e) => setErr(e.message)); }}
          >
            Render 1080p MP4
          </Button>
          <span className="text-xs text-zinc-500">
            Gemini TTS audio & 2× supersampled title cards are cached, so re-renders after edits finish in seconds.
          </span>
        </div>
        {s && <p className="mt-3 text-xs text-zinc-500">Output directory: <code>{s.output_dir}</code></p>}
      </div>

      {err && <Alert>{err}</Alert>}
      <JobStatus job={job.job} />

      {p.renders.map((r, i) => (
        <div key={r.file} className="card overflow-hidden">
          <video src={videoUrl(p.id, i)} controls preload="metadata" className="aspect-video w-full bg-black" />
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-xs sm:text-sm">
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
