import { ArrowDown, ArrowUp, Camera, CheckCircle2, FastForward, Globe, KeyRound, MousePointerClick, Plus, ShieldAlert, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, frameUrl, inAntigravitySidecar, newAction, sendToAntigravity, type Action, type ActionOp, type Segment } from "../../api";
import { Alert, Badge, Button, Empty } from "../../components/ui";
import type { TabProps } from "../Project";

const OPS: { op: ActionOp; label: string; needs: ("selector" | "value" | "seconds")[]; valueHint?: string }[] = [
  { op: "goto", label: "Go to", needs: ["value"], valueHint: "/path or full URL" },
  { op: "click", label: "Click", needs: ["selector"] },
  { op: "fill", label: "Type", needs: ["selector", "value"], valueHint: "text to type" },
  { op: "press", label: "Press key", needs: ["value"], valueHint: "Enter, Tab, Escape…" },
  { op: "hover", label: "Hover", needs: ["selector"] },
  { op: "highlight", label: "Highlight", needs: ["selector"] },
  { op: "verify", label: "Verify text", needs: ["value"], valueHint: "expected text on page" },
  { op: "scroll", label: "Scroll", needs: ["selector"] },
  { op: "wait_for", label: "Wait for", needs: ["selector", "value", "seconds"], valueHint: "…or visible text" },
  { op: "wait", label: "Pause", needs: ["seconds"] },
];

