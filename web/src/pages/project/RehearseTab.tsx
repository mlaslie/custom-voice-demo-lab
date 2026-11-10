import { ArrowDown, ArrowUp, CheckCircle2, FastForward, KeyRound, MousePointerClick, PlayCircle, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, checkUrl, newAction, type Action, type ActionOp, type Segment } from "../../api";
import { JobStatus, useJob } from "../../components/hooks";
import { Alert, Badge, Button, Empty } from "../../components/ui";
import type { TabProps } from "../Project";

const OPS: { op: ActionOp; label: string; needs: ("selector" | "value" | "seconds")[]; valueHint?: string }[] = [
  { op: "goto", label: "Go to", needs: ["value"], valueHint: "/path or URL" },
  { op: "click", label: "Click", needs: ["selector"] },
  { op: "fill", label: "Type", needs: ["selector", "value"], valueHint: "text to type" },
  { op: "press", label: "Press key", needs: ["value"], valueHint: "Enter, Tab, Escape…" },
  { op: "hover", label: "Hover", needs: ["selector"] },
  { op: "highlight", label: "Highlight", needs: ["selector"] },
  { op: "unhighlight", label: "Clear highlight", needs: [] },
  { op: "scroll", label: "Scroll", needs: ["selector"] },
  { op: "wait_for", label: "Wait for", needs: ["selector", "value", "seconds"], valueHint: "…or visible text" },
  { op: "wait", label: "Pause", needs: ["seconds"] },
];

export default function RehearseTab({ project: p, setProject, refresh, goto }: TabProps) {
  const [err, setErr] = useState("");
  const dry = useJob(() => refresh());
  const login = useJob(() => refresh());
  const steps = p.segments.filter((s) => s.type === "step");

  if (!steps.length) {
    return (
      <Empty icon={<MousePointerClick className="size-6" />} title="No web steps">
        This script has no live web-app steps, so there is nothing to rehearse.
        <div className="mt-4"><Button variant="primary" onClick={() => goto("render")}>Go to render</Button></div>
      </Empty>
    );
  }
  const failures = p.checks.filter((c) => !c.ok);
  const busy = dry.running || login.running;
  const run = (j: ReturnType<typeof useJob>, fn: () => Promise<import("../../api").Job>) => { setErr(""); j.start(fn()).catch((e) => setErr(e.message)); };

  return (
    <div className="space-y-5">
      {!p.base_url && <Alert tone="amber">Set the web app URL under "Brief & voice" first.</Alert>}
      <div className="card grid gap-4 p-5 md:grid-cols-3">
        <ToolBlock icon={<KeyRound className="size-4" />} title="Sign in" text={p.has_login ? "A saved session is used for every run." : "Only if the app needs a login. You sign in yourself in a browser window, then close it."}>
          <div className="flex gap-2">
            <Button size="sm" busy={login.running} disabled={busy || !p.base_url} onClick={() => run(login, () => api.login(p.id))}>{p.has_login ? "Sign in again" : "Open sign-in"}</Button>
            {p.has_login && <Button size="sm" variant="ghost" onClick={async () => setProject(await api.forgetLogin(p.id))}>Forget</Button>}
          </div>
        </ToolBlock>
        <ToolBlock icon={<PlayCircle className="size-4" />} title="Dry run" text={p.checks.length ? (failures.length ? `${failures.length} action(s) failed in the last run.` : "Last run: every action worked.") : "Runs every action headless, without narration, and checks each one works."}>
          <Button size="sm" busy={dry.running} disabled={busy || !p.base_url} onClick={() => run(dry, () => api.dryrun(p.id))}>Run check</Button>
        </ToolBlock>
      </div>
      {err && <Alert>{err}</Alert>}
      <JobStatus job={dry.job ?? login.job} />

      {steps.map((s, n) => (
        <StepActions key={s.id} n={n} s={s} pid={p.id} checks={p.checks.filter((c) => c.segment_id === s.id)} disabled={busy}
          onSaved={setProject} />
      ))}

      <div className="flex justify-end">
        <Button variant="primary" onClick={() => goto("render")}>Continue to render</Button>
      </div>
    </div>
  );
}

function ToolBlock({ icon, title, text, children }: { icon: React.ReactNode; title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 font-medium"><span className="text-brand-600">{icon}</span>{title}</div>
      <p className="flex-1 text-sm text-zinc-500">{text}</p>
      <div>{children}</div>
    </div>
  );
}

