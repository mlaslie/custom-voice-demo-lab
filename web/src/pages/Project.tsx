import { ArrowLeft, BookOpenCheck, Check, ChevronDown, ExternalLink, Film, Globe, MessagesSquare, MousePointerClick, PenLine, ShieldCheck, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type Project, type Scenario, type Settings } from "../api";
import { Alert, Badge, Field } from "../components/ui";
import { PacingControl } from "../components/PacingControl";
import RehearseTab from "./project/RehearseTab";
import RenderTab from "./project/RenderTab";
import ScriptTab from "./project/ScriptTab";

const TABS = [
  { key: "script", label: "Script", icon: PenLine },
  { key: "rehearse", label: "AGY Browser", icon: MousePointerClick },
  { key: "render", label: "Render", icon: Film },
] as const;
type Tab = (typeof TABS)[number]["key"];

export interface TabProps {
  project: Project;
  setProject: (p: Project) => void;
  refresh: () => Promise<Project>;
  speed: number;
  goto: (t: Tab) => void;
}

const SCENARIO_LABEL: Record<Scenario, { label: string; tone: "blue" | "amber" | "violet" }> = {
  slides: { label: "Slides Demo", tone: "blue" },
  website: { label: "Website Demo", tone: "amber" },
  hybrid: { label: "Hybrid Slides + Web", tone: "violet" },
};

