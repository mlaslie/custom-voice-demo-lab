import { AlertTriangle, Clapperboard, Film, Layers, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ProjectSummary, type Settings } from "../api";
import { Alert, Badge, Empty } from "../components/ui";

export default function Projects({ settings }: { settings: Settings | null }) {
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [err, setErr] = useState("");

  const load = () => api.projects().then(setList).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"? Its script, slides and audio cache are removed; rendered videos stay on disk.`)) return;
    await api.deleteProject(id);
    load();
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Demo videos</h1>
          <p className="mt-1 text-sm text-zinc-500">Made from your coding sessions. To start one, ask your agent in Claude or Antigravity to create a demo video of what you are working on.</p>
        </div>
      </div>

      {settings?.setup_needed && (
        <div className="mb-5">
          <Alert tone="amber">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 shrink-0" />
              <span>Add a Gemini API key and choose a narrator voice on the <Link className="font-medium underline" to="/setup">setup page</Link> before drafting or rendering.</span>
            </div>
          </Alert>
        </div>
      )}
      {err && <div className="mb-4"><Alert>{err}</Alert></div>}

      {list && list.length === 0 && (
        <Empty icon={<Clapperboard className="size-6" />} title="No demos yet">
          In a coding session, analyze some code, slides or an app with your agent, then ask it to create a demo video.
          It writes the script from the session and opens it here, beside the chat, for you to review and approve.
        </Empty>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {list?.map((p) => (
          <div key={p.id} className="card group relative flex flex-col p-5 transition hover:border-brand-500/60 hover:shadow-md">
            <Link to={`/projects/${p.id}`} className="absolute inset-0 rounded-2xl" aria-label={p.name} />
            <div className="mb-2 flex items-start justify-between gap-2">
              <h3 className="font-semibold leading-snug">{p.name}</h3>
              <button onClick={() => remove(p.id, p.name)} className="relative z-10 rounded-md p-1 text-zinc-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-950/40" title="Delete">
                <Trash2 className="size-4" />
              </button>
            </div>
            <p className="line-clamp-2 flex-1 text-sm text-zinc-500">{p.goal || p.base_url || "No description"}</p>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
              {p.script_approved ? <Badge tone="green">Approved</Badge> : p.segments ? <Badge tone="amber">In review</Badge> : <Badge>Draft</Badge>}
              <span className="inline-flex items-center gap-1"><Layers className="size-3.5" />{p.segments} segments</span>
              <span className="inline-flex items-center gap-1"><Film className="size-3.5" />{p.renders}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
