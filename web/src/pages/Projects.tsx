import { AlertTriangle, Clapperboard, Film, Layers, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ProjectSummary, type Settings } from "../api";
import { Alert, Badge, Button, Empty, Field } from "../components/ui";

export default function Projects({ settings }: { settings: Settings | null }) {
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", base_url: "", goal: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  const load = () => api.projects().then(setList).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const create = async () => {
    setBusy(true); setErr("");
    try {
      const p = await api.createProject(form);
      nav(`/projects/${p.id}`);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"? Its sources, script and audio cache are removed; rendered videos stay on disk.`)) return;
    await api.deleteProject(id);
    load();
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Demo projects</h1>
          <p className="mt-1 text-sm text-zinc-500">Turn a web app, a deck, code or notes into a narrated demo video in your own voice.</p>
        </div>
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>New project</Button>
      </div>

      {settings && (!settings.voice_id || !settings.gemini_key_set) && (
        <div className="mb-5">
          <Alert tone="amber">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 shrink-0" />
              <span>Add your custom voice id and the Gemini API key from the same AI Studio project in <Link className="font-medium underline" to="/settings">Settings</Link> before drafting or rendering.</span>
            </div>
          </Alert>
        </div>
      )}
      {err && <div className="mb-4"><Alert>{err}</Alert></div>}

      {creating && (
        <div className="card mb-6 p-5">
          <h2 className="mb-4 font-semibold">New project</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Name"><input autoFocus className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Agent Gateway: retail scenarios" /></Field>
            <Field label="Web app URL (optional)" hint="Leave empty for a slides-only demo."><input className="input" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="http://localhost:8090" /></Field>
            <Field label="What should the demo show?" className="md:col-span-2"><textarea className="input min-h-20" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} placeholder="Walk a new customer through creating their first policy and testing it…" /></Field>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
            <Button variant="primary" busy={busy} disabled={!form.name.trim()} onClick={create}>Create</Button>
          </div>
        </div>
      )}

      {list && list.length === 0 && !creating && (
        <Empty icon={<Clapperboard className="size-6" />} title="No demos yet">
          Create a project, add your sources (a URL, slides, a repo or notes), and Gemini drafts a script for you to review.
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