export default function RehearseTab({ project: p, setProject, goto }: TabProps) {
  const [err, setErr] = useState("");
  const [sent, setSent] = useState("");
  const steps = p.segments.filter((s) => s.type === "step");

  if (!steps.length) {
    return (
      <Empty icon={<MousePointerClick className="size-6" />} title="No live website steps">
        This project is a slides-only demo, so no Antigravity Browser steps are required.
        <div className="mt-4"><Button variant="primary" onClick={() => goto("render")}>Go to Render</Button></div>
      </Empty>
    );
  }

  const authStatus = p.web_auth?.status || (p.has_login ? "authenticated" : "unchecked");
  const authOk = authStatus === "authenticated" || authStatus === "not_needed";
  const capturedCount = steps.filter((s) => (s.frames?.length ?? 0) > 0).length;
  const isSidecar = inAntigravitySidecar();

  const askAgyBrowser = async (mode: "login" | "capture") => {
    setErr("");
    try {
      const prompt = mode === "login"
        ? `Check if I am logged into ${p.base_url || "the target website"} in Antigravity's built-in browser for demo project ${p.id}. If login is required, pause so I can sign in inside the Browser pane, then call record_web_auth.`
        : `Execute the web steps for demo project "${p.name}" (${p.id}) in Antigravity's built-in browser (checking login onboarding first if needed) and save before/during/result screenshots with record_step_frames.`;
      await sendToAntigravity(prompt);
      setSent("Instruction sent to Antigravity chat.");
      setTimeout(() => setSent(""), 4000);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      {!p.base_url && <Alert tone="amber">Set the target website URL under "Brief & voice" first.</Alert>}
      {sent && <Alert tone="blue">{sent}</Alert>}
      {err && <Alert>{err}</Alert>}

      <div className="card grid gap-4 p-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <KeyRound className="size-4 text-brand-600" />
            In-AGY Browser Login Onboarding
          </div>
          <p className="flex-1 text-xs text-zinc-500">
            {authStatus === "authenticated"
              ? `Signed in inside Antigravity Browser${p.web_auth?.account_hint ? ` (${p.web_auth.account_hint})` : ""}.`
              : authStatus === "not_needed"
                ? "Public website — no sign-in needed."
                : authStatus === "login_required"
                  ? "Paused waiting for you to sign in inside the Antigravity Browser pane."
                  : "Before running live steps (e.g. Cloud Console), Antigravity checks if you are signed in inside the built-in Browser pane."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {authOk
              ? <Badge tone="green"><ShieldCheck className="size-3" /> {authStatus === "not_needed" ? "Public Site" : "Authenticated"}</Badge>
              : <Badge tone="amber"><ShieldAlert className="size-3" /> {authStatus}</Badge>}
            {isSidecar && (
              <Button size="sm" onClick={() => askAgyBrowser("login")}>
                <Globe className="size-3.5" /> Check Sign-In in AGY
              </Button>
            )}
            {!authOk && (
              <Button size="sm" variant="ghost" onClick={async () => setProject(await api.setWebAuth(p.id, "not_needed"))}>
                No login needed
              </Button>
            )}
            {authOk && (
              <Button size="sm" variant="ghost" onClick={async () => setProject(await api.forgetLogin(p.id))}>
                Reset
              </Button>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Camera className="size-4 text-brand-600" />
            Captured Browser Frames ({capturedCount}/{steps.length} steps)
          </div>
          <p className="flex-1 text-xs text-zinc-500">
            Antigravity's built-in <code>browser</code> subagent runs each step live and captures crisp 1080p <code>before</code>, <code>during</code>, and <code>result</code> frames — zero external Playwright windows.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {isSidecar ? (
              <Button size="sm" variant="primary" onClick={() => askAgyBrowser("capture")}>
                <Sparkles className="size-3.5" /> Capture Steps in AGY Browser
              </Button>
            ) : (
              <span className="text-xs text-zinc-400">Ask Antigravity in chat to capture web steps.</span>
            )}
          </div>
        </div>
      </div>

      {steps.map((s, n) => (
        <StepActions key={s.id} n={n} s={s} pid={p.id} onSaved={setProject} />
      ))}

      <div className="flex justify-end">
        <Button variant="primary" onClick={() => goto("render")}>Continue to Render</Button>
      </div>
    </div>
  );
}

function StepActions({ n, s, pid, onSaved }: {
  n: number; s: Segment; pid: string;
  onSaved: (p: import("../../api").Project) => void;
}) {
  const [acts, setActs] = useState<Action[]>(s.actions);
  const [dirty, setDirty] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => { if (!dirty) setActs(s.actions); }, [s.actions, dirty]);

  const change = (next: Action[]) => {
    setActs(next);
    setDirty(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      onSaved(await api.patchSegment(pid, s.id, { actions: next }));
      setDirty(false);
    }, 650);
  };
  const upd = (i: number, b: Partial<Action>) =>
    change(acts.map((a, j) => (j === i ? { ...a, ...b, ...(b.selector !== undefined ? { target: b.selector } : {}) } : a)));
  const frames = s.frames ?? [];

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
        <Badge tone="amber">Step {n + 1}</Badge>
        <span className="text-sm font-medium">{s.title || "Untitled step"}</span>
        {frames.length > 0
          ? <Badge tone="green"><CheckCircle2 className="size-3" /> {frames.length} frame{frames.length === 1 ? "" : "s"}</Badge>
          : <Badge>Awaiting capture</Badge>}
        {dirty && <span className="text-xs text-zinc-400">saving…</span>}
      </div>

      <div className="space-y-4 p-4">
        <p className="text-xs italic text-zinc-500">“{s.narration || "No narration"}”</p>

        <div className="space-y-2">
          {acts.length === 0 && <p className="text-xs text-zinc-500">No actions specified yet.</p>}
          {acts.map((a, i) => {
            const meta = OPS.find((o) => o.op === a.op) ?? OPS[1];
            return (
              <div key={i} className="flex flex-wrap items-center gap-1.5 rounded-xl border border-zinc-200 p-2 dark:border-zinc-800">
                <span className="w-4 text-center text-xs text-zinc-400">{i + 1}</span>
                <select className="input !w-28 !py-1 text-xs" value={a.op} onChange={(e) => upd(i, { op: e.target.value as ActionOp })}>
                  {OPS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
                </select>
                {meta.needs.includes("selector") && (
                  <input
                    className="input !w-auto min-w-36 flex-1 !py-1 font-mono text-xs"
                    value={a.selector || a.target || ""}
                    placeholder="Target button / element"
                    onChange={(e) => upd(i, { selector: e.target.value })}
                  />
                )}
                {meta.needs.includes("value") && (
                  <input
                    className="input !w-auto min-w-28 flex-1 !py-1 text-xs"
                    value={a.value}
                    placeholder={meta.valueHint}
                    onChange={(e) => upd(i, { value: e.target.value })}
                  />
                )}
                {meta.needs.includes("seconds") && (
                  <input
                    className="input !w-16 !py-1 text-xs"
                    type="number"
                    min={0}
                    value={a.seconds || ""}
                    placeholder="secs"
                    onChange={(e) => upd(i, { seconds: Number(e.target.value) })}
                  />
                )}
                {(a.op === "wait_for" || a.op === "wait") && (
                  <button
                    title="Fast-forward this wait behind a banner"
                    onClick={() => upd(i, { ff: !a.ff })}
                    className={`rounded-lg p-1.5 ${a.ff ? "bg-brand-600 text-white" : "text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"}`}
                  >
                    <FastForward className="size-3.5" />
                  </button>
                )}
                <div className="flex">
                  <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => { const x = [...acts]; [x[i - 1], x[i]] = [x[i], x[i - 1]]; change(x); }}><ArrowUp className="size-3.5" /></Button>
                  <Button size="sm" variant="ghost" disabled={i === acts.length - 1} onClick={() => { const x = [...acts]; [x[i + 1], x[i]] = [x[i], x[i + 1]]; change(x); }}><ArrowDown className="size-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => change(acts.filter((_, j) => j !== i))}><Trash2 className="size-3.5" /></Button>
                </div>
              </div>
            );
          })}
          <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => change([...acts, newAction()])}>
            Add action
          </Button>
        </div>

        {frames.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-3">
            {frames.map((f) => (
              <a key={f.id} href={frameUrl(pid, f.file)} target="_blank" rel="noreferrer" className="group block overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
                <img src={frameUrl(pid, f.file)} alt={f.caption || f.phase} className="aspect-video w-full object-cover transition group-hover:scale-[1.02]" />
                <div className="flex items-center justify-between gap-1 bg-zinc-50 px-2.5 py-1 text-[11px] dark:bg-zinc-900">
                  <Badge tone={f.phase === "result" ? "green" : "blue"}>{f.phase}</Badge>
                  <span className="truncate text-zinc-500">{f.caption || f.ff_what || f.file}</span>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
