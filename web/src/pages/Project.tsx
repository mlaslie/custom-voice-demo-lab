import { ArrowLeft, Check, ChevronDown, Film, MessagesSquare, MousePointerClick, PenLine } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type Project, type Settings } from "../api";
import { Alert, Field } from "../components/ui";
import RehearseTab from "./project/RehearseTab";
import RenderTab from "./project/RenderTab";
import ScriptTab from "./project/ScriptTab";

const TABS = [
  { key: "script", label: "Script", icon: PenLine },
  { key: "rehearse", label: "Rehearse", icon: MousePointerClick },
  { key: "render", label: "Render", icon: Film },
] as const;
type Tab = (typeof TABS)[number]["key"];

export interface TabProps {
  project: Project;
  setProject: (p: Project) => void;
  refresh: () => Promise<Project>;
  goto: (t: Tab) => void;
}

export default function ProjectPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [p, setP] = useState<Project | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [err, setErr] = useState("");
  const [brief, setBrief] = useState(false);

  const refresh = useCallback(async () => {
    const x = await api.project(id);
    setP(x);
    return x;
  }, [id]);
  useEffect(() => { refresh().catch((e) => setErr(e.message)); }, [refresh]);
  useEffect(() => { api.settings().then(setSettings).catch(() => {}); }, []);

  if (err) return <Alert>{err}</Alert>;
  if (!p) return null;

  const steps = p.segments.filter((s) => s.type === "step");
  const done: Record<Tab, boolean> = {
    script: p.script_approved,
    rehearse: steps.length === 0 || (steps.every((s) => s.actions.length > 0) && p.checks.length > 0 && p.checks.every((c) => c.ok)),
    render: p.renders.length > 0,
  };
  const tab = (TABS.some((t) => t.key === params.get("tab")) ? params.get("tab") : "script") as Tab;
  const goto = (t: Tab) => setParams({ tab: t });

  const saveBrief = async (patch: Partial<Project>) => setP(await api.patchProject(p.id, patch));

  return (
    <div className="mx-auto max-w-5xl">
      <Link to="/" className="mb-3 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"><ArrowLeft className="size-4" />Projects</Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <input
            className="w-full bg-transparent text-2xl font-semibold tracking-tight outline-none focus:underline decoration-brand-500/40"
            defaultValue={p.name}
            onBlur={(e) => e.target.value.trim() && e.target.value !== p.name && saveBrief({ name: e.target.value.trim() })}
          />
          <p className="mt-0.5 truncate text-sm text-zinc-500">{p.base_url || "Slides / explainer (no web app)"}</p>
        </div>
        <button onClick={() => setBrief(!brief)} className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 dark:text-brand-100">
          Session brief & voice <ChevronDown className={`size-4 transition ${brief ? "rotate-180" : ""}`} />
        </button>
      </div>

      {brief && (
        <div className="card mb-5 grid gap-4 p-5 md:grid-cols-2">
          <Field label="Web app URL"><input className="input" defaultValue={p.base_url} onBlur={(e) => e.target.value !== p.base_url && saveBrief({ base_url: e.target.value.trim() })} placeholder="http://localhost:8090" /></Field>
          <Field label="Narrator voice" hint={<>Saved voices are managed in <Link className="underline" to="/settings">Settings</Link>.</>}>
            <select className="input" value={p.profile_id} onChange={(e) => saveBrief({ profile_id: e.target.value })}>
              <option value="">Active voice{settings?.active ? ` (${settings.active.name})` : ""}</option>
              {settings?.profiles.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </Field>
          <div className="md:col-span-2">
            <span className="label flex items-center gap-1.5"><MessagesSquare className="size-3.5" />From your coding session</span>
            <p className="whitespace-pre-wrap rounded-xl bg-zinc-50 p-3 text-sm leading-relaxed dark:bg-zinc-950">{p.brief || "No session brief."}</p>
          </div>
          <Field label="Goal: what must the demo show?"><textarea className="input min-h-24" defaultValue={p.goal} onBlur={(e) => e.target.value !== p.goal && saveBrief({ goal: e.target.value })} /></Field>
          <Field label="Audience"><input className="input" defaultValue={p.audience} onBlur={(e) => e.target.value !== p.audience && saveBrief({ audience: e.target.value })} placeholder="Default: new to the subject" /></Field>
          <Field label="Instructions for the script" hint="Tone, length, what to stress or skip. Your agent reads these."><textarea className="input min-h-24" defaultValue={p.instructions} onBlur={(e) => e.target.value !== p.instructions && saveBrief({ instructions: e.target.value })} /></Field>
          <Field label="Delivery style override" className="md:col-span-2"><input className="input" defaultValue={p.voice_style} onBlur={(e) => e.target.value !== p.voice_style && saveBrief({ voice_style: e.target.value })} placeholder="Empty = the voice's own style" /></Field>
        </div>
      )}

      <nav className="mb-6 grid grid-cols-3 gap-1 rounded-2xl border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-900">
        {TABS.map((t, i) => {
          const active = t.key === tab;
          return (
            <button key={t.key} onClick={() => goto(t.key)}
              className={`flex items-center justify-center gap-2 rounded-xl px-2 py-2.5 text-sm font-medium transition ${
                active ? "bg-brand-600 text-white shadow-sm" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"}`}>
              <span className={`grid size-5 place-items-center rounded-full text-[11px] ${active ? "bg-white/20" : done[t.key] ? "bg-emerald-500 text-white" : "bg-zinc-200 dark:bg-zinc-700"}`}>
                {done[t.key] && !active ? <Check className="size-3" /> : i + 1}
              </span>
              <span className="hidden sm:inline">{t.label}</span>
            </button>
          );
        })}
      </nav>

      {tab === "script" && <ScriptTab project={p} setProject={setP} refresh={refresh} goto={goto} />}
      {tab === "rehearse" && <RehearseTab project={p} setProject={setP} refresh={refresh} goto={goto} />}
      {tab === "render" && <RenderTab project={p} setProject={setP} refresh={refresh} goto={goto} />}
    </div>
  );
}
