import { FileCode2, FileText, Globe, Presentation, StickyNote, Trash2, Upload, Wand2 } from "lucide-react";
import { useRef, useState } from "react";
import { api, slideUrl, type Source } from "../../api";
import { useJob, JobStatus } from "../../components/hooks";
import { Alert, Badge, Button, Field } from "../../components/ui";
import type { TabProps } from "../Project";

const KINDS = [
  { key: "url", label: "Web page", icon: Globe, placeholder: "https://app.example.com/dashboard", hint: "Captures the page's text and controls (uses the saved login, if any)." },
  { key: "repo", label: "Source folder", icon: FileCode2, placeholder: "~/code/my-app", hint: "Reads the README, docs and the most relevant files." },
  { key: "gslides", label: "Google Slides", icon: Presentation, placeholder: "https://docs.google.com/presentation/d/…", hint: "Slides, speaker notes and slide images. Needs Google connected in Settings." },
  { key: "text", label: "Notes / script", icon: StickyNote, placeholder: "", hint: "Talking points, an existing script, anything the narration should cover." },
] as const;

const ICON: Record<Source["kind"], typeof Globe> = { url: Globe, repo: FileCode2, gslides: Presentation, pptx: Presentation, pdf: FileText, text: StickyNote };

export default function SourcesTab({ project: p, setProject, refresh, goto }: TabProps) {
  const [kind, setKind] = useState<(typeof KINDS)[number]["key"]>(p.base_url && !p.sources.length ? "url" : "text");
  const [ref, setRef] = useState(p.base_url && !p.sources.length ? p.base_url : "");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const draft = useJob(async (j) => { await refresh(); if (j.state === "done") goto("script"); });
  const k = KINDS.find((x) => x.key === kind)!;

  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setErr("");
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const add = () => act(async () => {
    setProject(await api.addSource(p.id, { kind, ref: ref.trim(), text, label: kind === "text" ? "Notes" : "" }));
    setRef(""); setText("");
  });
  const uploadFiles = (files: FileList | null) => act(async () => {
    for (const f of Array.from(files ?? [])) setProject(await api.upload(p.id, f));
  });

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="card p-5 lg:col-span-3">
          <div className="mb-4 flex flex-wrap gap-1">
            {KINDS.map((x) => (
              <button key={x.key} onClick={() => { setKind(x.key); setRef(x.key === "url" ? p.base_url : ""); }}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  kind === x.key ? "bg-brand-50 text-brand-700 dark:bg-brand-700/25 dark:text-brand-100" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"}`}>
                <x.icon className="size-4" />{x.label}
              </button>
            ))}
          </div>
          {kind === "text" ? (
            <Field label="Notes or script" hint={k.hint}><textarea className="input min-h-40" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          ) : (
            <Field label={k.label} hint={k.hint}><input className="input" value={ref} onChange={(e) => setRef(e.target.value)} placeholder={k.placeholder} onKeyDown={(e) => e.key === "Enter" && add()} /></Field>
          )}
          <div className="mt-4 flex justify-end">
            <Button variant="primary" busy={busy} disabled={kind === "text" ? !text.trim() : !ref.trim()} onClick={add}>Add source</Button>
          </div>
        </div>

        <button
          onClick={() => file.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); uploadFiles(e.dataTransfer.files); }}
          className={`card flex flex-col items-center justify-center gap-2 border-2 border-dashed p-6 text-center transition lg:col-span-2 ${
            drag ? "border-brand-500 bg-brand-50/60 dark:bg-brand-700/15" : "hover:border-brand-500/60"}`}>
          <Upload className="size-7 text-brand-600" />
          <span className="font-medium">Drop a deck or document</span>
          <span className="text-xs text-zinc-500">.pptx · .pdf · .md · .txt. Speaker notes are used as narration material.</span>
          <input ref={file} type="file" hidden multiple accept=".pptx,.pdf,.md,.txt,.markdown" onChange={(e) => uploadFiles(e.target.files)} />
        </button>
      </div>

      {err && <Alert>{err}</Alert>}

      {p.sources.length > 0 && (
        <div className="card divide-y divide-zinc-100 dark:divide-zinc-800">
          {p.sources.map((s) => {
            const Icon = ICON[s.kind];
            return (
              <div key={s.id} className="flex items-center gap-3 px-5 py-3">
                <Icon className="size-4 shrink-0 text-zinc-400" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{s.label}</div>
                  <div className="truncate text-xs text-zinc-500">{s.ref || `${s.text.length.toLocaleString()} characters`}</div>
                </div>
                <Badge>{s.kind}</Badge>
                {s.slide_count > 0 && <Badge tone="blue">{s.slide_count} slides</Badge>}
                <Button size="sm" variant="ghost" title="Remove" onClick={() => act(async () => setProject(await api.deleteSource(p.id, s.id)))}><Trash2 className="size-4" /></Button>
              </div>
            );
          })}
        </div>
      )}

      {p.slides.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-zinc-500">Slides</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {p.slides.map((_, i) => (
              <figure key={i} className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800">
                <img src={slideUrl(p.id, i)} alt={`Slide ${i + 1}`} loading="lazy" className="aspect-video w-full object-contain" />
                <figcaption className="px-2 py-1 text-[11px] text-zinc-500">#{i}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      <div className="card flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center">
        <div className="flex-1">
          <div className="font-medium">Draft the narration script</div>
          <div className="text-sm text-zinc-500">Gemini writes cards, slide narration and web steps from these sources. {p.segments.length > 0 && <b>This replaces the current script.</b>}</div>
        </div>
        <Button variant="primary" icon={<Wand2 className="size-4" />} busy={draft.running} disabled={!p.sources.length && !p.goal}
          onClick={() => {
            if (p.segments.length && !confirm("Replace the current script with a new draft?")) return;
            draft.start(api.draft(p.id)).catch((e) => setErr(e.message));
          }}>
          {p.segments.length ? "Redraft script" : "Draft script"}
        </Button>
      </div>
      <JobStatus job={draft.job} />
    </div>
  );
}