export default function ProjectPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [p, setP] = useState<Project | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [err, setErr] = useState("");
  const [briefOpen, setBriefOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);

  const refresh = useCallback(async () => {
    const x = await api.project(id);
    setP((prev) => (prev && prev.updated_at === x.updated_at ? prev : x));
    return x;
  }, [id]);
  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        refresh().catch(() => {});
      }
    }, 3500);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => { api.settings().then(setSettings).catch(() => {}); }, []);

  if (err) return <Alert>{err}</Alert>;
  if (!p) return null;

  const steps = p.segments.filter((s) => s.type === "step");
  const authOk = p.web_auth?.status === "authenticated" || p.web_auth?.status === "not_needed" || p.has_login;
  const done: Record<Tab, boolean> = {
    script: p.script_approved,
    rehearse: steps.length === 0 || (authOk && steps.every((s) => (s.frames?.length ?? 0) > 0)),
    render: p.renders.length > 0,
  };
  const tab = (TABS.some((t) => t.key === params.get("tab")) ? params.get("tab") : "script") as Tab;
  const goto = (t: Tab) => setParams({ tab: t });

  const voiceSpeed = (settings?.profiles.find((v) => v.id === p.profile_id) ?? settings?.active)?.speed ?? 1;
  const speed = p.speed || voiceSpeed;
  const saveBrief = async (patch: Partial<Project>) => setP(await api.patchProject(p.id, patch));
  const scen = SCENARIO_LABEL[p.scenario || "slides"] ?? SCENARIO_LABEL.slides;

  return (
    <div className="mx-auto max-w-4xl">
      <Link to="/" className="mb-2 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
        <ArrowLeft className="size-3.5" />All projects
      </Link>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <input
            className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none focus:underline decoration-brand-500/40"
            defaultValue={p.name}
            onBlur={(e) => e.target.value.trim() && e.target.value !== p.name && saveBrief({ name: e.target.value.trim() })}
          />
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
            <Badge tone={scen.tone}>{scen.label}</Badge>
            {p.base_url && (
              <span className="inline-flex items-center gap-1 truncate max-w-64">
                <Globe className="size-3 shrink-0" /> {p.base_url}
              </span>
            )}
            {(p.base_url || steps.length > 0) && (
              authOk
                ? <Badge tone="green"><ShieldCheck className="size-3" /> AGY Signed In</Badge>
                : <Badge tone="amber"><ShieldAlert className="size-3" /> Login Check Needed</Badge>
            )}
            {p.slides.length > 0 && <span>· {p.slides.length} slides</span>}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setResearchOpen(!researchOpen)}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
          >
            <BookOpenCheck className="size-3.5 text-emerald-600" />
            Research ({p.research?.length ?? 0})
            <ChevronDown className={`size-3.5 transition ${researchOpen ? "rotate-180" : ""}`} />
          </button>
          <button
            onClick={() => setBriefOpen(!briefOpen)}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-brand-700 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-brand-100"
          >
            Brief & voice <ChevronDown className={`size-3.5 transition ${briefOpen ? "rotate-180" : ""}`} />
          </button>
        </div>
      </div>

      {researchOpen && (
        <div className="card mb-4 space-y-3 p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
              Grounded Technical Research
            </span>
            <span className="text-xs text-zinc-400">{p.research?.length ?? 0} verified sources</span>
          </div>
          {p.research_summary && (
            <p className="whitespace-pre-wrap rounded-xl bg-emerald-50/60 p-3 text-xs leading-relaxed text-zinc-800 dark:bg-emerald-950/30 dark:text-zinc-200">
              {p.research_summary}
            </p>
          )}
          {(!p.research || p.research.length === 0) ? (
            <p className="text-xs text-zinc-500">
              No external research citations saved yet. Ask Antigravity to run <code>demo-researcher</code> to ground claims in docs, blogs, and videos.
            </p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {p.research.map((r) => (
                <div key={r.id} className="rounded-xl border border-zinc-200 p-3 text-xs dark:border-zinc-800">
                  <div className="flex items-center gap-1.5">
                    <Badge tone="blue">{r.source_type}</Badge>
                    <span className="truncate font-semibold">{r.title}</span>
                    {r.url_or_path.startsWith("http") && (
                      <a href={r.url_or_path} target="_blank" rel="noreferrer" className="ml-auto text-brand-600 hover:underline">
                        <ExternalLink className="size-3.5" />
                      </a>
                    )}
                  </div>
                  {r.summary && <p className="mt-1.5 text-zinc-600 dark:text-zinc-400">{r.summary}</p>}
                  {r.verified_claims?.length > 0 && (
                    <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-zinc-500">
                      {r.verified_claims.map((c, idx) => <li key={idx}>{c}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {briefOpen && (
        <div className="card mb-4 grid gap-4 p-4 md:grid-cols-2">
          <Field label="Target website URL (for AGY Browser steps)">
            <input className="input" defaultValue={p.base_url} onBlur={(e) => e.target.value !== p.base_url && saveBrief({ base_url: e.target.value.trim() })} placeholder="https://console.cloud.google.com" />
          </Field>
          <Field label="Narrator voice" hint={<>Manage keys & custom voices in <Link className="underline" to="/settings">Voices</Link>.</>}>
            <select className="input" value={p.profile_id} onChange={(e) => saveBrief({ profile_id: e.target.value })}>
              <option value="">Active voice{settings?.active ? ` (${settings.active.name})` : ""}</option>
              {settings?.profiles.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </Field>
          <div className="md:col-span-2">
            <span className="label flex items-center gap-1.5"><MessagesSquare className="size-3.5" />Antigravity Session Context</span>
            <p className="whitespace-pre-wrap rounded-xl bg-zinc-50 p-3 text-xs leading-relaxed dark:bg-zinc-950">{p.brief || "No session brief."}</p>
          </div>
          <Field label="Goal"><textarea className="input min-h-20" defaultValue={p.goal} onBlur={(e) => e.target.value !== p.goal && saveBrief({ goal: e.target.value })} /></Field>
          <Field label="Audience"><input className="input" defaultValue={p.audience} onBlur={(e) => e.target.value !== p.audience && saveBrief({ audience: e.target.value })} placeholder="Default: technical overview" /></Field>
          <Field label="User directions & script instructions" className="md:col-span-2">
            <textarea className="input min-h-20" defaultValue={p.instructions} onBlur={(e) => e.target.value !== p.instructions && saveBrief({ instructions: e.target.value })} />
          </Field>
          <Field label="Delivery style override" className="md:col-span-2">
            <input className="input" defaultValue={p.voice_style} onBlur={(e) => e.target.value !== p.voice_style && saveBrief({ voice_style: e.target.value })} placeholder="Empty = voice profile default" />
          </Field>
          <div className="md:col-span-2">
            <span className="label">Narration pace for this demo</span>
            <PacingControl
              value={speed}
              label={p.speed ? "Pace (this demo)" : "Pace (voice profile)"}
              with={{ project_id: p.id }}
              text={p.segments.find((s) => s.narration.split(/\s+/).length > 20)?.narration}
              onChange={(x) => saveBrief({ speed: x })}
              inherited={p.speed ? { speed: voiceSpeed, onReset: () => saveBrief({ speed: 0 }) } : null}
            />
          </div>
        </div>
      )}

      <nav className="mb-5 grid grid-cols-3 gap-1 rounded-2xl border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-900">
        {TABS.map((t, i) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              onClick={() => goto(t.key)}
              className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs font-medium transition ${
                active ? "bg-brand-600 text-white shadow-sm" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              }`}
            >
              <span className={`grid size-4.5 place-items-center rounded-full text-[10px] ${active ? "bg-white/20" : done[t.key] ? "bg-emerald-500 text-white" : "bg-zinc-200 dark:bg-zinc-700"}`}>
                {done[t.key] && !active ? <Check className="size-3" /> : i + 1}
              </span>
              <span>{t.label}</span>
            </button>
          );
        })}
      </nav>

      {tab === "script" && <ScriptTab project={p} speed={speed} setProject={setP} refresh={refresh} goto={goto} />}
      {tab === "rehearse" && <RehearseTab project={p} speed={speed} setProject={setP} refresh={refresh} goto={goto} />}
      {tab === "render" && <RenderTab project={p} speed={speed} setProject={setP} refresh={refresh} goto={goto} />}
    </div>
  );
}
