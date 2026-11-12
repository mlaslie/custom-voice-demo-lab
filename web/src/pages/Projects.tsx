import { AlertTriangle, BookOpenCheck, Clapperboard, Film, Globe, Layers, Presentation, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, inAntigravitySidecar, sendToAntigravity, type ProjectSummary, type Scenario, type Settings } from "../api";
import { Alert, Badge, Empty } from "../components/ui";

const SCENARIO_BADGE: Record<Scenario, { label: string; tone: "blue" | "amber" | "violet" }> = {
  slides: { label: "Slides", tone: "blue" },
  website: { label: "Live Web", tone: "amber" },
  hybrid: { label: "Hybrid", tone: "violet" },
};

export default function Projects({ settings }: { settings: Settings | null }) {
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [err, setErr] = useState("");
  const [sentPrompt, setSentPrompt] = useState("");

  const load = () => api.projects().then(setList).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"? Its script, slides and audio cache are removed; rendered MP4 videos stay on disk.`)) return;
    await api.deleteProject(id);
    load();
  };

  const askAgy = async (prompt: string) => {
    await sendToAntigravity(prompt);
    setSentPrompt("Sent prompt to Antigravity chat.");
    setTimeout(() => setSentPrompt(""), 3500);
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Automated Demo Videos</h1>
          <p className="mt-1 text-xs text-zinc-500">
            Orchestrated by Google Antigravity from in-AGY slides, user slide decks, or live websites in the AGY Browser — grounded in technical research and voiced in your Gemini TTS voice.
          </p>
        </div>
      </div>

      {settings?.setup_needed && (
        <div className="mb-4">
          <Alert tone="amber">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 shrink-0" />
              <span>Add a Gemini API key and choose a narrator voice on the <Link className="font-medium underline" to="/setup">setup page</Link> before drafting or rendering.</span>
            </div>
          </Alert>
        </div>
      )}
      {sentPrompt && <div className="mb-4"><Alert tone="blue">{sentPrompt}</Alert></div>}
      {err && <div className="mb-4"><Alert>{err}</Alert></div>}

      {list && list.length === 0 && (
        <Empty icon={<Clapperboard className="size-6" />} title="Ready to create your first demo">
          <p>Ask Antigravity in chat to automate a demo video from any of these workflows:</p>
          <div className="mt-4 grid gap-2 text-left text-xs">
            <div className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="flex items-center gap-1.5 font-semibold text-zinc-800 dark:text-zinc-200"><Presentation className="size-3.5 text-brand-600" /> 1. In-AGY or User-Provided Slides</div>
              <p className="mt-0.5 text-zinc-500">Create or attach Google Slides, PDF, or PowerPoint decks + session context, research recent docs/blogs, and render.</p>
            </div>
            <div className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="flex items-center gap-1.5 font-semibold text-zinc-800 dark:text-zinc-200"><Globe className="size-3.5 text-amber-600" /> 2. Live Website in Antigravity Browser</div>
              <p className="mt-0.5 text-zinc-500">Check login onboarding in the AGY Browser (e.g. Cloud Console), explore & capture live UI steps, and render.</p>
            </div>
          </div>
          {inAntigravitySidecar() && (
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <button
                onClick={() => askAgy("Create a narrated demo video from the slides in this session using Voice Demo Lab.")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
              >
                <Sparkles className="size-3.5" /> Start Slide Demo in AGY
              </button>
            </div>
          )}
        </Empty>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {list?.map((p) => {
          const scen = SCENARIO_BADGE[p.scenario || "slides"] ?? SCENARIO_BADGE.slides;
          return (
            <div key={p.id} className="card group relative flex flex-col p-4 transition hover:border-brand-500/60 hover:shadow-md">
              <Link to={`/projects/${p.id}`} className="absolute inset-0 rounded-2xl" aria-label={p.name} />
              <div className="mb-1.5 flex items-start justify-between gap-2">
                <h3 className="font-semibold leading-snug">{p.name}</h3>
                <button
                  onClick={() => remove(p.id, p.name)}
                  className="relative z-10 rounded-md p-1 text-zinc-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-950/40"
                  title="Delete"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
              <p className="line-clamp-2 flex-1 text-xs text-zinc-500">{p.goal || p.base_url || "No description"}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500">
                <Badge tone={scen.tone}>{scen.label}</Badge>
                {p.script_approved ? <Badge tone="green">Approved</Badge> : p.segments ? <Badge tone="amber">In review</Badge> : <Badge>Draft</Badge>}
                <span className="inline-flex items-center gap-1"><Layers className="size-3" />{p.segments}</span>
                {p.research_count > 0 && <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400" title="Grounded research sources"><BookOpenCheck className="size-3" />{p.research_count}</span>}
                <span className="inline-flex items-center gap-1"><Film className="size-3" />{p.renders}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