function StepActions({ n, s, pid, checks, disabled, onSaved }: {
  n: number; s: Segment; pid: string; checks: import("../../api").Check[]; disabled: boolean;
  onSaved: (p: import("../../api").Project) => void;
}) {
  const [acts, setActs] = useState<Action[]>(s.actions);
  const [dirty, setDirty] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => { if (!dirty) setActs(s.actions); }, [s.actions, dirty]);

  const change = (next: Action[]) => {
    setActs(next); setDirty(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      onSaved(await api.patchSegment(pid, s.id, { actions: next }));
      setDirty(false);
    }, 700);
  };
  const upd = (i: number, b: Partial<Action>) => change(acts.map((a, j) => (j === i ? { ...a, ...b } : a)));
  const shot = checks.find((c) => c.index === -1)?.shot;
  const failed = checks.find((c) => !c.ok);

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <Badge tone="amber">Step {n + 1}</Badge>
        <span className="font-medium">{s.title || "Untitled step"}</span>
        {checks.length > 0 && (failed ? <Badge tone="red"><XCircle className="size-3" />failed</Badge> : <Badge tone="green"><CheckCircle2 className="size-3" />ok</Badge>)}
        {dirty && <span className="text-xs text-zinc-400">saving…</span>}
      </div>
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0 space-y-2">
          <p className="text-sm italic text-zinc-500">“{s.narration || "No narration"}”</p>
          {acts.length === 0 && <p className="text-sm text-zinc-500">No actions yet. Ask your coding agent to add them, or add one here.</p>}
          {acts.map((a, i) => {
            const meta = OPS.find((o) => o.op === a.op)!;
            const bad = failed && failed.index === i;
            return (
              <div key={i} className={`flex flex-wrap items-center gap-2 rounded-xl border p-2 ${bad ? "border-red-300 bg-red-50/60 dark:border-red-900 dark:bg-red-950/30" : "border-zinc-200 dark:border-zinc-800"}`}>
                <span className="w-5 text-center text-xs text-zinc-400">{i + 1}</span>
                <select className="input !w-32 !py-1.5" value={a.op} onChange={(e) => upd(i, { op: e.target.value as ActionOp })}>
                  {OPS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
                </select>
                {meta.needs.includes("selector") && <input className="input !w-auto min-w-40 flex-1 !py-1.5 font-mono text-xs" value={a.selector} placeholder='role=button[name="Save"]' onChange={(e) => upd(i, { selector: e.target.value })} />}
                {meta.needs.includes("value") && <input className="input !w-auto min-w-28 flex-1 !py-1.5 text-xs" value={a.value} placeholder={meta.valueHint} onChange={(e) => upd(i, { value: e.target.value })} />}
                {meta.needs.includes("seconds") && <input className="input !w-20 !py-1.5 text-xs" type="number" min={0} value={a.seconds || ""} placeholder="secs" onChange={(e) => upd(i, { seconds: Number(e.target.value) })} />}
                {(a.op === "wait_for" || a.op === "wait") && (
                  <button title="Fast-forward this wait in the video" onClick={() => upd(i, { ff: !a.ff })}
                    className={`rounded-lg p-1.5 ${a.ff ? "bg-brand-600 text-white" : "text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"}`}><FastForward className="size-3.5" /></button>
                )}
                <input className="input !w-auto min-w-32 flex-1 !py-1.5 text-xs" value={a.label} placeholder="Label" onChange={(e) => upd(i, { label: e.target.value })} />
                <div className="flex">
                  <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => { const x = [...acts]; [x[i - 1], x[i]] = [x[i], x[i - 1]]; change(x); }}><ArrowUp className="size-3.5" /></Button>
                  <Button size="sm" variant="ghost" disabled={i === acts.length - 1} onClick={() => { const x = [...acts]; [x[i + 1], x[i]] = [x[i], x[i + 1]]; change(x); }}><ArrowDown className="size-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => change(acts.filter((_, j) => j !== i))}><Trash2 className="size-3.5" /></Button>
                </div>
                {bad && <p className="w-full px-7 text-xs text-red-700 dark:text-red-300">{failed.error}</p>}
              </div>
            );
          })}
          <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => change([...acts, newAction()])}>Add action</Button>
        </div>
        <div>
          {shot ? (
            <a href={checkUrl(pid, failed?.shot || shot)} target="_blank" rel="noreferrer">
              <img src={`${checkUrl(pid, failed?.shot || shot)}?t=${checks.length}`} alt="Screen after this step" className="aspect-video w-full rounded-lg border border-zinc-200 object-cover dark:border-zinc-800" />
            </a>
          ) : (
            <div className="grid aspect-video place-items-center rounded-lg border border-dashed border-zinc-300 text-xs text-zinc-400 dark:border-zinc-700">Run a check to see this step</div>
          )}
        </div>
      </div>
    </div>
  );
}
